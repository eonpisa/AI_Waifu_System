"""One session, one worker, no turn queue and no immediate cancellation."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
import time

from backend.conversation.service import TurnEvent, TurnResult, create_session, process_turn
from .schemas import public_event, public_result


class TurnRejected(Exception):
    pass


class Runtime:
    def __init__(self, processor=process_turn):
        # Constructed in ASGI lifespan, never during import.
        self.loop = asyncio.get_running_loop()
        self.session = create_session()
        self.processor = processor
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="waifu-turn")
        self.task = None
        self.busy = False
        self.accepting = True
        self.stage = "idle"
        self.turn_id = 0
        self.seq = 0
        self.started_at = None
        self.last_result = None
        self.subscribers = set()

    def state(self) -> dict:
        return {"busy": self.busy, "accepting": self.accepting, "stage": self.stage,
                "turn_id": self.turn_id or None, "seq": self.seq,
                "last_result": self.last_result}

    def envelope(self, kind, data) -> dict:
        elapsed = 0 if self.started_at is None else round((time.monotonic() - self.started_at) * 1000)
        return {"type": kind, "turn_id": self.turn_id or None, "seq": self.seq,
                "elapsed_ms": elapsed, "data": data}

    def publish(self, kind, data):
        self.seq += 1
        if kind == "state":
            data = {**data, "seq": self.seq}
        event = self.envelope(kind, data)
        for queue in tuple(self.subscribers):
            if queue.full():
                # A slow UI must never block voice. Close it instead of growing
                # memory indefinitely or dropping completion events silently.
                self.unsubscribe(queue)
                while not queue.empty():
                    queue.get_nowait()
                queue.put_nowait(None)
            else:
                queue.put_nowait(event)

    def subscribe(self):
        if len(self.subscribers) >= 4:
            raise TurnRejected("too_many_connections")
        queue = asyncio.Queue(maxsize=64)
        self.subscribers.add(queue)
        queue.put_nowait(self.envelope("state", self.state()))
        return queue

    def unsubscribe(self, queue):
        self.subscribers.discard(queue)

    def submit(self, text):
        # All callers and state writes use the event loop. Reserve before any
        # await, so simultaneous POSTs cannot start overlapping WAV/VTS work.
        if not self.accepting:
            raise TurnRejected("session_ended")
        if self.busy:
            raise TurnRejected("busy")
        self.busy = True
        self.turn_id += 1
        self.started_at = time.monotonic()
        self.stage = "queued"
        self.last_result = None
        self.publish("stage_changed", {"stage": self.stage})
        self.task = asyncio.create_task(self.run(text))
        return self.turn_id

    def on_event(self, event):
        data = public_event(event)
        if data is None:
            return
        if event.kind == "stage_changed":
            self.stage = data["stage"]
        self.publish(event.kind, data)

    async def run(self, text):
        original = [dict(message) for message in self.session.messages]

        def work():
            return self.processor(self.session, text, emit=lambda event:
                                  self.loop.call_soon_threadsafe(self.on_event, event))

        try:
            result = await self.loop.run_in_executor(self.executor, work)
            self.last_result = public_result(result)
        except Exception:
            # Do not expose exception text, URLs, response bodies or keys.
            self.session.messages[:] = original
            self.last_result = public_result(TurnResult("failed", errors=("turn_failed",)))
            self.on_event(TurnEvent("notice", {"code": "turn_failed"}))
        finally:
            self.busy = False
            self.stage = "idle" if self.accepting else "ended"
            self.publish("turn_finished", {"result": self.last_result, "stage": self.stage})

    def end(self):
        self.accepting = False
        if not self.busy:
            self.stage = "ended"
        self.publish("state", self.state())
        return self.state()

    async def close(self):
        self.end()
        if self.task is not None:
            # Disconnect/end/shutdown never cancel the blocking worker. Audio
            # and VTS finish via their existing finally blocks before teardown.
            await asyncio.shield(self.task)
        self.executor.shutdown(wait=True)
        for queue in tuple(self.subscribers):
            self.unsubscribe(queue)
            while not queue.empty():
                queue.get_nowait()
            queue.put_nowait(None)

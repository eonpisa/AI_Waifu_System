import json
import os
import websockets
import asyncio
import logging
import math
import sys
import time
import wave
from array import array
from dataclasses import dataclass
from backend.character.emotion import expression_presets


VTS_URI = "ws://127.0.0.1:8001"
PLUGIN_NAME = "AI Waifu"
PLUGIN_DEVELOPER = "eonpisa"
TOKEN_FILE = "vts_token.txt"
IO_TIMEOUT = 2.0
CLOSE_TIMEOUT = 0.2
STOP_POLL_INTERVAL = 0.05
# Calibrated on the user's current model: VoiceVolume 0..1 maps to
# ParamMouthOpenY 0..2.1. Recheck this calibration if its VTS mapping changes.
LIP_SYNC_MODEL_ID = "8d6febd38eee4bbf9b715fbf61af9c3e"
MOUTH_INPUT = "VoiceVolume"
MOUTH_OUTPUT_GAIN = 2.1
LIP_FRAME_SECONDS = 0.04
MOUTH_RESET_TIMEOUT = 0.5
LOGGER = logging.getLogger(__name__.rsplit(".", 1)[-1])
# websockets DEBUG frames can contain authentication tokens. Keep transport
# diagnostics isolated even when the application's debug mode is enabled.
TRANSPORT_LOGGER = logging.Logger("vts.transport", level=logging.CRITICAL)
TRANSPORT_LOGGER.addHandler(logging.NullHandler())
TRANSPORT_LOGGER.propagate = False
TRANSPORT_LOGGER.disabled = True


class _VTSFailure(Exception):
    pass


@dataclass
class WavLipSync:
    values: tuple[float, ...]
    frame_seconds: float
    duration: float
    started_at: float | None = None

    def mouth_value(self, now):
        if self.started_at is None:
            return 0.0
        elapsed = now - self.started_at
        if elapsed < 0 or elapsed >= self.duration:
            return 0.0
        index = int(elapsed / self.frame_seconds)
        return self.values[index] if index < len(self.values) else 0.0


def prepare_lip_sync(path):
    """Read PCM16 WAV once; failure disables only lip sync, never playback."""
    try:
        with wave.open(str(path), "rb") as wav:
            if (wav.getsampwidth() != 2 or wav.getnchannels() not in (1, 2)
                    or wav.getcomptype() != "NONE"):
                raise ValueError("unsupported WAV")
            rate, channels = wav.getframerate(), wav.getnchannels()
            frame_count = wav.getnframes()
            if rate <= 0 or frame_count <= 0:
                raise ValueError("empty WAV")
            window = max(1, round(rate * LIP_FRAME_SECONDS))
            silence = 10 ** (-45 / 20)
            values, previous, frames_read = [], 0.0, 0
            while raw := wav.readframes(window):
                if len(raw) % (2 * channels):
                    raise ValueError("incomplete PCM frame")
                samples = array("h")
                samples.frombytes(raw)
                if sys.byteorder != "little":
                    samples.byteswap()
                # Measure both stereo channels without cancelling opposite phases.
                rms = math.sqrt(sum(float(s) * s for s in samples) / len(samples)) / 32768
                if rms <= silence:
                    previous = 0.0
                else:
                    target = min(1.0, max(0.0, (rms - silence) / (0.25 - silence)))
                    alpha = 0.6 if target > previous else 0.3
                    previous += alpha * (target - previous)
                values.append(previous)
                frames_read += len(samples) // channels
            if frames_read != frame_count:
                raise ValueError("truncated WAV")
        return WavLipSync(tuple(values), window / rate, frame_count / rate)
    except (OSError, ValueError, EOFError, wave.Error):
        LOGGER.warning("VTS lip sync skipped: wav_unavailable_or_unsupported")
        return None


async def _inject_parameters(ws, values, request_id="expression"):
    async def exchange():
        await ws.send(json.dumps({
            "apiName": "VTubeStudioPublicAPI", "apiVersion": "1.0",
            "requestID": request_id, "messageType": "InjectParameterDataRequest",
            "data": {"mode": "set", "parameterValues": values},
        }))
        while True:
            response = await _receive(ws)
            # A cancelled receive can leave the previous injection's reply queued.
            if response.get("requestID", request_id) != request_id:
                continue
            if response.get("messageType") != "InjectParameterDataResponse":
                raise _VTSFailure("parameter_rejected")
            return
    await asyncio.wait_for(exchange(), timeout=IO_TIMEOUT)


async def _supports_lip_sync(ws):
    async def exchange():
        await ws.send(json.dumps({
            "apiName": "VTubeStudioPublicAPI", "apiVersion": "1.0",
            "requestID": "lip_model", "messageType": "CurrentModelRequest",
        }))
        response = await _receive(ws)
        data = response.get("data", {})
        return (response.get("messageType") == "CurrentModelResponse"
                and data.get("modelLoaded") is True
                and data.get("modelID") == LIP_SYNC_MODEL_ID)
    return await asyncio.wait_for(exchange(), timeout=IO_TIMEOUT)


async def _receive(ws):
    return json.loads(await asyncio.wait_for(ws.recv(), timeout=IO_TIMEOUT))


async def get_token(ws):
    await ws.send(json.dumps({
        "apiName": "VTubeStudioPublicAPI",
        "apiVersion": "1.0",
        "requestID": "token",
        "messageType": "AuthenticationTokenRequest",
        "data": {
            "pluginName": PLUGIN_NAME,
            "pluginDeveloper": PLUGIN_DEVELOPER
        }
    }))

    res = await _receive(ws)
    token = res["data"]["authenticationToken"]
    if not isinstance(token, str) or not token.strip():
        raise _VTSFailure("authentication_failed")

    with open(TOKEN_FILE, "w", encoding="utf-8") as f:
        f.write(token)

    print("토큰 저장 완료")
    return token


def load_token():
    if not os.path.exists(TOKEN_FILE):
        return None

    with open(TOKEN_FILE, "r", encoding="utf-8") as f:
        return f.read().strip()


async def auth(ws):
    token = load_token()

    if token is None:
        token = await get_token(ws)

    await ws.send(json.dumps({
        "apiName": "VTubeStudioPublicAPI",
        "apiVersion": "1.0",
        "requestID": "auth",
        "messageType": "AuthenticationRequest",
        "data": {
            "pluginName": PLUGIN_NAME,
            "pluginDeveloper": PLUGIN_DEVELOPER,
            "authenticationToken": token
        }
    }))

    res = await _receive(ws)

    if not res["data"]["authenticated"]:
        token = await get_token(ws)

        await ws.send(json.dumps({
            "apiName": "VTubeStudioPublicAPI",
            "apiVersion": "1.0",
            "requestID": "auth_retry",
            "messageType": "AuthenticationRequest",
            "data": {
                "pluginName": PLUGIN_NAME,
                "pluginDeveloper": PLUGIN_DEVELOPER,
                "authenticationToken": token
            }
        }))

        res = await _receive(ws)

    return res["data"]["authenticated"]


async def _apply_expression(emotion, duration, stop_event, lip_sync=None):
    preset = expression_presets.get(emotion, expression_presets["normal"])

    parameter_values = [
        {
            "id": param_id,
            "value": value
        }
        for param_id, value in preset.items()
    ]

    async with websockets.connect(
        VTS_URI, open_timeout=IO_TIMEOUT, close_timeout=CLOSE_TIMEOUT,
        logger=TRANSPORT_LOGGER,
    ) as ws:
        ok = await asyncio.wait_for(auth(ws), timeout=IO_TIMEOUT)

        if not ok:
            raise _VTSFailure("authentication_failed")

        if lip_sync is not None and not await _supports_lip_sync(ws):
            LOGGER.warning("VTS lip sync skipped: model_not_calibrated")
            lip_sync = None
        start = time.monotonic()
        mouth_sent = False
        try:
            while duration is None or time.monotonic() - start < duration:
                if stop_event is not None and stop_event.is_set():
                    return
                tick = time.monotonic()
                values = list(parameter_values)
                if lip_sync is not None:
                    mouth = min(1.0, max(0.0, lip_sync.mouth_value(tick)))
                    values.append({"id": MOUTH_INPUT, "value": mouth / MOUTH_OUTPUT_GAIN})
                    mouth_sent = True
                await _inject_parameters(ws, values)
                interval = LIP_FRAME_SECONDS if lip_sync is not None else 0.1
                # Use playback time, not message count: slow replies skip old frames.
                await asyncio.sleep(max(0, interval - (time.monotonic() - tick)))
        finally:
            if mouth_sent:
                try:
                    await asyncio.wait_for(_inject_parameters(
                        ws, [{"id": MOUTH_INPUT, "value": 0.0}], "mouth_reset",
                    ), timeout=MOUTH_RESET_TIMEOUT)
                except Exception:
                    LOGGER.warning("VTS lip sync: mouth_reset_failed")

        print(f"표정 적용 완료: {emotion}")


async def apply_expression(emotion, duration=4.0, stop_event=None, lip_sync=None):
    """Apply for four seconds by default; None requires a playback stop event."""
    if duration is None and stop_event is None:
        LOGGER.warning("VTS skipped: stop_event_required")
        return
    if stop_event is not None and stop_event.is_set():
        return
    task = asyncio.create_task(_apply_expression(emotion, duration, stop_event, lip_sync))
    try:
        while not task.done():
            if stop_event is not None and stop_event.is_set():
                task.cancel()
                break
            await asyncio.wait({task}, timeout=STOP_POLL_INTERVAL)
        if not task.cancelled():
            await task
    except asyncio.CancelledError:
        # A playback stop is expected; external cancellation still propagates.
        if stop_event is None or not stop_event.is_set():
            raise
    except _VTSFailure as exc:
        LOGGER.warning("VTS skipped: %s", str(exc))
    except asyncio.TimeoutError:
        LOGGER.warning("VTS skipped: timeout")
    except (OSError, websockets.exceptions.WebSocketException):
        LOGGER.warning("VTS skipped: connection_failed")
    except Exception:
        LOGGER.warning("VTS skipped: response_error")
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


if __name__ == "__main__":
    import asyncio

    async def test():
        await apply_expression("happy")
        input("표정 확인 중. Enter 누르면 종료: ")

    asyncio.run(test())

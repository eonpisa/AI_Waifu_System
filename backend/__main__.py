"""Run with the project Python: python -B -m backend."""

import logging
import os
from pathlib import Path
import re


class SafeConsoleFilter(logging.Filter):
    def filter(self, record):
        # The API owns its console. Legacy TTS errors may contain response
        # bodies/private paths; emit only fixed diagnostics and provider codes.
        if record.levelno < logging.INFO:
            return False
        record.exc_info = None
        record.exc_text = None
        record.stack_info = None
        if record.name == "translator" and re.fullmatch(
            r"JA->KO provider=(gemini|qwen|none) model=[A-Za-z0-9.:_-]+ "
            r"fallback_reason=[a-z0-9_;]+", record.getMessage()
        ):
            return True
        if record.levelno < logging.WARNING:
            return False
        record.msg = "service_warning" if record.levelno < logging.ERROR else "service_error"
        record.args = ()
        return True


def run_api():
    import uvicorn

    # Existing audio/VTS helpers use relative paths. Change only on explicit
    # launch, never on import; use one CLI or API process at a time.
    os.chdir(Path(__file__).resolve().parents[1])
    handler = logging.StreamHandler()
    handler.addFilter(SafeConsoleFilter())
    handler.setFormatter(logging.Formatter("%(levelname)s | %(name)s | %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True
    logging.getLogger("translator").setLevel(logging.INFO)
    print("Local API: http://127.0.0.1:8000/docs (Ctrl+C: finish current turn, then stop)")
    uvicorn.run("backend.api.app:app", host="127.0.0.1", port=8000, workers=1,
                reload=False, access_log=False, log_config=None, log_level="warning")


if __name__ == "__main__":
    run_api()

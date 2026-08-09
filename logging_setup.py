"""Small, idempotent console logging setup for the interactive application."""

import logging
import os


def configure_console_logging() -> None:
    """Enable debug logs only when explicitly requested, without duplicate handlers."""
    debug_enabled = os.environ.get("AI_WAIFU_DEBUG") == "1"
    level = logging.DEBUG if debug_enabled else logging.WARNING
    root = logging.getLogger()

    console_handlers = [
        handler
        for handler in root.handlers
        if isinstance(handler, logging.StreamHandler)
        and not isinstance(handler, logging.FileHandler)
    ]
    if not console_handlers:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(
            logging.Formatter("%(levelname)s | %(name)s | %(message)s")
        )
        console_handler._ai_waifu_console = True
        root.addHandler(console_handler)
        console_handlers.append(console_handler)

    root.setLevel(level)
    # Existing handlers may have been installed by logging.basicConfig() or a
    # library. They must be changed too; otherwise they still discard DEBUG.
    for handler in console_handlers:
        handler.setLevel(level)
    logging.getLogger("japanese_response").setLevel(level)
    logging.getLogger("translator").setLevel(level)
    # Application diagnostics are useful in debug mode; HTTP connection noise is not.
    logging.getLogger("urllib3").setLevel(logging.WARNING)

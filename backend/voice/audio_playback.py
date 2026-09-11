"""Small cross-platform WAV playback helper for the console application."""

import logging
import platform
import shutil
import subprocess
from pathlib import Path


LOGGER = logging.getLogger(__name__.rsplit(".", 1)[-1])


def play_wav(path: str | Path) -> bool:
    """Play a WAV file without allowing playback failures to end the app."""
    audio_path = Path(path).resolve()
    if not audio_path.is_file():
        LOGGER.error("Cannot play missing audio file: %s", audio_path)
        return False

    system = platform.system()
    try:
        if system == "Windows":
            import winsound

            winsound.PlaySound(str(audio_path), winsound.SND_FILENAME)
        elif system == "Darwin":
            subprocess.run(["afplay", str(audio_path)], check=True)
        elif shutil.which("aplay"):
            subprocess.run(["aplay", str(audio_path)], check=True)
        else:
            LOGGER.error("No supported WAV player found for %s.", system)
            return False
        return True
    except (OSError, subprocess.SubprocessError, RuntimeError) as exc:
        LOGGER.error("WAV playback failed for %s: %s", audio_path, exc)
        return False

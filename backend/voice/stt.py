"""Optional, local Korean speech-to-text for a recorded audio file.

The model must already exist locally. Importing this module never loads a
model, reads audio, or downloads anything.
"""

from dataclasses import dataclass
from functools import lru_cache
import os
from pathlib import Path
import time
from typing import Literal


MAX_AUDIO_BYTES = 20 * 1024 * 1024
MAX_AUDIO_SECONDS = 30
TranscriptionError = Literal[
    "audio_missing", "audio_too_large", "audio_too_long", "model_not_configured",
    "model_missing", "dependency_missing", "transcription_failed", "no_speech",
]


@dataclass(frozen=True)
class TranscriptionResult:
    text: str | None
    error: TranscriptionError | None
    elapsed_seconds: float


class AudioTooLong(Exception):
    pass


def _decode_audio(path):
    """Bound decoded audio too: a small compressed upload can be very long."""
    import av
    import numpy as np

    chunks = []
    samples = 0
    with av.open(str(path)) as container:
        resampler = av.AudioResampler(format="s16", layout="mono", rate=16000)
        for frame in container.decode(audio=0):
            for converted in resampler.resample(frame):
                samples += converted.samples
                if samples > MAX_AUDIO_SECONDS * 16000:
                    raise AudioTooLong()
                chunks.append(converted.to_ndarray().flatten())
        for converted in resampler.resample(None):
            samples += converted.samples
            if samples > MAX_AUDIO_SECONDS * 16000:
                raise AudioTooLong()
            chunks.append(converted.to_ndarray().flatten())
    return (np.concatenate(chunks).astype(np.float32) / 32768.0
            if chunks else np.empty(0, dtype=np.float32))


@lru_cache(maxsize=1)
def _load_model(model_path: str):
    from faster_whisper import WhisperModel

    return WhisperModel(model_path, device="cpu", compute_type="int8",
                        local_files_only=True)


def transcribe_file(audio_path: str | Path, *, model_path: str | Path | None = None) -> TranscriptionResult:
    """Transcribe Korean audio without changing a conversation session.

    The caller chooses whether to use the returned text as a draft. Errors
    are fixed codes: model paths, exception text and audio content stay private.
    """
    started = time.monotonic()

    def result(text: str | None = None, error: TranscriptionError | None = None) -> TranscriptionResult:
        return TranscriptionResult(text, error, time.monotonic() - started)

    try:
        audio = Path(audio_path)
        if not audio.is_file() or audio.stat().st_size == 0:
            return result(error="audio_missing")
        if audio.stat().st_size > MAX_AUDIO_BYTES:
            return result(error="audio_too_large")
    except OSError:
        return result(error="audio_missing")

    configured = model_path if model_path is not None else os.environ.get("AI_WAIFU_STT_MODEL")
    if not configured:
        return result(error="model_not_configured")
    model_dir = Path(configured).expanduser()
    if not model_dir.is_dir():
        return result(error="model_missing")

    try:
        waveform = _decode_audio(audio)
        if len(waveform) == 0:
            return result(error="no_speech")
        model = _load_model(str(model_dir))
        segments, _ = model.transcribe(
            waveform, language="ko", task="transcribe", beam_size=3,
            vad_filter=True, condition_on_previous_text=False,
        )
        text = " ".join(segment.text.strip() for segment in segments if segment.text.strip()).strip()
    except ImportError:
        return result(error="dependency_missing")
    except AudioTooLong:
        return result(error="audio_too_long")
    except Exception:
        return result(error="transcription_failed")
    return result(text=text) if text else result(error="no_speech")

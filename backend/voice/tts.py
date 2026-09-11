"""Configurable TTS entry point used by :mod:`main`.

The public ``speak`` signature is intentionally unchanged so the existing
text-cleaning and audio playback flow remains intact.
"""

import json
import logging
import os
import sys
import tempfile
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


LOGGER = logging.getLogger(__name__.rsplit(".", 1)[-1])
PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_PATH = PROJECT_ROOT / "output.wav"
_COSYVOICE_MODEL: Any = None


def _read_config() -> dict[str, Any]:
    """Load the optional local TTS configuration without breaking startup."""
    config_path = Path(
        os.environ.get("TTS_CONFIG_PATH", str(PROJECT_ROOT / "tts_config.json"))
    )
    if not config_path.is_file():
        LOGGER.warning("TTS config not found; using CosyVoice defaults: %s", config_path)
        return {}
    try:
        with config_path.open(encoding="utf-8") as file:
            data = json.load(file)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError) as exc:
        LOGGER.error("Could not read TTS config %s: %s", config_path, exc)
        return {}


def _setting(config: dict[str, Any], section: str, key: str, default: Any) -> Any:
    env_key = f"{section}_{key}".upper()
    if env_key in os.environ:
        return os.environ[env_key]
    section_value = config.get(section.lower(), {})
    if isinstance(section_value, dict):
        return section_value.get(key.lower(), default)
    return default


def _as_bool(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _write_wav_atomically(content: bytes) -> bool:
    if not content:
        LOGGER.error("SBV2 returned an empty audio response.")
        return False
    tmp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            suffix=".wav", delete=False, dir=OUTPUT_PATH.parent
        ) as tmp_file:
            tmp_file.write(content)
            tmp_name = tmp_file.name
        os.replace(tmp_name, OUTPUT_PATH)
        return True
    except OSError as exc:
        LOGGER.error("Could not save SBV2 audio to %s: %s", OUTPUT_PATH, exc)
        return False
    finally:
        if tmp_name and os.path.exists(tmp_name):
            os.remove(tmp_name)


def _speak_sbv2(text: str, speed: float, emotion: str, config: dict[str, Any]) -> bool:
    api_url = str(
        _setting(config, "SBV2", "API_URL", "http://127.0.0.1:5000")
    ).rstrip("/")
    model_name = str(_setting(config, "SBV2", "MODEL_NAME", ""))
    model_file = str(_setting(config, "SBV2", "MODEL_FILE", ""))
    speaker_name = str(_setting(config, "SBV2", "SPEAKER_NAME", ""))
    language = str(_setting(config, "SBV2", "LANGUAGE", "JP"))
    style = str(_setting(config, "SBV2", "STYLE", "Neutral"))
    try:
        style_weight = float(_setting(config, "SBV2", "STYLE_WEIGHT", 1.0))
        timeout = float(_setting(config, "SBV2", "TIMEOUT_SECONDS", 120))
    except (TypeError, ValueError) as exc:
        LOGGER.error("Invalid SBV2 numeric configuration: %s", exc)
        return False
    emotion_config = config.get("sbv2", {}).get("emotion", {})
    emotion_params = emotion_config.get(emotion, emotion_config.get("normal", {}))
    if not isinstance(emotion_params, dict):
        emotion_params = {}

    try:
        speed_value = max(float(speed), 0.1)
    except (TypeError, ValueError):
        speed_value = 1.0
    try:
        emotion_style_weight = float(emotion_params.get("style_weight", style_weight))
    except (TypeError, ValueError) as exc:
        LOGGER.error("Invalid SBV2 emotion style_weight for %s: %s", emotion, exc)
        return False
    params = {
        "text": text,
        "model_name": model_name,
        "model_file": model_file,
        "speaker_name": speaker_name,
        "language": language,
        "style": str(emotion_params.get("style", style)),
        "style_weight": emotion_style_weight,
        "assist_text": str(emotion_params.get("assist_text", "")),
        "length": 1.0 / speed_value,
    }
    params = {key: value for key, value in params.items() if value not in ("", None)}
    request = Request(
        f"{api_url}/voice?{urlencode(params)}", data=b"", method="POST"
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            if response.status != 200:
                LOGGER.error("SBV2 request failed with HTTP %s.", response.status)
                return False
            return _write_wav_atomically(response.read())
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        LOGGER.error("SBV2 rejected the request (HTTP %s): %s", exc.code, detail)
    except URLError as exc:
        LOGGER.error("SBV2 server is unavailable at %s: %s", api_url, exc.reason)
    except TimeoutError:
        LOGGER.error("SBV2 request timed out after %ss: %s", timeout, api_url)
    except OSError as exc:
        LOGGER.error("SBV2 request failed: %s", exc)
    return False


def _speak_cosyvoice(text: str, speed: float, config: dict[str, Any]) -> bool:
    """Original CosyVoice implementation, imported lazily for SBV2-only use."""
    cosyvoice_root = PROJECT_ROOT / "CosyVoice"
    matcha_dir = cosyvoice_root / "third_party" / "Matcha-TTS"
    if str(cosyvoice_root) not in sys.path:
        sys.path.insert(0, str(cosyvoice_root))
    if str(matcha_dir) not in sys.path:
        sys.path.append(str(matcha_dir))
    try:
        import torch
        import torchaudio
        from cosyvoice.cli.cosyvoice import AutoModel
    except Exception as exc:
        LOGGER.error("CosyVoice backend is unavailable: %s", exc)
        return False

    model_dir = str(_setting(config, "COSYVOICE", "MODEL_DIR", "iic/CosyVoice-300M"))
    prompt_wav = Path(str(_setting(config, "COSYVOICE", "PROMPT_WAV", "audio.wav")))
    if not prompt_wav.is_absolute():
        prompt_wav = PROJECT_ROOT / prompt_wav
    prompt_text = str(_setting(config, "COSYVOICE", "PROMPT_TEXT", ""))
    if not prompt_wav.is_file():
        LOGGER.error("CosyVoice prompt audio does not exist: %s", prompt_wav)
        return False
    tmp_prompt: str | None = None
    tmp_output: str | None = None
    try:
        waveform, sample_rate = torchaudio.load(prompt_wav)
        waveform = waveform.float().mean(dim=0, keepdim=True)
        if sample_rate != 16000:
            waveform = torchaudio.functional.resample(waveform, sample_rate, 16000)
            sample_rate = 16000
        waveform = waveform[:, : 30 * sample_rate].clamp(min=-1.0, max=1.0)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as file:
            tmp_prompt = file.name
        torchaudio.save(tmp_prompt, waveform, sample_rate)
        global _COSYVOICE_MODEL
        if _COSYVOICE_MODEL is None:
            _COSYVOICE_MODEL = AutoModel(model_dir=model_dir)
        cosyvoice = _COSYVOICE_MODEL
        outputs = [
            item["tts_speech"].detach().cpu()
            for item in cosyvoice.inference_zero_shot(
                tts_text=text,
                prompt_text=prompt_text,
                prompt_wav=tmp_prompt,
                stream=False,
                speed=max(float(speed), 0.1),
            )
            if item.get("tts_speech") is not None
        ]
        if not outputs:
            LOGGER.error("CosyVoice returned no audio.")
            return False
        with tempfile.NamedTemporaryFile(
            suffix=".wav", delete=False, dir=OUTPUT_PATH.parent
        ) as file:
            tmp_output = file.name
        torchaudio.save(tmp_output, torch.cat(outputs, dim=1), cosyvoice.sample_rate)
        os.replace(tmp_output, OUTPUT_PATH)
        tmp_output = None
        return True
    except Exception as exc:
        LOGGER.exception("CosyVoice synthesis failed: %s", exc)
        return False
    finally:
        for path in (tmp_prompt, tmp_output):
            if path and os.path.isfile(path):
                os.remove(path)


def speak(text_to_speak: str, speed: float, emotion: str, expression_duration: float) -> bool:
    """Synthesize ``text_to_speak`` to ``output.wav`` using the configured backend."""
    del expression_duration
    if not text_to_speak or not text_to_speak.strip():
        LOGGER.warning("Skipping TTS because the text is empty.")
        return False
    config = _read_config()
    backend = os.environ.get(
        "TTS_BACKEND", str(config.get("backend", "cosyvoice"))
    ).lower()
    if backend == "sbv2":
        if _speak_sbv2(text_to_speak, speed, emotion, config):
            LOGGER.info("SBV2 synthesis completed: %s", OUTPUT_PATH)
            return True
        fallback = os.environ.get(
            "TTS_FALLBACK_TO_COSYVOICE", config.get("fallback_to_cosyvoice", False)
        )
        if _as_bool(fallback):
            LOGGER.warning("SBV2 synthesis failed; falling back to CosyVoice.")
            return _speak_cosyvoice(text_to_speak, speed, config)
        return False
    if backend == "cosyvoice":
        return _speak_cosyvoice(text_to_speak, speed, config)
    LOGGER.error("Unsupported TTS_BACKEND=%r. Use 'sbv2' or 'cosyvoice'.", backend)
    return False


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("speak success:", speak("こんにちは。エレイナです。", 1.0, "normal", 0.0))

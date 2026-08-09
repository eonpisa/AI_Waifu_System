import os
import requests

DEFAULT_OLLAMA_API_URL = "http://127.0.0.1:11434/api/chat"


def _ollama_api_url() -> str:
    """Keep server bind address (0.0.0.0) out of client API requests."""
    configured = os.environ.get("OLLAMA_API_URL") or os.environ.get(
        "OLLAMA_HOST", DEFAULT_OLLAMA_API_URL
    )
    configured = configured.rstrip("/")
    if configured in {"0.0.0.0", "http://0.0.0.0", "https://0.0.0.0"}:
        return DEFAULT_OLLAMA_API_URL
    if "://0.0.0.0:" in configured:
        configured = configured.replace("://0.0.0.0:", "://127.0.0.1:", 1)
    if "://" not in configured:
        configured = f"http://{configured}"
    return configured if configured.endswith("/api/chat") else f"{configured}/api/chat"


OLLAMA_HOST = _ollama_api_url()
CHAT_MODEL = os.environ.get("OLLAMA_CHAT_MODEL", "qwen2.5:7b")
OLLAMA_TIMEOUT_SECONDS = float(os.environ.get("OLLAMA_TIMEOUT_SECONDS", "120"))
CHAT_TEMPERATURE = min(0.3, max(0.1, float(os.environ.get("OLLAMA_CHAT_TEMPERATURE", "0.2"))))


def chat(messages, model=None, temperature=None, response_format=None, timeout=None):

    data = {
        "model": model or CHAT_MODEL,
        "messages": messages,
        "stream": False
    }
    data["options"] = {"temperature": CHAT_TEMPERATURE if temperature is None else temperature}
    if response_format is not None:
        data["format"] = response_format

    response = requests.post(
        OLLAMA_HOST, json=data, timeout=OLLAMA_TIMEOUT_SECONDS if timeout is None else timeout
    )
    response.raise_for_status()

    return response.json()["message"]["content"]

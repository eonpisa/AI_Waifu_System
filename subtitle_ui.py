"""Display-only formatting for Korean subtitle results."""

from typing import Optional


def format_korean_subtitle(translation: Optional[str]) -> str:
    """Never label a Japanese fallback as a Korean subtitle."""
    if translation is None:
        return "자막 번역에 실패했습니다."
    return f"자막 (KO): {translation}"

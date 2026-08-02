"""Utilities for privacy-preserving Telegram content fingerprints."""

from __future__ import annotations

import hashlib
import re

_WHITESPACE = re.compile(r"\s+")


def normalize_content(text: str | None, caption: str | None = None) -> str:
    """Return text or caption with surrounding and repeated whitespace removed."""
    content = text if text is not None else caption
    if not content:
        return ""
    return _WHITESPACE.sub(" ", content.strip())


def content_fingerprint(text: str | None, caption: str | None = None) -> tuple[int, str]:
    """Return normalized character length and a SHA-256 digest without retaining text."""
    normalized = normalize_content(text, caption)
    return len(normalized), hashlib.sha256(normalized.encode("utf-8")).hexdigest()

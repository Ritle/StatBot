"""Tests for privacy-preserving comment content handling."""

import hashlib

from app.utils.content import content_fingerprint, normalize_content


def test_normalize_content_collapses_all_whitespace() -> None:
    assert normalize_content("  один\n\tдва   три  ") == "один два три"


def test_comment_length_is_calculated_after_normalization() -> None:
    length, digest = content_fingerprint("  ab   cd ")

    assert length == 5
    assert digest == hashlib.sha256(b"ab cd").hexdigest()


def test_caption_is_used_when_text_is_absent() -> None:
    assert content_fingerprint(None, "  media caption ")[0] == 13


def test_media_without_caption_has_zero_length() -> None:
    length, digest = content_fingerprint(None, None)

    assert length == 0
    assert digest == hashlib.sha256(b"").hexdigest()

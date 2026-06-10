"""Deterministic unit tests for server-side language-mirroring (ADR-008, cases 13).

These tests exercise the REAL server mechanism that runs *before/instead of* the
model: the pure functions `detect_response_language` and `language_display_name`.
No LLM is involved. Per 06-testing-strategy.md the correctness of language
mirroring must be proven by the deterministic server logic, not by "string is in
the prompt" assertions (which is the ADR-007 prod-failure lesson).

The lingua detector is deterministic, so the input->expected table below pins the
exact ISO codes the detector resolves for the configured Latin language set
(en/ru/de/fr/es/it/pt), including diacritics.
"""

from __future__ import annotations

import pytest

from app.core.language import (
    ISO_TO_ENGLISH_NAME,
    detect_response_language,
    language_display_name,
)

# A 2-letter alphabetic but non-resolvable sentinel used as the fallback value.
# lingua is configured for en/ru/de/fr/es/it/pt only, so it can never return
# "zz"; the script-guard never emits it either. Therefore a result of "zz" proves
# the fallback path was taken, and any other result proves it was NOT.
FALLBACK_SENTINEL = "zz"


# --- detect_response_language: language-of-message routing -------------------


@pytest.mark.parametrize(
    ("message", "transcription_language", "expected"),
    [
        # EN question over a RU transcription -> answer in EN (message wins).
        ("What tasks were discussed?", "ru", "en"),
        # Plain Cyrillic question -> ru via the script-guard (no library call).
        ("Какие задачи?", None, "ru"),
        # Latin samples with diacritics must resolve to their language, NOT to a
        # diacritic-driven fallback (the Latin range includes é/ü/ñ/ã/ç ...).
        ("café", None, "fr"),
        ("Grüße", None, "de"),
        ("Hola, ¿qué tareas hay?", None, "es"),
        ("Quali compiti?", None, "it"),
        ("Welche Aufgaben wurden besprochen?", None, "de"),
        ("Quelles tâches ont été discutées?", None, "fr"),
        ("Quais tarefas foram discutidas?", None, "pt"),
    ],
)
def test_detect_routes_message_to_expected_language(
    message: str, transcription_language: str | None, expected: str
) -> None:
    assert detect_response_language(message, transcription_language) == expected


def test_detect_diacritics_are_not_routed_to_fallback() -> None:
    """Diacritic words must resolve via lingua, never via the fallback path.

    With a sentinel fallback, a fallback would surface as "zz"; a real language
    code proves the diacritic characters were counted as Latin and detected.
    """
    assert detect_response_language("café", FALLBACK_SENTINEL) != FALLBACK_SENTINEL
    assert detect_response_language("Grüße", FALLBACK_SENTINEL) != FALLBACK_SENTINEL


# --- Script-mix routing (script-guard) --------------------------------------


def test_detect_cyrillic_dominant_mix_is_russian() -> None:
    """A mix where Cyrillic dominates the letters -> ru (script-guard)."""
    # "Какие" (5 cyr) + "tasks" (5 lat) is parity; add Cyrillic so it dominates.
    assert detect_response_language("Какие именно tasks?", None) == "ru"


def test_detect_latin_dominant_mix_defers_to_lingua_not_fallback() -> None:
    """A Latin-dominant mix -> lingua resolves it, NOT the fallback."""
    result = detect_response_language(
        "Which задачи were discussed today really?", FALLBACK_SENTINEL
    )
    assert result != FALLBACK_SENTINEL
    # Latin words dominate -> resolves into the Latin set (here English).
    assert result == "en"


def test_detect_latin_cyrillic_parity_uses_lingua_not_fallback() -> None:
    """At Latin/Cyrillic parity the algorithm defers to lingua, not fallback.

    ADR-008 §1.5: at parity use lingua (only lingua None -> fallback). The
    sentinel fallback must NOT appear in the result.
    """
    assert detect_response_language("abc абв", FALLBACK_SENTINEL) != FALLBACK_SENTINEL


# --- No usable signal -> fallback chain -------------------------------------


@pytest.mark.parametrize("message", ["123 456 789", "!!! ...", "🚀🔥✨", "   ", ""])
def test_detect_no_letters_uses_transcription_language_when_valid(message: str) -> None:
    """Digits/emoji/punctuation only + a valid translang -> that translang."""
    assert detect_response_language(message, "en") == "en"
    assert detect_response_language(message, "de") == "de"


@pytest.mark.parametrize(
    "bad_translang",
    [None, "", "x", "eng", "12", "  "],
)
def test_detect_no_letters_invalid_translang_uses_default(bad_translang: str | None) -> None:
    """No letters + None/invalid translang -> DEFAULT_RESPONSE_LANGUAGE ('ru')."""
    assert detect_response_language("123 !!! 🚀", bad_translang) == "ru"


def test_detect_no_letters_translang_is_normalized() -> None:
    """A valid translang is normalized (trim + lowercase) before use."""
    assert detect_response_language("123", "  EN  ") == "en"


# --- Non-Latin/Cyrillic scripts -> fallback (must not crash) ----------------


@pytest.mark.parametrize("message", ["你好世界", "مرحبا بالعالم", "こんにちは"])
def test_detect_other_scripts_fall_back_without_crashing(message: str) -> None:
    """CJK/Arabic/etc. dominate -> fallback chain (translang then default)."""
    # Valid translang is honored.
    assert detect_response_language(message, "fr") == "fr"
    # No translang -> default 'ru', and crucially: it does not raise.
    assert detect_response_language(message, None) == "ru"


# --- language_display_name --------------------------------------------------


@pytest.mark.parametrize(
    ("iso_code", "expected"),
    [
        ("en", "English"),
        ("ru", "Russian"),
        ("de", "German"),
        ("fr", "French"),
        ("es", "Spanish"),
        ("it", "Italian"),
        ("pt", "Portuguese"),
    ],
)
def test_display_name_maps_known_codes(iso_code: str, expected: str) -> None:
    assert language_display_name(iso_code) == expected


def test_display_name_is_case_insensitive() -> None:
    assert language_display_name("EN") == "English"
    assert language_display_name("Fr") == "French"


@pytest.mark.parametrize("unknown", ["zz", "ja", "xx", "ko"])
def test_display_name_unknown_code_returns_raw_iso(unknown: str) -> None:
    """A code outside the mapping returns the raw ISO code itself."""
    assert language_display_name(unknown) == unknown


def test_display_name_mapping_covers_configured_language_set() -> None:
    """Sanity: the seven configured languages all have an English display name."""
    for code in ("en", "ru", "de", "fr", "es", "it", "pt"):
        assert code in ISO_TO_ENGLISH_NAME

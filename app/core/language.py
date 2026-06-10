"""Deterministic server-side language detection for language-mirroring (ADR-008).

`detect_response_language` is a pure, synchronous function returning an ISO 639-1
code for the language the model should respond in. The algorithm is a hybrid:

1. Normalize: trim, consider only alphabetic characters.
2. Script-guard (v1: Cyrillic + Latin only): if Cyrillic dominates -> "ru".
   Any other script (CJK, Arabic, etc.) or no alphabetic chars -> fallback.
3. Latin-dominant -> lingua over a fixed language set; pick max-confidence.
4. Fallback: transcription_language (if a valid ISO code) else
   DEFAULT_RESPONSE_LANGUAGE (config).

The lingua detector is initialized once per process (lru_cache). The function
performs no I/O and is fully unit-testable via input->expected tables.
"""

from __future__ import annotations

from functools import lru_cache

from lingua import Language, LanguageDetector, LanguageDetectorBuilder

from app.core.config import get_settings

# Cyrillic Unicode ranges (script-guard, v1): basic block + supplement.
_CYRILLIC_RANGES: tuple[tuple[int, int], ...] = (
    (0x0400, 0x04FF),
    (0x0500, 0x052F),
)

# Latin Unicode ranges (script-guard, v1): Basic Latin + Latin-1 Supplement +
# Latin Extended-A/B. Includes diacritics common to the lingua language set
# (é, ü, ñ, ã, ç ...), so words like "café"/"Grüße" count as Latin rather than
# being misrouted to fallback. Deterministic: pure codepoint-range membership.
_LATIN_RANGES: tuple[tuple[int, int], ...] = (
    (0x0041, 0x005A),  # Basic Latin: A-Z
    (0x0061, 0x007A),  # Basic Latin: a-z
    (0x00C0, 0x00FF),  # Latin-1 Supplement letters (À-ÿ)
    (0x0100, 0x017F),  # Latin Extended-A
    (0x0180, 0x024F),  # Latin Extended-B
)

# Languages lingua is configured to discriminate (Latin-script set, ADR-008 §1.3).
# Russian is included so a Latin-but-transliterated input can still resolve, and
# so the detector set matches the ISO->name mapping coverage.
_LINGUA_LANGUAGES: tuple[Language, ...] = (
    Language.ENGLISH,
    Language.RUSSIAN,
    Language.GERMAN,
    Language.FRENCH,
    Language.SPANISH,
    Language.ITALIAN,
    Language.PORTUGUESE,
)

# Fixed ISO 639-1 -> English display name mapping for the language directive.
# Languages outside this map fall back to the raw ISO code (ADR-008 §2).
ISO_TO_ENGLISH_NAME: dict[str, str] = {
    "en": "English",
    "ru": "Russian",
    "de": "German",
    "fr": "French",
    "es": "Spanish",
    "it": "Italian",
    "pt": "Portuguese",
}


def _is_cyrillic(char: str) -> bool:
    """Whether a single character lies in a Cyrillic Unicode range."""
    code = ord(char)
    return any(start <= code <= end for start, end in _CYRILLIC_RANGES)


def _is_latin(char: str) -> bool:
    """Whether a single character lies in a Latin Unicode range (incl. diacritics)."""
    code = ord(char)
    return any(start <= code <= end for start, end in _LATIN_RANGES)


@lru_cache(maxsize=1)
def _get_detector() -> LanguageDetector:
    """Build the lingua detector once per process (singleton via lru_cache)."""
    return LanguageDetectorBuilder.from_languages(*_LINGUA_LANGUAGES).build()


def _resolve_fallback(transcription_language: str | None) -> str:
    """Resolve the fallback language: transcription language if valid, else default."""
    if transcription_language:
        candidate = transcription_language.strip().lower()
        # Accept a plausible ISO 639-1 alpha-2 code (e.g. "en", "ru").
        if len(candidate) == 2 and candidate.isalpha():
            return candidate
    return get_settings().DEFAULT_RESPONSE_LANGUAGE


def detect_response_language(message: str, transcription_language: str | None) -> str:
    """Return the ISO 639-1 language code the model should respond in (ADR-008).

    Pure and synchronous. `message` is the current user message; the script-guard
    and lingua decide its language. `transcription_language` is the fallback when
    `message` carries no usable signal (no letters / undetectable script).
    """
    # Step 1: normalize — keep only alphabetic characters.
    letters = [char for char in message.strip() if char.isalpha()]
    if not letters:
        return _resolve_fallback(transcription_language)

    # Step 2: script-guard (v1 — Cyrillic vs Latin).
    cyrillic_count = sum(1 for char in letters if _is_cyrillic(char))
    latin_count = sum(1 for char in letters if _is_latin(char))

    # Cyrillic dominates the alphabetic characters -> Russian, no library call.
    if cyrillic_count * 2 > len(letters):
        return "ru"

    # Defer to lingua when Latin is present and is not out-dominated by another
    # script: i.e. Latin parity-or-majority (ADR-008 §1.5 — at parity use lingua,
    # only lingua None -> fallback). Resolve via fallback only when a non-Latin
    # script dominates (CJK, Arabic, ...) or there is no Latin letter at all.
    if latin_count == 0 or latin_count < cyrillic_count:
        return _resolve_fallback(transcription_language)

    # Step 3: Latin-dominant -> lingua (max-confidence language).
    detected: Language | None = _get_detector().detect_language_of(message)
    if detected is None:
        return _resolve_fallback(transcription_language)

    # lingua returns the Language enum; map to a lowercase ISO 639-1 string.
    iso_code: str = detected.iso_code_639_1.name.lower()
    return iso_code


def language_display_name(iso_code: str) -> str:
    """Map an ISO 639-1 code to its English display name (ADR-008 §2).

    For codes outside the fixed mapping, the raw ISO code is returned.
    """
    return ISO_TO_ENGLISH_NAME.get(iso_code.lower(), iso_code)

"""Cheap checks that catch unusable bug report text before the LLM is called.

These run before the LLM is called. Text built from real words that still
makes no sense is left to the LLM, which reports it as an invalid bug report.
"""

import re
import string
from typing import Optional


READABILITY_FIELDS = (
    "title",
    "description",
    "expected_result",
    "actual_result",
)

MIN_READABLE_WORD_RATIO = 0.5

COMPARED_FIELDS = (
    "title",
    "description",
    "steps_to_reproduce",
    "expected_result",
    "actual_result",
)

# Keeps every report well inside the model's context window, so the text is
# never silently cut off.
MAX_FIELD_CHARS = 5000

UNREADABLE_TEXT_ERROR = "The bug report text is unreadable."
PLACEHOLDER_TEXT_ERROR = "The bug report contains only placeholder text."

KEYBOARD_ROWS = ("qwertyuiop", "asdfghjkl", "zxcvbnm")
KEYBOARD_SEQUENCE_LENGTH = 4
# Sequences found in real words, such as "property", "liberty", German
# "Wert" (value) or "strewn".
REAL_WORD_SEQUENCES = {"erty", "wert", "trew"}
KEYBOARD_SEQUENCES = {
    row[i : i + KEYBOARD_SEQUENCE_LENGTH]
    for keys in KEYBOARD_ROWS
    for row in (keys, keys[::-1])
    for i in range(len(row) - KEYBOARD_SEQUENCE_LENGTH + 1)
} - REAL_WORD_SEQUENCES

CONSONANT_RUN = re.compile(r"[bcdfghjklmnpqrstvwxz]{5,}")
# Letter groups that sound like one consonant, so "Deutschland" or
# "strengths" are not mistaken for random letters.
CONSONANT_DIGRAPHS = (("sch", "s"), ("ch", "c"), ("th", "t"), ("sh", "s"), ("ph", "p"), ("ck", "k"), ("gh", "g"))

# Technical tokens such as URLs, paths, e-mail addresses, versions, log
# fields and class names are split into parts at these characters.
# URL parts the letter checks would reject.
URL_WORDS = {"https", "www"}
TECHNICAL_SEPARATORS = re.compile(r"[/\\.:_=@\-\[\](){}<>,;\"']+")
REPEATED_LETTER = re.compile(r"(\w)\1\1")
MAX_ACRONYM_LENGTH = 6

PLACEHOLDER_WORDS = {
    "test",
    "tests",
    "testing",
    "deneme",
    "asd",
    "asdf",
    "qwe",
    "qwerty",
    "abc",
    "foo",
    "bar",
    "x",
    "xx",
    "xxx",
    "tbd",
    "todo",
    "n/a",
    "na",
    "none",
    "null",
    "lorem",
    "ipsum",
}


def field_length_error(values: dict[str, str]) -> Optional[str]:
    """Return an error when a field is too long for the model to read."""
    for field in COMPARED_FIELDS:
        if len(values.get(field, "")) > MAX_FIELD_CHARS:
            name = field.replace("_", " ").capitalize()
            return f"{name} is longer than {MAX_FIELD_CHARS} characters."
    return None


def normalize_text(value: str) -> str:
    """Lowercase and drop punctuation and extra whitespace for comparisons."""
    return " ".join(re.sub(r"[^\w]+", " ", value.lower()).split())


def identical_fields_error(values: dict[str, str]) -> Optional[str]:
    """Return an error when two or more fields contain the same text."""
    groups: dict[str, list[str]] = {}
    for field in COMPARED_FIELDS:
        text = normalize_text(values.get(field, ""))
        if text:
            groups.setdefault(text, []).append(field.replace("_", " "))

    repeated = next((fields for fields in groups.values() if len(fields) > 1), None)
    if repeated is None:
        return None

    names = (
        " and ".join(repeated)
        if len(repeated) == 2
        else ", ".join(repeated[:-1]) + " and " + repeated[-1]
    )
    return f"{names[0].upper()}{names[1:]} contain the same text."


def _strip(token: str) -> str:
    return token.strip(string.punctuation + "“”‘’")


def _is_word(token: str) -> bool:
    token = _strip(token)
    if not token:
        return False
    if token.isdigit():
        return True
    if not token.replace("-", "").replace("'", "").isalpha():
        return False

    # Acronyms such as HTTPS or CSRF are real words despite few vowels.
    if token.isupper() and len(token) <= MAX_ACRONYM_LENGTH:
        return True

    lowered = token.lower()
    consonants = lowered
    for digraph, sound in CONSONANT_DIGRAPHS:
        consonants = consonants.replace(digraph, sound)
    if REPEATED_LETTER.search(lowered) or CONSONANT_RUN.search(consonants):
        return False
    return not any(sequence in lowered for sequence in KEYBOARD_SEQUENCES)


def _is_word_part(part: str) -> bool:
    """A part of a technical token: a word, a number, or a short code such as
    v2, 500ms, IPv6, 04T13 or Android14."""
    if part.lower() in URL_WORDS or _is_word(part):
        return True
    letters = sum(char.isalpha() for char in part)
    if not part.isalnum() or not any(char.isdigit() for char in part):
        return False
    if letters <= 3:
        return True
    prefix = re.fullmatch(r"([^\W\d_]+)\d+", part)
    return prefix is not None and _is_word(prefix.group(1))


def _is_technical(token: str) -> bool:
    """URLs, paths, e-mails, versions, timestamps, log fields, class names."""
    parts = [part for part in TECHNICAL_SEPARATORS.split(token) if part]
    return bool(parts) and all(_is_word_part(part) for part in parts)


def _counts_as_word(token: str) -> bool:
    return _is_word(token) or _is_technical(_strip(token))


def _is_punctuation(token: str) -> bool:
    """Separators such as "-", "->" or "|" are neither words nor noise."""
    return not any(char.isalnum() for char in token)


def readability_error(values: dict[str, str]) -> Optional[str]:
    """Return why the bug report text is unusable, or None if it looks fine."""
    text = " ".join(values[field] for field in READABILITY_FIELDS)
    tokens = text.split()
    if not tokens:
        return UNREADABLE_TEXT_ERROR

    lowered = [_strip(token).lower() for token in tokens]
    if "lorem ipsum" in text.lower() or all(
        token in PLACEHOLDER_WORDS for token in lowered if token
    ):
        return PLACEHOLDER_TEXT_ERROR

    counted = [token for token in tokens if not _is_punctuation(token)]
    if not counted:
        return UNREADABLE_TEXT_ERROR
    words = sum(_counts_as_word(token) for token in counted)
    if words / len(counted) < MIN_READABLE_WORD_RATIO:
        return UNREADABLE_TEXT_ERROR

    return None

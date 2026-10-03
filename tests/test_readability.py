import pytest

from app.services.readability import (
    PLACEHOLDER_TEXT_ERROR,
    UNREADABLE_TEXT_ERROR,
    identical_fields_error,
    readability_error,
)


def report(title, description, expected, actual) -> dict:
    return {
        "title": title,
        "description": description,
        "expected_result": expected,
        "actual_result": actual,
    }


@pytest.mark.parametrize(
    "values",
    [
        report(
            "Login button stays disabled",
            "After entering valid credentials the Login button stays disabled.",
            "Login button becomes enabled",
            "Login button stays disabled",
        ),
        report(
            "Giriş butonu pasif kalıyor",
            "Geçerli bilgiler girildiğinde giriş butonu aktif olmuyor.",
            "Buton aktif olmalı",
            "Buton pasif kalıyor",
        ),
        report(
            "Anmeldeknopf bleibt deaktiviert",
            "Nach Eingabe gültiger Daten bleibt der Anmeldeknopf deaktiviert.",
            "Knopf wird aktiv",
            "Knopf bleibt deaktiviert",
        ),
        report(
            "TypeError on profile page",
            "TypeError: Cannot read property 'x' of undefined at app.js:42",
            "Profile loads over HTTPS",
            "API returns 500 on GET /api/v1/users?id=12",
        ),
        report("Bug", "It does not work.", "It works", "It does not work"),
    ],
)
def test_real_reports_are_readable(values) -> None:
    assert readability_error(values) is None


@pytest.mark.parametrize(
    "values",
    [
        report("Xq7#vL@ zR9$ kT~pW", "Fj%8 qwZ!x 9Lp#r Tz@4k", "Lx~6p Qr#4", "Dz*2q Pj+9"),
        report(
            "asdkj qweoiu zxcmn",
            "lkjsdf poiuqwe mnbzx qwpoeiru",
            "zxcvqw poiuy",
            "mnbvc lkjhg",
        ),
        report("asdfasdf qwerqwer", "asdfghjkl qwertyuiop zxcvbnm", "qwer", "zxcv"),
        report("aaaaaaa", "aaaaaaaaaaaa bbbbbbbbb", "aaaa", "bbbb"),
    ],
)
def test_gibberish_is_unreadable(values) -> None:
    assert readability_error(values) == UNREADABLE_TEXT_ERROR


@pytest.mark.parametrize(
    "values",
    [
        report("test", "test test test", "test", "test"),
        report(
            "Lorem ipsum",
            "Lorem ipsum dolor sit amet, consectetur adipiscing elit.",
            "Ut enim ad minim veniam",
            "Quis nostrud exercitation",
        ),
        report("deneme", "asdf", "n/a", "TBD"),
    ],
)
def test_placeholder_text_is_rejected(values) -> None:
    assert readability_error(values) == PLACEHOLDER_TEXT_ERROR


def full_report(**overrides) -> dict:
    return {
        "title": "Login fails",
        "description": "Cannot sign in with valid credentials",
        "steps_to_reproduce": "1. Open login\n2. Submit",
        "expected_result": "Dashboard opens",
        "actual_result": "Error message appears",
        **overrides,
    }


def test_distinct_fields_pass_identical_check() -> None:
    assert identical_fields_error(full_report()) is None


def test_identical_fields_ignore_case_and_punctuation() -> None:
    values = full_report(
        expected_result="Error message appears.",
        actual_result="  error   MESSAGE appears ",
    )

    assert identical_fields_error(values) == (
        "Expected result and actual result contain the same text."
    )


def test_more_than_two_identical_fields_are_listed() -> None:
    values = full_report(description="Login fails", expected_result="login fails!")

    assert identical_fields_error(values) == (
        "Title, description and expected result contain the same text."
    )

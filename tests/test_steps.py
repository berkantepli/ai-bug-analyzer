import pytest

from app.services.steps import split_steps


@pytest.mark.parametrize(
    ("line", "step"),
    [
        ("1. Open the login page", "Open the login page"),
        ("2) Enter the password", "Enter the password"),
        ("3 - Click Login", "Click Login"),
        ("- Click Login", "Click Login"),
        ("* Wait", "Wait"),
        ("• Open settings", "Open settings"),
        ("– Open settings", "Open settings"),
        ("a) Open the menu", "Open the menu"),
        ("Step 3: Click Save", "Click Save"),
        ("Adım 2. Kaydet'e tıkla", "Kaydet'e tıkla"),
        ("Open the app", "Open the app"),
    ],
)
def test_list_markers_are_removed(line, step) -> None:
    assert split_steps(line) == [step]


@pytest.mark.parametrize(
    "line",
    ["1.5 GB dosya yükle", "10.0.0.1 adresine git", "-5 derecede çalıştır", "e.g. Safari"],
)
def test_values_that_look_like_markers_are_kept(line) -> None:
    assert split_steps(line) == [line]


def test_each_non_empty_line_is_a_step() -> None:
    assert split_steps("1. Open\n\n  2. Click  \n-\n") == ["Open", "Click"]

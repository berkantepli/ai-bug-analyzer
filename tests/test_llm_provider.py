import pytest

from app.providers.llm import LLMProvider


def test_llm_provider_cannot_be_instantiated() -> None:
    with pytest.raises(TypeError):
        LLMProvider()

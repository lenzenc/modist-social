from app.config import settings
from app.llm.types import LLM


def make_llm() -> LLM:
    if settings.llm_mode == "mock":
        from app.llm.mock import MockLLM

        return MockLLM()
    from app.llm.live import AnthropicLLM

    return AnthropicLLM()

import json
from types import SimpleNamespace as NS

import pytest

from app.llm import live
from app.llm.live import AnthropicLLM
from app.llm.types import TurnRequest
from app.llm.usage import Usage


def resp(text="", stop="end_turn", content=None, **usage):
    u = NS(input_tokens=0, output_tokens=0, cache_read_input_tokens=0, cache_creation_input_tokens=0,
           server_tool_use=NS(web_search_requests=usage.pop("searches", 0)))
    for k, v in usage.items():
        setattr(u, k, v)
    blocks = content if content is not None else [NS(type="text", text=text)]
    return NS(content=blocks, stop_reason=stop, usage=u)


class StubClient:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []
        self.messages = NS(create=self._create)

    async def _create(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0)


@pytest.fixture
def llm(monkeypatch):
    fresh = Usage()
    monkeypatch.setattr(live, "usage", fresh)
    monkeypatch.setattr("app.llm.usage.usage", fresh)
    inst = AnthropicLLM()
    inst.fresh = fresh
    return inst


REQ = TurnRequest(person_id="p01", person_name="Dana", world="WORLD", persona="PERSONA", context="scene")


async def test_speak_parses_json_and_sends_cacheable_prefix(llm):
    payload = {"say": "Hey there.", "action": "none", "target": "", "lookup": ""}
    llm.client = StubClient(resp(json.dumps(payload), input_tokens=300, output_tokens=40,
                                 cache_read_input_tokens=1800, cache_creation_input_tokens=0))
    u = await llm.speak(REQ)
    assert u.say == "Hey there." and u.action == "none"

    call = llm.client.calls[0]
    assert call["model"] == "claude-haiku-5-5"
    assert call["thinking"] == {"type": "disabled"}
    assert call["output_config"]["effort"] == "low"
    assert call["output_config"]["format"]["type"] == "json_schema"
    assert "temperature" not in call  # sampling params are rejected on Haiku 5.5
    assert [b["text"] for b in call["system"]] == ["WORLD", "PERSONA"]
    assert all(b["cache_control"] == {"type": "ephemeral"} for b in call["system"])
    assert call["messages"] == [{"role": "user", "content": "scene"}]

    s = llm.fresh.snapshot()
    assert s["cache_read_tokens"] == 1800 and s["cache_hit_pct"] > 80
    # 300*0.10 + 40*0.50 + 1800*0.01 per million
    assert abs(llm.fresh.spent_today - (30 + 20 + 18) / 1_000_000) < 1e-9


async def test_speak_returns_none_on_refusal_truncation_and_bad_json(llm):
    for r in (resp("", stop="refusal"), resp('{"say": "cut', stop="max_tokens"), resp("not json")):
        llm.client = StubClient(r)
        assert await llm.speak(REQ) is None
    llm.client = StubClient(resp(json.dumps({"say": "  ", "action": "none", "target": "", "lookup": ""})))
    assert await llm.speak(REQ) is None


async def test_news_resumes_pause_turn_and_parses_lines(llm):
    paused = resp(stop="pause_turn", content=[NS(type="server_tool_use")], searches=2)
    done = resp("- City delays vote.\n- Brewery wins medal.\nnoise line\n- Rain this weekend.", output_tokens=60)
    llm.client = StubClient(paused, done)
    lines = await llm.news("Minneapolis, MN", "Monday", ["Old story about parking."])
    assert lines == ["City delays vote.", "Brewery wins medal.", "Rain this weekend."]
    assert "Old story about parking." in llm.client.calls[0]["messages"][0]["content"]
    assert llm.client.calls[0]["tools"][0]["type"] == "web_search_20250305"
    # The resume call replays the paused assistant turn.
    assert llm.client.calls[1]["messages"][-1]["role"] == "assistant"
    assert llm.fresh.searches == 2


async def test_budget_guard():
    u = Usage()
    u.budget = 0.0001
    assert not u.over_budget()
    u.record(NS(input_tokens=1000, output_tokens=500, cache_read_input_tokens=0, cache_creation_input_tokens=0))
    assert u.over_budget()

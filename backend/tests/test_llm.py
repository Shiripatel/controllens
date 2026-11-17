from types import SimpleNamespace

import anthropic

from app.agents import llm


class FakeMessages:
    def __init__(self, outputs):
        self.outputs = outputs
        self.calls = []

    def create(self, **kw):
        self.calls.append(kw)
        data = self.outputs.pop(0)
        return SimpleNamespace(
            content=[SimpleNamespace(type="tool_use", input=data)], model=kw["model"],
            usage=SimpleNamespace(input_tokens=100, output_tokens=50))


def test_anthropic_path_retries_on_bad_output(monkeypatch):
    fake = FakeMessages([{"wrong": 1}, {"notes": [], "overall": "ok"}])
    monkeypatch.setattr(anthropic, "Anthropic", lambda **kw: SimpleNamespace(messages=fake))
    monkeypatch.setattr(llm, "provider_name", lambda: "anthropic")
    r = llm.call_structured(tool_name="t", tool_description="d",
                            schema={"type": "object", "required": ["notes", "overall"]},
                            system="s", user="u", mock=lambda: {})
    assert r.data["overall"] == "ok" and r.provider == "anthropic" and r.input_tokens == 100
    assert len(fake.calls) == 2
    assert fake.calls[0]["tool_choice"] == {"type": "tool", "name": "t"}

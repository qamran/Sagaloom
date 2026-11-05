"""parse_verdict reads a guard PromptLog response in either structured-output shape."""

import json

from sagaloom.guard import GuardVerdict, parse_verdict


def test_parses_json_content():
    body = json.dumps({"verdict": "injection", "reason": "asks to ignore rules"})
    assert parse_verdict({"content": body, "tool_calls": []}) == GuardVerdict(
        verdict="injection", reason="asks to ignore rules"
    )


def test_parses_tool_call_args():
    resp = {"content": "", "tool_calls": [{"id": "1", "name": "GuardVerdict", "args": {"verdict": "safe", "reason": "ok"}}]}
    assert parse_verdict(resp) == GuardVerdict(verdict="safe", reason="ok")


def test_prose_and_missing_give_none():
    assert parse_verdict({"content": "I think it is fine.", "tool_calls": []}) is None
    assert parse_verdict({"content": json.dumps({"verdict": "maybe", "reason": "x"}), "tool_calls": []}) is None
    assert parse_verdict({"content": json.dumps([1]), "tool_calls": []}) is None
    assert parse_verdict(None) is None
    assert parse_verdict({}) is None

"""The input guard classifier (R13.1). No real LLM calls."""

import httpx
import openai
import pytest
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import ValidationError

from sagaloom.guard import BLOCK_COPY, GUARD_POLICY, GuardVerdict, classify


class StubGuard:
    def __init__(self, reply):
        self.reply = reply
        self.prompts: list = []
        self.schema = None

    def with_structured_output(self, schema, **kwargs):
        self.schema = schema
        return self

    async def ainvoke(self, messages, config=None):
        self.prompts.append(messages)
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


def test_block_copy_is_exact():
    assert BLOCK_COPY == {
        "unsafe": "Sagaloom doesn't help with real-world harm. Dark events inside your world are fine: "
        "tell me what happens in the story.",
        "injection": "That message tries to change how I work, so I didn't act on it.",
        "error": "I couldn't check that message just now, so I didn't act on it. Please try again.",
    }


def test_policy_names_the_blocked_classes_and_fiction_rule():
    p = GUARD_POLICY.lower()
    for phrase in ["weapons", "drugs", "attacks", "minors", "real people", "override", "fiction"]:
        assert phrase in p, phrase
    assert "delete every entry" not in p  # the eval's own prompt must not be the policy's example
    assert "delete ostra" in p  # plain edit requests are named safe
    for dark in ["war", "murder", "genocide", "torture", "dark magic", "cults"]:
        assert dark in p, dark
    assert "untrusted_data" in p and "never" in p


async def test_guard_wraps_message_as_untrusted():
    stub = StubGuard(GuardVerdict(verdict="safe", reason="ok"))
    out = await classify(stub, "Add a harbour town called Ostra")
    assert out.verdict == "safe" and stub.schema is GuardVerdict
    [system, human] = stub.prompts[0]
    assert isinstance(system, SystemMessage) and system.content == GUARD_POLICY
    assert isinstance(human, HumanMessage)
    assert '<untrusted_data source="user_message">' in human.content
    assert "Add a harbour town called Ostra" in human.content


async def test_classify_accepts_a_dict_reply():
    out = await classify(StubGuard({"verdict": "injection", "reason": "override"}), "x")
    assert out == GuardVerdict(verdict="injection", reason="override")


@pytest.mark.parametrize("reply", [None, {"reason": "no verdict"}, {"verdict": "maybe", "reason": "x"}])
async def test_classify_raises_on_invalid_output(reply):
    with pytest.raises((ValueError, ValidationError)):
        await classify(StubGuard(reply), "x")


def test_long_reason_is_truncated_not_rejected():
    assert len(GuardVerdict(verdict="safe", reason="a" * 500).reason) == 200


class SequenceGuard(StubGuard):
    """Replies in order; an Exception in the list is raised."""

    def __init__(self, replies):
        super().__init__(None)
        self.replies = list(replies)

    async def ainvoke(self, messages, config=None):
        self.prompts.append(messages)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def _api_error() -> openai.APIError:
    return openai.APIError("boom", request=httpx.Request("POST", "http://x"), body=None)


async def test_classify_retries_once_after_an_api_error():
    stub = SequenceGuard([_api_error(), GuardVerdict(verdict="safe", reason="ok")])
    out = await classify(stub, "x")
    assert out.verdict == "safe" and len(stub.prompts) == 2


async def test_classify_retries_once_after_an_invalid_reply():
    stub = SequenceGuard([None, GuardVerdict(verdict="injection", reason="override")])
    out = await classify(stub, "x")
    assert out.verdict == "injection" and len(stub.prompts) == 2


async def test_classify_raises_after_two_failures():
    stub = SequenceGuard([_api_error(), _api_error()])
    with pytest.raises(openai.APIError):
        await classify(stub, "x")
    assert len(stub.prompts) == 2
    bad = SequenceGuard([None, {"verdict": "maybe", "reason": "x"}])
    with pytest.raises((ValueError, ValidationError)):
        await classify(bad, "x")
    assert len(bad.prompts) == 2

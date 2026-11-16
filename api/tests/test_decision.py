"""The Jev decision-model router classifier (R6.6). No network: a fake classifier answers."""

from types import SimpleNamespace

import pytest
from langchain_typesafe import ClassifierResponse
from langchain_typesafe.types import ChoiceAnswer, Usage

from sagaloom.config import Settings
from sagaloom.decision import (
    ROUTER_QUESTION,
    DecisionFailed,
    JevDecision,
    classify_mode,
    decision_base_url,
    make_router_classifier,
)

KEY = "sk-or-SECRET-KEY-123"
S = Settings(_env_file=None, openrouter_api_key=KEY, api_shared_secret="shared")


def answer(choice: str, confidence: float = 0.94) -> ClassifierResponse:
    labels = ["brainstorm", "query", "edit"]
    probs = {label: (0.9 if label == choice else 0.05) for label in labels}
    return ClassifierResponse(
        model="typesafe/jev-1.14-20261014",
        answers={"mode": ChoiceAnswer(type="choice", choice=choice, probabilities=probs, confidence=confidence)},
        usage=Usage(input_tokens=120, output_tokens=3),
    )


class FakeClassifier:
    """Answers with a scripted response, or raises a scripted exception."""

    model = "jev-latest"

    def __init__(self, result):
        self.result = result
        self.inputs: list[dict] = []

    async def ainvoke(self, input, config=None):
        self.inputs.append(input)
        if isinstance(self.result, BaseException):
            raise self.result
        return self.result


def test_base_url_strips_v1():
    assert decision_base_url("https://openrouter.ai/api/v1") == "https://openrouter.ai/api"
    assert decision_base_url("https://openrouter.ai/api/v1/") == "https://openrouter.ai/api"
    assert decision_base_url("https://openrouter.ai/api") == "https://openrouter.ai/api"


def test_make_router_classifier_uses_settings():
    classifier = make_router_classifier(S)
    assert classifier.model == "jev-latest"
    assert classifier.base_url == "https://openrouter.ai/api"
    assert classifier.timeout == 10.0
    assert KEY not in repr(classifier)


def test_question_has_three_modes():
    assert set(ROUTER_QUESTION.criteria) == {"brainstorm", "query", "edit"}


async def test_classify_returns_mode_and_confidence():
    fake = FakeClassifier(answer("query", 0.94))
    decision = await classify_mode(fake, "Who rules Ister?")
    assert decision == JevDecision(mode="query", confidence=0.94, model="typesafe/jev-1.14-20261014")
    assert fake.inputs[0]["state"] == "Who rules Ister?"
    assert fake.inputs[0]["questions"] == {"mode": ROUTER_QUESTION}


async def test_unknown_label_raises():
    with pytest.raises(DecisionFailed):
        await classify_mode(FakeClassifier(answer("other")), "x")


async def test_missing_answer_raises():
    empty = ClassifierResponse(model="typesafe/jev-1.14-20261014", answers={})
    with pytest.raises(DecisionFailed):
        await classify_mode(FakeClassifier(empty), "x")


async def test_records_without_handler_do_not_raise():
    decision = await classify_mode(FakeClassifier(answer("edit")), "x")
    assert decision.mode == "edit"


async def test_classifier_exception_propagates_without_handler():
    with pytest.raises(TimeoutError):
        await classify_mode(FakeClassifier(TimeoutError("slow")), "x")


async def test_recording_error_never_replaces_the_decision():
    # A usage of the wrong type makes building the log payload raise; the decision still returns.
    odd = SimpleNamespace(
        model="typesafe/jev-1.14-20261014",
        choices={"mode": SimpleNamespace(choice="query", confidence=0.9)},
        usage="not a usage",
    )
    decision = await classify_mode(FakeClassifier(odd), "x")
    assert decision == JevDecision(mode="query", confidence=0.9, model="typesafe/jev-1.14-20261014")


async def test_recording_error_never_replaces_the_original_error(monkeypatch):
    def broken(_exc):
        raise ValueError("payload")

    monkeypatch.setattr("sagaloom.decision.failure_line", broken)
    with pytest.raises(TimeoutError):
        await classify_mode(FakeClassifier(TimeoutError("slow")), "x")

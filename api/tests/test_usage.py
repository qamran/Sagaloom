from langchain_core.messages import AIMessage

from sagaloom.config import Settings
from sagaloom.models import Usage
from sagaloom.usage import add_usage, extract_usage

S = Settings(_env_file=None, openrouter_api_key="k", api_shared_secret="s",
             web_origin="http://localhost:3000")


def test_extract_usage_prefers_openrouter_cost():
    msg = AIMessage(content="x", response_metadata={"token_usage": {
        "prompt_tokens": 100, "completion_tokens": 50, "cost": 0.0042}},
        usage_metadata={"input_tokens": 1, "output_tokens": 1, "total_tokens": 2})
    assert extract_usage(msg, S) == Usage(prompt_tokens=100, completion_tokens=50, cost_usd=0.0042)


def test_extract_usage_estimates_cost_when_missing():
    msg = AIMessage(content="x", usage_metadata={
        "input_tokens": 1_000_000, "output_tokens": 2_000_000, "total_tokens": 3_000_000})
    u = extract_usage(msg, S)
    assert (u.prompt_tokens, u.completion_tokens) == (1_000_000, 2_000_000)
    assert abs(u.cost_usd - (0.10 + 1.00)) < 1e-9


def test_extract_usage_no_usage_is_zero():
    assert extract_usage(AIMessage(content="x"), S) == Usage()


def test_add_usage_sums_fields():
    a = Usage(prompt_tokens=1, completion_tokens=2, cost_usd=0.5)
    b = Usage(prompt_tokens=3, completion_tokens=4, cost_usd=0.25)
    assert add_usage(a, b) == Usage(prompt_tokens=4, completion_tokens=6, cost_usd=0.75)

from langchain_core.messages import AIMessage

from sagaloom.config import Settings
from sagaloom.models import Usage


def extract_usage(msg: AIMessage, settings: Settings) -> Usage:
    tu = (msg.response_metadata or {}).get("token_usage") or {}
    cost = tu.get("cost")
    if tu.get("prompt_tokens") is not None or tu.get("completion_tokens") is not None:
        prompt = int(tu.get("prompt_tokens") or 0)
        completion = int(tu.get("completion_tokens") or 0)
    elif msg.usage_metadata:
        prompt = int(msg.usage_metadata.get("input_tokens") or 0)
        completion = int(msg.usage_metadata.get("output_tokens") or 0)
    else:
        prompt = completion = 0
    if cost is None:
        cost = (
            prompt / 1e6 * settings.price_in_per_mtok
            + completion / 1e6 * settings.price_out_per_mtok
        )
    return Usage(prompt_tokens=prompt, completion_tokens=completion, cost_usd=float(cost))


def add_usage(a: Usage, b: Usage) -> Usage:
    return Usage(
        prompt_tokens=a.prompt_tokens + b.prompt_tokens,
        completion_tokens=a.completion_tokens + b.completion_tokens,
        cost_usd=a.cost_usd + b.cost_usd,
    )

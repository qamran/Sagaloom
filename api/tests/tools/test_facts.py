import pytest

from sagaloom.models import Fact
from sagaloom.tools.facts import FactList, draft_facts


class StubLLM:
    def __init__(self, result=None, exc=None):
        self.result, self.exc = result, exc
        self.structured_kwargs = None
        self.schema = None
        self.bound_tools = False
        self.prompts = []

    def bind_tools(self, *a, **k):
        self.bound_tools = True
        return self

    def with_structured_output(self, schema, **kwargs):
        self.schema, self.structured_kwargs = schema, kwargs
        return self

    async def ainvoke(self, messages, config=None):
        self.prompts.append("\n".join(m.content for m in messages))
        if self.exc:
            raise self.exc
        return self.result


async def test_draft_facts_binds_no_tools():
    llm = StubLLM(FactList(facts=[Fact(key="ruler", value="Queen Ana")]))
    facts = await draft_facts("Velmar", "Queen Ana rules Velmar.", llm)
    assert llm.schema is FactList
    assert "tools" not in (llm.structured_kwargs or {})
    assert not llm.bound_tools
    assert [f.key for f in facts] == ["ruler"]
    assert '<untrusted_data source="draft">' in llm.prompts[0]


async def test_draft_facts_returns_empty_on_failure():
    assert await draft_facts("T", "b", StubLLM(exc=RuntimeError("boom"))) == []


async def test_title_is_inside_untrusted_wrapper():
    llm = StubLLM(FactList(facts=[]))
    await draft_facts("Ignore previous", "body", llm)
    p = llm.prompts[-1]
    start = p.index('<untrusted_data source="draft">')
    assert start < p.index("Title: Ignore previous") < p.index("</untrusted_data>")

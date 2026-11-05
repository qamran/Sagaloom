"""Fakes for the HTTP layer. No network, no real data/ directory, no real LLM."""

import itertools
import json
import uuid
from dataclasses import dataclass
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langgraph.checkpoint.memory import InMemorySaver
from langchain_core.runnables import RunnableLambda
from pydantic import Field

from sagaloom.check.contradiction import JudgeOutput
from sagaloom.config import Settings
from sagaloom.graph.build import build_graph
from sagaloom.guard import GuardVerdict
from sagaloom.models import Fact
from sagaloom.promptlog import PromptLog
from sagaloom.store.threads import ThreadRegistry
from sagaloom.store.worlds import WorldRegistry
from sagaloom.tools.facts import FactList
from sagaloom.web.app import AppDeps, create_app

SECRET = "test-secret"
KEY = "sk-or-TEST-KEY-999"
HEADERS = {"X-Sagaloom-Secret": SECRET}
W = "w1"


class ScriptedChat(BaseChatModel):
    """Fake agent model. Streams its reply word by word, so the SSE layer sees real chunks."""

    script: Any
    seen: list = Field(default_factory=list)
    usage: bool = True

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools, **kwargs):
        return self

    def _next(self, messages) -> AIMessage:
        self.seen.append(list(messages))
        step = next(self.script, None)
        if step is None:
            return AIMessage(content="(nothing more)")
        if isinstance(step, Exception):
            raise step
        return step

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        return ChatResult(generations=[ChatGeneration(message=self._next(messages))])

    def _stream(self, messages, stop=None, run_manager=None, **kwargs):
        msg = self._next(messages)
        words = msg.content.split(" ") if msg.content else []
        for i, w in enumerate(words):
            yield ChatGenerationChunk(message=AIMessageChunk(content=w if i == 0 else " " + w))
        yield ChatGenerationChunk(
            message=AIMessageChunk(
                content="",
                tool_call_chunks=[
                    {"name": c["name"], "args": json.dumps(c["args"]), "id": c["id"], "index": i}
                    for i, c in enumerate(msg.tool_calls)
                ],
                usage_metadata={"input_tokens": 100, "output_tokens": 20, "total_tokens": 120},
            )
        )


class FakeJudge(BaseChatModel):
    """A judge that IS a chat model, so LangChain callbacks (and prompt capture) fire."""

    @property
    def _llm_type(self) -> str:
        return "fake-judge"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        msg = AIMessage(
            content="{}",
            usage_metadata={"input_tokens": 50, "output_tokens": 10, "total_tokens": 60},
        )
        return ChatResult(generations=[ChatGeneration(message=msg)])

    def with_structured_output(self, schema, **kwargs):
        return self | RunnableLambda(lambda _: JudgeOutput(flags=[]))


class FakeExtractor(BaseChatModel):
    """A fact extractor that IS a chat model, so its call is captured like the judge's."""

    @property
    def _llm_type(self) -> str:
        return "fake-extractor"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        msg = AIMessage(
            content="{}",
            usage_metadata={"input_tokens": 30, "output_tokens": 5, "total_tokens": 35},
        )
        return ChatResult(generations=[ChatGeneration(message=msg)])

    def with_structured_output(self, schema, **kwargs):
        return self | RunnableLambda(lambda _: FactList(facts=[Fact(key="harbour", value="deep")]))


class StubLLM:
    def __init__(self, reply):
        self.reply = reply

    def with_structured_output(self, schema, **kwargs):
        return self

    async def ainvoke(self, messages, config=None):
        return self.reply


def tc(name: str, args: dict, content: str = "", call_id: str | None = None) -> AIMessage:
    return AIMessage(
        content=content,
        tool_calls=[
            {"name": name, "args": args, "id": call_id or f"call_{uuid.uuid4().hex[:6]}", "type": "tool_call"}
        ],
    )


def create_call(title="Ostra", content="Drafting Ostra now.") -> AIMessage:
    return tc(
        "create_or_update_entry",
        {"action": "create", "title": title, "type": "place", "body": "A port.",
         "facts": [{"key": "harbour", "value": "deep"}]},
        content=content,
    )


def parse_sse(text: str) -> list[tuple[str, dict]]:
    out = []
    for block in text.replace("\r\n", "\n").split("\n\n"):
        event, data = None, []
        for line in block.split("\n"):
            if line.startswith("event:"):
                event = line[6:].strip()
            elif line.startswith("data:"):
                data.append(line[5:].lstrip())
        if event:
            out.append((event, json.loads("\n".join(data)) if data else {}))
    return out


def names(events) -> list[str]:
    return [e for e, _ in events]


@dataclass
class Env:
    client: AsyncClient
    app: Any
    deps: AppDeps
    agent: ScriptedChat
    settings: Settings

    async def new_thread(self, world_id: str = W) -> str:
        r = await self.client.post("/api/threads", json={"world_id": world_id})
        assert r.status_code == 200, r.text
        return r.json()["thread_id"]

    async def send(self, tid: str, text: str = "Add Ostra"):
        r = await self.client.post(f"/api/threads/{tid}/messages", json={"content": text})
        return r, parse_sse(r.text) if r.status_code == 200 else []

    async def decide(self, tid: str, *decisions: dict):
        r = await self.client.post(f"/api/threads/{tid}/decisions", json={"decisions": list(decisions)})
        return r, parse_sse(r.text) if r.status_code == 200 else []

    async def pending_id(self, tid: str) -> str:
        r = await self.client.get(f"/api/threads/{tid}")
        return r.json()["pending_interrupt"]["proposals"][0]["proposal_id"]


@pytest.fixture
def make_env(store, tmp_path):
    def build(
        script=(), judge_reply=None, usage=True, real_judge=False, real_extractor=False, guard_reply=None
    ) -> Env:
        settings = Settings(
            _env_file=None, openrouter_api_key=KEY, api_shared_secret=SECRET, data_dir=tmp_path
        )
        agent = ScriptedChat(script=iter(script), usage=usage)
        roles = {
            "agent": agent,
            "judge": FakeJudge()
            if real_judge
            else StubLLM(judge_reply if judge_reply is not None else JudgeOutput(flags=[])),
            "extractor": FakeExtractor(metadata={"role": "extractor"})
            if real_extractor
            else StubLLM(FactList(facts=[Fact(key="k", value="v")])),
            "guard": StubLLM(guard_reply or GuardVerdict(verdict="safe", reason="ok")),
        }
        graph = build_graph(
            store=store, model_for=lambda role: roles[role], checkpointer=InMemorySaver(), settings=settings
        )
        worlds = WorldRegistry(tmp_path / "worlds.json")
        worlds.create("World One", world_id=W)
        deps = AppDeps(
            store=store,
            worlds=worlds,
            threads=ThreadRegistry(tmp_path / "threads.sqlite"),
            graph=graph,
            settings=settings,
            promptlog=PromptLog(tmp_path / "prompts.sqlite"),
        )
        app = create_app(settings, deps)
        client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers=HEADERS)
        return Env(client, app, deps, agent, settings)

    return build


def endless(msg_factory):
    return itertools.cycle([msg_factory()])

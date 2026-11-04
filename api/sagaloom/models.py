from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field

EntryType = Literal["character", "place", "faction", "item", "rule", "event"]
Status = Literal["canon", "myth", "rumour", "secret"]
Source = Literal["user", "official", "reference"]


def _now() -> str:
    return datetime.now(UTC).isoformat()


class Fact(BaseModel):
    key: str = Field(min_length=1, max_length=40)
    value: str = Field(min_length=1, max_length=200)
    refs: list[str] = Field(default_factory=list)
    status: Status = "canon"
    told_by: str | None = None


class Link(BaseModel):
    target_id: str
    relation: str


class Entry(BaseModel):
    id: str = Field(pattern=r"^ent_\d{4}$")
    world_id: str
    title: str = Field(min_length=1, max_length=120)
    type: EntryType
    body: str = Field(max_length=4000)
    status: Status = "canon"
    source: Source = "user"
    source_url: str | None = None
    licence: str | None = None
    trusted: bool = True
    aliases: list[str] = Field(default_factory=list)
    links: list[Link] = Field(default_factory=list)
    facts: list[Fact] = Field(default_factory=list)
    version: int = 1
    created_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)


class EntryDraft(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    type: EntryType
    body: str = Field(max_length=4000)
    status: Status = "canon"
    aliases: list[str] = Field(default_factory=list)
    facts: list[Fact] = Field(default_factory=list)


class World(BaseModel):
    id: str
    name: str
    is_demo: bool = False
    divergent: bool = False


class SearchHit(BaseModel):
    id: str
    title: str
    type: EntryType
    status: Status
    source: Source
    snippet: str
    score: float

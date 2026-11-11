from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from sagaloom.licence import is_nc

EntryType = Literal["character", "place", "faction", "item", "rule", "event"]
Status = Literal["canon", "myth", "rumour", "secret"]
Source = Literal["user", "official", "reference"]
SourceKind = Literal["official", "reference"]


def _now() -> str:
    return datetime.now(UTC).isoformat()


class Fact(BaseModel):
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    key: str = Field(min_length=1, max_length=40)
    value: str = Field(min_length=1, max_length=200)
    refs: list[str] = Field(default_factory=list)
    status: Status = "canon"
    told_by: str | None = None


class EntrySource(BaseModel):
    """One page an entry's content came from (R-W3-1). Set by the server, never by the agent."""

    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    kind: SourceKind
    url: str
    licence: str | None = None
    licence_url: str | None = None
    nc: bool = False
    added_at: str = Field(default_factory=_now)


def _legacy_sources(m: "Entry | EntryDraft", added_at: str) -> None:
    """An entry stored before `sources` existed reads its one primary source as a list (R-W3-1)."""
    if not m.sources and m.source in ("official", "reference") and m.source_url:
        m.sources = [
            EntrySource(
                kind=m.source,
                url=m.source_url,
                licence=m.licence,
                nc=is_nc(m.licence, None),
                added_at=added_at,
            )
        ]


class Link(BaseModel):
    target_id: str
    relation: str


class Entry(BaseModel):
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

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
    sources: list[EntrySource] = Field(default_factory=list)
    version: int = Field(default=1, ge=1)
    created_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)

    @model_validator(mode="after")
    def _fill_legacy_sources(self) -> "Entry":
        _legacy_sources(self, self.created_at)
        return self


class EntryDraft(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    type: EntryType
    body: str = Field(max_length=4000)
    status: Status = "canon"
    aliases: list[str] = Field(default_factory=list)
    facts: list[Fact] = Field(default_factory=list)
    # Provenance (R2.S, R11.4.6): set by the server, never by the agent's tool arguments.
    source: Source = "user"
    source_url: str | None = None
    licence: str | None = None
    trusted: bool = True
    sources: list[EntrySource] = Field(default_factory=list)

    @model_validator(mode="after")
    def _fill_legacy_sources(self) -> "EntryDraft":
        _legacy_sources(self, _now())
        return self


PROVENANCE_FIELDS = ("source", "source_url", "licence", "trusted", "sources")


class World(BaseModel):
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    id: str
    name: str
    is_demo: bool = False
    divergent: bool = False
    owner_id: str | None = None


class User(BaseModel):
    """A Clerk user as the API stores them. `is_admin` is never stored: the caller sets it per
    request from `admin_flag`."""

    id: str
    email: str
    email_verified: bool
    display_name: str
    last_world_id: str | None = None
    created_at: str
    profile_checked_at: str
    is_admin: bool = False


class HitFact(BaseModel):
    key: str
    value: str
    status: Status


class SearchHit(BaseModel):
    id: str
    title: str
    type: EntryType
    status: Status
    source: Source
    snippet: str
    facts: list[HitFact] = Field(default_factory=list)  # non-secret facts only
    score: float
    trusted: bool = True


FlagKind = Literal["conflict", "retcon", "note"]


class Flag(BaseModel):
    kind: FlagKind
    entry_id: str
    title: str
    fact_key: str | None = None
    existing_fact: str | None = None
    new_fact: str | None = None
    existing_quote: str | None = None
    new_quote: str | None = None
    severity: Literal["hard", "possible", "note"] | None = None
    explanation: str
    suggested_fix: str | None = None
    # The existing side is (or may be) a secret fact; the card masks this flag's free text.
    existing_secret: bool = False


class _RefBase(BaseModel):
    id: str
    title: str
    type: EntryType


class EntryRef(_RefBase):
    """A delete-check dependent. `via="link"` marks an entry tied only by a link (which may be
    secret), so the web can count it without naming it while secrets are hidden."""

    via: Literal["text", "link"] = "text"


class MentionRef(_RefBase):
    """An entry that names another in its text ("Mentioned in"); the web masks a secret one."""

    status: Status


class CheckResult(BaseModel):
    proposal_id: str
    verdict: Literal["none", "possible", "conflict", "failed"]
    flags: list[Flag] = Field(default_factory=list)
    dependents: list[EntryRef] = Field(default_factory=list)


class Proposal(BaseModel):
    proposal_id: str
    action: Literal["create", "update", "delete"]
    world_id: str
    entry_id: str | None
    before: Entry | None
    after: EntryDraft | None
    # Set only by the import builders (`importing/extract.py`, `importing/wiki.py`), never from a
    # tool argument: it tells Save as myth that a merge section in `after.body` is the server's, so
    # the imported passage is kept (R-W5-11, R3.5). A pending proposal from a checkpoint written
    # before this field existed reads as False, so a myth save on it restores the stored body.
    imported: bool = False


class Decision(BaseModel):
    proposal_id: str
    action: Literal["approve", "edit", "reject", "save_as_myth"]
    edited: EntryDraft | None = None
    told_by: str | None = None


class Usage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0


class RoleUsage(BaseModel):
    """One model role's calls in a turn; `role` is None for a record logged without one."""

    role: str | None
    calls: int
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float


class TurnUsage(BaseModel):
    """A turn's usage (the PromptLog records sharing its `run_id`), total and by role."""

    turn_id: str
    usage: Usage
    by_role: list[RoleUsage]


# Long-term author preferences (R10.2, spec §3.5). Here rather than in `sagaloom.memory` so the
# strict checkpoint serde, which allows every class defined in this module, covers them.
PreferenceKey = Literal["tone", "genre", "banned_tropes", "notes"]


class MemoryUpdate(BaseModel):
    """A preference the agent asked to remember; the `remember` node gates and writes it."""

    key: PreferenceKey
    value: str


# Why a result is what it is; `agent_note` switches on it, never on the note text.
MemoryReason = Literal["stored", "not_said", "full", "invalid", "unavailable"]


class MemoryResult(BaseModel):
    """What the `remember` node did with one update; `note` is the exact chat copy."""

    key: str
    value: str
    stored: bool
    note: str
    reason: MemoryReason

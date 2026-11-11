import re
from datetime import UTC, datetime
from typing import Literal

import chromadb
from langchain_core.embeddings import Embeddings

from sagaloom.models import Entry, HitFact, SearchHit

_QUOTES = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"'})
MAX_K = 10


def norm(s: str) -> str:
    return " ".join(s.translate(_QUOTES).casefold().split())


class DuplicateTitleError(Exception):
    def __init__(self, title: str):
        super().__init__(f"An entry titled {title!r} already exists in this world")
        self.title = title


class VersionConflictError(ValueError):
    """The stored version is not the one the writer read (`actual` is None: no such entry)."""

    def __init__(self, entry_id: str, expected: int, actual: int | None):
        found = "does not exist" if actual is None else f"is at v{actual}"
        super().__init__(f"Entry {entry_id} {found}, expected v{expected}")
        self.entry_id, self.expected, self.actual = entry_id, expected, actual


def _mentions(text_norm: str, name: str) -> bool:
    n = norm(name)
    return bool(n) and re.search(rf"(?<!\w){re.escape(n)}(?!\w)", text_norm) is not None


def _record_id(world_id: str, entry_id: str) -> str:
    """The Chroma record id: entry ids are unique per world, so the world is part of the key.
    The entry id itself (`Entry.id`) stays `ent_NNNN`, kept in metadata as `entry_id`."""
    return f"{world_id}/{entry_id}"


def _and(*clauses: dict) -> dict:
    return clauses[0] if len(clauses) == 1 else {"$and": list(clauses)}


class CanonStore:
    def __init__(
        self,
        client: chromadb.ClientAPI,
        embeddings: Embeddings,
        collection_name: str = "entries",
    ):
        self.embeddings = embeddings
        # Chroma caps how many records one call may carry; migration works in chunks of it.
        get_max = getattr(client, "get_max_batch_size", None)
        self._batch_size = get_max() if callable(get_max) else 1000
        self.col = client.get_or_create_collection(
            collection_name, metadata={"hnsw:space": "cosine"}
        )

    def next_entry_id(self, world_id: str) -> str:
        """The id after the highest `ent_NNNN` in this world (ids are unique per world)."""
        rids = self.col.get(where={"world_id": world_id}, include=[])["ids"]
        ids = [r.rsplit("/", 1)[-1] for r in rids]
        nums = [int(i[4:]) for i in ids if re.fullmatch(r"ent_\d{4}", i)]
        return f"ent_{max(nums, default=0) + 1:04d}"

    def has_id(self, world_id: str, entry_id: str) -> bool:
        """Whether this world holds an entry with this id."""
        return bool(self.col.get(ids=[_record_id(world_id, entry_id)], include=[])["ids"])

    def get_entry(self, world_id: str, entry_id: str) -> Entry | None:
        return self._read(world_id, entry_id)

    def _read(self, world_id: str, entry_id: str) -> Entry | None:
        res = self.col.get(ids=[_record_id(world_id, entry_id)], include=["metadatas"])
        if not res["ids"]:
            return None
        return Entry.model_validate_json(res["metadatas"][0]["entry_json"])

    def list_entries(self, world_id: str) -> list[Entry]:
        res = self.col.get(where={"world_id": world_id}, include=["metadatas"])
        entries = [Entry.model_validate_json(m["entry_json"]) for m in res["metadatas"]]
        return sorted(entries, key=lambda e: e.id)

    def upsert_entry(self, entry: Entry, *, expected_version: int | None = None) -> Entry:
        """Write `entry`. `expected_version` guards the write: `None` writes unconditionally
        (seed, import), `0` means the id must not exist yet, `n` means the stored version must
        be `n`; a mismatch raises VersionConflictError and nothing is written.

        Chroma has no compare-and-swap, so this is still read-then-write inside one process. It
        moves the check into the store, so every writer gets it, and it narrows the window; the
        actual guarantee is the commit node's `_COMMIT_LOCK` plus running the API as a single
        process."""
        tn = norm(entry.title)
        clash = self.col.get(
            where=_and({"world_id": entry.world_id}, {"title_norm": tn}), include=[]
        )["ids"]
        rid = _record_id(entry.world_id, entry.id)
        if any(i != rid for i in clash):
            raise DuplicateTitleError(entry.title)
        # Its own read, not get_entry: callers may wrap get_entry (the race tests do).
        prev = self._read(entry.world_id, entry.id)
        if expected_version is not None:
            actual = prev.version if prev is not None else None
            if (0 if actual is None else actual) != expected_version:
                raise VersionConflictError(entry.id, expected_version, actual)
        entry = entry.model_copy(update={"updated_at": datetime.now(UTC).isoformat()})
        doc = f"{entry.title}\n\n{entry.body}"
        self.col.upsert(
            ids=[rid],
            documents=[doc],
            embeddings=[self.embeddings.embed_documents([doc])[0]],
            metadatas=[
                {
                    "world_id": entry.world_id,
                    "entry_id": entry.id,
                    "type": entry.type,
                    "status": entry.status,
                    "title_norm": tn,
                    "entry_json": entry.model_dump_json(),
                }
            ],
        )
        return entry

    def delete_entry(self, world_id: str, entry_id: str) -> None:
        self.col.delete(ids=[_record_id(world_id, entry_id)])

    def migrate_record_ids(self) -> int:
        """Re-key records stored before ids were per world (record id == entry id) to
        `{world_id}/{entry_id}`, copying their stored embedding, document and metadata (no
        re-embed). A legacy record whose target id already exists is not copied (the keyed
        record wins) but is still deleted. Works in chunks of Chroma's batch size; each chunk is
        copied before its legacy records are deleted, so a run cut short is safe to repeat.
        Returns the number re-keyed; a second run finds none and returns 0."""
        legacy_ids = [rid for rid in self.col.get(include=[])["ids"] if "/" not in rid]
        moved = 0
        for start in range(0, len(legacy_ids), self._batch_size):
            chunk = legacy_ids[start : start + self._batch_size]
            res = self.col.get(ids=chunk, include=["embeddings", "documents", "metadatas"])
            metas = [{**m, "entry_id": rid} for rid, m in zip(res["ids"], res["metadatas"])]
            targets = [_record_id(m["world_id"], m["entry_id"]) for m in metas]
            existing = set(self.col.get(ids=targets, include=[])["ids"])
            fresh = [i for i, t in enumerate(targets) if t not in existing]
            if fresh:
                self.col.upsert(
                    ids=[targets[i] for i in fresh],
                    embeddings=[res["embeddings"][i] for i in fresh],
                    documents=[res["documents"][i] for i in fresh],
                    metadatas=[metas[i] for i in fresh],
                )
            self.col.delete(ids=res["ids"])
            moved += len(fresh)
        return moved

    def search(
        self,
        world_id: str,
        query: str,
        k: int = 5,
        entry_types: list[str] | None = None,
        statuses: list[str] | None = None,
    ) -> list[SearchHit]:
        k = max(1, min(k, MAX_K))
        clauses: list[dict] = [{"world_id": world_id}]
        if entry_types:
            clauses.append({"type": {"$in": list(entry_types)}})
        if statuses:
            clauses.append({"status": {"$in": list(statuses)}})
        res = self.col.query(
            query_embeddings=[self.embeddings.embed_query(query)],
            n_results=k,
            where=_and(*clauses),
            include=["metadatas", "distances"],
        )
        hits = []
        for meta, dist in zip(res["metadatas"][0], res["distances"][0]):
            e = Entry.model_validate_json(meta["entry_json"])
            hits.append(
                SearchHit(
                    id=e.id,
                    title=e.title,
                    type=e.type,
                    status=e.status,
                    source=e.source,
                    # A secret entry keeps its id and title (so the agent does not create a
                    # duplicate), but no body text, and no secret fact of any entry, reaches it.
                    snippet="" if e.status == "secret" else e.body[:200],
                    facts=[]
                    if e.status == "secret"
                    else [
                        HitFact(key=f.key, value=f.value, status=f.status)
                        for f in e.facts
                        if f.status != "secret"
                    ],
                    score=1 - dist,
                    trusted=e.trusted,
                )
            )
        return sorted(hits, key=lambda h: h.score, reverse=True)

    def name_index(self, world_id: str) -> dict[str, Entry]:
        """`norm(name)` to its entry, for every title and alias, from one read of canon. Entries
        are visited in id order and the first claim on a name wins, as `find_by_name` finds."""
        index: dict[str, Entry] = {}
        for e in self.list_entries(world_id):  # sorted by id
            for name in [e.title, *e.aliases]:
                index.setdefault(norm(name), e)
        return index

    def find_by_name(self, world_id: str, name: str) -> Entry | None:
        return self.name_index(world_id).get(norm(name))

    def mentioned_in(self, world_id: str, text: str) -> list[Entry]:
        t = norm(text)
        return [
            e
            for e in self.list_entries(world_id)
            if any(_mentions(t, n) for n in [e.title, *e.aliases])
        ]

    def find_dependents(
        self, world_id: str, entry: Entry
    ) -> list[tuple[Entry, Literal["text", "link"]]]:
        """Entries that depend on `entry`: those whose body names it (title or alias) first, as
        "text", then those tied to it only by a link, as "link". A link may be secret (the
        Mayor's to the Choir), so the delete card names a "link" dependent only while the
        world shows secrets."""
        names = [entry.title, *entry.aliases]
        text: list[tuple[Entry, Literal["text", "link"]]] = []
        linked: list[tuple[Entry, Literal["text", "link"]]] = []
        for e in self.list_entries(world_id):
            if e.id == entry.id:
                continue
            body = norm(e.body)
            if any(_mentions(body, n) for n in names):
                text.append((e, "text"))
            elif any(link.target_id == entry.id for link in e.links):
                linked.append((e, "link"))
        return text + linked

    def find_mentions(self, world_id: str, entry: Entry) -> list[Entry]:
        """Entries whose body names `entry` (title or alias). Text only: a link alone, such as
        the Mayor's secret one to the Choir, is not a mention. Callers that need links too
        (the delete check) use `find_dependents`."""
        return [e for e, via in self.find_dependents(world_id, entry) if via == "text"]

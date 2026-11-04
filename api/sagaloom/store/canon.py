import re
from datetime import UTC, datetime

import chromadb
from langchain_core.embeddings import Embeddings

from sagaloom.models import Entry, SearchHit

_QUOTES = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"'})
MAX_K = 10


def norm(s: str) -> str:
    return " ".join(s.translate(_QUOTES).casefold().split())


class DuplicateTitleError(Exception):
    def __init__(self, title: str):
        super().__init__(f"An entry titled {title!r} already exists in this world")
        self.title = title


def _mentions(text_norm: str, name: str) -> bool:
    n = norm(name)
    return bool(n) and re.search(rf"(?<!\w){re.escape(n)}(?!\w)", text_norm) is not None


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
        self.col = client.get_or_create_collection(
            collection_name, metadata={"hnsw:space": "cosine"}
        )

    def next_entry_id(self) -> str:
        ids = self.col.get(include=[])["ids"]
        nums = [int(i[4:]) for i in ids if re.fullmatch(r"ent_\d{4}", i)]
        return f"ent_{max(nums, default=0) + 1:04d}"

    def get_entry(self, world_id: str, entry_id: str) -> Entry | None:
        res = self.col.get(
            ids=[entry_id], where={"world_id": world_id}, include=["metadatas"]
        )
        if not res["ids"]:
            return None
        return Entry.model_validate_json(res["metadatas"][0]["entry_json"])

    def list_entries(self, world_id: str) -> list[Entry]:
        res = self.col.get(where={"world_id": world_id}, include=["metadatas"])
        entries = [Entry.model_validate_json(m["entry_json"]) for m in res["metadatas"]]
        return sorted(entries, key=lambda e: e.id)

    def upsert_entry(self, entry: Entry) -> Entry:
        tn = norm(entry.title)
        clash = self.col.get(
            where=_and({"world_id": entry.world_id}, {"title_norm": tn}), include=[]
        )["ids"]
        if any(i != entry.id for i in clash):
            raise DuplicateTitleError(entry.title)
        existing = self.col.get(ids=[entry.id], include=["metadatas"])
        if existing["ids"]:
            prev = Entry.model_validate_json(existing["metadatas"][0]["entry_json"])
            if prev.world_id != entry.world_id:
                raise ValueError(f"Entry id {entry.id} belongs to another world")
        entry = entry.model_copy(update={"updated_at": datetime.now(UTC).isoformat()})
        doc = f"{entry.title}\n\n{entry.body}"
        self.col.upsert(
            ids=[entry.id],
            documents=[doc],
            embeddings=[self.embeddings.embed_documents([doc])[0]],
            metadatas=[
                {
                    "world_id": entry.world_id,
                    "type": entry.type,
                    "status": entry.status,
                    "title_norm": tn,
                    "entry_json": entry.model_dump_json(),
                }
            ],
        )
        return entry

    def delete_entry(self, world_id: str, entry_id: str) -> None:
        self.col.delete(ids=[entry_id], where={"world_id": world_id})

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
                    snippet=e.body[:200],
                    score=1 - dist,
                )
            )
        return sorted(hits, key=lambda h: h.score, reverse=True)

    def find_by_name(self, world_id: str, name: str) -> Entry | None:
        n = norm(name)
        for e in self.list_entries(world_id):
            if norm(e.title) == n or any(norm(a) == n for a in e.aliases):
                return e
        return None

    def mentioned_in(self, world_id: str, text: str) -> list[Entry]:
        t = norm(text)
        return [
            e
            for e in self.list_entries(world_id)
            if any(_mentions(t, n) for n in [e.title, *e.aliases])
        ]

    def find_mentions(self, world_id: str, entry: Entry) -> list[Entry]:
        names = [entry.title, *entry.aliases]
        out = []
        for e in self.list_entries(world_id):
            if e.id == entry.id:
                continue
            body = norm(e.body)
            if any(link.target_id == entry.id for link in e.links) or any(
                _mentions(body, n) for n in names
            ):
                out.append(e)
        return out

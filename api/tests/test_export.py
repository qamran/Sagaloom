"""Markdown export (R11.5.1, R11.5.2) and the read-only export_world tool."""

import io
import json
import re
import zipfile

import yaml

from sagaloom.export import entry_filename, export_markdown
from sagaloom.models import Entry, EntrySource, Fact, Link
from sagaloom.seed import VELMAR_ID, load_seed
from sagaloom.store.worlds import WorldRegistry
from sagaloom.tools.export import make_export_tool
from sagaloom.web.app import SEED_DIR

R2S = {
    "id", "world_id", "title", "type", "status", "source", "source_url", "licence", "trusted",
    "aliases", "links", "facts", "sources", "version", "created_at", "updated_at",
}


def entry(n=1, title="Ostra", **kw):
    return Entry(id=f"ent_{n:04d}", world_id="w", title=title, type="place", body="Body.", **kw)


def read_zip(data: bytes) -> dict[str, str]:
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        return {n: z.read(n).decode("utf-8") for n in z.namelist()}


def split(text: str):
    head, _, body = text[4:].partition("\n---\n")
    return yaml.safe_load(head), body


def test_export_one_file_per_entry_and_yaml_parses(store, tmp_path):
    n = load_seed(store, WorldRegistry(tmp_path / "w.json"), SEED_DIR)
    entries = store.list_entries(VELMAR_ID)
    files = read_zip(export_markdown(entries, exclude_secrets=False))
    assert len(files) == n == len(entries)
    by_id = {e.id: e for e in entries}
    for name, text in files.items():
        assert text.startswith("---\n")
        meta, body = split(text)
        assert set(meta) == R2S
        assert isinstance(meta["facts"], list) and all(isinstance(f, dict) for f in meta["facts"])
        e = by_id[meta["id"]]
        assert body.strip() == e.body.strip()
        assert meta["facts"] == [f.model_dump() for f in e.facts]


def test_exclude_secrets_strips_entries_and_facts():
    hidden = entry(1, "Vault", status="secret", facts=[Fact(key="loc", value="UNDER-THE-OAK")])
    mixed = entry(
        2, "Keep",
        facts=[Fact(key="a", value="public"), Fact(key="b", value="MURDERER-IS-MARA", status="secret")],
    )
    raw = export_markdown([hidden, mixed], exclude_secrets=True)
    files = read_zip(raw)
    assert len(files) == 1
    meta, _ = split(next(iter(files.values())))
    assert [f["key"] for f in meta["facts"]] == ["a"]
    blob = b"".join(zipfile.ZipFile(io.BytesIO(raw)).read(n) for n in files) + b"".join(
        n.encode() for n in files
    )
    for leak in (b"UNDER-THE-OAK", b"MURDERER-IS-MARA", b"Vault"):
        assert leak not in blob
    # Without the flag everything is exported.
    assert len(read_zip(export_markdown([hidden, mixed], exclude_secrets=False))) == 2


def test_export_filenames_unique_and_safe():
    es = [entry(1, "Ister: North"), entry(2, "Ister / North"), entry(3, "Café *?\"<>|")]
    names = list(read_zip(export_markdown(es, exclude_secrets=False)))
    assert len(set(names)) == 3
    for n in names:
        assert not set('/:*?"<>|') & set(n)
        assert re.fullmatch(r"ent_\d{4}-[a-z0-9-]+\.md", n), n
    taken = {"ent_0001-ister-north.md"}
    assert entry_filename(entry(1, "Ister: North"), taken) != "ent_0001-ister-north.md"
    assert re.fullmatch(r"ent_\d{4}-[a-z0-9-]+\.md", entry_filename(entry(4, "???"), set()))


async def test_export_world_tool_is_read_only(store):
    store.upsert_entry(entry(1, "Ostra"))
    store.upsert_entry(entry(2, "Vault", status="secret"))
    before = store.list_entries("w")
    tool = make_export_tool(store)
    assert tool.name == "export_world"
    assert "world_id" not in tool.tool_call_schema.model_json_schema()["properties"]
    out = json.loads(await tool.ainvoke({"world_id": "w"}))
    assert out["download"] == "/api/proxy/worlds/w/export?format=md"
    out = json.loads(await tool.ainvoke({"world_id": "w", "exclude_secrets": True}))
    assert out["download"] == "/api/proxy/worlds/w/export?format=md&exclude_secrets=true"
    assert store.list_entries("w") == before


async def test_export_world_count_excludes_secret_entries(store):
    """The count never reveals how many secret entries exist (Wave 2 Fable M1)."""
    store.upsert_entry(entry(1, "Ostra"))
    store.upsert_entry(entry(2, "Vault", status="secret"))
    store.upsert_entry(entry(3, "Keep"))
    tool = make_export_tool(store)
    for exclude in (False, True):
        out = json.loads(await tool.ainvoke({"world_id": "w", "exclude_secrets": exclude}))
        assert out["entries"] == 2
        assert out["secrets_included"] is (not exclude)


def test_exclude_secrets_scrubs_references_to_secret_entries():
    secret = entry(1, "Heir", status="secret")
    keep = entry(
        2, "Throne",
        links=[Link(target_id="ent_0001", relation="secret heir of"), Link(target_id="ent_0003", relation="near")],
        facts=[Fact(key="ruler", value="Mara", refs=["ent_0001", "ent_0003"], told_by="ent_0001")],
    )
    raw = export_markdown([secret, keep], exclude_secrets=True)
    files = read_zip(raw)
    blob = "\n".join(files) + "\n".join(files.values())
    assert "ent_0001" not in blob and "secret heir of" not in blob
    meta, _ = split(next(iter(files.values())))
    assert meta["links"] == [{"target_id": "ent_0003", "relation": "near"}]
    assert meta["facts"][0]["refs"] == ["ent_0003"] and meta["facts"][0]["told_by"] is None
    full = read_zip(export_markdown([secret, keep], exclude_secrets=False))
    assert "secret heir of" in "\n".join(full.values())


def test_front_matter_round_trips_adversarial_text():
    e = entry(
        1, "a: b", aliases=["--- x"], facts=[Fact(key="k", value="x\n---\nevil: 1")]
    )
    text = next(iter(read_zip(export_markdown([e], exclude_secrets=False)).values()))
    meta, body = split(text)
    assert "evil" not in meta
    assert meta["title"] == "a: b" and meta["aliases"] == ["--- x"]
    assert meta["facts"][0]["value"] == "x\n---\nevil: 1"
    assert body.strip() == "Body."


# ---------- ATTRIBUTION.md (R-W3) ----------

WP = "https://en.wikipedia.org/wiki/Gandalf"
FD = "https://lotr.fandom.com/wiki/Gandalf"


def test_attribution_lists_every_source_with_licence():
    e = entry(
        1, "Gandalf", source="official", trusted=False,
        sources=[
            EntrySource(
                kind="official", url=FD, licence="CC BY-NC-SA 3.0",
                licence_url="https://creativecommons.org/licenses/by-nc-sa/3.0/", nc=True,
            ),
            EntrySource(kind="reference", url=WP, licence=None),
        ],
    )
    files = read_zip(export_markdown([e, entry(2, "Plain")], exclude_secrets=False))
    text = files["ATTRIBUTION.md"]
    assert text.startswith("# Attribution\n")
    assert "## Gandalf (ent_0001)" in text and "Plain" not in text
    assert (
        f"- official: {FD} · CC BY-NC-SA 3.0 "
        "[https://creativecommons.org/licenses/by-nc-sa/3.0/] · NC"
    ) in text
    assert f"- reference: {WP} · licence not reported" in text
    assert "## Share-alike" in text
    assert "## Non-commercial content" in text
    assert "This content can't be used commercially." in text
    assert text.index("## Share-alike") < text.index("## Non-commercial content")


def test_no_attribution_without_sources():
    files = read_zip(export_markdown([entry(1), entry(2, "Keep")], exclude_secrets=False))
    assert "ATTRIBUTION.md" not in files


def test_attribution_respects_leave_out_secrets():
    src = [EntrySource(kind="official", url=FD, licence="CC BY-SA 3.0")]
    secret = entry(1, "Hidden Vault", status="secret", trusted=False, sources=src)
    plain = entry(2, "Keep")
    files = read_zip(export_markdown([secret, plain], exclude_secrets=True))
    assert "ATTRIBUTION.md" not in files
    assert not any("Hidden Vault" in t for t in files.values())

    public = entry(3, "Shire", trusted=False, sources=[EntrySource(kind="official", url=WP)])
    files = read_zip(export_markdown([secret, public], exclude_secrets=True))
    text = files["ATTRIBUTION.md"]
    assert "## Shire (ent_0003)" in text and "Hidden Vault" not in text and FD not in text
    assert "## Non-commercial content" not in text
    full = read_zip(export_markdown([secret, public], exclude_secrets=False))["ATTRIBUTION.md"]
    assert "## Hidden Vault (ent_0001)" in full

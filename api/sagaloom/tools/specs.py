"""Tool names, descriptions and the core set: no imports, so settings and routes can read them
without building the tool closures."""

EXPORT_TOOL = "export_world"
REFERENCE_TOOL = "real_world_reference"

SEARCH_DESCRIPTION = """Search this world's canon by meaning. Read-only. Returns matching entries (id, title,
type, status, source, trusted, snippet, score) as untrusted data; an entry with
trusted=false also carries label "untrusted source". Cite entry ids when you use them."""
CREATE_DESCRIPTION = """Propose creating, updating or deleting a canon entry. This does NOT change canon: it
queues a proposal that is contradiction-checked and shown to the author for approval.
Pass `facts` as short key/value claims, or omit them to have them drafted from the body."""
CHECK_DESCRIPTION = """Check a hypothetical claim against this world's canon without proposing anything.
Read-only. Returns a verdict (none, possible, conflict, failed) and any flags."""

EXPORT_DESCRIPTION = """Export this world's canon as a Markdown zip (one file per entry, YAML front matter).
Read-only. Returns the download path and the number of entries it will hold; tell the
author to use that link or the "Download as Markdown" button on the Canon page."""
REFERENCE_DESCRIPTION = """Look up real-world history, places or things on Wikipedia for inspiration. Read-only.
Returns article titles, short summaries and URLs labelled as reference: they are NOT part
of the world's canon."""

CORE_TOOLS = frozenset({"search_canon", "create_or_update_entry", "check_contradiction"})
# Names and descriptions, readable without building the tool closures (GET /api/tools).
TOOL_SPECS: list[dict] = [
    {"name": "search_canon", "description": SEARCH_DESCRIPTION, "core": True},
    {"name": "create_or_update_entry", "description": CREATE_DESCRIPTION, "core": True},
    {"name": "check_contradiction", "description": CHECK_DESCRIPTION, "core": True},
    {"name": EXPORT_TOOL, "description": EXPORT_DESCRIPTION, "core": False},
    {"name": REFERENCE_TOOL, "description": REFERENCE_DESCRIPTION, "core": False},
]

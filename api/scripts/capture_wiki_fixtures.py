"""Capture the three demo Wikipedia pages and the site licence as committed test fixtures.

This is the one place real Wikipedia requests are made for tests: 4 throttled requests through
`WikiClient` (honest User-Agent, no LLM). Run it once, review the diff, and commit the output.

    cd api && uv run python scripts/capture_wiki_fixtures.py tests/fixtures/wiki
"""

import asyncio
import json
import sys
from pathlib import Path

from sagaloom.wiki.client import WikiClient
from sagaloom.wiki.pages import parse_page_url, parse_request_url

PAGES = [
    "https://en.wikipedia.org/wiki/Rivendell",
    "https://en.wikipedia.org/wiki/Gandalf",
    "https://en.wikipedia.org/wiki/Shire_(Middle-earth)",
]
HOST = "en.wikipedia.org"


async def capture(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    client = WikiClient(out_dir)
    try:
        entries = []
        for raw in PAGES:
            page = parse_page_url(raw)
            fetched = await client.fetch_page(page)
            entries.append(
                {
                    "in": raw,
                    "title": fetched.title,
                    "url": fetched.url,
                    "revid": fetched.revid,
                    "parse_request": parse_request_url(page),
                }
            )
        licence = await client.site_licence(HOST)
    finally:
        await client.aclose()
    manifest = {"licence": licence.model_dump(), "pages": entries}
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    lines = [
        "# Wikipedia fixtures",
        "",
        "These files are Wikipedia content committed as test fixtures under the licence below.",
        "",
        f"Licence: {licence.text or 'licence not reported'}",
        f"Licence URL: {licence.url or 'licence not reported'}",
        "",
        "Pages:",
        "",
    ]
    for e in entries:
        revision = e["revid"] if e["revid"] is not None else "not reported"
        requested = f", requested as {e['in']}" if e["in"] != e["url"] else ""
        lines.append(f"- {e['title']}: {e['url']} (revision id {revision}{requested})")
    (out_dir / "ATTRIBUTION.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(capture(Path(sys.argv[1] if len(sys.argv) > 1 else "tests/fixtures/wiki")))

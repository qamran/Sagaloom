"""The one opt-in network test of the MediaWiki client (`-m live`; run in Task 9 only)."""

import pytest

from sagaloom.wiki.client import WikiClient
from sagaloom.wiki.pages import parse_page_url


@pytest.mark.live
async def test_live_wikipedia_page_and_licence(tmp_path):
    client = WikiClient(tmp_path / "cache")
    try:
        fetched = await client.fetch_page(parse_page_url("https://en.wikipedia.org/wiki/Rivendell"))
        assert "Rivendell" in fetched.wikitext
        licence = await client.site_licence("en.wikipedia.org")
        assert licence.text
    finally:
        await client.aclose()

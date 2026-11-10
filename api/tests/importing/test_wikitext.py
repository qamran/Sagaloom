"""Wikitext stripping (M3 design §5.4), on the committed Wikipedia fixtures and small snippets."""

import json
from pathlib import Path

import pytest

from sagaloom.importing.wikitext import strip_wikitext, type_from_infobox
from sagaloom.wiki.client import WikiClient
from sagaloom.wiki.pages import parse_page_url, parse_request_url

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "wiki"
GANDALF = "https://en.wikipedia.org/wiki/Gandalf"
RIVENDELL = "https://en.wikipedia.org/wiki/Rivendell"
SHIRE = "https://en.wikipedia.org/wiki/Shire_(Middle-earth)"

# A sentence from each page's lead, copied from the committed fixture.
LEAD_SENTENCES = {
    GANDALF: "He is a wizard, one of the Istari order, and the leader of the Company of the Ring.",
    RIVENDELL: "It is an important location in The Hobbit and The Lord of the Rings, "
    "being the place where the quest to destroy the One Ring begins.",
    SHIRE: "The Shire is an inland area settled exclusively by hobbits, the Shire-folk, "
    "largely sheltered from the goings-on in the rest of Middle-earth.",
}


def wikitext_of(url: str, tmp_path: Path) -> str:
    path = WikiClient(tmp_path)._cache_path(parse_request_url(parse_page_url(url)))
    return json.loads((FIXTURES / path.name).read_text(encoding="utf-8"))["body"]["parse"]["wikitext"]


@pytest.fixture(params=[GANDALF, RIVENDELL, SHIRE])
def page_url(request):
    return request.param


def test_strip_removes_markup(page_url, tmp_path):
    text = strip_wikitext(wikitext_of(page_url, tmp_path)).text
    for leftover in ("{{", "}}", "<ref", "[[", "]]", "{|", "'''", "<!--"):
        assert leftover not in text


def test_strip_removes_every_listed_construct():
    raw = (
        "__NOTOC__\nA<ref name=a>cite {{cite web|url=x}}</ref>b<ref name=b/>c<!-- hidden -->d "
        "<gallery>\nFile:A.jpg|x\n</gallery><math>x^2</math>e\n"
        "{| class=wikitable\n| cell {{t}}\n{|\n| inner\n|}\n|}\n"
        "[[File:A.jpg|thumb|A [[Link|label]] caption]]f [[Category:Things]][[Image:B.png]]\n"
        "'''bold''' and ''italic''."
    )
    assert strip_wikitext(raw).text == "Abcd e\nf\nbold and italic."


def test_strip_keeps_link_text_and_headings():
    raw = "[[Elrond|the Lord]] lives in [[Rivendell]].\n== History ==\nOld."
    assert strip_wikitext(raw).text == "the Lord lives in Rivendell.\nHistory\nOld."


def test_strip_external_links_and_lists():
    raw = "See [https://example.org the site] and [https://example.org/x].\n* one\n** two\n# three"
    assert strip_wikitext(raw).text == "See the site and.\none\ntwo\nthree"


def test_whitespace_is_stable():
    raw = "A  b   \n\n\n\n{{gone}}\n\n\nC\t d  \n"
    out = strip_wikitext(raw).text
    assert out == "A b\n\nC d"
    assert strip_wikitext(out).text == out


def test_infobox_captured_and_leads_text(tmp_path):
    page = strip_wikitext(wikitext_of(GANDALF, tmp_path))
    assert page.infobox_name is not None
    assert page.infobox_name.startswith("Infobox")
    assert page.infobox["name"] == "Gandalf"
    lines = [f"{k.replace('_', ' ').title()}: {v}" for k, v in page.infobox.items() if v]
    assert page.text.startswith("\n".join(lines) + "\n\n")


def test_infobox_inline_values_and_order():
    raw = (
        "{{Infobox person\n| alt_name = ''A''<br/>[[B|b]]\n| empty =\n| born = {{birth date|1892|1|3}}\n"
        "| image = <!-- no -->x.jpg\n}}\nProse."
    )
    page = strip_wikitext(raw)
    assert page.infobox_name == "Infobox person"
    assert page.infobox == {"alt_name": "A, b", "empty": "", "born": "", "image": "x.jpg"}
    assert page.text == "Alt Name: A, b\nImage: x.jpg\n\nProse."


def test_only_the_first_infobox_is_captured():
    page = strip_wikitext("{{Infobox a|x=1}}{{Infobox b|y=2}}")
    assert (page.infobox_name, page.infobox) == ("Infobox a", {"x": "1"})
    assert page.text == "X: 1"


def test_type_from_infobox(tmp_path):
    names = {
        url: strip_wikitext(wikitext_of(url, tmp_path)).infobox_name for url in (GANDALF, RIVENDELL, SHIRE)
    }
    assert type_from_infobox(names[GANDALF]) == "character"
    assert type_from_infobox(names[RIVENDELL]) == "place"
    assert type_from_infobox(names[SHIRE]) == "place"
    assert type_from_infobox(None) is None
    assert type_from_infobox("Infobox book") is None


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Infobox deity", "character"),
        ("Infobox settlement", "place"),
        ("Infobox company", "faction"),
        ("Infobox military unit", "faction"),
        ("Infobox weapon", "item"),
        ("Infobox military conflict battle", "event"),
        ("Infobox war", "event"),
        ("Infobox person place", "character"),  # earlier rules win
    ],
)
def test_type_from_infobox_rules(name, expected):
    assert type_from_infobox(name) == expected


def test_lead_end_marks_first_heading():
    page = strip_wikitext("{{Infobox x|a=b}}\nLead.\n\n== One ==\nBody\n=== Two ===\nMore")
    assert page.text == "A: b\n\nLead.\n\nOne\nBody\nTwo\nMore"
    assert page.text[page.lead_end :].startswith("One\n")
    assert page.text[: page.lead_end].endswith("Lead.\n\n")
    assert strip_wikitext("No headings.").lead_end == len("No headings.")


def test_lead_end_on_fixtures(page_url, tmp_path):
    page = strip_wikitext(wikitext_of(page_url, tmp_path))
    assert 0 < page.lead_end < len(page.text)
    assert LEAD_SENTENCES[page_url] in page.text[: page.lead_end]
    assert page.text[page.lead_end - 2 : page.lead_end] == "\n\n"
    assert page.text[page.lead_end] != "\n"


def test_lead_sentence_survives_verbatim(page_url, tmp_path):
    assert LEAD_SENTENCES[page_url] in strip_wikitext(wikitext_of(page_url, tmp_path)).text


def test_template_only_page_strips_to_empty_prose():
    page = strip_wikitext("{{Disambiguation}}")
    assert page.text == ""
    assert page.infobox_name is None
    assert page.lead_end == 0


def test_unbalanced_braces_do_not_hang_or_eat_text():
    assert strip_wikitext("a {{b c").text == "a b c"


def test_one_line_table_is_dropped_and_the_rest_survives():
    assert strip_wikitext("Before\n{| class=x | a |}\nAfter").text == "Before\nAfter"


def test_unclosed_table_drops_only_its_opener():
    assert strip_wikitext("Before\n{| class=x\n| a\nAfter").text == "Before\n| a\nAfter"


def test_nested_one_line_table_inside_a_table():
    assert strip_wikitext("A\n{|\n{| x |}\n|-\n|}\nB").text == "A\nB"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("A\n\n== {{anchor}} ==\n\nB", "A\n\nB"),
        ("A\n== {{anchor}} ==", "A"),
        ("A\n==[[File:x.jpg]]==\nB", "A\n\nB"),
    ],
)
def test_empty_heading_leaves_no_extra_blank_lines(raw, expected):
    assert strip_wikitext(raw).text == expected


@pytest.mark.parametrize(
    "raw",
    [
        "A\n\n== {{anchor}} ==\n\nB",
        "A\n== {{anchor}} ==",
        "Rivendell () is a valley , with ( ) gaps .\n\n== One ==\n\n\nBody ;  x",
        "{{Infobox x|a=b ( )}}\n\n\nLead .\n== H ==\nT",
    ],
)
def test_stripping_twice_gives_the_same_text(raw):
    once = strip_wikitext(raw).text
    assert strip_wikitext(once).text == once


def test_stripping_twice_is_stable_on_fixtures(page_url, tmp_path):
    once = strip_wikitext(wikitext_of(page_url, tmp_path)).text
    assert strip_wikitext(once).text == once


def test_entities_are_unescaped_before_quote_runs():
    assert strip_wikitext("&#39;&#39;&#39;x&#39;&#39;&#39; &amp; y").text == "x & y"


def test_non_http_external_links_keep_their_text():
    raw = "[mailto:a@b.c mail me] and [ftp://h/f the file] and [//h/p proto]"
    assert strip_wikitext(raw).text == "mail me and the file and proto"


def test_space_before_punctuation_and_empty_parentheses_are_tidied():
    raw = "Rivendell {{IPA|x}} ({{IPA|y}}) is a valley{{efn|n}} . It has a ref<ref>r</ref> , and more ; yes : no"
    assert strip_wikitext(raw).text == "Rivendell is a valley. It has a ref, and more; yes: no"

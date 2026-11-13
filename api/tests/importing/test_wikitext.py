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


@pytest.mark.parametrize("closer", ["|}{{clear}}", "|}</div>"])
def test_table_closed_with_a_trailing_token_is_dropped(closer):
    """Fandom often closes a table with a token after `|}`: the rows must not leak (M4)."""
    raw = "Before\n{| class=wikitable\n| secret cell\n|-\n| other cell\n" + closer + "\nAfter the table."
    text = strip_wikitext(raw).text
    assert "cell" not in text
    assert text.startswith("Before") and text.endswith("After the table.")


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


# ---------- article templates (Fandom wikis such as the Marvel Database) ----------

MARVEL_STYLE = """{{Marvel Database:Organization Template
| Image                   = Team.jpg
| Name                    = 50-State Initiative
| Identity                = Public
| FormerMembers           = {{Navigation | body = [[A]], [[B]]}}
| Quotation               = We train heroes.
| History                 =
===[[Anthony Stark (Earth-616)|Tony Stark]]'s Initiative===
====Formation====
In the aftermath of the [[Civil War]], the Initiative was launched.{{r|Avengers: The Initiative Vol 1 1}}

It trained young heroes at Camp Hammond.
===Later years===
Norman Osborn took it over.
| Notes                   = A note.
}}
[[Category:Teams]]"""


def test_article_template_is_read_as_the_article():
    s = strip_wikitext(MARVEL_STYLE)
    assert s.infobox_name == "Marvel Database:Organization Template"
    assert type_from_infobox(s.infobox_name) == "faction"
    # Short fields are the fact lines; pictures, quotes, member lists and notes are not.
    assert s.infobox == {"Name": "50-State Initiative", "Identity": "Public"}
    lead = s.text[: s.lead_end]
    assert lead.startswith("Name: 50-State Initiative\nIdentity: Public\n\n")
    # History's opening headings are dropped, and the lead is its first section.
    assert "In the aftermath of the Civil War, the Initiative was launched." in lead
    assert "It trained young heroes at Camp Hammond." in lead
    assert "Norman Osborn" not in lead and "Norman Osborn took it over." in s.text
    for leftover in ("{{", "[[", "Team.jpg", "We train heroes", "A note"):
        assert leftover not in s.text


def test_article_template_prefers_overview_and_names_camel_case_fields():
    s = strip_wikitext(
        "{{Marvel Database:Item Template\n| CauseOfDeath = None\n| Overview = A hammer of uru.\n"
        "| History = ===Forging===\nForged in a star.\n}}"
    )
    assert s.infobox == {"Cause Of Death": "None"}
    assert s.text[: s.lead_end].rstrip() == "Cause Of Death: None\n\nA hammer of uru."
    assert "Forged in a star." in s.text


def test_long_article_template_lead_is_cut_at_a_paragraph():
    para = "word " * 300  # 1,500 characters
    s = strip_wikitext("{{Marvel Database:Character Template\n| History = " + "\n\n".join([para] * 6) + "\n}}")
    lead = s.text[: s.lead_end]
    assert len(lead) <= 6_000 and lead.endswith("word")


def test_a_page_with_an_infobox_ignores_article_templates():
    s = strip_wikitext("{{Infobox character | name = Gandalf}}\n{{Some Wiki:Character Template | History = Hidden.}}\nGandalf is a wizard.")
    assert s.infobox_name == "Infobox character"
    assert "Hidden." not in s.text
    assert "Gandalf is a wizard." in s.text


def test_a_plain_template_is_not_an_article_template():
    assert strip_wikitext("{{Disambiguation | group1 = Asgard (Earth-616)}}").text == ""


# The Game of Thrones Wiki's shape: a bare-named fact box ({{Character}}, {{House}}, …) after
# other templates, with deceased people in single braces and {{Ref}}s inside the values.
GOT_STYLE = """{{Canonicity|Canon}}
{{Heraldry
| Image = House Targaryen.svg
| Link  = House Targaryen
}}
{{Character
| Title       = {{PAGENAME}}
| Image       =
<gallery>
Rhaenyra 308.png|Adult
</gallery>
| Birth       = [[97 AC]]{{Dateref|Rhaenyra Targaryen}} (age 35)
| House       = [[House Targaryen/House of the Dragon|Targaryen]]{{Ref|HOTD101}}
| Father      = {[[Viserys I Targaryen]]}{{Ref|HOTD101}}
| Spouse      = [[Laenor Velaryon]]{{Ref|HOTD105}} {{C|separated}}<br>[[Daemon Targaryen]]
}}
{{Quote|Speaker|A line.}}
'''Princess Rhaenyra Targaryen''' is the eldest child of [[Viserys I Targaryen|King Viserys I]].

==Biography==
Later text.
"""


def test_bare_named_fact_box_is_read_as_an_infobox():
    s = strip_wikitext(GOT_STYLE)
    assert s.infobox_name == "Character"
    assert s.text[: s.lead_end].rstrip() == (
        "Birth: 97 AC (age 35)\n"
        "House: Targaryen\n"
        "Father: Viserys I Targaryen\n"
        "Spouse: Laenor Velaryon, Daemon Targaryen\n\n"
        "Princess Rhaenyra Targaryen is the eldest child of King Viserys I."
    )
    assert type_from_infobox(s.infobox_name) == "character"


@pytest.mark.parametrize(
    ("name", "expected"),
    [("House", "faction"), ("Settlement", "place"), ("Organization", "faction"),
     ("Government", "faction"), ("Location", "place"), ("Character", "character")],
)
def test_bare_fact_box_types(name, expected):
    s = strip_wikitext(f"{{{{{name}\n| Name = X\n| Image = {{{{Arms}}}}.svg\n}}}}\nX is here.\n")
    assert s.infobox_name == name
    assert s.infobox == {"Name": "X"}  # a picture is not a fact
    assert type_from_infobox(s.infobox_name) == expected


def test_heraldry_and_other_templates_are_not_fact_boxes():
    s = strip_wikitext("{{Heraldry\n| Image = A.svg\n}}\n{{Quote|S|Q}}\nPlain prose.\n")
    assert s.infobox_name is None
    assert s.text == "Plain prose."


def test_an_infobox_template_still_wins_over_a_later_bare_fact_box():
    s = strip_wikitext("{{Infobox character\n| name = A\n}}\n{{Character\n| Birth = 1\n}}\nProse.\n")
    assert s.infobox_name == "Infobox character"
    assert s.infobox == {"name": "A"}

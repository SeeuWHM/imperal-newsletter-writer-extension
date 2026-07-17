"""richtext.py — plain-text/markdown <-> HTML round trip for the panel's
single merged RichEditor. A newsletter is a plain heading+content document,
exactly like an Article Writer article (no block types, no markers).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from richtext import sections_to_html, html_to_sections, to_html, from_html, to_export_text


def test_sections_to_html_text_block_with_heading():
    sections = [{"order_index": 0, "heading": "Welcome", "content": "Hi **there**!"}]
    assert sections_to_html(sections) == "<h2>Welcome</h2><p>Hi <strong>there</strong>!</p>"


def test_to_html_merges_adjacent_bullets_into_one_list():
    text = "- one\n\n- two\n\n- three"
    assert to_html(text) == "<ul><li>one</li><li>two</li><li>three</li></ul>"


def test_to_html_link_and_italic():
    assert to_html("See [our site](https://x.com) *now*") == (
        '<p>See <a href="https://x.com">our site</a> <em>now</em></p>'
    )


def test_from_html_round_trips_prose_list_and_link():
    html = (
        '<p>Hey <strong>there</strong>!</p>'
        '<p>Check <a href="https://example.com">our site</a> out.</p>'
        '<ul><li>one</li><li>two</li></ul>'
    )
    text = from_html(html)
    assert "Hey **there**!" in text
    assert "Check [our site](https://example.com) out." in text
    assert "- one\n- two" in text


def test_html_to_sections_round_trips_headings_and_body():
    original = [
        {"order_index": 0, "heading": "Welcome",
         "content": "Hey **there**!\n\nCheck [our site](https://example.com) out."},
        {"order_index": 1, "heading": "Details", "content": "- item one\n- item two"},
    ]
    html = sections_to_html(original)
    decoded = html_to_sections(html)

    assert [s["heading"] for s in decoded] == ["Welcome", "Details"]
    assert "Check [our site](https://example.com) out." in decoded[0]["content"]
    assert decoded[1]["content"] == "- item one\n- item two"


def test_html_to_sections_leading_body_before_first_heading():
    html = "<p>Intro with no heading.</p><h2>Body</h2><p>Section body.</p>"
    decoded = html_to_sections(html)
    assert decoded[0]["heading"] is None
    assert decoded[0]["content"] == "Intro with no heading."
    assert decoded[1]["heading"] == "Body"


def test_html_to_sections_ignores_empty_document():
    assert html_to_sections("") == []
    assert html_to_sections("   ") == []


def test_html_to_sections_empty_paragraph_is_one_empty_section():
    # TipTap emits "<p></p>" for a truly-empty editor — same behavior as
    # Article Writer's html_to_sections (mirrored 1:1): one empty section.
    assert html_to_sections("<p></p>") == [{"heading": None, "content": ""}]


def test_sections_to_html_empty_list():
    assert sections_to_html([]) == ""


def test_to_export_text_strips_markdown_and_underlines_headings():
    sections = [{"heading": "Sale", "content": "Get **50%** off\n\n- fast\n- easy"}]
    out = to_export_text(sections)
    assert "SALE\n----" in out
    assert "Get 50% off" in out
    assert "• fast" in out

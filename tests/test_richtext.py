"""richtext.py — plain-text/markdown <-> HTML round trip for the panel's
single merged RichEditor. A newsletter is a plain heading+content document,
exactly like an Article Writer article (no block types, no markers).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from richtext import (
    sections_to_html, html_to_sections, to_html, from_html, to_export_text,
    document_to_html, html_to_document, document_to_markdown, markdown_to_document,
)


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


def test_document_to_html_puts_subject_as_leading_h1():
    sections = [{"heading": "Intro", "content": "Hello."}]
    html = document_to_html("Big Sale", sections)
    assert html == "<h1>Big Sale</h1><h2>Intro</h2><p>Hello.</p>"


def test_document_to_html_no_subject_is_body_only():
    assert document_to_html("", [{"heading": None, "content": "Hi."}]) == "<p>Hi.</p>"


def test_html_to_document_extracts_subject_and_sections():
    html = "<h1>Big Sale</h1><h2>Intro</h2><p>Hello **there**.</p><h2>Offer</h2><p>Grab it.</p>"
    subject, sections = html_to_document(html)
    assert subject == "Big Sale"
    assert [s["heading"] for s in sections] == ["Intro", "Offer"]
    assert sections[0]["content"] == "Hello **there**."


def test_html_to_document_round_trips_with_document_to_html():
    subject = "Welcome aboard"
    sections = [
        {"heading": "Hi", "content": "Thanks for joining."},
        {"heading": "Next", "content": "- step one\n- step two"},
    ]
    subj2, sec2 = html_to_document(document_to_html(subject, sections))
    assert subj2 == subject
    assert [s["heading"] for s in sec2] == ["Hi", "Next"]
    assert sec2[1]["content"] == "- step one\n- step two"


def test_html_to_document_no_h1_yields_empty_subject():
    # No leading <h1> — caller keeps the existing subject rather than blank it.
    subject, sections = html_to_document("<h2>Body</h2><p>Text.</p>")
    assert subject == ""
    assert sections[0]["heading"] == "Body"


def test_markdown_document_round_trip():
    # Realistic shape: every section has a heading (generation always emits one)
    # -> exact round trip.
    subject = "Spring Sale"
    sections = [
        {"heading": "Intro", "content": "Hello **there**.\n\nSecond paragraph."},
        {"heading": "Offer", "content": "- point one\n- point two"},
    ]
    md = document_to_markdown(subject, sections)
    assert md.startswith("# Spring Sale")
    assert "## Intro" in md and "## Offer" in md
    subj2, sec2 = markdown_to_document(md)
    assert subj2 == subject
    assert sec2 == sections


def test_markdown_round_trip_with_leading_headingless_section():
    subject = "Hi"
    sections = [
        {"heading": None, "content": "Intro before any heading."},
        {"heading": "Body", "content": "Section body."},
    ]
    subj2, sec2 = markdown_to_document(document_to_markdown(subject, sections))
    assert subj2 == subject
    assert sec2 == sections


def test_markdown_to_document_no_h1_keeps_subject_empty():
    subj, sections = markdown_to_document("## Body\n\nJust text.")
    assert subj == ""
    assert sections == [{"heading": "Body", "content": "Just text."}]

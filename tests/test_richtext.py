"""richtext.py — plain-fields <-> HTML round trip for the panel's single
merged RichEditor. Newsletter blocks add button/image/divider marker-link
encoding on top of Article Writer's plain heading+content contract — those
cases are the focus here (base markdown conversions mirror Article Writer's
own test_richtext.py 1:1 in spirit).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from richtext import sections_to_html, html_to_sections


def test_sections_to_html_text_block_with_heading():
    sections = [{"order_index": 0, "block_type": "text", "heading": "Welcome", "content": "Hi **there**!"}]
    assert sections_to_html(sections) == "<h2>Welcome</h2><p>Hi <strong>there</strong>!</p>"


def test_sections_to_html_button_block_is_a_real_link():
    sections = [{"order_index": 0, "block_type": "button", "heading": None,
                 "button_label": "Get 50% off", "button_url": "https://x.com/promo"}]
    html = sections_to_html(sections)
    assert '<a href="https://x.com/promo">Get 50% off</a>' in html
    assert "\U0001F518" in html  # 🔘 marker present


def test_sections_to_html_image_block_is_a_real_link():
    sections = [{"order_index": 0, "block_type": "image", "heading": None,
                 "image_alt": "A nice picture", "image_url": "https://x.com/pic.png"}]
    html = sections_to_html(sections)
    assert '<a href="https://x.com/pic.png">A nice picture</a>' in html
    assert "\U0001F5BC" in html  # 🖼️ marker present


def test_sections_to_html_divider_block():
    sections = [{"order_index": 0, "block_type": "divider", "heading": None}]
    assert "divider" in sections_to_html(sections)


def test_html_to_sections_round_trips_all_four_block_types():
    original = [
        {"order_index": 0, "block_type": "text", "heading": "Welcome",
         "content": "Hey **there**!\n\nCheck [our site](https://example.com) out."},
        {"order_index": 1, "block_type": "button", "heading": None,
         "button_label": "Get 50% off", "button_url": "https://example.com/promo"},
        {"order_index": 2, "block_type": "divider", "heading": None},
        {"order_index": 3, "block_type": "image", "heading": "Look at this",
         "image_url": "https://example.com/pic.png", "image_alt": "A nice picture"},
        {"order_index": 4, "block_type": "text", "heading": None, "content": "- item one\n- item two"},
    ]
    html = sections_to_html(original)
    decoded = html_to_sections(html)

    assert [b["block_type"] for b in decoded] == ["text", "button", "divider", "image", "text"]
    assert decoded[0]["heading"] == "Welcome"
    assert "Check [our site](https://example.com) out." in decoded[0]["content"]
    assert decoded[1]["button_label"] == "Get 50% off"
    assert decoded[1]["button_url"] == "https://example.com/promo"
    assert decoded[3]["heading"] == "Look at this"
    assert decoded[3]["image_alt"] == "A nice picture"
    assert decoded[3]["image_url"] == "https://example.com/pic.png"
    assert decoded[4]["content"] == "- item one\n- item two"


def test_html_to_sections_splits_multiple_blocks_under_one_heading():
    """A heading's following content may contain several distinct blocks —
    plain text, then a button, then trailing text with no heading of its
    own. Each must become its own separate block, never merged."""
    html = (
        "<h2>Mixed section</h2><p>Some intro text.</p>"
        "<p>\U0001F518 <a href=\"https://example.com/buy\">Buy now</a></p>"
        "<p>Trailing note after the button, no heading.</p>"
    )
    decoded = html_to_sections(html)
    assert [b["block_type"] for b in decoded] == ["text", "button", "text"]
    assert decoded[0]["heading"] == "Mixed section"
    assert decoded[1]["button_url"] == "https://example.com/buy"
    assert decoded[2]["heading"] is None
    assert decoded[2]["content"] == "Trailing note after the button, no heading."


def test_html_to_sections_ignores_empty_document():
    assert html_to_sections("") == []
    assert html_to_sections("<p></p>") == []


def test_sections_to_html_empty_list():
    assert sections_to_html([]) == ""

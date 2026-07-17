"""Plain-fields <-> HTML conversion for the panel's single merged RichEditor.

Unlike Article Writer's articles (plain heading+content sections only),
a newsletter block has a block_type (text/button/image/divider) with distinct
fields per kind. TipTap's confirmed-safe schema for this component instance
is paragraphs, h1/h2/h3 headings, bold/italic, lists and <a href> links (see
article-writer-extension/richtext.py's "Known SDK/frontend gap" note — custom
tags/data-attributes are NOT guaranteed to survive a save round-trip). So
non-text blocks are encoded as an ordinary paragraph containing a real,
clickable <a href> link prefixed with a distinctive emoji marker — this is
both 100% safe against the editor's schema AND directly readable/editable by
a human (a real link they can click or retarget), not invisible markup.

Markers (never legitimate body text, so detection on decode is unambiguous):
  🔘 <button label>   -> button block  (link href = button_url)
  🖼️ <image alt text>  -> image block   (link href = image_url)
  ▬▬▬ divider ▬▬▬      -> divider block (own paragraph, no link)
"""
from __future__ import annotations

import re

_BOLD = re.compile(r"\*\*(.+?)\*\*")
_ITALIC = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)")
_LINK_MD = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_HTML_STRONG = re.compile(r"<(?:strong|b)>(.*?)</(?:strong|b)>", re.DOTALL)
_HTML_EM = re.compile(r"<(?:em|i)>(.*?)</(?:em|i)>", re.DOTALL)
_HTML_LINK = re.compile(r'<a\s+[^>]*href="([^"]*)"[^>]*>(.*?)</a>', re.DOTALL)
_HTML_LIST = re.compile(r"<(ul|ol)>(.*?)</\1>", re.DOTALL)
_HTML_LI = re.compile(r"<li>(.*?)</li>", re.DOTALL)
_HTML_TAG = re.compile(r"<[^>]+>")
_HTML_HEADING = re.compile(r"<h[123]>(.*?)</h[123]>", re.DOTALL)

BUTTON_MARK = "\U0001F518"  # 🔘
IMAGE_MARK = "\U0001F5BC\uFE0F"  # 🖼️
DIVIDER_TEXT = "\u25AC\u25AC\u25AC divider \u25AC\u25AC\u25AC"  # ▬▬▬ divider ▬▬▬

_BUTTON_LINE = re.compile(rf"^{re.escape(BUTTON_MARK)}\s*\[([^\]]*)\]\(([^)]+)\)\s*$")
_IMAGE_LINE = re.compile(rf"^{re.escape(IMAGE_MARK)}\s*\[([^\]]*)\]\(([^)]+)\)\s*$")

# Walks the document in true order — a heading OR one <p>/<ul>/<ol> block,
# whichever comes next — rather than splitting only at headings. This
# matters because the content following one heading may contain several
# DISTINCT blocks (plain text, then a button, then a divider): each marker
# paragraph must become its own separate block, never merged into
# surrounding text.
_TOKEN = re.compile(
    r"(?P<heading><h[123]>.*?</h[123]>)|(?P<block><p>.*?</p>|<ul>.*?</ul>|<ol>.*?</ol>)",
    re.DOTALL,
)


def _inline_to_html(text: str) -> str:
    text = _LINK_MD.sub(r'<a href="\2">\1</a>', text)
    text = _BOLD.sub(r"<strong>\1</strong>", text)
    text = _ITALIC.sub(r"<em>\1</em>", text)
    return text


def _text_to_html(text: str) -> str:
    """Plain text (light markdown) -> HTML paragraphs/lists — same rules as
    Article Writer's richtext.to_html()."""
    if not text or not text.strip():
        return ""
    grouped: list[tuple[bool, list[str]]] = []
    for para in re.split(r"\n\s*\n", text.strip()):
        lines = [ln.strip() for ln in para.split("\n") if ln.strip()]
        is_bullets = bool(lines) and all(ln.startswith(("- ", "* ")) for ln in lines)
        if is_bullets and grouped and grouped[-1][0]:
            grouped[-1][1].extend(lines)
        else:
            grouped.append((is_bullets, lines))

    blocks = []
    for is_bullets, lines in grouped:
        if is_bullets:
            items = "".join(f"<li>{_inline_to_html(ln[2:])}</li>" for ln in lines)
            blocks.append(f"<ul>{items}</ul>")
        else:
            blocks.append(f"<p>{_inline_to_html(' '.join(lines))}</p>")
    return "".join(blocks)


def _unescape(text: str) -> str:
    return (
        text.replace("&nbsp;", " ").replace("&amp;", "&")
        .replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"')
    )


def _block_to_text(block: str) -> str:
    list_match = _HTML_LIST.match(block)
    if list_match:
        items = _HTML_LI.findall(list_match.group(2))
        return "\n".join(f"- {_HTML_TAG.sub('', it).strip()}" for it in items)
    inner = re.sub(r"</?p>", "", block)
    inner = re.sub(r"<br\s*/?>", "\n", inner)
    return _HTML_TAG.sub("", inner).strip()


def _text_from_html(html: str) -> str:
    """Convert ONE block's raw HTML (a single <p>/<ul>/<ol>, or a run of
    them) back to plain text with light markdown."""
    if not html or not html.strip():
        return ""
    text = _HTML_LINK.sub(lambda m: f"[{_HTML_TAG.sub('', m.group(2))}]({m.group(1)})", html)
    text = _HTML_STRONG.sub(r"**\1**", text)
    text = _HTML_EM.sub(r"*\1*", text)

    blocks = re.findall(r"<p>.*?</p>|<ul>.*?</ul>|<ol>.*?</ol>", text, re.DOTALL)
    if not blocks:
        return _unescape(_HTML_TAG.sub("", text)).strip()

    converted = [_block_to_text(b) for b in blocks]
    return _unescape("\n\n".join(b for b in converted if b))


def block_body_to_html(s: dict) -> str:
    """One block's body (no heading) -> its HTML paragraph(s)."""
    block_type = s.get("block_type", "text")
    if block_type == "button":
        label = (s.get("button_label") or "Click here").strip() or "Click here"
        url = (s.get("button_url") or "#").strip() or "#"
        return f'<p>{BUTTON_MARK} <a href="{url}">{label}</a></p>'
    if block_type == "image":
        alt = (s.get("image_alt") or "Image").strip() or "Image"
        url = (s.get("image_url") or "#").strip() or "#"
        return f'<p>{IMAGE_MARK} <a href="{url}">{alt}</a></p>'
    if block_type == "divider":
        return f"<p>{DIVIDER_TEXT}</p>"
    return _text_to_html(s.get("content") or "")


def sections_to_html(sections: list[dict]) -> str:
    """Merge a newsletter's blocks into ONE HTML document — the panel's
    single-window editor. Each block's heading becomes a real <h2>; the body
    is either normal rich text (text blocks) or a marker paragraph carrying
    a real link (button/image/divider — see module docstring)."""
    parts = []
    for s in sections:
        heading = (s.get("heading") or "").strip()
        if heading:
            parts.append(f"<h2>{heading}</h2>")
        parts.append(block_body_to_html(s))
    return "".join(parts)


def _paragraph_to_block(block_html: str) -> dict | None:
    """Decide whether ONE <p>/<ul>/<ol> chunk is a button/image/divider
    marker or plain text. Returns None for an empty/whitespace-only chunk
    (nothing to record). Markers always live in their own paragraph (see
    block_body_to_html), so a single chunk never mixes a marker with other
    text — no disambiguation needed within one call."""
    plain = _text_from_html(block_html).strip()
    if not plain:
        return None

    if plain == DIVIDER_TEXT:
        return {"block_type": "divider", "content": ""}

    m = _BUTTON_LINE.match(plain)
    if m:
        return {"block_type": "button", "content": "", "button_label": m.group(1), "button_url": m.group(2)}

    m = _IMAGE_LINE.match(plain)
    if m:
        return {"block_type": "image", "content": "", "image_alt": m.group(1), "image_url": m.group(2)}

    return {"block_type": "text", "content": plain}


def html_to_sections(html: str) -> list[dict]:
    """Split ONE merged document back into block dicts — the inverse of
    sections_to_html(). A heading attaches to whichever block comes right
    after it; consecutive plain-text/list paragraphs under one heading are
    merged into that one text block's content, but a button/image/divider
    marker always becomes its own separate block (never merged with
    surrounding text, and it "uses up" the pending heading so a later text
    paragraph under the same heading starts a fresh heading-less block).
    Each resulting block is fully shaped for NewsletterSectionInput
    (block_type + only the fields that type uses)."""
    if not html or not html.strip():
        return []

    sections: list[dict] = []
    pending_heading: str | None = None
    pending_text_htmls: list[str] = []

    def flush_text() -> None:
        nonlocal pending_heading, pending_text_htmls
        if pending_text_htmls:
            content = _text_from_html("".join(pending_text_htmls)).strip()
            if content:
                sections.append({"block_type": "text", "content": content, "heading": pending_heading})
                pending_heading = None
            pending_text_htmls = []

    for m in _TOKEN.finditer(html):
        if m.group("heading"):
            flush_text()
            pending_heading = _unescape(_HTML_TAG.sub("", m.group("heading"))).strip()
            continue
        block_html = m.group("block")
        marker = _paragraph_to_block(block_html)
        if marker is None:
            continue
        if marker["block_type"] == "text":
            pending_text_htmls.append(block_html)
        else:
            flush_text()
            marker["heading"] = pending_heading
            pending_heading = None
            sections.append(marker)

    flush_text()
    return sections


def to_export_text(sections: list[dict]) -> str:
    """Plain-text export — human-legible rendering for any future export
    function, mirrors Article Writer's to_export_text()."""
    parts = []
    for s in sections:
        heading = (s.get("heading") or "").strip()
        if heading:
            parts.append(f"{heading.upper()}\n{'-' * len(heading)}")
        block_type = s.get("block_type", "text")
        if block_type == "button":
            parts.append(f"[BUTTON] {s.get('button_label') or 'Click here'} -> {s.get('button_url') or ''}")
        elif block_type == "image":
            parts.append(f"[IMAGE] {s.get('image_alt') or 'Image'} -> {s.get('image_url') or ''}")
        elif block_type == "divider":
            parts.append("----------")
        else:
            content = s.get("content") or ""
            content = _BOLD.sub(r"\1", content)
            content = _ITALIC.sub(r"\1", content)
            content = re.sub(r"(?m)^[-*] ", "\u2022 ", content)
            if content:
                parts.append(content)
    return "\n\n".join(parts)

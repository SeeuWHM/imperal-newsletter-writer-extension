# imperal-newsletter-writer-extension

[![Imperal SDK](https://img.shields.io/badge/imperal--sdk-5.9.12-blue)](https://pypi.org/project/imperal-sdk/)
[![Version](https://img.shields.io/badge/version-1.6.0-green)](https://github.com/SeeuWHM/imperal-newsletter-writer-extension/releases)
[![License](https://img.shields.io/badge/license-LGPL--2.1-orange)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Imperal%20Cloud-purple)](https://panel.imperal.io)

**Newsletter writing extension for [Imperal Cloud](https://panel.imperal.io).**

Newsletter Writer keeps a per-brand "project" context — goals, brand voice, keywords, internal reference links to weave into copy, and a rotating "fill" stock of promo codes/links/topics the generator draws from least-used-first. Ask Webbee to write a newsletter and it drafts through the shared `newsletter-writer-api` backend (outline → draft → mechanical quality gates → self-review), grounded in that context and any real facts you hand it. The full newsletter text lives in that backend's own database — never in chat or `ctx.store` — so Webbee can `read_full_newsletter` / `edit_full_newsletter` on request, but the panel's single merged rich-text editor is the one place the whole document (subject included) gets written end to end.

---

## What It Does

Talk to it naturally:

```
"create a newsletter project for our hosting brand"
"add a promo code HOSTING50 — 50% off the annual plan"
"write a newsletter about the new promo, tied to this link"
"is the newsletter ready yet?"
"rewrite the block about the promo code, make it more urgent"
"shorten the intro and make the CTA punchier"
"send this newsletter's text to my inbox"
```

Or work in the panel: pick a project on the left, open a newsletter on the kanban board, and edit the whole thing — subject as the leading heading, body below — in one rich-text editor.

---

## Capabilities

- **Project context** — one container per brand: goals, brand voice, keywords, useful/social links, MailerLite targeting label, and internal reference links the writer can anchor into copy.
- **Fill stock** — named categories (promo codes, priority links, topics to cover) with individual items the pipeline rotates through least-used-first, so the same offer isn't repeated every issue.
- **Newsletter lifecycle** — idea → writing → review → scheduled → sent, tracked per newsletter with word count and quality flags.
- **AI generation** — background job per newsletter: outline → draft → mechanical gates → judge, grounded in project context plus whatever source facts (web search, Article Writer, Matomo/GSC data) are handed in.
- **Natural-language patching** — locate and rewrite one block by instruction, without touching the rest of the newsletter.
- **Full-text read/edit for chat** — `read_full_newsletter` / `edit_full_newsletter` work over Markdown, but chat functions never return or accept a full body anywhere else — metadata only.
- **Export for handoff** — `export_newsletter_text` returns the full body as real HTML + plain text, for handing to MailerLite, Mail, or Notes — Markdown syntax never leaks into a sent email.
- **Panel-only full editor** — one merged `ui.RichEditor` document (subject as `<h1>`, sections as `<h2>` + body) is the true read/write surface, zero LLM tokens regardless of corpus size.
- **Honest patch results** — `patch_newsletter` reports `matched`/`replaced_count`; if the instruction's target text genuinely isn't in the newsletter, it says so instead of a false "Patched block".
- **Proactive "ready" notice** — the skeleton fires a `ctx.notify()` the moment a generation job lands a newsletter in "review" (tracked in our own durable storage, not the kernel's in-memory diff state — see docs/extension.md "Proactivity"), so Webbee can tell the user without being asked.

---

## Architecture

```
imperal-newsletter-writer-extension/
├── main.py                  # Entry point — sys.modules hot-reload cleanup + imports
├── app.py                   # Extension/ChatExtension setup, backend_jwt secret, health check
├── params.py                 # Pydantic parameter models for every chat function
├── response_models.py        # Pydantic response models (ProjectRecord, NewsletterSummaryRecord, ...)
├── api_client.py              # call_backend() — HTTP bridge to the newsletter-writer-api backend
├── richtext.py                # HTML <-> {subject, sections} <-> Markdown conversion for the merged editor
├── navstate.py                # Tiny ctx.store doc remembering the last open project/newsletter/view
├── skeleton.py                 # LLM context cache (project/newsletter counts) + proactive "ready" alert
├── handlers_projects.py        # Chat functions: project CRUD + open_project + reference links
├── handlers_fill.py            # Chat functions: fill category/item CRUD
├── handlers_newsletters.py     # Chat functions: newsletter metadata CRUD + full-text read/edit/export
├── handlers_generate.py        # Chat functions: generate_newsletter, status poll, patch_newsletter
├── panels_side.py               # Left panel — project switcher + new-project form
├── panels_workspace.py           # Center panel — kanban board + single merged RichEditor
├── cache_helpers.py              # ctx.cache wrapper — caches the sidebar project-list + workspace board reads only
├── icon.svg                      # Extension icon
└── imperal.json                  # Generated manifest (via `imperal build`)
```

Newsletter text lives in this extension's own backend + database — not in `ctx.store` — with the panel as the full read/edit surface.

---

## Function Reference

| Function | Type | Description |
|----------|------|-------------|
| `create_project` | write | Create a newsletter project — a container for one brand's context |
| `list_projects` | read | List all newsletter projects — id, name, keywords, goals |
| `update_project_context` | write | Update name, description, brand voice, goals, keywords, links, MailerLite targeting |
| `delete_project` | destructive | Delete a project and cascade-delete all its newsletters/fill data |
| `open_project` | write | Panel-only: switch the active project (sidebar detail + workspace board) |
| `add_reference_link` | write | Add one internal page as a reference link the writer may anchor into copy |
| `list_reference_links` | read | List a project's internal reference links |
| `remove_reference_link` | destructive | Remove one reference link by URL |
| `create_fill_category` | write | Add a named "stock" category (promo codes, priority links, topics) |
| `list_fill_categories` | read | List a project's fill categories |
| `delete_fill_category` | destructive | Delete a fill category and all its items |
| `create_fill_item` | write | Add one value (a promo code, a link, a topic) to a fill category |
| `list_fill_items` | read | List a category's items, least-used-first |
| `update_fill_item` | write | Change a fill item's value/note, or retire it without losing usage history |
| `delete_fill_item` | destructive | Permanently delete one fill item |
| `create_newsletter` | write | Create an empty newsletter shell under a project — no AI call yet |
| `list_newsletters` | read | List newsletters (metadata only — id, subject, status, word count, quality flags) |
| `update_newsletter_status` | write | Move a newsletter to idea / writing / review / scheduled / sent |
| `update_newsletter_meta` | write | Fix subject and/or preheader without touching the body |
| `update_newsletter_section` | write | Panel-only: overwrite one block's fields verbatim — no AI, skips the judge |
| `save_full_newsletter` | write | Panel-only: replace the entire newsletter from the merged editor document |
| `read_full_newsletter` | read | Read the entire newsletter body as editable Markdown |
| `edit_full_newsletter` | write | Replace the entire newsletter with an edited Markdown version, verbatim |
| `export_newsletter_text` | read | Return the full body as HTML + plain text, for handing to another extension (MailerLite/Mail/Notes) |
| `delete_newsletter` | destructive | Permanently delete a newsletter |
| `generate_newsletter` | write | Start the background generation pipeline: outline → draft → gates → judge; check it's done with `list_newsletters(status='review')` |
| `patch_newsletter` | write | Rewrite one block by natural-language instruction; returns `matched`/`replaced_count` honesty fields plus a short preview |

---

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `NEWSLETTER_WRITER_BACKEND_URL` | `https://api.webhostmost.com/newsletter-writer` | newsletter-writer-api backend base URL |

The `backend_jwt` secret (`scope="app"`, developer-managed only) authenticates this extension to the backend — it is never entered or seen by end users. Every backend call also carries the caller's `imperal_id` as `X-Imperal-Id`, since project/newsletter ownership is scoped by platform tenant, not an external per-user API key.

---

## Development

```bash
python3 -m py_compile *.py          # syntax check — mandatory before every commit
.venv/bin/pytest -q                 # 72 tests: handlers, richtext, skeleton, newsletters, params, cache_helpers
imperal build .                     # regenerate imperal.json from registered tools
imperal validate .                  # validate against current SDK federal rules (V1-V24+V31)
```

---

## Built with

- [imperal-sdk](https://github.com/imperalcloud/imperal-sdk) 5.9.12
- [Imperal Cloud](https://panel.imperal.io)

# Newsletter Writer Extension — Full Documentation

**Version:** 1.4.0 (code HEAD `910bdf7`; prod = **draft v1.0.0** — Dev Portal deploy pending) |
**app_id:** `imperal-newsletter-writer-extension` | **tool_name:** `newsletter_writer`
**Git:** `github.com/SeeuWHM/imperal-newsletter-writer-extension`
**Backend:** `SeeU-Extensions/newsletter-writer-backend/` (source of truth for backend —
schema, pipeline, deploy). This doc covers the extension side only. Sibling of Article Writer.

> **Resume point (2026-07-17).** Reflects the real code at HEAD. The extension code is pushed;
> **the Dev Portal draft still runs v1.0.0** (the pre-text-only, per-block-card version) until the
> next git deploy. The **backend `newsletter-writer-api` WAS deployed today** (text-only rewrite,
> restarted, 19/19 backend tests green) — so backend and extension are briefly out of step until the
> extension is redeployed.

---

## What this actually is

A **project-based email newsletter writer** — Article Writer's sibling, adapted for email:

- A **project** = per-brand context: name, description, brand voice, goals, keywords, useful/social
  links, reference links, MailerLite targeting label + group ids (context only, no key), **fill
  categories** (see below). Webbee fills this using whatever other extensions exist.
- A **newsletter** belongs to a project and moves `idea → writing → review → scheduled → sent`.
  Written by the backend pipeline (`generate_newsletter`) or edited (`patch_newsletter` /
  `edit_full_newsletter`), never hand-written blindly in chat.
- **A newsletter is plain heading+content prose — exactly like an Article Writer article.** The old
  block model (text/button/image/divider + emoji markers 🔘/🖼️/▬▬▬) was **removed 2026-07-17** at
  the owner's request: layout/buttons/images are the sending tool's job (MailerLite); here it's just
  the copy. The DB block columns remain but are unused (non-destructive).
- **The subject is the leading `# ` (H1) of the single editor document**; section headings are `## `.
  No separate subject field — subject and body are one editor/markdown; first H1 = subject on save.
  The **preheader** is still generated and stored (a connector uses it as the inbox preview line) but
  is not a manual panel field.
- **Webbee can read and edit the full text** (`read_full_newsletter` / `edit_full_newsletter`).

**Fill categories (the "proactive domain data" mechanism)** — free-form, NOT hardcoded. Webbee
creates any category the topic needs (promo codes for hosting, address/hours for a local business,
topics to cover, …) and stores each item's real **conditions in its `note`**. The generation
pipeline injects them as "use only these, never invent an offer/code". This is the piece Article
Writer does **not** have. ✅ Already used live: both WHM projects have `Promo codes` + `Promo
conditions` categories with the 5 real codes and their eligibility in the notes.

MailerLite itself is out of scope — a future `mailerlite-connector` owns the key and pushes the
finished newsletter into a campaign.

---

## Architecture

```
User (panel / chat)
    ↓ chat.function (26) or panel action
handlers_projects.py / handlers_fill.py / handlers_newsletters.py / handlers_generate.py
    ↓ HTTP (api_client.call_backend) — Bearer backend_jwt + X-Imperal-Id header
      newsletter-writer-api (shared backend, api-server 127.0.0.1:8018)  [DEPLOYED today]
      public route: api.webhostmost.com/newsletter-writer/   ·   Galera db imperal_newsletter_writer
      (pipeline/schema/deploy → newsletter-writer-backend/README.md)
```

Same two-credential model as Article Writer: `backend_jwt` (`ext.secret scope="app"`, developer-set,
authenticates the extension) + `X-Imperal-Id` (per-caller tenancy). No external per-user account, so
no user-facing secret. No cross-extension IPC.

---

## File structure

```
newsletter-writer-extension/
├── main.py · app.py · api_client.py · navstate.py · icon.svg · imperal.json · pyproject.toml
├── params.py             — chat-function param models (mirror backend request schemas)
├── response_models.py    — data models (NewsletterSummaryRecord is body-free; NewsletterTextRecord = read-for-edit markdown)
├── richtext.py           — text/markdown <-> HTML (panel) + markdown <-> document (Webbee edit):
│                            sections_to_html/html_to_sections, document_to_html/html_to_document,
│                            document_to_markdown/markdown_to_document   (NO block/marker code — text-only)
├── skeleton.py           — @ext.skeleton(alert=True) refresh + paired skeleton_alert_* tool
├── handlers_projects.py  — project CRUD + reference links
├── handlers_fill.py      — fill categories + fill items (the domain-data store; note = conditions)
├── handlers_newsletters.py — newsletter CRUD, status/meta, section/full save (panel), read_full, edit_full
├── handlers_generate.py  — generate_newsletter, check_newsletter_generation_status, patch_newsletter
├── panels_side.py        — LEFT "sidebar": active project + project switcher
├── panels_workspace.py   — CENTER "workspace": newsletter board + single-editor view (H1 subject)
└── tests/  test_handlers.py · test_newsletters.py · test_richtext.py · test_skeleton.py   (54 tests, green)
```

Every file < 300 lines.

---

## Chat-function inventory (26 functions + 2 skeleton tools)

### Projects (`handlers_projects.py`)
- `create_project`, `list_projects`, `update_project_context`, `delete_project` (cascades)
- `add_reference_link` / `list_reference_links` / `remove_reference_link` — `{url, description}` interlinking targets

### Fill categories & items (`handlers_fill.py`) — the proactive-data store
- `create_fill_category(project_id, name, category_type?, instructions?)` / `list_fill_categories` / `delete_fill_category`
- `create_fill_item(project_id, category_id, value, note?)` — **`note` holds the item's real conditions**
- `list_fill_items` (least-used-first) / `update_fill_item(…, value?, note?, is_active?)` / `delete_fill_item`
  - Generation uses active items least-used-first and records which were actually used → honest "don't repeat the same promo code".

### Newsletters (`handlers_newsletters.py`)
- `create_newsletter(project_id, subject?, brief_topic?)` — **empty shell, no AI**
- `list_newsletters(project_id?, status?)` — metadata only (never the body)
- `update_newsletter_status` · `update_newsletter_meta(subject?, preheader?)`
- `update_newsletter_section(order_index, heading?, content?)` — PANEL manual one-section overwrite
- `save_full_newsletter(content_html)` — PANEL-ONLY editor Save: first `<h1>` = subject (→ meta), rest → sections
- `read_full_newsletter(newsletter_id)` — read, returns whole body as editable **Markdown** (`# subject`, `## headings`)
- `edit_full_newsletter(newsletter_id, content_markdown)` — write, replaces the whole newsletter **verbatim** from Markdown (subject via `/meta`); prefer `patch_newsletter` for small edits
- `delete_newsletter` — destructive

### Generation (`handlers_generate.py`)
- `generate_newsletter(newsletter_id, topic, goal?, audience_hint?, tone_override?, target_word_count?, fill_selections?, source_snippets?)` — enqueues async pipeline → `{job_id,…}`
- `check_newsletter_generation_status(newsletter_id, job_id)` — read
- `patch_newsletter(newsletter_id, instruction, section_hint?)` — one-section NL rewrite, returns a preview

### Skeleton (`skeleton.py`)
- `skeleton_refresh_newsletter_writer_overview` — `alert=True`, ttl-hint 60s. Returns
  `{"response": {project_count, newsletter_count, by_status, latest_ready, instruction}}` — flat
  scalars, counts from paged `total`, `latest_ready` = newest `review` subject.
- `skeleton_alert_newsletter_writer_overview(ctx, old, new)` — fires when `review` count rises →
  proactive "your newsletter «…» is ready for review"; "" otherwise.

---

## Generation pipeline (backend) & quality

`outline → draft → mechanical gates (0-token) → LLM judge → targeted revision of only flagged
sections → lands in 'review'`. The judge's individual issues are logged to `generation_events`
(stage `judge`), but only a **count** ("N issue(s) flagged by review, revised") is stored on the
newsletter's `quality_flags`. 🔴 **Open**: the actual issue text isn't surfaced to chat/panel — the
`list_newsletters` `quality_flags` only carries the summary count, so Webbee can't explain *what* was
flagged without reading `generation_events`. Consider storing the real notes in `quality_flags`.

Anti-slop/anti-hallucination: mechanical gate (slop phrases, placeholders, contrastive-tic, subject/
preheader length) + fill-category rule ("only codes from fill_categories, never invent") + judge.
Note: with **no fill_categories set up, any promo code from the brief gets flagged** as not-in-list —
which is exactly why setting up the `Promo codes` category (done) removes the false flags.

---

## Panels

- **`sidebar`** (left) — active project detail + compact switcher (ListItem must live in a `ui.List`).
- **`workspace`** (center) — `newsletters` board by status (navigation only), and `newsletter` view:
  a `generate_newsletter` form if empty, otherwise **one single merged `ui.RichEditor`** with the
  **subject as the leading `<h1>`** and section headings as `<h2>` (`richtext.document_to_html`). Save
  (`save_full_newsletter`) splits the first `<h1>` back to the subject and the rest to sections. No
  separate subject/preheader form; a standalone subject header shows only in the empty/generate state.

Same RichEditor link-button gap as Article Writer (SDK/TipTap).

---

## Proactivity (2026-07-17)

1. **"Newsletter ready" notifications** — skeleton `alert=True` + paired `skeleton_alert_*`; fires when
   the `review` count rises. Latency = refresh interval (hint 60s; authoritative TTL = Registry row,
   kernel default 300s → ~1–5 min).
2. **Proactive domain data** — the chat description tells Webbee that fill categories are free-form and
   to proactively offer to set up the reusable data the topic needs (promo codes w/ conditions,
   address/hours…) with conditions in each item `note`, so the writer states offers accurately and
   never broadens a promise. This is native guidance now (Webbee shouldn't need to be walked through it).

---

## Pricing (per_action) — current + recommendation

Only `generate_newsletter` (multi-LLM pipeline) and `patch_newsletter` (2 LLM calls) spend backend
LLM tokens; `read_full`/`edit_full` spend Webbee context tokens (newsletters are short, so small);
the rest is cheap DB. Notes on the current prices:
- `list_*`, `check_status` = 10 ✓ (called constantly — keep cheapest)
- create/update/delete/status/meta, fill/reference ops = 10–15 ✓
- `update_newsletter_section`, `save_full_newsletter` (PANEL, 0 LLM) = 10 → **consider 0/min**
- `read_full_newsletter` 30 / `edit_full_newsletter` 20 → make **edit ≥ read** (editing outputs the whole body)
- `patch_newsletter` = 30 ✓
- 🔴 `generate_newsletter` = 50 → **300–400**. It runs the SAME 4-call pipeline as `generate_article`
  (which is priced 800); a short email is ~40–55% of an article's tokens, not 6%. Currently it's
  priced like a `list` call and barely above `patch` — it must be the most expensive newsletter function.

---

## Deploy / state

- Extension: code **v1.4.0** pushed (`910bdf7`). Dev Portal app is **status `draft` at v1.0.0** (old
  per-block editor). ⏭️ **Deploy from git in the Developer Portal** to ship text-only editor + H1
  subject + "ready" alerts + Webbee read/edit + proactive-data guidance.
- Backend: **deployed today** at `/opt/newsletter-writer-api` (systemd `newsletter-writer-api`, :8018),
  text-only, restarted, healthy, 19/19 backend tests green. Migrations 001–004 applied; block columns
  present but unused.
- DB provisioning recipe & schema → `newsletter-writer-backend/README.md`.

---

## Open items

1. 🔴 **Dev Portal deploy pending** (extension v1.0.0 draft → v1.4.0).
2. 🔴 **Review issues not surfaced** — store the judge's actual notes in `quality_flags` (see pipeline above).
3. Optional cleanup — both projects have both a `Promo codes` and a `Promo conditions` category (Webbee
   made both); can be consolidated to one.
4. `mailerlite-connector` (future) — owns the MailerLite key, pushes finished newsletters to campaigns.
5. Backend open items → `newsletter-writer-backend/README.md`.

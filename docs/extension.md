# Newsletter Writer Extension — Full Documentation

**Version:** 1.5.0 (code HEAD = prod, deployed and verified live 2026-07-18) |
**SDK:** imperal-sdk 5.9.9 | **app_id:** `imperal-newsletter-writer-extension` | **tool_name:** `newsletter_writer`
**Git:** `github.com/SeeuWHM/imperal-newsletter-writer-extension`
**Backend:** `SeeU-Extensions/newsletter-writer-backend/` (source of truth for backend —
schema, pipeline, deploy). This doc covers the extension side only. Sibling of Article Writer.

> **Resume point (2026-07-18).** Reflects the real code at HEAD, and it is the real code running in
> prod — confirmed live today (`list_newsletters`, `open_project`). `capabilities` now declares
> `notify:push` (see "Deploy gotcha" below) — without it every deploy silently rolled back to the
> previous commit.

---

## What this actually is

A **project-based email newsletter writer** — Article Writer's sibling, adapted for email:

- A **project** = per-brand context: name, description, brand voice, goals, keywords, useful/social
  links, reference links, MailerLite targeting label + group ids (context only, no key), **fill
  categories** (see below). Webbee fills this using whatever other extensions exist.
- A **newsletter** belongs to a project and moves `idea → writing → review → scheduled → sent`.
  Written by the backend pipeline (`generate_newsletter`) or edited (`patch_newsletter` /
  `edit_full_newsletter`), never hand-written blindly in chat.
- **A newsletter is plain heading+content prose — exactly like an Article Writer article.** Layout/
  buttons/images are the sending tool's job (MailerLite); here it's just the copy.
- **The subject is the leading `# ` (H1) of the single editor document**; section headings are `## `.
  No separate subject field — subject and body are one editor/markdown; first H1 = subject on save.
  The **preheader** is still generated and stored (a connector uses it as the inbox preview line) but
  is not a manual panel field.
- **Webbee can read and edit the full text** (`read_full_newsletter` / `edit_full_newsletter`), and
  **hand it to another tool as real HTML** (`export_newsletter_text` [NEW 2026-07-18] — see below).
- **All tool descriptions and hints are English-only** (2026-07-18 policy) — no bilingual
  `русская_фраза, english_phrase` trigger lists anywhere in a description. Webbee already understands
  non-English input semantically without needing the literal phrase baked in.

**Fill categories (the "proactive domain data" mechanism)** — free-form, NOT hardcoded. Webbee
creates any category the topic needs (promo codes for hosting, address/hours for a local business,
topics to cover, …) and stores each item's real **conditions in its `note`**. The generation
pipeline injects them as "use only these, never invent an offer/code". This is the piece Article
Writer does **not** have. Live in production: WHM projects and KS Renovation Group both have real
fill categories with real conditions in the notes.

**MailerLite:** a separate `imperal-mailerlite-connector-extension` now exists in this workspace (its
own repo, own API key, own docs) — it owns the actual send/campaign step. Newsletter Writer itself
never sees a MailerLite key; it only stores a targeting label/group-id list as context.

---

## Architecture

```
User (panel / chat)
    ↓ chat.function (28) or panel action
handlers_projects.py / handlers_fill.py / handlers_newsletters.py / handlers_generate.py
    ↓ HTTP (api_client.call_backend) — Bearer backend_jwt + X-Imperal-Id header
      newsletter-writer-api (shared backend, api-server 127.0.0.1:8018)
      public route: api.webhostmost.com/newsletter-writer/   ·   Galera db imperal_newsletter_writer
      (pipeline/schema/deploy → newsletter-writer-backend/README.md)
```

Same two-credential model as Article Writer: `backend_jwt` (`ext.secret scope="app"`, developer-set,
authenticates the extension) + `X-Imperal-Id` (per-caller tenancy). No external per-user account, so
no user-facing secret. No cross-extension IPC.

Every `call_backend` failure now carries a **structured `error_code`** (SDK 5.9.9
`ActionResult.error(code=...)`), not just prose — see "Error handling" below.

---

## File structure

```
newsletter-writer-extension/
├── main.py · app.py · api_client.py · navstate.py · icon.svg · imperal.json
├── pyproject.toml        — imperal-sdk>=5.9.9
├── params.py             — chat-function param models (mirror backend request schemas).
│                            EntityId type rejects obvious placeholder ids ("unknown", "null", "",
│                            "string", …) client-side before ever hitting the network.
├── response_models.py    — data models (NewsletterSummaryRecord is body-free; NewsletterTextRecord =
│                            read-for-edit markdown; NewsletterFullText = HTML+text export [NEW];
│                            PatchResult carries matched/replaced_count honesty fields)
├── richtext.py           — text/markdown <-> HTML (panel) + markdown <-> document (Webbee edit):
│                            sections_to_html/html_to_sections, document_to_html/html_to_document,
│                            document_to_markdown/markdown_to_document
├── skeleton.py           — @ext.skeleton(alert=True) refresh + paired skeleton_alert_* tool, PLUS a
│                            direct ctx.notify() call gated on our own ctx.store baseline (the
│                            reliable proactive-alert path — see "Proactivity" below)
├── handlers_projects.py  — project CRUD + reference links + open_project (sidebar-switch fix)
├── handlers_fill.py      — fill categories + fill items (the domain-data store; note = conditions)
├── handlers_newsletters.py — newsletter CRUD, status/meta, section/full save (panel), read_full,
│                              edit_full, export_newsletter_text [NEW]
├── handlers_generate.py  — generate_newsletter, patch_newsletter
├── panels_side.py        — LEFT "sidebar": active project + project switcher
├── panels_workspace.py   — CENTER "workspace": newsletter board + single-editor view (H1 subject)
└── tests/  test_handlers.py · test_newsletters.py · test_richtext.py · test_skeleton.py ·
           test_params.py   (70 tests, green)
```

Every file < 300 lines.

---

## Chat-function inventory (27 functions + 2 skeleton tools)

### Projects (`handlers_projects.py`)
- `create_project`, `list_projects`, `update_project_context`, `delete_project` (cascades)
- `open_project(project_id)` — write, **PANEL-ONLY** [NEW 2026-07-18]. Switches the active project —
  see "Sidebar bug fix" below. Not a Webbee-facing action; pure UI navigation state.
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
- `read_full_newsletter(newsletter_id)` — read, returns whole body as editable **Markdown** (`# subject`, `## headings`). Description now points to `export_newsletter_text` for any cross-tool handoff.
- `edit_full_newsletter(newsletter_id, content_markdown)` — write, replaces the whole newsletter **verbatim** from Markdown (subject via `/meta`); prefer `patch_newsletter` for small edits
- `export_newsletter_text(newsletter_id)` — read [NEW 2026-07-18]. Returns the full body as **both**
  `html` (real `<h2>`/`<strong>`/`<ul>` markup) and `text` — mirrors Article Writer's
  `export_article_text`. **Root-cause fix**: before this existed, the only way to hand a newsletter to
  another tool (MailerLite, Mail, Notes) was `read_full_newsletter`'s raw Markdown — which is why sent
  newsletters were showing up with literal `**bold**`/`##` syntax instead of formatting. Use this,
  never the Markdown, for anything that leaves the panel.
- `delete_newsletter` — destructive

### Generation (`handlers_generate.py`)
- `generate_newsletter(newsletter_id, topic, goal?, audience_hint?, tone_override?, target_word_count?, fill_selections?, source_snippets?)` — enqueues async pipeline → `{job_id,…}`. To check when it's done, call `list_newsletters(status='review')` a bit later — status lands on `review` the moment the draft is ready, so that one call shows everything that finished with no job_id tracking. **`check_generation_status` was removed (2026-07-18):** its `GET /v1/newsletters/{id}/jobs/{job_id}` job-poll endpoint returned an error in production while the direct status-list path worked, so the broken duplicate was dropped in favour of the one reliable path (Ignat's call). Mirrors the same removal in Article Writer.
- `patch_newsletter(newsletter_id, instruction, section_hint?)` — one-section NL rewrite, returns a
  preview. **Honesty fix (2026-07-18):** `PatchResult` now carries `matched`/`replaced_count`. If the
  locate step can't find a block actually containing the instruction's target — or the edit model left
  the block byte-identical — the response is `matched=false, replaced_count=0` and **nothing is
  written**, instead of a false "Patched block". Verified live: a deliberately bogus instruction
  against a real newsletter correctly no-op'd once the fix landed.

### Skeleton (`skeleton.py`)
- `skeleton_refresh_newsletter_writer_overview` — `alert=True`, ttl-hint 60s. Returns
  `{"response": {project_count, newsletter_count, by_status, latest_ready, instruction}}` — flat
  scalars, counts from paged `total`, `latest_ready` = newest `review` subject. **Also** fires a
  direct `ctx.notify()` when the review count rises against our own persisted baseline — see
  "Proactivity" below.
- `skeleton_alert_newsletter_writer_overview(ctx, old, new)` — the kernel's own old/new diff
  mechanism. Kept as a harmless second layer (mirrors mail-client's `mail_inbox_summary` pattern) but
  not relied on — see "Proactivity."

---

## Generation pipeline (backend) & quality

`outline → draft → mechanical gates (0-token) → LLM judge → targeted revision of only flagged
sections → lands in 'review'`. The judge's individual issues are logged to `generation_events`
(stage `judge`), but only a **count** ("N issue(s) flagged by review, revised") is stored on the
newsletter's `quality_flags`. 🔴 **Open**: the actual issue text isn't surfaced to chat/panel — the
`list_newsletters` `quality_flags` only carries the summary count, so Webbee can't explain *what* was
flagged without reading `generation_events`. Consider storing the real notes in `quality_flags`.

Anti-slop/anti-hallucination: mechanical gate (slop phrases, placeholders, contrastive-tic, subject/
preheader length) + fill-category rule ("only codes from fill_categories, never invent") + judge. Also
hardened 2026-07-18 (backend `patch.py`/`locate.py`): the natural-language patch locate step now sees
each section's actual content (not just headings), can honestly answer "no section matches" instead
of being forced to guess, and a stop-word list stops an instruction spuriously "matching" a heading on
a shared word like "with" alone.

---

## Panels

- **`sidebar`** (left) — active project detail + compact switcher (ListItem must live in a `ui.List`).
  **Project rows route through `open_project` (a chat.function), never a raw
  `ui.Call("__panel__workspace", ...)`** — see "Sidebar bug fix" below.
- **`workspace`** (center) — `newsletters` board by status (navigation only), and `newsletter` view:
  a `generate_newsletter` form if empty, otherwise **one single merged `ui.RichEditor`** with the
  **subject as the leading `<h1>`** and section headings as `<h2>` (`richtext.document_to_html`). Save
  (`save_full_newsletter`) splits the first `<h1>` back to the subject and the rest to sections. No
  separate subject/preheader form; a standalone subject header shows only in the empty/generate state.

Same RichEditor link-button gap as Article Writer (SDK/TipTap).

---

## Sidebar bug fix (2026-07-18) — panel clicks vs. chat.function calls

**Symptom:** clicking a different project in the sidebar updated the workspace board, but the sidebar
itself kept showing the *previous* project's expanded detail (keywords/goals) until a full page
reload.

**Root cause:** `_project_list_item`'s `on_click` called `ui.Call("__panel__workspace",
view="newsletters", project_id=p["id"])` directly. A plain panel-to-panel `ui.Call` only ever
refreshes the ONE panel it targets — the sidebar had no trigger to re-render on project switch.

**Fix:** the click now calls `open_project` — a real `@chat.function` with
`refresh_panels=["sidebar", "workspace"]`, the same mechanism `delete_newsletter`/`delete_project`
already use successfully. `open_project` also explicitly resets `newsletter_id` to `""` on switch.

---

## Proactivity (2026-07-18 — investigated and hardened)

**"Newsletter ready" notifications ship TWO ways now:**

1. **Direct `ctx.notify()` (the reliable path).** `skeleton_refresh_newsletter_writer_overview`
   persists its own "last-seen review count" in `ctx.store` (`newsletter_writer_notify_state`
   collection) and calls `ctx.notify(...)` directly whenever that count rises against the count it
   saved last time. This survives *any* kernel-side workflow respawn, because the baseline lives in
   our own durable storage, not in a Temporal workflow's in-memory state.
2. **`skeleton_alert_newsletter_writer_overview` (the kernel's own diff mechanism, kept as a harmless
   second layer)** — the platform's `IcnliSkeletonWorkflow` compares the previous skeleton snapshot to
   the new one and calls this tool when `review` count rises.

**Why #2 alone wasn't reliable (root cause, traced into the kernel source 2026-07-18):** live-observed
symptom — three newsletters were generated and finished, but no proactive notice ever arrived; Webbee
had to be asked explicitly and only saw "review" by reading the newsletters directly. The comparison
baseline (`_previous_data`) for path #2 lives *only* in the `IcnliSkeletonWorkflow` Temporal workflow
instance's memory. It survives the workflow's *own* periodic self-rotation (`continue_as_new` — the
kernel devs explicitly carry it forward there), but **not** the *parent* session workflow's own
periodic rotation, which kills the skeleton child (`ParentClosePolicy.TERMINATE`) and respawns a fresh
one on the next message — `workflows/session/skeleton_watchdog.py`'s `_spawn()` never passes
`previous_data` forward on that path. If generation finishes while that respawn happens to occur, the
newly-spawned workflow sees the already-changed state on its first tick with nothing to compare
against — the kernel's own alert is silently skipped, no error logged. Kernel-level gap, not fixable
from extension code; path #1 sidesteps it entirely.

**Deploy gotcha:** adding `ctx.notify()` requires declaring `"notify:push"` in
`Extension(capabilities=[...])`. Missing it doesn't produce a soft warning — the platform's deploy
validator (`I-NOTIFY-APP-ATTRIBUTED`) rejects the deploy outright and silently rolls back to the
previous commit. Confirmed live 2026-07-18.

**Proactive domain data** (unchanged): the chat description tells Webbee that fill categories are
free-form and to proactively offer to set up the reusable data the topic needs (promo codes w/
conditions, address/hours…) with conditions in each item `note`, so the writer states offers
accurately and never broadens a promise.

---

## Error handling (2026-07-18)

Every `call_backend()` failure now carries a structured `error_code` (SDK 5.9.9
`ActionResult.error(code=...)`) instead of bare prose:

| Situation | `error_code` | `retryable` |
|---|---|---|
| Backend URL/JWT not configured | `BACKEND_NOT_CONFIGURED` | false |
| Backend timed out | `BACKEND_TIMEOUT` | true |
| Backend unreachable (connection error) | `BACKEND_5XX` | true |
| 401 from backend | `PERMISSION_DENIED` | false |
| 404 from backend | `NOT_FOUND` | false |
| Backend 5xx | `BACKEND_5XX` | true |
| Backend other 4xx | `BACKEND_REJECTED` | false |
| Client-side "nothing to update/save" | `VALIDATION_MISSING_FIELD` | false |
| Placeholder-looking id (`"unknown"`, `""`, …) | Pydantic `ValidationError` at the arg gate, before any network call | — |

`_err()` lives once in `api_client.py` now (every `handlers_*.py` imports it) — previously each file
had its own copy that only ever built a code-less error.

---

## Cyrillic strip (2026-07-18)

Every `@chat.function`/`Extension`/`ChatExtension` description used to carry bilingual
`"Use for: русская фраза, english phrase"` trigger lists. Per policy, all of these are now
**English-only**. This does not reduce Russian-language usability: Webbee already understands
non-English chat input semantically without needing the literal phrase baked into a tool's
description. (The newsletters' own *generated content* for Russian-speaking audiences, e.g. the WHM
Moldova project, is untouched — that's real content, not a description/hint.)

---

## Pricing (per_action) — current + recommendation

Only `generate_newsletter` (multi-LLM pipeline) and `patch_newsletter` (2 LLM calls) spend backend
LLM tokens; `read_full`/`edit_full`/`export` spend Webbee context tokens (newsletters are short, so
small); the rest is cheap DB. Notes on the current prices:
- `list_*` = 10 ✓ (called constantly — including as the generation-done check — keep cheapest)
- create/update/delete/status/meta, fill/reference ops = 10–15 ✓
- `open_project` [NEW] → **0/free** — pure UI navigation, no LLM, no meaningful backend cost
- `update_newsletter_section`, `save_full_newsletter` (PANEL, 0 LLM) = 10 → **consider 0/min**
- `read_full_newsletter` 30 / `edit_full_newsletter` 20 → make **edit ≥ read** (editing outputs the whole body)
- `export_newsletter_text` [NEW] → **≥ read** (returns 2 copies text+html — shouldn't be cheaper than read)
- `patch_newsletter` = 30 ✓
- 🔴 `generate_newsletter` = 50 → **300–400**. It runs the SAME 4-call pipeline as `generate_article`
  (which is priced 800); a short email is ~40–55% of an article's tokens, not 6%. Currently it's
  priced like a `list` call and barely above `patch` — it must be the most expensive newsletter function.

---

## Tests

70 tests (`.venv/bin/pytest tests/ -q`):
- `test_handlers.py` — project CRUD, fill categories/items, **`open_project` refreshes both panels + resets `newsletter_id`**
- `test_newsletters.py` — newsletter CRUD, generate/patch, read_full/edit_full round-trip,
  **`export_newsletter_text` returns real HTML with no literal Markdown syntax**
- `test_richtext.py` — pure round-trip tests for markdown <-> HTML <-> plaintext <-> document
- `test_skeleton.py` — change-alert logic, **plus the new direct `ctx.notify()` path**: fires when
  review count rises against the persisted baseline, seeds silently on first-ever run, never
  re-notifies when the count is unchanged
- `test_params.py` — placeholder ids (`"unknown"`, `""`, …) rejected before any network call

---

## Open items

1. **Review issues not surfaced** — store the judge's actual notes in `quality_flags` (see pipeline above).
2. Optional cleanup — some projects may have both a `Promo codes` and a `Promo conditions` category;
   can be consolidated to one.
3. Backend open items → `newsletter-writer-backend/README.md`. Backend's own `patch.py`/`locate.py`/
   `llm_client.py` got the matching honesty fix, deployed to api-server 2026-07-17/18, covered by its
   own test suite there.

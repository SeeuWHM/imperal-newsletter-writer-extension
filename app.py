"""Newsletter Writer extension — core init + shared helpers.

Architecture (mirrors imperal-article-writer-extension's shared-backend
pattern exactly — see newsletter-writer-backend/README.md for the full
backend design):

  - Webbee assembles a project's context (brand voice, goals, keywords,
    reference links, MailerLite targeting label/groups) using whatever
    other extensions are installed — THIS extension has no idea those
    exist. It only persists that context and hands it to the backend
    when asked to generate or patch a newsletter.

  - The extension calls a SHARED backend microservice (newsletter-writer-api)
    that owns the Galera-backed database and the whole generation pipeline
    (outline -> draft -> mechanical gates -> judge -> targeted revision).
    The backend is multi-tenant by platform identity: every request carries
    the caller's `imperal_id` as `X-Imperal-Id`, and the backend scopes
    every query to it — never an external per-user API key, since there is
    no external account here (unlike SE Ranking or MailerLite itself).

  - newsletter-writer-api requires a platform JWT on every call. That token
    is NOT a per-user credential — it identifies this extension to the
    backend, same value for every installer — so it's declared as an
    ext.secret with write_mode="extension" (developer-set only, via
    developer.save_app_secret; never entered by end users, never
    committed to source).

  - Full newsletter bodies are read/edited ONLY through this extension's
    panel, which calls the backend directly with plain Python (zero LLM
    tokens, any corpus size). Chat-facing functions never return a full
    newsletter body — only metadata (see response_models.NewsletterSummaryRecord).

  - MailerLite itself is deliberately out of scope here — this extension
    never sees a MailerLite API key. A separate mailerlite-connector
    extension (future phase) owns that account/key and actually pushes a
    finished newsletter into a MailerLite campaign; this extension only
    stores a label + group id list as context for the writer (e.g. "who is
    this newsletter for").
"""
from __future__ import annotations

import os

from imperal_sdk import Extension, ChatExtension

# Shared backend bridge — same public API gateway host every extension on
# this platform calls. Not a secret: it's the platform's own microservice.
SERVER_URL = os.environ.get("NEWSLETTER_WRITER_BACKEND_URL", "") or "https://api.webhostmost.com/newsletter-writer"

ext = Extension(
    "imperal-newsletter-writer-extension",
    version="1.1.0",
    display_name="Newsletter Writer",
    description=(
        "Project-based email newsletter writing: keep per-project context (brand voice, goals, "
        "reference links, reusable 'fill' items like promo codes) and have newsletters written "
        "cheaply, with mechanical quality gates and self-review, grounded in that context. "
        "Read/edit full newsletters in the panel — chat never touches full bodies."
    ),
    icon="icon.svg",
    actions_explicit=True,
    capabilities=[
        "Project Context Store",
        "Reusable Fill Items (promo codes, links, topics)",
        "AI Newsletter Generation",
        "Mechanical Quality Gates",
        "Panel Newsletter Editor",
        "Natural-Language Newsletter Patching",
    ],
)

chat = ChatExtension(
    ext,
    tool_name="newsletter_writer",
    description=(
        "Newsletter Writer — project-based email newsletter writing. Use for: create/update a "
        "project's context (brand voice, goals, reference links — создай проект для рассылок, "
        "обнови контекст проекта), manage reusable fill items like promo codes or priority links "
        "(добавь категорию для промокодов, добавь промокод), list projects/newsletters (покажи "
        "проекты, покажи рассылки), create a newsletter and generate its draft (напиши рассылку, "
        "сгенерируй письмо), check generation status, patch a specific block by instruction "
        "(перепиши абзац про акцию), change newsletter status (idea/writing/review/scheduled/sent). "
        "Never returns full newsletter bodies to chat — full text is read/edited only in the "
        "Newsletter Writer panel."
    ),
    max_rounds=10,
)

ext.secret(
    name="backend_jwt",
    description=(
        "Platform JWT authenticating this extension to the newsletter-writer-api backend "
        "microservice. Developer-managed only — never entered or seen by end users."
    ),
    required=True,
    scope="app",  # app-scope secrets are owner-only regardless of write_mode
    env_fallback="IMPERAL_APPSECRET_NEWSLETTER_WRITER_BACKEND_JWT",
    max_bytes=2048,
)(lambda: None)


@ext.health_check
async def health(ctx) -> dict:
    """Report whether the backend JWT is configured."""
    jwt = await ctx.secrets.get("backend_jwt")
    return {"status": "ok" if jwt else "degraded", "version": ext.version}

"""Chat-function handlers: newsletters — metadata CRUD only.

Full newsletter bodies (blocks/sections) are read/edited exclusively in the
panel (panels_workspace.py), which calls the backend directly with plain
Python — zero LLM tokens regardless of corpus size. None of the functions
here ever return a full body — see response_models.NewsletterSummaryRecord's
docstring. Mirrors imperal-article-writer-extension/handlers_articles.py.

Actual content only ever gets written through generate_newsletter or
patch_newsletter (handlers_generate.py) — both go through the backend's real
pipeline. Nothing here does AI writing.
"""
# No `from __future__ import annotations` — see params.py for why.

from imperal_sdk import ui
from imperal_sdk.types import ActionResult

from app import chat
from api_client import call_backend
from params import (
    CreateNewsletterParams, ListNewslettersParams, NewsletterIdParams,
    UpdateNewsletterStatusParams, UpdateNewsletterMetaParams, UpdateNewsletterSectionParams,
    SaveFullNewsletterParams,
)
from response_models import NewsletterSummaryRecord, NewsletterListResponse, DeletedResponse
from richtext import html_to_sections


def _err(data: dict) -> ActionResult:
    return ActionResult.error(error=data.get("error", "unknown error"))


def _to_summary(n: dict) -> NewsletterSummaryRecord:
    return NewsletterSummaryRecord(
        id=n.get("id", ""), project_id=n.get("project_id", ""),
        subject=n.get("subject"), preheader=n.get("preheader"),
        status=n.get("status", "idea"), word_count=n.get("word_count", 0),
        model_used=n.get("model_used"), quality_flags=n.get("quality_flags"),
        mailerlite_campaign_id=n.get("mailerlite_campaign_id"),
        scheduled_at=str(n["scheduled_at"]) if n.get("scheduled_at") else None,
        sent_at=str(n["sent_at"]) if n.get("sent_at") else None,
    )


@chat.function(
    "create_newsletter",
    description=(
        "Create a new newsletter shell under a project — just a placeholder, no content yet. "
        "Does not call any AI. Follow up with generate_newsletter to actually write it. Use "
        "for: создай рассылку, новая рассылка, add a newsletter idea, start a new email draft."
    ),
    action_type="write",
    event="newsletter-writer.newsletter.created",
    effects=["create:newsletter"],
    data_model=NewsletterSummaryRecord,
)
async def fn_create_newsletter(ctx, params: CreateNewsletterParams) -> ActionResult:
    """Create an empty newsletter shell under a project; does not call any LLM."""
    body = params.model_dump(exclude_none=True, exclude={"project_id"})
    data = await call_backend(ctx, "POST", "/v1/newsletters",
                              json={"project_id": params.project_id, **body})
    if "error" in data:
        return _err(data)
    result = _to_summary(data)
    return ActionResult.success(data=result, summary=f"Created newsletter shell in project {params.project_id}.")


@chat.function(
    "list_newsletters",
    description=(
        "List newsletters (metadata only — id, subject, status, word count, quality flags — "
        "never the full body). Optionally filter by project or status. Use for: покажи рассылки, "
        "list newsletters, what's in review, show idea/writing/review/scheduled/sent newsletters."
    ),
    action_type="read",
    data_model=NewsletterListResponse,
)
async def fn_list_newsletters(ctx, params: ListNewslettersParams) -> ActionResult:
    """List newsletters (metadata only — never full block bodies), optionally filtered."""
    query: dict = {"limit": 100, "offset": 0}
    if params.project_id:
        query["project_id"] = params.project_id
    if params.status:
        query["status"] = params.status
    data = await call_backend(ctx, "GET", "/v1/newsletters", params=query)
    if "error" in data:
        return _err(data)
    rows = data.get("data") if isinstance(data.get("data"), list) else []
    rows = rows or []
    result = NewsletterListResponse(newsletters=[_to_summary(n) for n in rows], count=len(rows))
    ui_node = ui.DataTable(
        columns=[
            ui.DataColumn(key="subject", label="Subject", width="40%"),
            ui.DataColumn(key="status", label="Status", width="20%"),
            ui.DataColumn(key="word_count", label="Words", width="20%"),
        ],
        rows=[{"subject": n.subject or "(untitled)", "status": n.status, "word_count": n.word_count} for n in result.newsletters],
    ) if result.newsletters else None
    return ActionResult.success(data=result, summary=f"{result.count} newsletter(s)", ui=ui_node)


@chat.function(
    "update_newsletter_status",
    description=(
        "Move a newsletter to a new status: idea, writing, review, scheduled, sent. Use for: "
        "отправь в ревью, пометь как готово, move this newsletter to review/scheduled."
    ),
    action_type="write",
    event="newsletter-writer.newsletter.updated",
    effects=["update:newsletter"],
    data_model=NewsletterSummaryRecord,
)
async def fn_update_newsletter_status(ctx, params: UpdateNewsletterStatusParams) -> ActionResult:
    """Move a newsletter's kanban status (idea/writing/review/scheduled/sent)."""
    data = await call_backend(ctx, "PATCH", f"/v1/newsletters/{params.newsletter_id}/status",
                              json={"status": params.status})
    if "error" in data:
        return _err(data)
    result = _to_summary(data)
    return ActionResult.success(data=result, summary=f"Status set to {params.status}.")


@chat.function(
    "update_newsletter_meta",
    description=(
        "Fix a newsletter's subject and/or preheader without touching the body. Use for: "
        "поменяй тему письма, обнови прехедер, change the subject line."
    ),
    action_type="write",
    event="newsletter-writer.newsletter.updated",
    effects=["update:newsletter"],
    data_model=NewsletterSummaryRecord,
)
async def fn_update_newsletter_meta(ctx, params: UpdateNewsletterMetaParams) -> ActionResult:
    """Fix subject/preheader without touching block content."""
    body = params.model_dump(exclude_none=True, exclude={"newsletter_id"})
    if not body:
        return ActionResult.error(error="Nothing to update — provide subject and/or preheader.")
    data = await call_backend(ctx, "PATCH", f"/v1/newsletters/{params.newsletter_id}/meta", json=body)
    if "error" in data:
        return _err(data)
    result = _to_summary(data)
    return ActionResult.success(data=result, summary="Updated.")


@chat.function(
    "update_newsletter_section",
    description=(
        "PANEL-ONLY: directly overwrite one block's fields with EXACT values — a raw manual "
        "save, NOT an AI writing step (it skips the judge entirely). Not for chat use — Webbee "
        "should use generate_newsletter or patch_newsletter to write content."
    ),
    action_type="write",
    event="newsletter-writer.newsletter.section_saved",
    effects=["update:newsletter"],
    data_model=DeletedResponse,
)
async def fn_update_newsletter_section(ctx, params: UpdateNewsletterSectionParams) -> ActionResult:
    """Overwrite one block's fields verbatim — no AI involved."""
    fields = params.model_dump(exclude_none=True, exclude={"newsletter_id", "order_index"})
    if not fields:
        return ActionResult.error(error="Nothing to save — provide at least one field.")
    data = await call_backend(
        ctx, "PATCH", f"/v1/newsletters/{params.newsletter_id}/sections/{params.order_index}", json=fields,
    )
    if "error" in data:
        return _err(data)
    return ActionResult.success(
        data=DeletedResponse(deleted=False), summary="Block saved.", refresh_panels=["workspace"],
    )


@chat.function(
    "save_full_newsletter",
    description=(
        "PANEL-ONLY: replace the entire newsletter body from the panel's single merged editor. "
        "Splits the submitted document into {heading, content} sections at heading boundaries "
        "(see richtext.py) — this is the one path that lets a section be added/removed/reordered "
        "by editing the document directly. "
        "Not for chat use — Webbee should use generate_newsletter or patch_newsletter to write content."
    ),
    action_type="write",
    event="newsletter-writer.newsletter.section_saved",
    effects=["update:newsletter"],
    data_model=DeletedResponse,
)
async def fn_save_full_newsletter(ctx, params: SaveFullNewsletterParams) -> ActionResult:
    """Panel's single-editor Save — split the merged HTML back into blocks."""
    sections = html_to_sections(params.content_html)
    data = await call_backend(
        ctx, "PUT", f"/v1/newsletters/{params.newsletter_id}/sections",
        json={"sections": sections},
    )
    if "error" in data:
        return _err(data)
    return ActionResult.success(
        data=DeletedResponse(deleted=False), summary="Newsletter saved.", refresh_panels=["workspace"],
    )


@chat.function(
    "delete_newsletter",
    description="Permanently delete a newsletter. Use for: удали рассылку, delete this newsletter.",
    action_type="destructive",
    event="newsletter-writer.newsletter.deleted",
    effects=["delete:newsletter"],
    data_model=DeletedResponse,
)
async def fn_delete_newsletter(ctx, params: NewsletterIdParams) -> ActionResult:
    """Permanently delete a newsletter and all of its blocks/jobs."""
    data = await call_backend(ctx, "DELETE", f"/v1/newsletters/{params.newsletter_id}")
    if isinstance(data, dict) and "error" in data:
        return _err(data)
    result = DeletedResponse(deleted=True, id=params.newsletter_id)
    return ActionResult.success(data=result, summary="Deleted.")

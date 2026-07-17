"""Chat-function handlers: projects — the per-brand newsletter context store
— plus internal reference links (targets the writer may link to). Fill
categories/items live in handlers_fill.py (split out to keep files under the
federal-grade 300-line guideline).

Webbee fills a project's context in via whatever extensions are installed
(SE Ranking, GSC, Matomo, an Article Writer project for source facts, etc.)
— this extension only persists the assembled context; it has no idea those
extensions exist. Mirrors imperal-article-writer-extension/handlers_projects.py.

NOTE: unlike Article Writer's `/context` sub-route, this backend's project
update route is PATCH /v1/projects/{project_id} directly.
"""
# No `from __future__ import annotations` — see params.py for why.

from imperal_sdk import ui
from imperal_sdk.types import ActionResult

from app import chat
from api_client import call_backend, _err
from params import (
    CreateProjectParams, UpdateProjectContextParams, ProjectIdParams,
    AddReferenceLinkParams, RemoveReferenceLinkParams,
)
from response_models import (
    ProjectRecord, ProjectListResponse, DeletedResponse,
    ReferenceLinkRecord, ReferenceLinksResponse,
)
from pydantic import BaseModel


class _EmptyParams(BaseModel):
    """No input required."""


def _to_record(p: dict) -> ProjectRecord:
    return ProjectRecord(
        id=p.get("id", ""), name=p.get("name", ""), description=p.get("description"),
        brand_voice=p.get("brand_voice"), goals=p.get("goals"),
        keywords=p.get("keywords") or [], useful_links=p.get("useful_links") or [],
        social_links=p.get("social_links") or [],
        reference_links=p.get("reference_links") or [],
        mailerlite_account_label=p.get("mailerlite_account_label"),
        mailerlite_group_ids=p.get("mailerlite_group_ids") or [],
        reference_article_project_id=p.get("reference_article_project_id"),
    )


def _links_response(project_id: str, links: list) -> ReferenceLinksResponse:
    recs = [
        ReferenceLinkRecord(url=(l.get("url") or ""), description=(l.get("description") or ""))
        for l in links if isinstance(l, dict)
    ]
    return ReferenceLinksResponse(project_id=project_id, links=recs, count=len(recs))


# ── Projects ─────────────────────────────────────────────────────────────

@chat.function(
    "create_project",
    description=(
        "Create a new newsletter project — a container for one brand's context: goals, brand "
        "voice, keywords, useful links, socials, MailerLite targeting label. Use for: "
        "add a new newsletter project."
    ),
    action_type="write",
    event="newsletter-writer.project.created",
    effects=["create:project"],
    data_model=ProjectRecord,
)
async def fn_create_project(ctx, params: CreateProjectParams) -> ActionResult:
    """Create a new project context container for the caller's tenant."""
    data = await call_backend(ctx, "POST", "/v1/projects", json=params.model_dump(exclude_none=True))
    if "error" in data:
        return _err(data)
    record = _to_record(data)
    return ActionResult.success(
        data=record, summary=f'Created newsletter project "{record.name}".',
        refresh_panels=["sidebar"],
    )


@chat.function(
    "list_projects",
    description=(
        "List all newsletter projects — id, name, keywords, goals. Use for: "
        "list my newsletter projects, what newsletter projects do I have."
    ),
    action_type="read",
    chain_callable=True,
    data_model=ProjectListResponse,
)
async def fn_list_projects(ctx, params: _EmptyParams) -> ActionResult:
    """Return every project owned by the caller's tenant."""
    data = await call_backend(ctx, "GET", "/v1/projects", params={"limit": 100, "offset": 0})
    if "error" in data:
        return _err(data)
    raw = data.get("data") if isinstance(data.get("data"), list) else data.get("items") or []
    projects = [_to_record(p) for p in raw]
    result = ProjectListResponse(projects=projects, count=len(projects))
    rows = [
        {"name": p.name, "goals": p.goals or "", "keywords": ", ".join(p.keywords[:5])}
        for p in projects
    ]
    ui_node = ui.DataTable(
        columns=[
            ui.DataColumn(key="name", label="Project", width="30%"),
            ui.DataColumn(key="goals", label="Goals", width="35%"),
            ui.DataColumn(key="keywords", label="Keywords", width="35%"),
        ],
        rows=rows,
    ) if rows else ui.Empty(message="No newsletter projects yet — create one first.")
    return ActionResult.success(data=result, summary=f"{len(projects)} project(s)", ui=ui_node)


@chat.function(
    "update_project_context",
    description=(
        "Update a newsletter project's context — any of: name, description, brand voice, goals, "
        "keywords, useful links, social links, MailerLite targeting label/group ids. Only send "
        "fields that changed. Use for: add keywords to newsletter "
        "project, update brand voice, set MailerLite targeting."
    ),
    action_type="write",
    event="newsletter-writer.project.updated",
    effects=["update:project"],
    data_model=ProjectRecord,
)
async def fn_update_project_context(ctx, params: UpdateProjectContextParams) -> ActionResult:
    """Patch one or more context fields on an existing project."""
    fields = params.model_dump(exclude_none=True, exclude={"project_id"})
    if not fields:
        return ActionResult.error(
            error="Nothing to update — provide at least one field.", code="VALIDATION_MISSING_FIELD",
        )
    data = await call_backend(ctx, "PATCH", f"/v1/projects/{params.project_id}", json=fields)
    if "error" in data:
        return _err(data)
    record = _to_record(data)
    return ActionResult.success(
        data=record, summary=f'Updated "{record.name}".', refresh_panels=["sidebar"],
    )


@chat.function(
    "delete_project",
    description=(
        "Permanently delete a newsletter project and ALL its newsletters, fill categories and "
        "fill items. Use for: delete this newsletter project, remove "
        "newsletter site."
    ),
    action_type="destructive",
    event="newsletter-writer.project.deleted",
    effects=["delete:project"],
    data_model=DeletedResponse,
)
async def fn_delete_project(ctx, params: ProjectIdParams) -> ActionResult:
    """Delete a project and cascade-delete all of its newsletters/fill data."""
    data = await call_backend(ctx, "DELETE", f"/v1/projects/{params.project_id}")
    if "error" in data:
        return _err(data)
    return ActionResult.success(
        data=DeletedResponse(id=params.project_id), summary="Project deleted.",
        refresh_panels=["sidebar", "workspace"],
    )


# ── Reference links — internal-linking targets the writer may use ──────────

@chat.function(
    "add_reference_link",
    description=(
        "Add ONE internal page of THIS project's own site as a reference link the newsletter "
        "writer may link to, with a short description of what that page is about. The writer "
        "uses the description to weave a natural, in-sentence anchor. Use for: "
        "add an internal link for the newsletter writer."
    ),
    action_type="write",
    event="newsletter-writer.project.updated",
    effects=["update:project"],
    data_model=ReferenceLinksResponse,
)
async def fn_add_reference_link(ctx, params: AddReferenceLinkParams) -> ActionResult:
    """Append (or update, deduped by URL) one internal reference link on a project."""
    proj = await call_backend(ctx, "GET", f"/v1/projects/{params.project_id}")
    if "error" in proj:
        return _err(proj)
    url = params.url.strip()
    links = [l for l in (proj.get("reference_links") or [])
             if isinstance(l, dict) and (l.get("url") or "").strip() != url]
    links.append({"url": url, "description": params.description.strip()})
    data = await call_backend(ctx, "PATCH", f"/v1/projects/{params.project_id}",
                              json={"reference_links": links})
    if "error" in data:
        return _err(data)
    result = _links_response(params.project_id, data.get("reference_links") or [])
    return ActionResult.success(
        data=result, summary=f"Saved. {result.count} reference link(s) the writer can use.",
        refresh_panels=["sidebar", "workspace"],
    )


@chat.function(
    "list_reference_links",
    description=(
        "List the internal reference links saved on a newsletter project. Use for: "
        "list reference links, what internal links can the newsletter writer use."
    ),
    action_type="read",
    chain_callable=True,
    data_model=ReferenceLinksResponse,
)
async def fn_list_reference_links(ctx, params: ProjectIdParams) -> ActionResult:
    """Return a project's reference links — the writer's allowed internal-link targets."""
    proj = await call_backend(ctx, "GET", f"/v1/projects/{params.project_id}")
    if "error" in proj:
        return _err(proj)
    result = _links_response(params.project_id, proj.get("reference_links") or [])
    rows = [{"url": r.url, "description": r.description} for r in result.links]
    ui_node = ui.DataTable(
        columns=[
            ui.DataColumn(key="url", label="Page", width="45%"),
            ui.DataColumn(key="description", label="What it's about (anchor topic)", width="55%"),
        ],
        rows=rows,
    ) if rows else ui.Empty(message="No reference links yet — add pages the writer can link to.")
    return ActionResult.success(data=result, summary=f"{result.count} reference link(s).", ui=ui_node)


@chat.function(
    "remove_reference_link",
    description=(
        "Remove ONE internal reference link from a newsletter project by its URL. Use for: "
        "remove a reference link."
    ),
    action_type="destructive",
    event="newsletter-writer.project.updated",
    effects=["update:project"],
    data_model=ReferenceLinksResponse,
)
async def fn_remove_reference_link(ctx, params: RemoveReferenceLinkParams) -> ActionResult:
    """Drop one internal reference link (matched by URL) from a project."""
    proj = await call_backend(ctx, "GET", f"/v1/projects/{params.project_id}")
    if "error" in proj:
        return _err(proj)
    url = params.url.strip()
    links = [l for l in (proj.get("reference_links") or [])
             if isinstance(l, dict) and (l.get("url") or "").strip() != url]
    data = await call_backend(ctx, "PATCH", f"/v1/projects/{params.project_id}",
                              json={"reference_links": links})
    if "error" in data:
        return _err(data)
    result = _links_response(params.project_id, data.get("reference_links") or [])
    return ActionResult.success(
        data=result, summary=f"Removed. {result.count} reference link(s) left.",
        refresh_panels=["sidebar", "workspace"],
    )

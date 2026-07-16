"""Chat-function handlers: projects — the per-brand newsletter context store,
plus fill categories/items (the project's rotating "stock" — promo codes,
priority links, topics to cover — the generation pipeline draws from so the
same item isn't reused every time).

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
from api_client import call_backend
from params import (
    CreateProjectParams, UpdateProjectContextParams, ProjectIdParams,
    AddReferenceLinkParams, RemoveReferenceLinkParams,
    CreateFillCategoryParams, FillCategoryIdParams,
    CreateFillItemParams, UpdateFillItemParams, DeleteFillItemParams,
)
from response_models import (
    ProjectRecord, ProjectListResponse, DeletedResponse,
    ReferenceLinkRecord, ReferenceLinksResponse,
    FillCategoryRecord, FillCategoryListResponse,
    FillItemRecord, FillItemListResponse,
)
from pydantic import BaseModel


class _EmptyParams(BaseModel):
    """No input required."""


class _ProjectOnlyParams(BaseModel):
    project_id: str


def _err(data: dict) -> ActionResult:
    return ActionResult.error(error=data.get("error", "unknown error"))


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
        "voice, keywords, useful links, socials, MailerLite targeting label. Use for: создай "
        "проект рассылки, новый проект для newsletter, add a new newsletter project."
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
        "List all newsletter projects — id, name, keywords, goals. Use for: покажи мои проекты "
        "рассылок, list my newsletter projects, what newsletter projects do I have."
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
        "fields that changed. Use for: обнови проект рассылки, add keywords to newsletter "
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
        return ActionResult.error(error="Nothing to update — provide at least one field.")
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
        "fill items. Use for: удали проект рассылки, delete this newsletter project, remove "
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
        "uses the description to weave a natural, in-sentence anchor. Use for: добавь ссылку для "
        "перелинковки в рассылке, add an internal link for the newsletter writer."
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
        "List the internal reference links saved on a newsletter project. Use for: покажи ссылки "
        "для перелинковки, list reference links, what internal links can the newsletter writer use."
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
        "Remove ONE internal reference link from a newsletter project by its URL. Use for: убери "
        "ссылку для перелинковки, remove a reference link."
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


# ── Fill categories / items — the project's rotating "stock" ───────────────

@chat.function(
    "create_fill_category",
    description=(
        "Add a named 'stock' category (e.g. promo codes, priority links, topics to cover) to a "
        "newsletter project. Capped per project — ask the user proactively which categories they "
        "want. Use for: добавь категорию для рассылки, create a fill category, add a promo-code slot."
    ),
    action_type="write",
    event="newsletter-writer.project.updated",
    effects=["create:fill_category"],
    data_model=FillCategoryRecord,
)
async def fn_create_fill_category(ctx, params: CreateFillCategoryParams) -> ActionResult:
    """Add one named 'stock' category (promo codes, priority links, topics) to a project."""
    data = await call_backend(
        ctx, "POST", f"/v1/projects/{params.project_id}/fill-categories",
        json={"name": params.name, "category_type": params.category_type, "instructions": params.instructions},
    )
    if "error" in data:
        return _err(data)
    record = FillCategoryRecord(**data)
    return ActionResult.success(
        data=record, summary=f'Created fill category "{record.name}".',
        refresh_panels=["sidebar", "workspace"],
    )


@chat.function(
    "list_fill_categories",
    description=(
        "List the fill categories (promo codes, links, topics, etc.) on a newsletter project. "
        "Use for: покажи категории рассылки, list fill categories."
    ),
    action_type="read",
    chain_callable=True,
    data_model=FillCategoryListResponse,
)
async def fn_list_fill_categories(ctx, params: ProjectIdParams) -> ActionResult:
    """List a project's fill categories (metadata only, item counts not full values)."""
    data = await call_backend(ctx, "GET", f"/v1/projects/{params.project_id}/fill-categories")
    if "error" in data:
        return _err(data)
    raw = data if isinstance(data, list) else data.get("data") or []
    cats = [FillCategoryRecord(**c) for c in raw]
    result = FillCategoryListResponse(categories=cats, count=len(cats))
    rows = [{"name": c.name, "instructions": c.instructions or ""} for c in cats]
    ui_node = ui.DataTable(
        columns=[
            ui.DataColumn(key="name", label="Category", width="40%"),
            ui.DataColumn(key="instructions", label="Instructions", width="60%"),
        ],
        rows=rows,
    ) if rows else ui.Empty(message="No fill categories yet.")
    return ActionResult.success(data=result, summary=f"{result.count} fill categor{'y' if result.count == 1 else 'ies'}.", ui=ui_node)


@chat.function(
    "delete_fill_category",
    description=(
        "Permanently delete a fill category and all its items. Use for: удали категорию рассылки, "
        "delete this fill category."
    ),
    action_type="destructive",
    event="newsletter-writer.project.updated",
    effects=["delete:fill_category"],
    data_model=DeletedResponse,
)
async def fn_delete_fill_category(ctx, params: FillCategoryIdParams) -> ActionResult:
    """Permanently delete a fill category and all of its items."""
    data = await call_backend(
        ctx, "DELETE", f"/v1/projects/{params.project_id}/fill-categories/{params.category_id}",
    )
    if "error" in data:
        return _err(data)
    return ActionResult.success(
        data=DeletedResponse(id=params.category_id), summary="Fill category deleted.",
        refresh_panels=["sidebar", "workspace"],
    )


@chat.function(
    "create_fill_item",
    description=(
        "Add one value (a promo code, a specific link, a topic) to a fill category. The "
        "generation pipeline rotates through items least-used-first. Use for: добавь промокод, "
        "add an item to the category, add a value to fill category."
    ),
    action_type="write",
    event="newsletter-writer.project.updated",
    effects=["create:fill_item"],
    data_model=FillItemRecord,
)
async def fn_create_fill_item(ctx, params: CreateFillItemParams) -> ActionResult:
    """Add one value (e.g. a promo code) to an existing fill category."""
    data = await call_backend(
        ctx, "POST",
        f"/v1/projects/{params.project_id}/fill-categories/{params.category_id}/items",
        json={"value": params.value, "note": params.note},
    )
    if "error" in data:
        return _err(data)
    record = FillItemRecord(**data)
    return ActionResult.success(
        data=record, summary=f'Added item "{record.value}".', refresh_panels=["workspace"],
    )


@chat.function(
    "list_fill_items",
    description=(
        "List the items in a fill category, least-used-first. Use for: покажи элементы категории, "
        "list fill items."
    ),
    action_type="read",
    chain_callable=True,
    data_model=FillItemListResponse,
)
async def fn_list_fill_items(ctx, params: FillCategoryIdParams) -> ActionResult:
    """List items in a fill category, least-used-first (how the generator naturally rotates)."""
    data = await call_backend(
        ctx, "GET",
        f"/v1/projects/{params.project_id}/fill-categories/{params.category_id}/items",
    )
    if "error" in data:
        return _err(data)
    raw = data if isinstance(data, list) else data.get("data") or []
    items = [FillItemRecord(**i) for i in raw]
    result = FillItemListResponse(items=items, count=len(items))
    rows = [
        {"value": i.value, "note": i.note or "", "active": "yes" if i.is_active else "no",
         "times_used": i.times_used}
        for i in items
    ]
    ui_node = ui.DataTable(
        columns=[
            ui.DataColumn(key="value", label="Value", width="30%"),
            ui.DataColumn(key="note", label="Note", width="35%"),
            ui.DataColumn(key="active", label="Active", width="15%"),
            ui.DataColumn(key="times_used", label="Used", width="20%"),
        ],
        rows=rows,
    ) if rows else ui.Empty(message="No items in this category yet.")
    return ActionResult.success(data=result, summary=f"{result.count} item(s).", ui=ui_node)


@chat.function(
    "update_fill_item",
    description=(
        "Change a fill item's value/note, or retire it (is_active=false) without deleting its "
        "usage history — e.g. an expired promo code. Use for: обнови элемент категории, retire "
        "this promo code, deactivate fill item."
    ),
    action_type="write",
    event="newsletter-writer.project.updated",
    effects=["update:fill_item"],
    data_model=FillItemRecord,
)
async def fn_update_fill_item(ctx, params: UpdateFillItemParams) -> ActionResult:
    """Change a fill item's value/note, or retire it (is_active=false) in place."""
    fields = params.model_dump(exclude_none=True, exclude={"project_id", "category_id", "item_id"})
    if not fields:
        return ActionResult.error(error="Nothing to update — provide at least one field.")
    data = await call_backend(
        ctx, "PATCH",
        f"/v1/projects/{params.project_id}/fill-categories/{params.category_id}/items/{params.item_id}",
        json=fields,
    )
    if "error" in data:
        return _err(data)
    record = FillItemRecord(**data)
    return ActionResult.success(
        data=record, summary=f'Updated item "{record.value}".', refresh_panels=["workspace"],
    )


@chat.function(
    "delete_fill_item",
    description=(
        "Permanently delete one fill item. Use for: удали элемент категории, delete this fill item."
    ),
    action_type="destructive",
    event="newsletter-writer.project.updated",
    effects=["delete:fill_item"],
    data_model=DeletedResponse,
)
async def fn_delete_fill_item(ctx, params: DeleteFillItemParams) -> ActionResult:
    """Permanently delete one fill item."""
    data = await call_backend(
        ctx, "DELETE",
        f"/v1/projects/{params.project_id}/fill-categories/{params.category_id}/items/{params.item_id}",
    )
    if "error" in data:
        return _err(data)
    return ActionResult.success(
        data=DeletedResponse(id=params.item_id), summary="Fill item deleted.",
        refresh_panels=["workspace"],
    )

"""Chat-function handlers: fill categories/items — a project's rotating
"stock" (promo codes, priority links, topics to cover) that the generation
pipeline draws from least-used-first so the same item isn't reused every
time. Split out of handlers_projects.py to keep each file under the
federal-grade 300-line guideline; still mirrors
imperal-article-writer-extension's project-scoped-sub-resource conventions.
"""
# No `from __future__ import annotations` — see params.py for why.

from imperal_sdk import ui
from imperal_sdk.types import ActionResult

from app import chat
from api_client import call_backend
from params import (
    CreateFillCategoryParams, FillCategoryIdParams, ProjectIdParams,
    CreateFillItemParams, UpdateFillItemParams, DeleteFillItemParams,
)
from response_models import (
    DeletedResponse, FillCategoryRecord, FillCategoryListResponse,
    FillItemRecord, FillItemListResponse,
)


def _err(data: dict) -> ActionResult:
    return ActionResult.error(error=data.get("error", "unknown error"))


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

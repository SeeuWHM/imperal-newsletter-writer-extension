"""Unit tests — no network. MockContext + monkeypatched call_backend.

Mirrors imperal-article-writer-extension/tests/test_handlers.py's convention:
patch `call_backend` on the HANDLER module (where it's imported and used),
never on api_client (where it's merely defined) — patching the wrong one
lets the real function run and hit the network during tests.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pytest
from imperal_sdk.testing import MockContext
from imperal_sdk.testing.mock_secrets import MockSecretStore

import handlers_projects
import handlers_fill
from params import (
    CreateProjectParams, UpdateProjectContextParams, ProjectIdParams,
    AddReferenceLinkParams, RemoveReferenceLinkParams,
    CreateFillCategoryParams, FillCategoryIdParams,
    CreateFillItemParams, UpdateFillItemParams, DeleteFillItemParams,
)


class _EmptyParams:
    """Matches the handler modules' own local _EmptyParams — no fields."""


def _ctx(configured: bool = True) -> MockContext:
    ctx = MockContext(user_id="tenant-abc-123")
    ctx.secrets = MockSecretStore({"backend_jwt": "test-jwt"} if configured else {})
    return ctx


# ─── projects ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_project_success(monkeypatch):
    async def fake_call(ctx, method, path, **kw):
        assert method == "POST" and path == "/v1/projects"
        assert kw["json"]["name"] == "My Brand"
        return {"id": "p1", "name": "My Brand", "keywords": ["a", "b"]}

    monkeypatch.setattr(handlers_projects, "call_backend", fake_call)
    result = await handlers_projects.fn_create_project(_ctx(), CreateProjectParams(name="My Brand"))
    assert result.status == "success"
    assert result.data.name == "My Brand"
    assert result.data.keywords == ["a", "b"]


@pytest.mark.asyncio
async def test_create_project_backend_error(monkeypatch):
    async def fake_call(ctx, method, path, **kw):
        return {"error": "backend down"}

    monkeypatch.setattr(handlers_projects, "call_backend", fake_call)
    result = await handlers_projects.fn_create_project(_ctx(), CreateProjectParams(name="X"))
    assert result.status == "error"
    assert result.error == "backend down"


@pytest.mark.asyncio
async def test_list_projects_empty(monkeypatch):
    async def fake_call(ctx, method, path, **kw):
        return {"data": []}

    monkeypatch.setattr(handlers_projects, "call_backend", fake_call)
    result = await handlers_projects.fn_list_projects(_ctx(), _EmptyParams())
    assert result.status == "success"
    assert result.data.count == 0


@pytest.mark.asyncio
async def test_update_project_context_requires_a_field(monkeypatch):
    result = await handlers_projects.fn_update_project_context(
        _ctx(), UpdateProjectContextParams(project_id="p1")
    )
    assert result.status == "error"


@pytest.mark.asyncio
async def test_update_project_context_success(monkeypatch):
    async def fake_call(ctx, method, path, **kw):
        assert method == "PATCH" and path == "/v1/projects/p1"
        assert kw["json"] == {"goals": "grow signups"}
        return {"id": "p1", "name": "Brand", "goals": "grow signups"}

    monkeypatch.setattr(handlers_projects, "call_backend", fake_call)
    result = await handlers_projects.fn_update_project_context(
        _ctx(), UpdateProjectContextParams(project_id="p1", goals="grow signups")
    )
    assert result.status == "success"
    assert result.data.goals == "grow signups"


@pytest.mark.asyncio
async def test_delete_project_success(monkeypatch):
    async def fake_call(ctx, method, path, **kw):
        assert method == "DELETE" and path == "/v1/projects/p1"
        return {}

    monkeypatch.setattr(handlers_projects, "call_backend", fake_call)
    result = await handlers_projects.fn_delete_project(_ctx(), ProjectIdParams(project_id="p1"))
    assert result.status == "success"
    assert result.data.deleted is True


@pytest.mark.asyncio
async def test_open_project_refreshes_sidebar_and_workspace(monkeypatch):
    """2026-07-18 live bug: switching projects via the sidebar's ListItem only
    ever refreshed the workspace panel (a plain ui.Call("__panel__workspace",
    ...) targets one panel), so the sidebar silently kept showing the
    previous project's expanded detail until a full page reload. open_project
    must refresh both, and must reset newsletter_id (never carry over the
    previously-open newsletter into a different project)."""
    async def fake_call(ctx, method, path, **kw):
        assert method == "GET" and path == "/v1/projects/p2"
        return {"id": "p2", "name": "Other Brand", "keywords": ["a"]}

    saved = {}
    async def fake_save_nav(ctx, values):
        saved.update(values)

    monkeypatch.setattr(handlers_projects, "call_backend", fake_call)
    monkeypatch.setattr(handlers_projects, "save_nav", fake_save_nav)
    result = await handlers_projects.fn_open_project(_ctx(), ProjectIdParams(project_id="p2"))
    assert result.status == "success"
    assert result.data.name == "Other Brand"
    assert result.refresh_panels == ["sidebar", "workspace"]
    assert saved == {"view": "newsletters", "project_id": "p2", "newsletter_id": ""}


@pytest.mark.asyncio
async def test_add_reference_link_dedupes_by_url(monkeypatch):
    calls = []

    async def fake_call(ctx, method, path, **kw):
        calls.append((method, path, kw))
        if method == "GET":
            return {"reference_links": [{"url": "https://x.com/a", "description": "old"}]}
        return {"reference_links": kw["json"]["reference_links"]}

    monkeypatch.setattr(handlers_projects, "call_backend", fake_call)
    result = await handlers_projects.fn_add_reference_link(
        _ctx(), AddReferenceLinkParams(project_id="p1", url="https://x.com/a", description="new")
    )
    assert result.status == "success"
    assert result.data.count == 1
    assert result.data.links[0].description == "new"


@pytest.mark.asyncio
async def test_remove_reference_link(monkeypatch):
    async def fake_call(ctx, method, path, **kw):
        if method == "GET":
            return {"reference_links": [{"url": "https://x.com/a", "description": "d"}]}
        assert kw["json"]["reference_links"] == []
        return {"reference_links": []}

    monkeypatch.setattr(handlers_projects, "call_backend", fake_call)
    result = await handlers_projects.fn_remove_reference_link(
        _ctx(), RemoveReferenceLinkParams(project_id="p1", url="https://x.com/a")
    )
    assert result.status == "success"
    assert result.data.count == 0


# ─── fill categories / items ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_fill_category(monkeypatch):
    async def fake_call(ctx, method, path, **kw):
        assert path == "/v1/projects/p1/fill-categories"
        assert kw["json"] == {"name": "Promo codes", "category_type": "custom", "instructions": None}
        return {
            "id": "c1", "project_id": "p1", "name": "Promo codes", "category_type": "custom",
            "instructions": None, "order_index": 0, "item_count": 0,
        }

    monkeypatch.setattr(handlers_fill, "call_backend", fake_call)
    result = await handlers_fill.fn_create_fill_category(
        _ctx(), CreateFillCategoryParams(project_id="p1", name="Promo codes")
    )
    assert result.status == "success"
    assert result.data.name == "Promo codes"


@pytest.mark.asyncio
async def test_list_fill_categories(monkeypatch):
    async def fake_call(ctx, method, path, **kw):
        return [{
            "id": "c1", "project_id": "p1", "name": "Promo codes", "category_type": "custom",
            "instructions": "seasonal", "order_index": 0, "item_count": 2,
        }]

    monkeypatch.setattr(handlers_fill, "call_backend", fake_call)
    result = await handlers_fill.fn_list_fill_categories(_ctx(), ProjectIdParams(project_id="p1"))
    assert result.status == "success"
    assert result.data.count == 1
    assert result.data.categories[0].item_count == 2


@pytest.mark.asyncio
async def test_delete_fill_category(monkeypatch):
    async def fake_call(ctx, method, path, **kw):
        assert method == "DELETE"
        assert path == "/v1/projects/p1/fill-categories/c1"
        return {}

    monkeypatch.setattr(handlers_fill, "call_backend", fake_call)
    result = await handlers_fill.fn_delete_fill_category(
        _ctx(), FillCategoryIdParams(project_id="p1", category_id="c1")
    )
    assert result.status == "success"


@pytest.mark.asyncio
async def test_create_fill_item(monkeypatch):
    async def fake_call(ctx, method, path, **kw):
        assert path == "/v1/projects/p1/fill-categories/c1/items"
        assert kw["json"] == {"value": "SAVE10", "note": None}
        return {
            "id": "i1", "category_id": "c1", "value": "SAVE10", "note": None,
            "is_active": True, "times_used": 0, "last_used_at": None,
        }

    monkeypatch.setattr(handlers_fill, "call_backend", fake_call)
    result = await handlers_fill.fn_create_fill_item(
        _ctx(), CreateFillItemParams(project_id="p1", category_id="c1", value="SAVE10")
    )
    assert result.status == "success"
    assert result.data.value == "SAVE10"


@pytest.mark.asyncio
async def test_list_fill_items(monkeypatch):
    async def fake_call(ctx, method, path, **kw):
        return [{
            "id": "i1", "category_id": "c1", "value": "SAVE10", "note": None,
            "is_active": True, "times_used": 3, "last_used_at": None,
        }]

    monkeypatch.setattr(handlers_fill, "call_backend", fake_call)
    result = await handlers_fill.fn_list_fill_items(
        _ctx(), FillCategoryIdParams(project_id="p1", category_id="c1")
    )
    assert result.status == "success"
    assert result.data.count == 1
    assert result.data.items[0].times_used == 3


@pytest.mark.asyncio
async def test_update_fill_item(monkeypatch):
    async def fake_call(ctx, method, path, **kw):
        assert method == "PATCH"
        assert path == "/v1/projects/p1/fill-categories/c1/items/i1"
        assert kw["json"] == {"is_active": False}
        return {
            "id": "i1", "category_id": "c1", "value": "SAVE10", "note": None,
            "is_active": False, "times_used": 3, "last_used_at": None,
        }

    monkeypatch.setattr(handlers_fill, "call_backend", fake_call)
    result = await handlers_fill.fn_update_fill_item(
        _ctx(), UpdateFillItemParams(project_id="p1", category_id="c1", item_id="i1", is_active=False)
    )
    assert result.status == "success"
    assert result.data.is_active is False


@pytest.mark.asyncio
async def test_delete_fill_item(monkeypatch):
    async def fake_call(ctx, method, path, **kw):
        assert method == "DELETE"
        assert path == "/v1/projects/p1/fill-categories/c1/items/i1"
        return {}

    monkeypatch.setattr(handlers_fill, "call_backend", fake_call)
    result = await handlers_fill.fn_delete_fill_item(
        _ctx(), DeleteFillItemParams(project_id="p1", category_id="c1", item_id="i1")
    )
    assert result.status == "success"


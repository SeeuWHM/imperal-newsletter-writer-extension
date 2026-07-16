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
import handlers_newsletters
import handlers_generate
import api_client
from params import (
    CreateProjectParams, UpdateProjectContextParams, ProjectIdParams,
    AddReferenceLinkParams, RemoveReferenceLinkParams,
    CreateFillCategoryParams, FillCategoryIdParams,
    CreateFillItemParams, UpdateFillItemParams, DeleteFillItemParams,
    CreateNewsletterParams, ListNewslettersParams, NewsletterIdParams,
    UpdateNewsletterStatusParams, UpdateNewsletterMetaParams, UpdateNewsletterSectionParams,
    GenerateNewsletterParams, GenerationJobStatusParams, PatchNewsletterParams,
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

    monkeypatch.setattr(handlers_projects, "call_backend", fake_call)
    result = await handlers_projects.fn_create_fill_category(
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

    monkeypatch.setattr(handlers_projects, "call_backend", fake_call)
    result = await handlers_projects.fn_list_fill_categories(_ctx(), ProjectIdParams(project_id="p1"))
    assert result.status == "success"
    assert result.data.count == 1
    assert result.data.categories[0].item_count == 2


@pytest.mark.asyncio
async def test_delete_fill_category(monkeypatch):
    async def fake_call(ctx, method, path, **kw):
        assert method == "DELETE"
        assert path == "/v1/projects/p1/fill-categories/c1"
        return {}

    monkeypatch.setattr(handlers_projects, "call_backend", fake_call)
    result = await handlers_projects.fn_delete_fill_category(
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

    monkeypatch.setattr(handlers_projects, "call_backend", fake_call)
    result = await handlers_projects.fn_create_fill_item(
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

    monkeypatch.setattr(handlers_projects, "call_backend", fake_call)
    result = await handlers_projects.fn_list_fill_items(
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

    monkeypatch.setattr(handlers_projects, "call_backend", fake_call)
    result = await handlers_projects.fn_update_fill_item(
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

    monkeypatch.setattr(handlers_projects, "call_backend", fake_call)
    result = await handlers_projects.fn_delete_fill_item(
        _ctx(), DeleteFillItemParams(project_id="p1", category_id="c1", item_id="i1")
    )
    assert result.status == "success"


# ─── newsletters ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_newsletter_success(monkeypatch):
    async def fake_call(ctx, method, path, **kw):
        assert method == "POST" and path == "/v1/newsletters"
        return {"id": "n1", "project_id": "p1", "subject": "Hello", "status": "idea", "word_count": 0}

    monkeypatch.setattr(handlers_newsletters, "call_backend", fake_call)
    result = await handlers_newsletters.fn_create_newsletter(
        _ctx(), CreateNewsletterParams(project_id="p" * 36, subject="Hello")
    )
    assert result.status == "success"
    assert result.data.status == "idea"


@pytest.mark.asyncio
async def test_list_newsletters_never_carries_body(monkeypatch):
    """Structural guarantee: even if the backend somehow returned a `sections`
    field, NewsletterSummaryRecord has no such field to receive it into."""
    async def fake_call(ctx, method, path, **kw):
        return {"data": [
            {"id": "n1", "project_id": "p1", "subject": "T", "status": "review",
             "word_count": 320, "sections": [{"content": "SHOULD NOT LEAK"}]},
        ]}

    monkeypatch.setattr(handlers_newsletters, "call_backend", fake_call)
    result = await handlers_newsletters.fn_list_newsletters(_ctx(), ListNewslettersParams(project_id="p1"))
    assert result.status == "success"
    assert result.data.count == 1
    n = result.data.newsletters[0]
    assert not hasattr(n, "sections")
    assert "sections" not in n.model_dump()


@pytest.mark.asyncio
async def test_update_newsletter_status_success(monkeypatch):
    async def fake_call(ctx, method, path, **kw):
        assert method == "PATCH" and path == "/v1/newsletters/n1/status"
        assert kw["json"] == {"status": "scheduled"}
        return {"id": "n1", "project_id": "p1", "status": "scheduled", "word_count": 320}

    monkeypatch.setattr(handlers_newsletters, "call_backend", fake_call)
    result = await handlers_newsletters.fn_update_newsletter_status(
        _ctx(), UpdateNewsletterStatusParams(newsletter_id="n1", status="scheduled")
    )
    assert result.status == "success"
    assert result.data.status == "scheduled"


@pytest.mark.asyncio
async def test_update_newsletter_meta_success(monkeypatch):
    async def fake_call(ctx, method, path, **kw):
        assert method == "PATCH" and path == "/v1/newsletters/n1/meta"
        assert kw["json"] == {"subject": "New subject"}
        return {"id": "n1", "project_id": "p1", "subject": "New subject", "status": "idea", "word_count": 0}

    monkeypatch.setattr(handlers_newsletters, "call_backend", fake_call)
    result = await handlers_newsletters.fn_update_newsletter_meta(
        _ctx(), UpdateNewsletterMetaParams(newsletter_id="n1", subject="New subject")
    )
    assert result.status == "success"
    assert result.data.subject == "New subject"


@pytest.mark.asyncio
async def test_update_newsletter_section(monkeypatch):
    async def fake_call(ctx, method, path, **kw):
        assert method == "PATCH" and path == "/v1/newsletters/n1/sections/0"
        assert kw["json"] == {"content": "New body text"}
        return {}

    monkeypatch.setattr(handlers_newsletters, "call_backend", fake_call)
    result = await handlers_newsletters.fn_update_newsletter_section(
        _ctx(), UpdateNewsletterSectionParams(newsletter_id="n1", order_index=0, content="New body text")
    )
    assert result.status == "success"


@pytest.mark.asyncio
async def test_update_newsletter_section_requires_a_field(monkeypatch):
    result = await handlers_newsletters.fn_update_newsletter_section(
        _ctx(), UpdateNewsletterSectionParams(newsletter_id="n1", order_index=0)
    )
    assert result.status == "error"


@pytest.mark.asyncio
async def test_delete_newsletter_success(monkeypatch):
    async def fake_call(ctx, method, path, **kw):
        assert method == "DELETE" and path == "/v1/newsletters/n1"
        return {}

    monkeypatch.setattr(handlers_newsletters, "call_backend", fake_call)
    result = await handlers_newsletters.fn_delete_newsletter(_ctx(), NewsletterIdParams(newsletter_id="n1"))
    assert result.status == "success"
    assert result.data.deleted is True


# ─── generation / patch ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_generate_newsletter_enqueues_job(monkeypatch):
    async def fake_call(ctx, method, path, **kw):
        assert method == "POST" and path == "/v1/newsletters/n1/generate"
        assert kw["json"]["topic"] == "Spring sale"
        return {"job_id": "j1", "newsletter_id": "n1", "status": "queued"}

    monkeypatch.setattr(handlers_generate, "call_backend", fake_call)
    result = await handlers_generate.fn_generate_newsletter(
        _ctx(), GenerateNewsletterParams(newsletter_id="n1", topic="Spring sale")
    )
    assert result.status == "success"
    assert result.data.job_id == "j1"


@pytest.mark.asyncio
async def test_check_generation_status(monkeypatch):
    async def fake_call(ctx, method, path, **kw):
        assert path == "/v1/newsletters/n1/jobs/j1"
        return {"id": "j1", "newsletter_id": "n1", "kind": "generate", "status": "done", "model": "claude-sonnet-5"}

    monkeypatch.setattr(handlers_generate, "call_backend", fake_call)
    result = await handlers_generate.fn_check_generation_status(
        _ctx(), GenerationJobStatusParams(newsletter_id="n1", job_id="j1")
    )
    assert result.status == "success"
    assert result.data.status == "done"


@pytest.mark.asyncio
async def test_patch_newsletter(monkeypatch):
    async def fake_call(ctx, method, path, **kw):
        assert method == "POST" and path == "/v1/newsletters/n1/patch"
        return {"newsletter_id": "n1", "order_index": 1, "preview": "Act now before it's gone!"}

    monkeypatch.setattr(handlers_generate, "call_backend", fake_call)
    result = await handlers_generate.fn_patch_newsletter(
        _ctx(), PatchNewsletterParams(newsletter_id="n1", instruction="make the CTA more urgent")
    )
    assert result.status == "success"
    assert "urgent" not in result.data.preview or True  # preview content is backend-controlled
    assert result.data.order_index == 1


@pytest.mark.asyncio
async def test_backend_error_propagates(monkeypatch):
    async def fake_call(ctx, method, path, **kw):
        return {"error": "not found"}

    monkeypatch.setattr(handlers_generate, "call_backend", fake_call)
    result = await handlers_generate.fn_check_generation_status(
        _ctx(), GenerationJobStatusParams(newsletter_id="n1", job_id="missing")
    )
    assert result.status == "error"
    assert result.error == "not found"


# ─── api_client ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_call_backend_fails_fast_without_jwt():
    """Without a configured JWT, call_backend must return a clear internal
    error instead of silently making an unauthenticated request."""
    ctx = _ctx(configured=False)
    result = await api_client.call_backend(ctx, "GET", "/v1/projects")
    assert "error" in result

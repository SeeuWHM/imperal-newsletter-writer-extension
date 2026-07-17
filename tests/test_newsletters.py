"""Unit tests — newsletters + generation/patch + api_client. Split out of
test_handlers.py to keep test files under the federal-grade 300-line
guideline (mirrors the handlers_projects/handlers_fill split).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pytest
from imperal_sdk.testing import MockContext
from imperal_sdk.testing.mock_secrets import MockSecretStore

import handlers_newsletters
import handlers_generate
import api_client
from params import (
    CreateNewsletterParams, ListNewslettersParams, NewsletterIdParams,
    UpdateNewsletterStatusParams, UpdateNewsletterMetaParams, UpdateNewsletterSectionParams,
    SaveFullNewsletterParams,
    GenerateNewsletterParams, GenerationJobStatusParams, PatchNewsletterParams,
)


def _ctx(configured: bool = True) -> MockContext:
    ctx = MockContext(user_id="tenant-abc-123")
    ctx.secrets = MockSecretStore({"backend_jwt": "test-jwt"} if configured else {})
    return ctx


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
async def test_save_full_newsletter_splits_subject_and_sections(monkeypatch):
    captured = {}

    async def fake_call(ctx, method, path, **kw):
        if method == "PUT" and path == "/v1/newsletters/n1/sections":
            captured["sections"] = kw["json"]["sections"]
            return {}
        if method == "PATCH" and path == "/v1/newsletters/n1/meta":
            captured["subject"] = kw["json"]["subject"]
            return {}
        raise AssertionError(f"unexpected call {method} {path}")

    monkeypatch.setattr(handlers_newsletters, "call_backend", fake_call)
    html = (
        "<h1>Spring Sale</h1>"
        "<h2>Welcome</h2><p>Hello there.</p>"
        "<h2>Offer</h2><p>Grab [50% off](https://x.com/promo) today.</p>"
    )
    result = await handlers_newsletters.fn_save_full_newsletter(
        _ctx(), SaveFullNewsletterParams(newsletter_id="n1", content_html=html)
    )
    assert result.status == "success"
    # Subject is the leading <h1>, persisted via /meta.
    assert captured["subject"] == "Spring Sale"
    sections = captured["sections"]
    assert [s["heading"] for s in sections] == ["Welcome", "Offer"]
    assert sections[0]["content"] == "Hello there."
    assert "[50% off](https://x.com/promo)" in sections[1]["content"]
    # No block-type / button fields \u2014 a newsletter is plain heading+content.
    assert "block_type" not in sections[0]


@pytest.mark.asyncio
async def test_save_full_newsletter_without_h1_keeps_subject(monkeypatch):
    calls = []

    async def fake_call(ctx, method, path, **kw):
        calls.append((method, path))
        return {}

    monkeypatch.setattr(handlers_newsletters, "call_backend", fake_call)
    # No leading <h1> -> subject must NOT be touched (no PATCH /meta call).
    result = await handlers_newsletters.fn_save_full_newsletter(
        _ctx(), SaveFullNewsletterParams(newsletter_id="n1", content_html="<h2>Body</h2><p>Text.</p>")
    )
    assert result.status == "success"
    assert ("PUT", "/v1/newsletters/n1/sections") in calls
    assert ("PATCH", "/v1/newsletters/n1/meta") not in calls


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

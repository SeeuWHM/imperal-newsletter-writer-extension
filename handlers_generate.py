"""Chat-function handlers: AI generation, job polling, and natural-language
patching.

These are the ONLY two ways a newsletter's content should actually get
written — both run through the backend's real pipeline (outline -> draft ->
mechanical gates -> judge -> targeted revision for generate; locate -> edit
for patch). Neither ever returns a full body — generate_newsletter returns a
job you poll; patch_newsletter returns a short preview. Mirrors
imperal-article-writer-extension/handlers_generate.py.
"""
# No `from __future__ import annotations` — see params.py for why.

from imperal_sdk.types import ActionResult

from app import chat
from api_client import call_backend, _err, GENERATE_TIMEOUT, PATCH_TIMEOUT
from params import GenerateNewsletterParams, GenerationJobStatusParams, PatchNewsletterParams
from response_models import GenerationJobResponse, GenerationStatusResponse, PatchResult


@chat.function(
    "generate_newsletter",
    description=(
        "Start writing a newsletter's first draft using the project's context (brand voice, "
        "goals, fill categories) plus a topic/goal brief and any real source facts (from web "
        "search or other extensions, e.g. an Article Writer article or Matomo/GSC data) the "
        "draft's claims must be grounded in. Runs in the background. To check when it's done: if "
        "you generated just this ONE newsletter and want cost/model/error detail on THIS run, poll "
        "check_generation_status with the returned job_id; if you generated SEVERAL newsletters at "
        "once (or don't need per-run detail), it's simpler and more reliable to just call "
        "list_newsletters(status='review') a bit later instead of tracking every job_id — status "
        "lands on 'review' when ready either way. Use for: write the newsletter, draft this email."
    ),
    action_type="write",
    event="newsletter-writer.newsletter.generation_started",
    effects=["update:newsletter"],
    data_model=GenerationJobResponse,
)
async def fn_generate_newsletter(ctx, params: GenerateNewsletterParams) -> ActionResult:
    """Enqueue the full generation pipeline for a newsletter; returns a job to poll."""
    body = params.model_dump(exclude_none=True, exclude={"newsletter_id"})
    data = await call_backend(
        ctx, "POST", f"/v1/newsletters/{params.newsletter_id}/generate",
        json=body, timeout=GENERATE_TIMEOUT,
    )
    if "error" in data:
        return _err(data)
    result = GenerationJobResponse(
        job_id=data.get("job_id", ""), newsletter_id=data.get("newsletter_id", params.newsletter_id),
        status=data.get("status", "queued"),
    )
    return ActionResult.success(
        data=result,
        summary=(
            f"Generation started (job {result.job_id}). Poll check_generation_status for this one "
            "job, or just list_newsletters(status='review') later if you started several at once."
        ),
    )


@chat.function(
    "check_generation_status",
    description=(
        "Check ONE specific generate_newsletter job by its job_id — status, model used, cost, "
        "error detail. This needs the exact (newsletter_id, job_id) pair from when you started it, "
        "so it does NOT scale well to checking several newsletters generated in the same turn — for "
        "that, call list_newsletters(status='review') instead, which needs no job_id at all and "
        "just shows what's actually ready right now. Use this one only when you genuinely need the "
        "per-run cost/model/error detail for a single job. Use for: check generation progress for "
        "this one job, what model/cost did this generation use."
    ),
    action_type="read",
    data_model=GenerationStatusResponse,
)
async def fn_check_generation_status(ctx, params: GenerationJobStatusParams) -> ActionResult:
    """Poll a generate_newsletter job — status, model used, cost estimate."""
    data = await call_backend(ctx, "GET", f"/v1/newsletters/{params.newsletter_id}/jobs/{params.job_id}")
    if "error" in data:
        return _err(data)
    result = GenerationStatusResponse(
        id=data.get("id", ""), newsletter_id=data.get("newsletter_id", params.newsletter_id),
        kind=data.get("kind", ""), status=data.get("status", ""), model=data.get("model"),
        tokens_used=data.get("tokens_used"), cost_estimate=data.get("cost_estimate"),
        error=data.get("error"),
    )
    return ActionResult.success(data=result, summary=f"Job status: {result.status}.")


@chat.function(
    "patch_newsletter",
    description=(
        "Rewrite ONE block of a newsletter by natural-language instruction (e.g. 'rewrite the "
        "block about the promo to be more urgent', 'shorten the intro'). Locates the block "
        "automatically (heading/keyword match) and returns a short preview — never the full "
        "body. Use for: shorten this newsletter's intro, make the CTA punchier."
    ),
    action_type="write",
    event="newsletter-writer.newsletter.patched",
    effects=["update:newsletter"],
    data_model=PatchResult,
)
async def fn_patch_newsletter(ctx, params: PatchNewsletterParams) -> ActionResult:
    """Locate and rewrite ONE block by natural-language instruction; returns a short preview."""
    body = params.model_dump(exclude_none=True, exclude={"newsletter_id"})
    data = await call_backend(
        ctx, "POST", f"/v1/newsletters/{params.newsletter_id}/patch",
        json=body, timeout=PATCH_TIMEOUT,
    )
    if "error" in data:
        return _err(data)
    matched = data.get("matched", True)
    result = PatchResult(
        matched=matched, replaced_count=data.get("replaced_count", 1 if matched else 0),
        order_index=data.get("order_index"), heading=data.get("heading"),
        preview=data.get("preview", ""),
    )
    if not matched:
        summary = (
            "Could not find any block containing that text — nothing was changed. "
            "Check the target text is still in the newsletter (read_full_newsletter) before retrying."
        )
    else:
        summary = f"Patched block {result.order_index}."
    return ActionResult.success(data=result, summary=summary)

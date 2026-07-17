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
from params import GenerateNewsletterParams, PatchNewsletterParams
from response_models import GenerationJobResponse, PatchResult


@chat.function(
    "generate_newsletter",
    description=(
        "Start writing a newsletter's first draft using the project's context (brand voice, "
        "goals, fill categories) plus a topic/goal brief and any real source facts (from web "
        "search or other extensions, e.g. an Article Writer article or Matomo/GSC data) the "
        "draft's claims must be grounded in. Runs in the background — it does not block. To see "
        "when it's done, call list_newsletters(status='review') a bit later: a newsletter's status "
        "lands on 'review' the moment its draft is ready, so that one call shows everything that "
        "finished — no job_id tracking needed. Use for: write the newsletter, draft this email."
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
            f"Generation started (job {result.job_id}). Call list_newsletters(status='review') a "
            "little later to see it once the draft is ready."
        ),
    )


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

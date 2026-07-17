"""Skeleton context providers for Newsletter Writer.

Per Imperal SDK: skeleton = LLM context cache holding ready API responses.
More data here = better Webbee routing and answers, with zero extra
round-trips. Never carries full newsletter bodies — same rule as the chat
functions (response_models.NewsletterSummaryRecord docstring). Mirrors
imperal-article-writer-extension/skeleton.py.
"""
from app import ext
from api_client import call_backend


@ext.skeleton("newsletter_writer_overview", ttl=60, alert=True,
              description="Newsletter Writer projects + newsletter counts by status — degrades to zeros if backend unreachable")
async def skeleton_refresh_overview(ctx) -> dict:
    # Skeleton contract: return {"response": <flat-scalars dict>} — the outer
    # "response" wrapper is MANDATORY (returning the inner dict directly is a
    # federal error the kernel rejects, which is what made this skeleton fail
    # to save). Keep it small: scalars + counts only, never full project rows.
    projects_data = await call_backend(ctx, "GET", "/v1/projects", params={"limit": 100, "offset": 0})
    projects = projects_data.get("data") if isinstance(projects_data.get("data"), list) else []
    projects = projects or []

    # limit must be <= 100 (backend caps it via Query(le=100)); 200 returned a
    # 422 every refresh, so newsletter counts never populated. Use the paged
    # `total` for the true count regardless of page size.
    newsletters_data = await call_backend(ctx, "GET", "/v1/newsletters", params={"limit": 100, "offset": 0})
    newsletters = newsletters_data.get("data") if isinstance(newsletters_data.get("data"), list) else []
    newsletters = newsletters or []

    project_count = projects_data.get("total", len(projects)) if isinstance(projects_data, dict) else len(projects)
    newsletter_count = newsletters_data.get("total", len(newsletters)) if isinstance(newsletters_data, dict) else len(newsletters)

    by_status = {"idea": 0, "writing": 0, "review": 0, "scheduled": 0, "sent": 0}
    for n in newsletters:
        s = n.get("status", "idea")
        by_status[s] = by_status.get(s, 0) + 1

    # Subject of the most-recently-updated newsletter sitting in "review" —
    # this is what a just-finished generation lands as. The paired alert tool
    # fires when the review count goes up and names this one, so Webbee can
    # proactively tell the user "<subject> is ready" the moment it's written.
    review_items = [n for n in newsletters if n.get("status") == "review"]
    latest_ready = ""
    if review_items:
        newest = max(review_items, key=lambda n: n.get("updated_at") or "")
        latest_ready = (newest.get("subject") or "(untitled)")[:60]

    if not projects and "error" in projects_data:
        instruction = (
            "Newsletter Writer backend is unreachable right now — tell the user generation/project "
            "actions may fail, but don't block on it."
        )
    elif not projects:
        instruction = "No projects yet — create one with create_project before writing newsletters."
    else:
        instruction = (
            f"{project_count} project(s), {newsletter_count} newsletter(s) total: "
            + ", ".join(f"{v} {k}" for k, v in by_status.items())
            + ". Use list_projects/list_newsletters for details, generate_newsletter to write, "
              "patch_newsletter for targeted edits. Full bodies are edited in the panel only."
        )

    return {"response": {
        "project_count": project_count,
        "newsletter_count": newsletter_count,
        "by_status": by_status,
        "latest_ready": latest_ready,
        "instruction": instruction,
    }}


@ext.tool(
    "skeleton_alert_newsletter_writer_overview",
    description="Fires when a newsletter finishes generating and lands in 'review' — proactive 'your newsletter is ready' notice.",
)
async def skeleton_alert_newsletter_writer_overview(ctx, old: dict | None = None, new: dict | None = None) -> dict:
    """Compare the previous vs current skeleton snapshot; if the number of
    newsletters in 'review' went up, a generation just finished — return a
    short notice naming the newest one so Webbee tells the user proactively.
    Returns {"response": ""} (no alert) on first snapshot or no change."""
    try:
        if not old or not new:
            return {"response": ""}
        old_review = int((old.get("by_status") or {}).get("review", 0))
        new_review = int((new.get("by_status") or {}).get("review", 0))
        if new_review <= old_review:
            return {"response": ""}
        latest = (new.get("latest_ready") or "").strip()
        added = new_review - old_review
        if latest and added == 1:
            return {"response": f'Your newsletter "{latest}" is written and ready for review in the Newsletter Writer panel.'}
        return {"response": f"{added} newsletters just finished and are ready for review in the Newsletter Writer panel."}
    except Exception:
        return {"response": ""}

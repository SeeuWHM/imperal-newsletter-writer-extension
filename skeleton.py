"""Skeleton context providers for Newsletter Writer.

Per Imperal SDK: skeleton = LLM context cache holding ready API responses.
More data here = better Webbee routing and answers, with zero extra
round-trips. Never carries full newsletter bodies — same rule as the chat
functions (response_models.NewsletterSummaryRecord docstring). Mirrors
imperal-article-writer-extension/skeleton.py.
"""
from app import ext
from api_client import call_backend


@ext.skeleton("newsletter_writer_overview", ttl=60,
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
        "instruction": instruction,
    }}

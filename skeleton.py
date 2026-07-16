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
    projects_data = await call_backend(ctx, "GET", "/v1/projects", params={"limit": 100, "offset": 0})
    projects = projects_data.get("data") if isinstance(projects_data.get("data"), list) else []
    projects = projects or []

    newsletters_data = await call_backend(ctx, "GET", "/v1/newsletters", params={"limit": 200, "offset": 0})
    newsletters = newsletters_data.get("data") if isinstance(newsletters_data.get("data"), list) else []
    newsletters = newsletters or []

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
            f"{len(projects)} project(s), {len(newsletters)} newsletter(s) total: "
            + ", ".join(f"{v} {k}" for k, v in by_status.items())
            + ". Use list_projects/list_newsletters for details, generate_newsletter to write, "
              "patch_newsletter for targeted edits. Full bodies are edited in the panel only."
        )

    return {
        "projects": projects[:20],
        "newsletter_counts_by_status": by_status,
        "total_projects": len(projects),
        "total_newsletters": len(newsletters),
        "instruction": instruction,
    }

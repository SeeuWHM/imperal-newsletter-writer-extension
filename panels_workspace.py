"""Center workspace panel — newsletter board + newsletter editor.

Reads/edits full newsletter bodies directly via plain server-side Python
(call_backend) — no LLM completion is ever involved in rendering this panel
or in submitting its forms, so it costs zero LLM tokens regardless of how
many newsletters or how long they are. This is the ONLY place full
newsletter bodies are ever displayed — chat functions never receive them
(see response_models.NewsletterSummaryRecord's docstring).

A newsletter is a plain heading+content document, exactly like an Article
Writer article. The panel edits the WHOLE newsletter as one seamless merged
ui.RichEditor document (richtext.sections_to_html / richtext.html_to_sections)
— headings are real <h2>s inside the same editor, not N separate per-section
forms. Saving posts the whole document to save_full_newsletter, which splits
it back into {heading, content} sections at heading boundaries — exactly
Article Writer's save_full_article contract. Layout/buttons/images are the
sending tool's job (MailerLite); here it's the copy.

Routing: `__panel__workspace` accepts (view, project_id, newsletter_id) as
plain kwargs (SDK panel mechanism — see imperal_sdk.extension.Extension.panel).
Buttons/list items pass them via ui.Call("__panel__workspace", **kwargs). A
tiny nav-state doc in ctx.store remembers the last position across a plain
reload (no kwargs) — it holds only IDs/view name, never newsletter content.
"""
from __future__ import annotations

from imperal_sdk import ui

from app import ext
from api_client import call_backend
from cache_helpers import LIST_CACHE_TTL, cached_call
from navstate import load_nav, save_nav
from richtext import document_to_html

STATUS_ORDER = ["idea", "writing", "review", "scheduled", "sent"]
STATUS_COLOR = {"idea": "gray", "writing": "blue", "review": "yellow", "scheduled": "purple", "sent": "green"}


def _back_button(project_id: str) -> ui.UINode:
    return ui.Button(label="← Back to newsletters", variant="ghost", size="sm",
                      on_click=ui.Call("__panel__workspace", view="newsletters", project_id=project_id))


async def _render_newsletters_view(ctx, project_id: str) -> ui.UINode:
    if not project_id:
        return ui.Empty(message="Pick a project on the left, or create one, to see its newsletters.")

    data = await cached_call(
        ctx, "newsletters_board", ctx.user.imperal_id, {"project_id": project_id}, LIST_CACHE_TTL,
        lambda: call_backend(ctx, "GET", "/v1/newsletters", params={"project_id": project_id, "limit": 100, "offset": 0}),
    )
    if "error" in data:
        return ui.Alert(message=data["error"], type="error")
    newsletters = data.get("data") if isinstance(data.get("data"), list) else []
    newsletters = newsletters or []

    by_status: dict[str, list] = {s: [] for s in STATUS_ORDER}
    for n in newsletters:
        by_status.setdefault(n.get("status", "idea"), []).append(n)

    columns = []
    for status in STATUS_ORDER:
        items = by_status.get(status, [])
        columns.append(ui.Column(gap=2, children=[
            ui.Header(text=f"{status.capitalize()} · {len(items)}", level=6),
            *([
                ui.List(items=[
                    ui.ListItem(
                        id=n["id"], title=n.get("subject") or "(untitled)",
                        subtitle=f"{n.get('word_count', 0)} words",
                        badge=ui.Badge(label=status, color=STATUS_COLOR.get(status, "gray")),
                        on_click=ui.Call("__panel__workspace", view="newsletter", project_id=project_id, newsletter_id=n["id"]),
                    )
                    for n in items
                ]),
            ] if items else [ui.Text(content="—", variant="caption")]),
        ]))

    # No "+ New newsletter" form here — Webbee creates newsletters via chat
    # (create_newsletter); this panel's job is navigation + reading/editing,
    # not duplicating actions Webbee already owns.
    return ui.Grid(columns=len(STATUS_ORDER), gap=3, children=columns)


def _newsletter_editor(newsletter_id: str, subject: str, sections: list[dict]) -> ui.UINode:
    """One seamless editable document — the SUBJECT is the leading <h1> and
    each section heading is an <h2>, all inside the same RichEditor. No
    separate subject field, no separate save button per part: Save writes the
    whole thing at once — the first <h1> becomes the subject, the rest becomes
    the body (richtext.html_to_document). What is the subject vs the body is
    left to whoever sends it (MailerLite via a connector)."""
    return ui.Form(
        action="save_full_newsletter",
        submit_label="Save newsletter",
        defaults={"newsletter_id": newsletter_id},
        children=[
            ui.RichEditor(param_name="content_html", content=document_to_html(subject, sections)),
        ],
    )


async def _render_newsletter_view(ctx, project_id: str, newsletter_id: str) -> ui.UINode:
    if not newsletter_id:
        return ui.Empty(message="No newsletter selected.")

    data = await call_backend(ctx, "GET", f"/v1/newsletters/{newsletter_id}")
    if "error" in data:
        return ui.Stack(children=[_back_button(project_id), ui.Alert(message=data["error"], type="error")])

    project_id = project_id or data.get("project_id", "")
    quality_flags = data.get("quality_flags") or {}
    flags = quality_flags.get("flags") if isinstance(quality_flags, dict) else None
    flags = flags or []
    sections = data.get("sections") or []
    status = data.get("status", "idea")

    delete_btn = ui.Button(label="Delete newsletter", icon="Trash2", variant="danger", size="sm",
                           on_click=ui.Call("delete_newsletter", newsletter_id=newsletter_id))

    top_bar = ui.Stack(direction="h", gap=2, justify="between", align="center", wrap=True, children=[
        _back_button(project_id), delete_btn,
    ])

    badges = ui.Stack(direction="h", gap=2, wrap=True, children=[
        ui.Badge(label=status, color=STATUS_COLOR.get(status, "gray")),
        ui.Badge(label=f"{data.get('word_count', 0)} words", color="gray"),
        *([ui.Badge(label=f.get("code", str(f)) if isinstance(f, dict) else str(f), color="yellow") for f in flags]),
    ])

    status_form = ui.Form(
        action="update_newsletter_status", submit_label="Update status",
        defaults={"newsletter_id": newsletter_id},
        children=[
            ui.Select(param_name="status", value=status, options=[
                {"value": s, "label": s.capitalize()} for s in STATUS_ORDER
            ]),
        ],
    )

    # Subject lives INSIDE the editor as the leading <h1> — no separate
    # subject/preheader form. The preheader is still generated + stored by the
    # backend (and Webbee can adjust it via chat / a connector uses it as the
    # inbox preview line); it's just not a manual field cluttering the panel.
    header_nodes: list = []
    if not sections:
        # Nothing to edit yet: show the subject for orientation + the generate
        # form. Once generated, the subject becomes the editor's <h1> instead.
        header_nodes.append(ui.Header(text=data.get("subject") or "(untitled)", level=4))
        body = ui.Form(
            action="generate_newsletter", submit_label="Generate first draft",
            defaults={"newsletter_id": newsletter_id},
            children=[
                ui.Input(param_name="topic", placeholder="Topic (required)"),
                ui.Input(param_name="goal", placeholder="Goal (optional, e.g. drive signups)"),
                ui.TagInput(param_name="source_snippets",
                            placeholder="Real facts/data to ground the newsletter in (optional)"),
            ],
        )
    else:
        # No "Patch with AI" form here — that's Webbee's job via chat
        # (patch_newsletter); this panel edits the merged document directly.
        body = _newsletter_editor(newsletter_id, data.get("subject") or "", sections)

    return ui.Stack(gap=3, className="px-4 pb-4", children=[
        top_bar,
        *header_nodes,
        badges,
        status_form,
        ui.Divider(),
        body,
    ])


@ext.panel("workspace", slot="center", title="Newsletter Writer", icon="Mail",
           refresh="on_event:newsletter-writer.newsletter.created,newsletter-writer.newsletter.status_changed,"
                   "newsletter-writer.newsletter.section_saved,newsletter-writer.newsletter.patched,"
                   "newsletter-writer.newsletter.deleted,newsletter-writer.newsletter.generation_started,"
                   "newsletter-writer.project.deleted")
async def workspace_panel(ctx, view: str = "", project_id: str = "", newsletter_id: str = ""):
    nav = await load_nav(ctx)
    view = view or nav.get("view") or "newsletters"
    project_id = project_id or nav.get("project_id") or ""
    newsletter_id = newsletter_id or nav.get("newsletter_id") or ""

    await save_nav(ctx, {"view": view, "project_id": project_id, "newsletter_id": newsletter_id})

    if view == "newsletter":
        return await _render_newsletter_view(ctx, project_id, newsletter_id)
    return await _render_newsletters_view(ctx, project_id)

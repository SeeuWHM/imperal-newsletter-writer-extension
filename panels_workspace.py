"""Center workspace panel — newsletter board + newsletter editor.

Reads/edits full newsletter bodies directly via plain server-side Python
(call_backend) — no LLM completion is ever involved in rendering this panel
or in submitting its forms, so it costs zero LLM tokens regardless of how
many newsletters or how long they are. This is the ONLY place full
newsletter bodies are ever displayed — chat functions never receive them
(see response_models.NewsletterSummaryRecord's docstring).

Unlike Article Writer's plain-text sections, a newsletter block has a
block_type (text/button/image/divider) with distinct fields per kind — so
this panel edits blocks individually (list + per-block form) rather than
force-fitting everything into one merged rich-text document.

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
from navstate import load_nav, save_nav

STATUS_ORDER = ["idea", "writing", "review", "scheduled", "sent"]
STATUS_COLOR = {"idea": "gray", "writing": "blue", "review": "yellow", "scheduled": "purple", "sent": "green"}
BLOCK_TYPES = ["text", "button", "image", "divider"]


def _back_button(project_id: str) -> ui.UINode:
    return ui.Button(label="← Back to newsletters", variant="ghost", size="sm",
                      on_click=ui.Call("__panel__workspace", view="newsletters", project_id=project_id))


async def _render_newsletters_view(ctx, project_id: str) -> ui.UINode:
    if not project_id:
        return ui.Empty(message="Pick a project on the left, or create one, to see its newsletters.")

    data = await call_backend(ctx, "GET", "/v1/newsletters", params={"project_id": project_id, "limit": 100, "offset": 0})
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


def _block_card(newsletter_id: str, order_index: int, s: dict) -> ui.UINode:
    block_type = s.get("block_type", "text")
    fields = [
        ui.Select(param_name="block_type", value=block_type,
                  options=[{"value": b, "label": b.capitalize()} for b in BLOCK_TYPES]),
        ui.Input(param_name="heading", value=s.get("heading") or "", placeholder="Heading (optional)"),
    ]
    if block_type == "button":
        fields.append(ui.Input(param_name="button_url", value=s.get("button_url") or "", placeholder="Button URL"))
        fields.append(ui.Input(param_name="button_label", value=s.get("button_label") or "", placeholder="Button label"))
    elif block_type == "image":
        fields.append(ui.Input(param_name="image_url", value=s.get("image_url") or "", placeholder="Image URL"))
        fields.append(ui.Input(param_name="image_alt", value=s.get("image_alt") or "", placeholder="Alt text"))
    if block_type != "divider":
        fields.append(ui.TextArea(param_name="content", value=s.get("content") or "", rows=4, placeholder="Block content"))

    return ui.Card(children=[
        ui.Form(
            action="update_newsletter_section", submit_label=f"Save block #{order_index}",
            defaults={"newsletter_id": newsletter_id, "order_index": order_index},
            children=fields,
        ),
    ])


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

    meta_form = ui.Form(
        action="update_newsletter_meta", submit_label="Update subject/preheader",
        defaults={"newsletter_id": newsletter_id},
        children=[
            ui.Input(param_name="subject", value=data.get("subject") or "", placeholder="Subject line"),
            ui.Input(param_name="preheader", value=data.get("preheader") or "", placeholder="Preheader"),
        ],
    )

    status_form = ui.Form(
        action="update_newsletter_status", submit_label="Update status",
        defaults={"newsletter_id": newsletter_id},
        children=[
            ui.Select(param_name="status", value=status, options=[
                {"value": s, "label": s.capitalize()} for s in STATUS_ORDER
            ]),
        ],
    )

    if not sections:
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
        # (patch_newsletter); this panel edits blocks directly, it doesn't
        # duplicate Webbee's own AI-writing actions.
        body = ui.Stack(gap=2, children=[
            _block_card(newsletter_id, s.get("order_index", i), s) for i, s in enumerate(sections)
        ])

    return ui.Stack(gap=3, className="px-4 pb-4", children=[
        top_bar,
        ui.Header(text=data.get("subject") or "(untitled)", level=4),
        badges,
        meta_form,
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

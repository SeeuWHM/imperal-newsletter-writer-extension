"""Pydantic param models for Newsletter Writer chat functions.

Mirrors the backend's own request schemas exactly (see
newsletter-writer-backend/service/apps/{projects,newsletters}/schemas.py) —
this extension is a thin, faithful client, not a second source of truth for
validation rules.
"""
# No `from __future__ import annotations` — chat.function's param validator
# needs real runtime type annotations (see se-ranking-connector/handlers.py
# for the same convention/reasoning).

from typing import List, Optional
from pydantic import BaseModel, Field


# ── Projects ─────────────────────────────────────────────────────────────

class CreateProjectParams(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="Project name")
    description: Optional[str] = Field(default=None, max_length=5000)
    brand_voice: Optional[str] = Field(default=None, max_length=5000, description="How this brand writes/sounds")
    goals: Optional[str] = Field(default=None, max_length=2000, description="What these newsletters are meant to achieve")
    keywords: List[str] = Field(default_factory=list, description="Topics/keywords this project's newsletters cover")
    useful_links: List[str] = Field(default_factory=list)
    social_links: List[str] = Field(default_factory=list)
    mailerlite_account_label: Optional[str] = Field(
        default=None, max_length=255,
        description="Which MailerLite account/list this project targets, purely as context (no key stored here)",
    )
    mailerlite_group_ids: List[str] = Field(default_factory=list, description="MailerLite group IDs this project targets")
    reference_article_project_id: Optional[str] = Field(
        default=None, min_length=36, max_length=36,
        description="Optional: an Article Writer project ID to pull grounding facts from",
    )


class UpdateProjectContextParams(BaseModel):
    project_id: str = Field(..., description="Project ID from list_projects")
    name: Optional[str] = Field(default=None, max_length=255)
    description: Optional[str] = Field(default=None, max_length=5000)
    brand_voice: Optional[str] = Field(default=None, max_length=5000)
    goals: Optional[str] = Field(default=None, max_length=2000)
    keywords: Optional[List[str]] = Field(default=None)
    useful_links: Optional[List[str]] = Field(default=None)
    social_links: Optional[List[str]] = Field(default=None)
    mailerlite_account_label: Optional[str] = Field(default=None, max_length=255)
    mailerlite_group_ids: Optional[List[str]] = Field(default=None)
    reference_article_project_id: Optional[str] = Field(default=None, min_length=36, max_length=36)


class ProjectIdParams(BaseModel):
    project_id: str = Field(..., description="Project ID from list_projects")


class AddReferenceLinkParams(BaseModel):
    project_id: str = Field(..., description="Project ID from list_projects")
    url: str = Field(..., min_length=1, max_length=500, description="URL of an internal page on this project's own site")
    description: str = Field(..., min_length=1, max_length=300, description="What that page is about / its topic")


class RemoveReferenceLinkParams(BaseModel):
    project_id: str = Field(..., description="Project ID from list_projects")
    url: str = Field(..., min_length=1, max_length=500, description="URL to remove from the reference links")


# ── Fill categories / items ─────────────────────────────────────────────

class CreateFillCategoryParams(BaseModel):
    project_id: str = Field(..., description="Project ID from list_projects")
    name: str = Field(..., min_length=1, max_length=100, description="e.g. 'Promo codes', 'Priority links', 'Topics to cover'")
    category_type: str = Field(default="custom", description="One of: promo_code, link, topic, custom")
    instructions: Optional[str] = Field(default=None, max_length=500, description="How/when the writer should use items from this category")


class FillCategoryIdParams(BaseModel):
    project_id: str = Field(..., description="Project ID from list_projects")
    category_id: str = Field(..., description="Fill category ID from list_fill_categories")


class ListFillItemsParams(BaseModel):
    project_id: str = Field(..., description="Project ID from list_projects")
    category_id: str = Field(..., description="Fill category ID from list_fill_categories")
    active_only: bool = Field(default=False, description="Only items not yet marked inactive/exhausted")


class CreateFillItemParams(BaseModel):
    project_id: str = Field(..., description="Project ID from list_projects")
    category_id: str = Field(..., description="Fill category ID from list_fill_categories")
    value: str = Field(..., min_length=1, max_length=1000, description="The actual promo code / URL / topic text")
    note: Optional[str] = Field(default=None, max_length=500)


class UpdateFillItemParams(BaseModel):
    project_id: str = Field(..., description="Project ID from list_projects")
    category_id: str = Field(..., description="Fill category ID from list_fill_categories")
    item_id: str = Field(..., description="Fill item ID from list_fill_items")
    value: Optional[str] = Field(default=None, min_length=1, max_length=1000)
    note: Optional[str] = Field(default=None, max_length=500)
    is_active: Optional[bool] = Field(default=None, description="Set false to retire it (e.g. an expired promo code)")


class DeleteFillItemParams(BaseModel):
    project_id: str = Field(..., description="Project ID from list_projects")
    category_id: str = Field(..., description="Fill category ID from list_fill_categories")
    item_id: str = Field(..., description="Fill item ID from list_fill_items")


# ── Newsletters ──────────────────────────────────────────────────────────

class CreateNewsletterParams(BaseModel):
    project_id: str = Field(..., min_length=36, max_length=36, description="Project ID from list_projects")
    subject: Optional[str] = Field(default=None, max_length=500)
    brief_topic: Optional[str] = Field(default=None, max_length=500)


class ListNewslettersParams(BaseModel):
    project_id: Optional[str] = Field(default=None, description="Filter by project")
    status: Optional[str] = Field(default=None, description="idea | writing | review | scheduled | sent")


class NewsletterIdParams(BaseModel):
    newsletter_id: str = Field(..., description="Newsletter ID from list_newsletters")


class UpdateNewsletterStatusParams(BaseModel):
    newsletter_id: str = Field(..., description="Newsletter ID from list_newsletters")
    status: str = Field(..., description="One of: idea, writing, review, scheduled, sent")


class UpdateNewsletterMetaParams(BaseModel):
    newsletter_id: str = Field(..., description="Newsletter ID from list_newsletters")
    subject: Optional[str] = Field(default=None, max_length=500)
    preheader: Optional[str] = Field(default=None, max_length=200)


class FillSelectionParam(BaseModel):
    category_id: str = Field(..., min_length=36, max_length=36)
    item_ids: List[str] = Field(default_factory=list, max_length=20)


class GenerateNewsletterParams(BaseModel):
    newsletter_id: str = Field(..., description="Newsletter ID from create_newsletter")
    topic: str = Field(..., min_length=1, max_length=1000, description="What this newsletter should cover")
    goal: Optional[str] = Field(default=None, max_length=500)
    audience_hint: Optional[str] = Field(default=None, max_length=500)
    tone_override: Optional[str] = Field(default=None, max_length=500)
    target_word_count: int = Field(default=300, ge=80, le=1200)
    fill_selections: List[FillSelectionParam] = Field(default_factory=list, max_length=6)
    source_snippets: List[str] = Field(
        default_factory=list, max_length=50,
        description="Real facts/data (from web search or other extensions) the draft's claims must be grounded in",
    )


class GenerationJobStatusParams(BaseModel):
    newsletter_id: str = Field(..., description="Newsletter ID from list_newsletters")
    job_id: str = Field(..., description="Job ID returned by generate_newsletter")


class PatchNewsletterParams(BaseModel):
    newsletter_id: str = Field(..., description="Newsletter ID from list_newsletters")
    instruction: str = Field(..., min_length=1, max_length=1000, description="e.g. 'rewrite the block about the promo to be more urgent'")
    section_hint: Optional[str] = Field(default=None, max_length=500)


class UpdateNewsletterSectionParams(BaseModel):
    """PANEL-ONLY manual section overwrite — not an AI writing step. Mirrors
    Article Writer's SaveArticleSectionParams (plain heading+content)."""
    newsletter_id: str = Field(...)
    order_index: int = Field(..., ge=0)
    heading: Optional[str] = Field(default=None, max_length=500)
    content: Optional[str] = Field(default=None, max_length=200000)


class EditFullNewsletterParams(BaseModel):
    """Webbee's own full-text edit — the complete edited newsletter as Markdown
    (leading `# ` = subject, `## ` = section headings, body in light markdown).
    Distinct from patch_newsletter (targeted one-section rewrite): this replaces
    the whole document with exactly what you submit — nothing is re-generated,
    so preserve every unchanged part verbatim."""
    newsletter_id: str = Field(..., description="Newsletter ID from list_newsletters")
    content_markdown: str = Field(..., min_length=1, max_length=400000,
                                  description="The COMPLETE edited newsletter as Markdown (# subject, ## headings, body)")


class SaveFullNewsletterParams(BaseModel):
    """PANEL-ONLY: the whole merged document from the single-window editor —
    not something Webbee should ever construct from chat. Mirrors Article
    Writer's SaveFullArticleParams; the document splits back into
    {heading, content} sections at heading boundaries (see richtext.py)."""
    newsletter_id: str = Field(...)
    content_html: str = Field(default="", max_length=400000)

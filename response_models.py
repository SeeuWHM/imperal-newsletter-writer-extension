"""Pydantic response models for Newsletter Writer chat functions.

Every @chat.function(action_type="read") must declare a data_model so the
platform can validate return shapes (federal V23).

CRITICAL: NewsletterSummaryRecord has no sections/content field, by design —
mirrors the backend's own apps/newsletters/schemas.py::NewsletterSummary.
list_newsletters must never be able to carry full block bodies, independent
of what the backend happens to send — see Article Writer's own
response_models.py for the identical rule. Full bodies exist only in the
panel (panels_workspace.py), which this extension never returns from a
chat.function.
"""
from __future__ import annotations

from typing import Optional, List
from pydantic import BaseModel, Field


class ReferenceLinkRecord(BaseModel):
    """One internal page the writer may link to. `description` = what the
    page is about / its target topic; the writer turns it into a natural,
    in-sentence anchor phrase (never the bare brand/domain)."""

    url: str = ""
    description: str = ""


class ProjectRecord(BaseModel):
    id: str
    name: str = ""
    description: Optional[str] = None
    brand_voice: Optional[str] = None
    goals: Optional[str] = None
    keywords: List[str] = Field(default_factory=list)
    useful_links: List[str] = Field(default_factory=list)
    social_links: List[str] = Field(default_factory=list)
    reference_links: List[ReferenceLinkRecord] = Field(default_factory=list)
    mailerlite_account_label: Optional[str] = None
    mailerlite_group_ids: List[str] = Field(default_factory=list)
    reference_article_project_id: Optional[str] = None


class ProjectListResponse(BaseModel):
    projects: List[ProjectRecord] = Field(default_factory=list)
    count: int = 0


class DeletedResponse(BaseModel):
    deleted: bool = True
    id: str = ""


class ReferenceLinksResponse(BaseModel):
    project_id: str = ""
    links: List[ReferenceLinkRecord] = Field(default_factory=list)
    count: int = 0


class FillCategoryRecord(BaseModel):
    id: str
    project_id: str = ""
    name: str = ""
    category_type: str = "custom"
    instructions: Optional[str] = None
    order_index: int = 0
    item_count: int = 0


class FillCategoryListResponse(BaseModel):
    categories: List[FillCategoryRecord] = Field(default_factory=list)
    count: int = 0


class FillItemRecord(BaseModel):
    id: str
    category_id: str = ""
    value: str = ""
    note: Optional[str] = None
    is_active: bool = True
    times_used: int = 0
    last_used_at: Optional[str] = None


class FillItemListResponse(BaseModel):
    items: List[FillItemRecord] = Field(default_factory=list)
    count: int = 0


class NewsletterSummaryRecord(BaseModel):
    """Metadata only — no sections/content field, by design (see module docstring)."""

    id: str
    project_id: str = ""
    subject: Optional[str] = None
    preheader: Optional[str] = None
    status: str = "idea"
    word_count: int = 0
    model_used: Optional[str] = None
    quality_flags: Optional[dict] = None
    mailerlite_campaign_id: Optional[str] = None
    scheduled_at: Optional[str] = None
    sent_at: Optional[str] = None


class NewsletterListResponse(BaseModel):
    newsletters: List[NewsletterSummaryRecord] = Field(default_factory=list)
    count: int = 0


class GenerationJobResponse(BaseModel):
    job_id: str = ""
    newsletter_id: str = ""
    status: str = "queued"


class GenerationStatusResponse(BaseModel):
    id: str
    newsletter_id: str = ""
    kind: str = ""
    status: str = ""
    model: Optional[str] = None
    tokens_used: Optional[int] = None
    cost_estimate: Optional[float] = None
    error: Optional[str] = None


class PatchResult(BaseModel):
    order_index: int = 0
    heading: Optional[str] = None
    preview: str = ""


class NewsletterTextRecord(BaseModel):
    """Full newsletter body as editable Markdown — the read side of Webbee's
    edit loop (read_full_newsletter -> edit -> edit_full_newsletter). Returned
    to chat on purpose, unlike NewsletterSummaryRecord."""

    id: str
    subject: Optional[str] = None
    status: str = "idea"
    word_count: int = 0
    markdown: str = ""

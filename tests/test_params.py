"""Param-model validation — placeholder ids are rejected before ever
reaching the network. Mirrors imperal-article-writer-extension's
tests/test_params.py."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pytest
from pydantic import ValidationError

from params import NewsletterIdParams, ProjectIdParams


@pytest.mark.parametrize("junk", ["unknown", "UNKNOWN", "null", "undefined", "", "   ", "n/a"])
def test_newsletter_id_rejects_placeholders(junk):
    with pytest.raises(ValidationError):
        NewsletterIdParams(newsletter_id=junk)


def test_newsletter_id_accepts_a_real_looking_id():
    params = NewsletterIdParams(newsletter_id="247be7c4-ee2f-453f-b45e-ad1fda032c7b")
    assert params.newsletter_id == "247be7c4-ee2f-453f-b45e-ad1fda032c7b"


@pytest.mark.parametrize("junk", ["unknown", "null", ""])
def test_project_id_rejects_placeholders(junk):
    with pytest.raises(ValidationError):
        ProjectIdParams(project_id=junk)

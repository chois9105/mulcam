import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api_contract import approval_body, newsletter_request_body, revision_body


def test_newsletter_request_contract():
    assert newsletter_request_body("생성형 AI") == {
        "request_text": "생성형 AI"
    }


def test_revision_contract_uses_backend_direction_field():
    assert revision_body("더 간결하게") == {
        "direction": "더 간결하게"
    }


def test_approval_contract_includes_rendered_template():
    assert approval_body("every_30_minutes", "<article>승인본</article>") == {
        "frequency": "every_30_minutes",
        "approved_template": "<article>승인본</article>",
    }

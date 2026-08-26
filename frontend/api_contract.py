"""Frontend와 Backend가 공유하는 뉴스레터 API 요청 본문 형식."""

from __future__ import annotations

from typing import Dict, Optional


def newsletter_request_body(request_text: str) -> Dict[str, str]:
    return {"request_text": request_text}


def revision_body(direction: str) -> Dict[str, str]:
    return {"direction": direction}


def approval_body(frequency: str, approved_template: Optional[str]) -> Dict:
    return {
        "frequency": frequency,
        "approved_template": approved_template,
    }

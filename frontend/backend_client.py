"""
백엔드 연결 모듈

화면(streamlit_app.py)이 부르던 가짜 데이터(agent_graph.workflow_engine) 자리에
진짜 백엔드를 끼워 넣는다. 화면 코드는 거의 그대로 두고, 여기서 형식만 맞춘다.

백엔드 주소는 환경변수로 바꿀 수 있다.
    BACKEND_URL=https://mulcam.1435.co.kr     (배포)
    BACKEND_URL=http://127.0.0.1:8001         (로컬, 기본값)

부르는 엔드포인트는 세 개뿐이다.
    ① POST /api/newsletter/request     { request_text }
    ② POST /api/drafts/{id}/revise     { direction }
    ③ POST /api/drafts/{id}/approve    { frequency, approved_template }
"""

from __future__ import annotations

import os
from typing import Dict, List, Optional

import requests

from api_contract import approval_body, newsletter_request_body, revision_body

BASE = os.getenv(
    "NEWSLETTER_BACKEND_URL",
    os.getenv("BACKEND_URL", "https://mulcam.1435.co.kr"),
).rstrip("/")

# 생성은 뉴스 검색·요약·검수를 거쳐 10~20초 걸린다
TIMEOUT_LONG = 180
TIMEOUT_SHORT = 15


class BackendError(Exception):
    """화면에 그대로 보여줄 수 있는 오류 메시지를 담는다."""


def _post(path: str, body: Dict, timeout: int = TIMEOUT_LONG) -> Dict:
    try:
        r = requests.post(f"{BASE}{path}", json=body, timeout=timeout)
    except requests.exceptions.ConnectionError:
        raise BackendError(
            f"백엔드에 연결하지 못했습니다. 서버가 켜져 있는지 확인해 주세요. ({BASE})"
        )
    except requests.exceptions.Timeout:
        raise BackendError("응답이 너무 늦습니다. 잠시 후 다시 시도해 주세요.")

    if r.status_code >= 400:
        try:
            detail = r.json().get("detail", "")
        except Exception:
            detail = r.text[:200]
        raise BackendError(str(detail) or f"오류가 발생했습니다. (HTTP {r.status_code})")
    return r.json()


def _get(path: str, timeout: int = TIMEOUT_SHORT) -> Dict:
    try:
        r = requests.get(f"{BASE}{path}", timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception:
        return {}


# ------------------------------------------------------------------
# 형식 맞추기
# ------------------------------------------------------------------
def _to_ui(d: Dict) -> Dict:
    """
    백엔드 응답 -> 화면이 쓰던 형식.

    화면은 id / title / summary / score / status / date / frequency 를 쓴다.
    백엔드는 created_at 을 주므로 date 로 옮기고, 나머지는 그대로 쓴다.
    """
    return {
        "id": d.get("id"),
        "title": d.get("title", ""),
        "summary": d.get("summary", ""),
        "score": d.get("score", 0),
        "score_grade": d.get("score_grade", ""),
        "status": d.get("status", "pending"),
        "date": d.get("created_at", ""),
        "frequency": d.get("frequency") or "daily",
        "revision_count": d.get("revision_count", 0),
        # 상세 표시용 (화면에서 필요하면 쓴다)
        "article_html": d.get("article_html", ""),
        "markdown": d.get("markdown", ""),
        "audit_report": d.get("audit_report", {}),
        "sources": d.get("sources", []),
        "send_result": d.get("send_result", {}),
        "message": d.get("message", ""),
    }


# ------------------------------------------------------------------
# 화면이 부르는 세 가지
# ------------------------------------------------------------------
def create(request_text: str) -> Dict:
    """① 뉴스레터 요청"""
    return _to_ui(_post("/api/newsletter/request", newsletter_request_body(request_text)))


def revise(draft_id: str, direction: str) -> Dict:
    """② 수정 요청 — 화면의 '이렇게 바꾸어주세요' 한 칸"""
    return _to_ui(_post(f"/api/drafts/{draft_id}/revise", revision_body(direction)))


def approve(draft_id: str, frequency: str = "daily",
            approved_template: Optional[str] = None) -> Dict:
    """③ 최종 승인 (+ 주기)"""
    return _to_ui(_post(
        f"/api/drafts/{draft_id}/approve",
        approval_body(frequency, approved_template),
    ))


# ------------------------------------------------------------------
# 보조
# ------------------------------------------------------------------
def advise(keyword: str) -> Dict:
    """
    ① 보조 — 키워드를 넣으면 되묻는 질문 3가지와 추천 요청문 3가지를 준다.
    초보자가 무엇을 적어야 할지 모를 때 쓴다.
    """
    return _post("/api/newsletter/advise", {"keyword": keyword}, timeout=60)


def list_drafts() -> List[Dict]:
    """이미 만들어 둔 요약본 목록. 화면을 새로 열어도 남아 있게 한다."""
    data = _get("/api/drafts")
    return [_to_ui(d) for d in data.get("drafts", [])]


def status() -> Optional[Dict]:
    """백엔드가 살아있는지, 어디에 저장 중인지."""
    data = _get("/api/status")
    return data or None


def health_line() -> str:
    """화면 아래에 보여줄 한 줄."""
    s = status()
    if not s:
        return f"백엔드에 연결하지 못했습니다. ({BASE})"
    store = s.get("storage", {})
    where = "MySQL 저장" if store.get("mode") == "mysql" else "메모리 저장(서버 끄면 사라짐)"
    sch = "동작 중" if s.get("scheduler", {}).get("running") else "꺼짐"
    return f"백엔드 연결됨 · {BASE} · {where} · 스케줄러 {sch}"

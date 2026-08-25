"""
저장소

MySQL 이 준비돼 있으면 MySQL 에, 아니면 메모리에 저장한다.

이렇게 나눈 이유:
    팀원마다 각자 로컬 MySQL 을 쓰기로 했는데, 아직 비밀번호를 안 넣었거나
    서비스를 안 켠 상태에서도 화면 연동 테스트는 되어야 한다.
    MySQL 이 없다고 서버가 안 뜨면 곤란하다.

    메모리 모드에서도 기능은 똑같이 동작한다. 다만 서버를 끄면 사라진다.
    .env 에 MYSQL_PASSWORD 를 넣고 python init_db.py 를 한 번 돌리면
    자동으로 MySQL 모드로 바뀐다.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Dict, List, Optional

_MODE = None          # "mysql" | "memory"
_REASON = ""          # 메모리 모드일 때 그 이유


# ------------------------------------------------------------------
# 모드 결정
# ------------------------------------------------------------------
def _detect() -> str:
    global _MODE, _REASON
    if _MODE is not None:
        return _MODE
    try:
        from database import check_connection
        info = check_connection()
        if info["ok"]:
            from sqlalchemy import inspect
            from database import engine
            if "drafts" in inspect(engine).get_table_names():
                _MODE = "mysql"
                _REASON = ""
            else:
                _MODE, _REASON = "memory", "테이블이 없습니다. python init_db.py 를 실행하세요."
        else:
            _MODE, _REASON = "memory", info["reason"]
    except Exception as e:
        _MODE, _REASON = "memory", f"MySQL 을 쓸 수 없습니다: {str(e)[:120]}"
    return _MODE


def mode() -> Dict:
    """지금 어디에 저장하고 있는지"""
    m = _detect()
    return {
        "mode": m,
        "persistent": m == "mysql",
        "reason": _REASON,
        "note": ("MySQL 에 저장됩니다." if m == "mysql"
                 else "메모리에 저장됩니다. 서버를 끄면 사라집니다."),
    }


def reset_mode():
    """.env 를 고친 뒤 다시 판단하게 한다."""
    global _MODE, _REASON
    _MODE, _REASON = None, ""


# ------------------------------------------------------------------
# 메모리 저장소
# ------------------------------------------------------------------
_memory: Dict[str, Dict] = {}


# ------------------------------------------------------------------
# 요약본 저장 / 조회
# ------------------------------------------------------------------
def _to_row(draft: Dict) -> Dict:
    """서비스가 쓰는 형태 -> DB 컬럼"""
    audit = draft.get("audit_report") or {}
    return {
        "draft_code": draft["id"],
        "request_text": draft.get("_request_text"),
        "search_query": draft.get("_query"),
        "title": draft.get("title"),
        "summary": draft.get("summary"),
        "markdown": draft.get("markdown"),
        "article_html": draft.get("article_html"),
        "sources": draft.get("sources"),
        "score": draft.get("score"),
        "score_grade": draft.get("score_grade"),
        "readability": audit.get("readability"),
        "fact_accuracy": audit.get("fact_accuracy"),
        "coherence": audit.get("coherence"),
        "reviewer_comment": audit.get("reviewer_comment"),
        "status": draft.get("status"),
        "revision_count": draft.get("revision_count", 0),
        "last_direction": draft.get("_last_direction"),
        "frequency": draft.get("frequency"),
    }


def _from_row(row) -> Dict:
    """DB 행 -> 서비스가 쓰는 형태"""
    def fmt(dt):
        return dt.strftime("%Y.%m.%d %H:%M") if dt else None

    return {
        "id": row.draft_code,
        "title": row.title,
        "summary": row.summary,
        "score": row.score,
        "score_grade": row.score_grade,
        "status": row.status,
        "frequency": row.frequency,
        "frequency_label": None,      # 서비스에서 다시 채운다
        "created_at": fmt(row.created_at),
        "approved_at": fmt(row.approved_at),
        "sent_at": fmt(row.sent_at),
        "revision_count": row.revision_count,
        "article_html": row.article_html,
        "markdown": row.markdown,
        "sources": row.sources or [],
        "audit_report": {
            "readability": row.readability,
            "fact_accuracy": row.fact_accuracy,
            "coherence": row.coherence,
            "reviewer_comment": row.reviewer_comment,
            "loop_count": f"{row.revision_count}회",
        },
        "_request_text": row.request_text,
        "_query": row.search_query,
        "_article_count": 8,
        "_last_direction": row.last_direction,
    }


def save_draft(draft: Dict) -> None:
    """새로 만들거나 덮어쓴다."""
    if _detect() == "memory":
        _memory[draft["id"]] = draft
        return

    from database import session_scope
    from db_models import Draft

    row_data = _to_row(draft)
    with session_scope() as s:
        row = s.query(Draft).filter_by(draft_code=draft["id"]).first()
        if row is None:
            row = Draft(**row_data)
            s.add(row)
        else:
            for k, v in row_data.items():
                setattr(row, k, v)


def get_draft(draft_code: str) -> Optional[Dict]:
    if _detect() == "memory":
        return _memory.get(draft_code)

    from database import session_scope
    from db_models import Draft
    with session_scope() as s:
        row = s.query(Draft).filter_by(draft_code=draft_code).first()
        return _from_row(row) if row else None


def list_drafts(status: str = "all") -> List[Dict]:
    if _detect() == "memory":
        items = list(_memory.values())
        if status != "all":
            items = [d for d in items if d["status"] == status]
        return sorted(items, key=lambda d: d["id"], reverse=True)

    from database import session_scope
    from db_models import Draft
    with session_scope() as s:
        q = s.query(Draft)
        if status != "all":
            q = q.filter_by(status=status)
        rows = q.order_by(Draft.created_at.desc()).all()
        return [_from_row(r) for r in rows]


def mark_approved(draft_code: str, frequency: str) -> None:
    if _detect() == "memory":
        d = _memory.get(draft_code)
        if d:
            d["status"] = "approved"
            d["frequency"] = frequency
            d["approved_at"] = datetime.now().strftime("%Y.%m.%d %H:%M")
        return

    from database import session_scope
    from db_models import Draft
    with session_scope() as s:
        row = s.query(Draft).filter_by(draft_code=draft_code).first()
        if row:
            row.status = "approved"
            row.frequency = frequency
            row.approved_at = datetime.now()


def mark_sent(draft_code: str, error: str = None) -> None:
    if _detect() == "memory":
        d = _memory.get(draft_code)
        if d:
            d["status"] = "sent" if not error else d["status"]
            d["sent_at"] = datetime.now().strftime("%Y.%m.%d %H:%M")
            d["send_error"] = error
        return

    from database import session_scope
    from db_models import Draft
    with session_scope() as s:
        row = s.query(Draft).filter_by(draft_code=draft_code).first()
        if row:
            if not error:
                row.status = "sent"
            row.sent_at = datetime.now()
            row.send_error = error


# ------------------------------------------------------------------
# 기사 저장 (수집 결과 보관)
# ------------------------------------------------------------------
def save_articles(news_items: List[Dict]) -> int:
    """수집한 기사를 저장한다. 이미 있는 것은 건너뛴다."""
    if _detect() == "memory":
        return 0

    import hashlib
    from database import session_scope
    from db_models import Article

    saved = 0
    with session_scope() as s:
        for n in news_items:
            link = n.get("link", "")
            if not link:
                continue
            h = hashlib.md5(link.encode()).hexdigest()
            if s.query(Article).filter_by(url_hash=h).first():
                continue
            s.add(Article(
                url_hash=h,
                title=n.get("title", "")[:500],
                link=link[:1000],
                description=n.get("description"),
                content=n.get("content"),
                source=n.get("source"),
                published=n.get("published"),
                has_full_text=n.get("has_full_text", False),
            ))
            saved += 1
    return saved

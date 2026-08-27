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
            from database import engine, missing_draft_columns
            inspector = inspect(engine)
            if "drafts" in inspector.get_table_names():
                missing = missing_draft_columns(
                    c["name"] for c in inspector.get_columns("drafts")
                )
                if missing:
                    _MODE, _REASON = (
                        "memory",
                        "DB 스키마가 이전 버전입니다. 누락 컬럼: " + ", ".join(missing),
                    )
                    return _MODE
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
        "research_items": draft.get("_research_items"),
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
        "user_email": draft.get("user_email"),
        "approved_template": draft.get("approved_template"),
        "schedule_parent_code": draft.get("schedule_parent_code"),
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
        "user_email": row.user_email,
        "approved_template": row.approved_template,
        "schedule_parent_code": row.schedule_parent_code,
        "created_at": fmt(row.created_at),
        "approved_at": fmt(row.approved_at),
        "next_run_at": fmt(row.next_run_at),
        "sent_at": fmt(row.sent_at),
        "send_error": row.send_error,
        "revision_count": row.revision_count,
        "article_html": row.article_html,
        "markdown": row.markdown,
        "sources": row.sources or [],
        "pipeline": ["keyword_search", "research", "newsletter", "review"],
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
        "_research_items": row.research_items or [],
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


def mark_approved(draft_code: str, frequency: str, *, user_email: str,
                  approved_template: str, next_run_at: datetime | None) -> None:
    if _detect() == "memory":
        d = _memory.get(draft_code)
        if d:
            d["status"] = "approved"
            d["frequency"] = frequency
            d["user_email"] = user_email
            d["approved_template"] = approved_template
            d["approved_at"] = datetime.now().strftime("%Y.%m.%d %H:%M")
            d["_next_run_at"] = next_run_at
        return

    from database import session_scope
    from db_models import Draft
    with session_scope() as s:
        row = s.query(Draft).filter_by(draft_code=draft_code).first()
        if row:
            row.status = "approved"
            row.frequency = frequency
            row.user_email = user_email
            row.approved_template = approved_template
            row.approved_at = datetime.now()
            row.next_run_at = next_run_at


def mark_dispatch_pending(draft_code: str, *, schedule_parent_code: str,
                          user_email: str, approved_template: str) -> None:
    """정기 생성본을 n8n이 가져갈 미발송 상태로 등록한다."""
    if _detect() == "memory":
        d = _memory.get(draft_code)
        if d:
            d["status"] = "approved"
            d["user_email"] = user_email
            d["approved_template"] = approved_template
            d["schedule_parent_code"] = schedule_parent_code
            d["approved_at"] = datetime.now().strftime("%Y.%m.%d %H:%M")
        return

    from database import session_scope
    from db_models import Draft
    with session_scope() as s:
        row = s.query(Draft).filter_by(draft_code=draft_code).first()
        if row:
            row.status = "approved"
            row.user_email = user_email
            row.approved_template = approved_template
            row.schedule_parent_code = schedule_parent_code
            row.approved_at = datetime.now()


def list_pending_dispatches() -> List[Dict]:
    """최초 승인본과 정기 생성본 중 아직 발송되지 않은 건을 조회한다."""
    if _detect() == "memory":
        items = [
            d for d in _memory.values()
            if d.get("status") == "approved"
            and d.get("approved_at")
            and d.get("user_email")
            and not d.get("sent_at")
        ]
        return sorted(items, key=lambda d: d["id"])

    from database import session_scope
    from db_models import Draft
    with session_scope() as s:
        rows = s.query(Draft).filter(
            Draft.status == "approved",
            Draft.approved_at.isnot(None),
            Draft.user_email.isnot(None),
            Draft.sent_at.is_(None),
        ).order_by(Draft.created_at.asc()).all()
        return [_from_row(r) for r in rows]


def list_schedules(due_at: datetime | None = None) -> List[Dict]:
    """DB에 저장된 반복 승인 건을 스케줄러가 쓰는 형태로 돌려준다."""
    if _detect() == "memory":
        rows = []
        for d in _memory.values():
            next_run = d.get("_next_run_at")
            if not d.get("approved_at") or not d.get("frequency"):
                continue
            if due_at is not None and (next_run is None or next_run > due_at):
                continue
            rows.append({
                "schedule_id": d["id"],
                "draft_id": d["id"],
                "request_text": d.get("_request_text"),
                "frequency": d.get("frequency"),
                "user_email": d.get("user_email"),
                "approved_template": d.get("approved_template"),
                "next_run_at": next_run,
                "is_active": True,
            })
        return rows

    from database import session_scope
    from db_models import Draft
    with session_scope() as s:
        q = s.query(Draft).filter(
            Draft.approved_at.isnot(None),
            Draft.frequency.isnot(None),
        )
        if due_at is not None:
            q = q.filter(Draft.next_run_at.isnot(None), Draft.next_run_at <= due_at)
        rows = q.order_by(Draft.next_run_at.asc()).all()
        return [{
            "schedule_id": r.id,
            "draft_id": r.draft_code,
            "request_text": r.request_text,
            "frequency": r.frequency,
            "user_email": r.user_email,
            "approved_template": r.approved_template,
            "next_run_at": r.next_run_at,
            "is_active": True,
        } for r in rows]


def mark_schedule_run(draft_code: str, *, last_run_at: datetime,
                      next_run_at: datetime) -> None:
    if _detect() == "memory":
        d = _memory.get(draft_code)
        if d:
            d["_last_scheduled_at"] = last_run_at
            d["_next_run_at"] = next_run_at
        return

    from database import session_scope
    from db_models import Draft
    with session_scope() as s:
        row = s.query(Draft).filter_by(draft_code=draft_code).first()
        if row:
            row.last_scheduled_at = last_run_at
            row.next_run_at = next_run_at


def mark_sent(draft_code: str, error: str = None) -> None:
    if _detect() == "memory":
        d = _memory.get(draft_code)
        if d:
            d["status"] = "sent" if not error else d["status"]
            d["sent_at"] = (
                datetime.now().strftime("%Y.%m.%d %H:%M") if not error else None
            )
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
            else:
                row.sent_at = None
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

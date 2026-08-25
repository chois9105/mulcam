"""
프론트엔드 형식 변환기

백엔드와 프론트엔드가 쓰는 필드 이름이 다르다.
프론트엔드(frontend/models.py)가 기대하는 모양으로 바꿔주는 곳.

    백엔드 sources          ->  프론트 ResearchSource
    title / source / link       title / domain / summary / url

한쪽 형식이 바뀌어도 이 파일만 고치면 되도록 따로 뺐다.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Dict, List
from urllib.parse import urlparse


def _domain(url: str) -> str:
    """https://www.yna.co.kr/view/... -> yna.co.kr"""
    try:
        host = urlparse(url).netloc
        return host[4:] if host.startswith("www.") else host
    except Exception:
        return ""


def to_research_sources(sources: List[Dict]) -> List[Dict]:
    """백엔드 sources -> 프론트 ResearchSource 목록"""
    return [
        {
            "title": s.get("title", ""),
            "domain": _domain(s.get("link", "")) or s.get("source", ""),
            "summary": s.get("source", ""),   # 매체명을 요약란에 표시
            "url": s.get("link", ""),
        }
        for s in sources
    ]


def extract_title(markdown_text: str, fallback: str = "뉴스레터") -> str:
    """마크다운 첫 번째 제목(#)을 뽑는다."""
    m = re.search(r"^#\s+(.+)$", markdown_text, flags=re.M)
    if m:
        return m.group(1).strip()
    for line in markdown_text.splitlines():
        line = line.strip()
        if line and not line.startswith(("-", "*", ">", "|")):
            return line.lstrip("#").strip()[:60]
    return fallback


def extract_summary(markdown_text: str, limit: int = 160) -> str:
    """목록 카드에 보여줄 짧은 요약을 뽑는다."""
    for pattern in (r"오늘의 한 줄\s*[:：]?\s*(.+)", r"한 줄 정리\s*[:：]?\s*(.+)"):
        m = re.search(pattern, markdown_text)
        if m:
            return m.group(1).strip().lstrip("*").strip()[:limit]
    for line in markdown_text.splitlines():
        line = line.strip()
        if line and not line.startswith(("#", "-", "*", ">", "|")):
            return line[:limit]
    return ""


def build_draft(
    draft_id: str,
    result: Dict,
    review=None,
    audit: Dict = None,
    frequency: str = "daily",
    status: str = "pending",
    keywords: List[str] = None,
) -> Dict:
    """
    RAG 결과 + 검수 결과를 프론트엔드 NewsletterDraft 형식으로 합친다.

    result : rag_engine.summarize() 반환값
    review : reviewer.ReviewResult (없으면 점수 항목은 기본값)
    """
    markdown_text = result.get("newsletter", "")
    tags = list(keywords or [])
    tags += [result.get("style_name", "뉴스레터"), "RAG"]

    return {
        "id": draft_id,
        "title": extract_title(markdown_text, result.get("topic", "뉴스레터")),
        "summary": extract_summary(markdown_text),
        "tags": tags,
        "date": datetime.now().strftime("%Y.%m.%d %H:%M"),
        "frequency": frequency,
        "status": status,
        "score": review.score if review else 0,
        "score_grade": _grade(review.score) if review else "미검수",
        "author_agent": f"작성 에이전트 (RAG + {result.get('style_name', '')})",
        "inspector_agent": "검수 에이전트 (사실성35/출처25/구성20/독자20)",
        "selected": False,
        "article_html": result.get("article_html", ""),
        "sources": to_research_sources(result.get("sources", [])),
        "audit_report": audit or {
            "readability": 0, "fact_accuracy": 0, "coherence": 0,
            "reviewer_comment": "검수를 실행하지 않았습니다.", "loop_count": "0회",
        },
        # 백엔드 원본도 함께 보낸다 (프론트가 필요하면 쓰도록)
        "markdown": markdown_text,
        "style": result.get("style", ""),
    }


def _grade(score: int) -> str:
    if score >= 95:
        return "A+ 우수"
    if score >= 90:
        return "A 양호"
    if score >= 80:
        return "B 통과"
    if score >= 70:
        return "C 보완 필요"
    return "D 재작성 권장"

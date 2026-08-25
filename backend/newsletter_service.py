"""
뉴스레터 파이프라인

화면의 버튼 세 개가 부르는 실제 작업을 여기서 처리한다.
API 층(api_v1.py)은 요청을 받고 이 서비스를 부르기만 한다.

    생성 : 요청 분석 -> 기사 검색 -> 요약 -> 다듬기 -> 검수 -> 저장
    수정 : 기존 요약 + 수정 요청 -> 다시 작성 -> 다듬기 -> 재검수
    승인 : 상태 변경 + 주기 저장

저장은 지금 메모리에 한다. MySQL 이 준비되면 _store 부분만 바꾸면 된다.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Dict, List, Optional

from langchain_core.prompts import ChatPromptTemplate

from adapters import extract_summary, extract_title, to_research_sources
from html_render import to_dashboard_html
from polisher import Polisher
from rag_engine import DEFAULT_STYLE, STYLE_PROMPTS, NewsRAG
from request_analyzer import RequestAnalyzer
from reviewer import NewsletterReviewer

# 주기 표시 문구
FREQUENCY_LABEL = {
    "once": "한 번만",
    "daily": "매일",
    "weekly": "매주",
    "biweekly": "격주",
    "monthly": "매월",
}

# 수정 요청용 프롬프트
# 화면 ②의 "이렇게 바꾸어주세요" 한 칸을 받는다.
REVISE_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "당신은 뉴스 큐레이터입니다. 아래 [기존 요약]을 사용자의 [요청]대로 고쳐 쓰세요.\n\n"
     "지킬 것:\n"
     "- 아래 [기사]에 있는 내용만 쓴다. 없는 사실을 새로 만들지 않는다.\n"
     "- **모든 항목 끝에 근거 기사 번호 [1] [2] 를 반드시 붙인다.**\n"
     "  쉽게 풀어 쓰라는 요청을 받아도 번호는 절대 빼지 않는다.\n"
     "  번호가 빠지면 검수에서 출처 점수가 0점이 된다.\n"
     "- 기사 하나당 한 항목으로 쓴다. 뭉뚱그리지 않는다.\n"
     "- 요청에서 말한 부분을 실제로 바꾼다. 형식만 바꾸고 넘어가지 않는다.\n"
     "- 마크다운, 한국어.\n\n"
     "[기사]\n{context}\n\n"
     "[기존 요약]\n{previous}"),
    ("human", "[요청]\n{direction}"),
])


class NewsletterService:
    """
    세 버튼이 쓰는 하나의 서비스.
    무거운 객체(RAG, 검수, 다듬기)는 한 번만 만들어 재사용한다.
    """

    def __init__(self):
        self._rag: Optional[NewsRAG] = None
        self._analyzer: Optional[RequestAnalyzer] = None
        self._reviewer: Optional[NewsletterReviewer] = None
        self._polisher: Optional[Polisher] = None
        # 만들어진 요약본 보관 (MySQL 준비되면 교체)
        self._store: Dict[str, Dict] = {}
        self._schedules: Dict[int, Dict] = {}
        self._next_schedule_id = 1

    # ---------- 지연 생성 ----------
    @property
    def rag(self) -> NewsRAG:
        if self._rag is None:
            self._rag = NewsRAG()
            self._rag.load()
        return self._rag

    @property
    def analyzer(self) -> RequestAnalyzer:
        if self._analyzer is None:
            self._analyzer = RequestAnalyzer()
        return self._analyzer

    @property
    def reviewer(self) -> NewsletterReviewer:
        if self._reviewer is None:
            self._reviewer = NewsletterReviewer()
        return self._reviewer

    @property
    def polisher(self) -> Polisher:
        if self._polisher is None:
            self._polisher = Polisher()
        return self._polisher

    # ---------- 조회 ----------
    def get(self, draft_id: str) -> Optional[Dict]:
        return self._store.get(draft_id)

    def list_drafts(self, status: str = "all") -> List[Dict]:
        items = list(self._store.values())
        if status != "all":
            items = [d for d in items if d["status"] == status]
        return sorted(items, key=lambda d: d["id"], reverse=True)

    # ---------- ① 뉴스레터 요청 ----------
    def create(self, request_text: str) -> Dict:
        """요청 문장 -> 요약본 한 건"""
        # 1. 요청 분석
        plan = self.analyzer.analyze(request_text)
        query = self.analyzer.to_query(plan)

        # 2. 기사 검색 + 3. 기사별 요약
        result = self.rag.summarize(query, style=DEFAULT_STYLE, k=plan.article_count)
        markdown = result["newsletter"]
        sources = result["sources"]

        # 4. 한국어 다듬기
        markdown = self.polisher.polish(markdown)

        # 5. 검수
        review = self.reviewer.review(markdown, sources)
        audit = self.reviewer.audit_report(review, loop_count=0)

        # 6. 저장
        return self._save(
            markdown=markdown,
            sources=sources,
            review=review,
            audit=audit,
            request_text=request_text,
            plan=plan,
            query=query,
            title_hint=plan.title_hint,
        )

    # ---------- ② 수정 요청 ----------
    def revise(self, draft_id: str, direction: str) -> Dict:
        """화면 ②의 '이렇게 바꾸어주세요' 한 칸을 받아 다시 쓴다."""
        draft = self._store[draft_id]

        # 원래 근거 기사를 그대로 다시 쓴다 (검색을 다시 하지 않는다)
        docs = self.rag.search(draft["_query"], k=draft["_article_count"])
        context = self.rag._format_context(docs)

        markdown = (REVISE_PROMPT | self.rag.llm).invoke({
            "context": context,
            "previous": draft["markdown"],
            "direction": direction,
        }).content

        markdown = self.polisher.polish(markdown)

        sources = self.rag._sources(docs)
        review = self.reviewer.review(markdown, sources)
        loop = draft["revision_count"] + 1
        audit = self.reviewer.audit_report(review, loop_count=loop)

        return self._save(
            markdown=markdown,
            sources=sources,
            review=review,
            audit=audit,
            request_text=draft["_request_text"],
            plan=None,
            query=draft["_query"],
            title_hint=draft["title"],
            draft_id=draft_id,             # 같은 id 에 덮어쓴다
            revision_count=loop,
            direction=direction,
        )

    # ---------- ③ 최종 승인 (+ 주기) ----------
    def approve(self, draft_id: str, frequency: str,
                recipients: List[str] = None) -> Dict:
        """승인하고 발송 주기를 저장한다."""
        draft = self._store[draft_id]
        now = datetime.now()

        draft["status"] = "approved"
        draft["approved_at"] = now.strftime("%Y.%m.%d %H:%M")
        draft["frequency"] = frequency
        draft["frequency_label"] = FREQUENCY_LABEL.get(frequency, frequency)

        schedule_id = self._next_schedule_id
        self._next_schedule_id += 1
        self._schedules[schedule_id] = {
            "schedule_id": schedule_id,
            "draft_id": draft_id,
            "request_text": draft["_request_text"],
            "frequency": frequency,
            "recipients": recipients or [],
            "is_active": frequency != "once",
            "created_at": now.strftime("%Y.%m.%d %H:%M"),
        }
        draft["schedule_id"] = schedule_id
        return draft

    def reject(self, draft_id: str) -> Dict:
        draft = self._store[draft_id]
        draft["status"] = "rejected"
        return draft

    # ---------- 저장 ----------
    def _save(self, *, markdown, sources, review, audit, request_text,
              plan, query, title_hint, draft_id=None,
              revision_count=0, direction=None) -> Dict:
        now = datetime.now()
        if draft_id is None:
            draft_id = f"draft_{now:%Y%m%d_%H%M%S}"

        article_count = plan.article_count if plan else len(sources)

        draft = {
            "id": draft_id,
            "title": title_hint or extract_title(markdown),
            "summary": self._make_summary(request_text),
            "score": review.score,
            "score_grade": self.reviewer.to_grade(review.score),
            "status": "pending",
            "frequency": None,
            "frequency_label": None,
            "created_at": now.strftime("%Y.%m.%d %H:%M"),
            "revision_count": revision_count,

            "article_html": to_dashboard_html(markdown, sources),
            "markdown": markdown,
            "audit_report": audit,
            "sources": to_research_sources(sources),

            # 내부용 (응답에서는 빼고 내보낸다)
            "_request_text": request_text,
            "_query": query,
            "_article_count": article_count,
            "_last_direction": direction,
        }
        self._store[draft_id] = draft
        return draft

    @staticmethod
    def _make_summary(request_text: str) -> str:
        """화면 카드에 들어갈 한 줄 설명. 실제 화면 문구를 따랐다."""
        text = request_text.strip()
        if len(text) > 70:
            text = text[:70] + "..."
        return (f"사용자 요청 '{text}'을 반영하여 리서치·작성·검수 "
                f"에이전트가 구성한 맞춤형 뉴스레터 초안입니다.")

    # ---------- 응답용 ----------
    @staticmethod
    def to_response(draft: Dict) -> Dict:
        """밑줄로 시작하는 내부 항목을 빼고 내보낸다."""
        return {k: v for k, v in draft.items() if not k.startswith("_")}


# 앱 전체에서 하나만 쓴다
service = NewsletterService()

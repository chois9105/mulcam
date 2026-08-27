"""
뉴스레터 파이프라인

화면의 버튼 세 개가 부르는 실제 작업을 여기서 처리한다.
API 층(api_v1.py)은 요청을 받고 이 서비스를 부르기만 한다.

    생성 : 요청 분석 -> 기사 검색 -> 요약 -> 다듬기 -> 검수 -> 저장
    수정 : 기존 요약 + 수정 요청 -> 다시 작성 -> 다듬기 -> 재검수
    승인 : 상태 변경 + 주기 저장

저장은 store.py 가 맡는다. MySQL 이 준비돼 있으면 MySQL, 아니면 메모리.
"""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime
from typing import Dict, List, Optional

from dotenv import load_dotenv
from langchain_core.prompts import ChatPromptTemplate

from adapters import extract_summary, extract_title, to_research_sources
from html_render import to_dashboard_html
from polisher import Polisher
import compose
import live_search
import store
from rag_engine import DEFAULT_STYLE, STYLE_PROMPTS, NewsRAG
from request_analyzer import RequestAnalyzer
from reviewer import NewsletterReviewer

load_dotenv()
logger = logging.getLogger(__name__)
# 로그인 화면이 없는 단일 사용자 서비스라 승인자 메일은 하나로 고정한다.
# .env 의 MAIL_TO 를 넣어두면 그쪽으로 간다. (팀원별 로컬 시연용)
DEFAULT_USER_EMAIL = (
    os.getenv("MAIL_TO", "").split(",")[0].strip() or "contact@1435.co.kr"
)

# 주기 표시 문구
FREQUENCY_LABEL = {
    "every_30_minutes": "30분마다",
    "hourly": "매시간",
    "daily": "매일",
    "weekly": "매주",
}

# 수정 요청용 프롬프트
# 화면 ②의 "이렇게 바꾸어주세요" 한 칸을 받는다.
REVISE_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "당신은 뉴스 큐레이터입니다. 아래 [기존 요약]을 사용자의 [요청]대로 고쳐 쓰세요.\n\n"
     "절대 지킬 것:\n"
     "1. **항목을 {item_count}개 그대로 유지한다.** 하나도 빼지 않는다.\n"
     "   '쉽게 써 달라', '줄여 달라'는 요청은 각 항목을 쉽게·짧게 쓰라는 뜻이지\n"
     "   기사를 버리라는 뜻이 아니다.\n"
     "2. **각 항목의 제목 끝에 근거 번호 [n] 을 붙인다.** 원래 번호를 그대로 쓴다.\n"
     "   번호가 빠지면 검수에서 출처 점수가 0점이 된다.\n"
     "3. 아래 [기사]에 있는 내용만 쓴다. 없는 사실을 새로 만들지 않는다.\n"
     "4. 기사 하나당 한 항목. 여러 기사를 하나로 합치지 않는다.\n"
     "5. 요청에서 말한 부분을 실제로 바꾼다.\n"
     "6. 마크다운, 한국어.\n\n"
     "형식은 이대로 유지한다:\n"
     "**기사 제목** [n]\n"
     "설명 문장.\n\n"
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
        # 저장은 store 가 맡는다 (MySQL 이 준비돼 있으면 MySQL, 아니면 메모리)

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
        d = store.get_draft(draft_id)
        if d and d.get("frequency"):
            d["frequency_label"] = FREQUENCY_LABEL.get(d["frequency"], d["frequency"])
        return d

    def list_drafts(self, status: str = "all") -> List[Dict]:
        items = store.list_drafts(status)
        for d in items:
            if d.get("frequency"):
                d["frequency_label"] = FREQUENCY_LABEL.get(d["frequency"], d["frequency"])
        return items

    @staticmethod
    def storage_mode() -> Dict:
        return store.mode()

    # ---------- ① 뉴스레터 요청 ----------
    def research(self, keywords: List[str], article_count: int) -> List[Dict]:
        """실시간 키워드 검색을 우선하고 사전 색인은 선택적으로 보강한다."""
        #
        #    (가) 미리 모아둔 색인 : 국내 16곳, 본문 900자, 원문 링크
        #    (나) 실시간 검색      : 키워드로 지금 찾아옴, 빠짐이 없다
        #
        #    미리 모아둔 것만 쓰면 그 안에 없는 주제를 못 만든다.
        #    실시간만 쓰면 본문이 없어 요약이 얕아진다. 그래서 둘 다 쓴다.
        live = live_search.search(keywords, per_keyword=6)
        indexed = []
        try:
            indexed = compose.docs_to_items(
                self.rag.search_multi(keywords, k=article_count)
            )
        except RuntimeError as e:
            # 색인은 품질 보강용일 뿐 필수 선행조건이 아니다.
            logger.info("사전 색인 없이 실시간 리서치만 사용합니다: %s", e)
        items = live_search.merge_with_indexed(indexed, live,
                                               limit=article_count)
        return items

    def create(self, request_text: str) -> Dict:
        """요청 문장 -> 요약본 한 건"""
        # 1. 요청 분석
        plan = self.analyzer.analyze(request_text)
        query = self.analyzer.to_query(plan)

        # 2. 요청 시점 리서치
        items = self.research(plan.keywords, plan.article_count)
        if not items:
            raise ValueError(f"'{query}' 와 관련된 뉴스를 찾지 못했습니다.")

        # 3. 기사별 요약
        result = compose.summarize_items(self.rag.llm, query, items,
                                         style=DEFAULT_STYLE)
        markdown = result["newsletter"]
        sources = result["sources"]

        # 관련 기사가 하나도 없으면 억지로 만들지 않는다.
        if "NO_RELEVANT_NEWS" in markdown:
            raise ValueError(
                f"'{query}' 와 관련된 뉴스를 찾지 못했습니다. "
                "다른 키워드로 시도해 주세요."
            )

        # 4. 한국어 다듬기
        markdown = self.polisher.polish(markdown)

        # 실제로 요약에 쓰인 근거만 남긴다.
        # 검색이 가져왔지만 무관해서 빠진 기사가 근거 목록에 남으면
        # 화면에 "근거 8건 / 항목 1개" 처럼 어긋나 보인다.
        markdown, sources = self._used_sources(markdown, sources)

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
            research_items=items,
        )

    # ---------- ② 수정 요청 ----------
    def revise(self, draft_id: str, direction: str) -> Dict:
        """화면 ②의 '이렇게 바꾸어주세요' 한 칸을 받아 다시 쓴다."""
        draft = store.get_draft(draft_id)

        # 원래 응답을 만든 리서치 결과를 그대로 사용한다. 수정 요청에서
        # 재검색하면 근거와 기사 번호가 바뀌어 "이전 답변 기반 수정"이 아니다.
        items = draft.get("_research_items") or self._items_from_sources(
            draft.get("sources", [])
        )
        context = compose.format_items(items)

        # 기존 요약에 항목이 몇 개였는지 세어, 그 수를 유지하라고 알려준다.
        # (쉽게 써 달라는 요청에 모델이 기사를 통째로 버리는 일이 있었다)
        item_count = len(re.findall(r"^\*\*.+\*\*", draft["markdown"], flags=re.M)) or len(items)

        markdown = (REVISE_PROMPT | self.rag.llm).invoke({
            "context": context,
            "previous": draft["markdown"],
            "direction": direction,
            "item_count": item_count,
        }).content

        markdown = self.polisher.polish(markdown)

        markdown, sources = self._used_sources(markdown,
                                               compose.items_to_sources(items))
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
            research_items=items,
        )

    # ---------- ③ 최종 승인 (+ 주기) ----------
    def approve(self, draft_id: str, frequency: str,
                approved_template: str | None = None) -> Dict:
        """승인하고 발송 주기를 저장한다."""
        draft = store.get_draft(draft_id)
        now = datetime.now()

        draft["status"] = "approved"
        draft["approved_at"] = now.strftime("%Y.%m.%d %H:%M")
        draft["frequency"] = frequency
        draft["frequency_label"] = FREQUENCY_LABEL.get(frequency, frequency)
        draft["user_email"] = DEFAULT_USER_EMAIL
        draft["approved_template"] = approved_template or draft.get("article_html", "")
        next_run_at = self._next_run(now, frequency)

        store.mark_approved(
            draft_id,
            frequency,
            user_email=DEFAULT_USER_EMAIL,
            approved_template=draft["approved_template"],
            next_run_at=next_run_at,
        )
        draft["schedule_id"] = draft_id
        draft["next_run_at"] = (
            next_run_at.strftime("%Y.%m.%d %H:%M") if next_run_at else None
        )

        return draft

    def schedules(self) -> List[Dict]:
        return store.list_schedules()

    def due_schedules(self, now: datetime | None = None) -> List[Dict]:
        return store.list_schedules(due_at=now or datetime.now())

    def pending_dispatches(self) -> List[Dict]:
        return store.list_pending_dispatches()

    @staticmethod
    def to_dispatch_response(draft: Dict) -> Dict:
        """n8n 발송에 필요한 최소 정보만 돌려준다."""
        parent_id = draft.get("schedule_parent_code")
        schedule = store.get_draft(parent_id) if parent_id else draft
        schedule = schedule or draft
        return {
            "draft_id": draft.get("id"),
            "email": draft.get("user_email") or DEFAULT_USER_EMAIL,
            "frequency": schedule.get("frequency"),
            "request_text": (
                schedule.get("_request_text")
                or draft.get("_request_text")
                or ""
            ),
            "template": (
                draft.get("approved_template")
                or draft.get("article_html")
                or ""
            ),
        }

    def prepare_dispatch(self, schedule: Dict) -> Dict:
        """승인된 요청으로 최신 뉴스를 만들고 n8n 발송 대기에 등록한다."""
        draft = self.create(schedule["request_text"])
        html = draft.get("article_html", "")
        store.mark_dispatch_pending(
            draft["id"],
            schedule_parent_code=schedule["draft_id"],
            user_email=schedule.get("user_email") or DEFAULT_USER_EMAIL,
            approved_template=html,
        )
        draft.update({
            "status": "approved",
            "user_email": schedule.get("user_email") or DEFAULT_USER_EMAIL,
            "approved_template": html,
            "schedule_parent_code": schedule["draft_id"],
        })
        return draft

    def record_dispatch_result(self, draft_id: str, *, sent: bool,
                               error: str | None = None) -> Dict:
        draft = store.get_draft(draft_id)
        dispatchable = bool(
            draft
            and draft.get("status") in ("approved", "sent")
            and draft.get("user_email")
            and (draft.get("approved_template") or draft.get("article_html"))
        )
        if not dispatchable:
            raise ValueError("발송 대기 뉴스레터를 찾을 수 없습니다.")
        store.mark_sent(draft_id, error=None if sent else (error or "발송 실패"))
        return store.get_draft(draft_id)

    def mark_schedule_run(self, draft_id: str, frequency: str,
                          now: datetime | None = None) -> None:
        current = now or datetime.now()
        store.mark_schedule_run(
            draft_id,
            last_run_at=current,
            next_run_at=self._next_run(current, frequency),
        )

    def reject(self, draft_id: str) -> Dict:
        draft = store.get_draft(draft_id)
        draft["status"] = "rejected"
        store.save_draft(draft)
        return draft

    @staticmethod
    def _used_sources(markdown: str, sources: List[Dict]):
        """
        본문에 실제로 인용된 기사만 남기고 번호를 1부터 다시 매긴다.
        본문의 번호도 함께 바꿔서 근거 목록과 어긋나지 않게 한다.

        반환: (바뀐 본문, 남은 근거 목록)

        왜 필요한가:
          검색은 관련이 옅은 기사까지 가져온다. 작성 모델이 그런 것을 빼면
          근거 목록에만 남아 "근거 8건인데 항목 1개" 처럼 보인다.
          또 번호만 다시 매기고 본문을 그대로 두면 본문 [3] 을 눌러도
          근거 목록에 [3] 이 없는 상태가 된다.
        """
        used = sorted({int(n) for n in re.findall(r"\[(\d+)\]", markdown)})
        if not used:
            return markdown, sources

        by_no = {s.get("n"): s for s in sources}
        kept, mapping = [], {}
        for new_no, old_no in enumerate(used, 1):
            src = by_no.get(old_no)
            if not src:
                continue
            item = dict(src)
            item["n"] = new_no
            kept.append(item)
            mapping[old_no] = new_no

        if not kept:
            return markdown, sources

        # 본문 번호도 새 번호로 바꾼다.
        # 한 번에 바꾸면 [1]->[2], [2]->[1] 같은 경우가 꼬이므로
        # 임시 표시를 거쳐 두 단계로 바꾼다.
        out = re.sub(r"\[(\d+)\]",
                     lambda m: f"[[#{mapping[int(m.group(1))]}]]"
                     if int(m.group(1)) in mapping else m.group(0),
                     markdown)
        out = re.sub(r"\[\[#(\d+)\]\]", lambda m: f"[{m.group(1)}]", out)
        return out, kept

    @staticmethod
    def _items_from_sources(sources: List[Dict]) -> List[Dict]:
        """구버전 DB 초안도 재검색 없이 수정할 수 있게 최소 근거를 복원한다."""
        return [{
            "title": s.get("title", ""),
            "link": s.get("url", s.get("link", "")),
            "source": s.get("summary", s.get("source", "")),
            "published": s.get("published", ""),
            "description": s.get("description", ""),
            "content": s.get("content", ""),
            "has_full_text": bool(s.get("content")),
            "live": s.get("live", False),
        } for s in sources]

    @staticmethod
    def _next_run(now: datetime, frequency: str) -> datetime | None:
        from datetime import timedelta

        intervals = {
            "every_30_minutes": timedelta(minutes=30),
            "hourly": timedelta(hours=1),
            "daily": timedelta(days=1),
            "weekly": timedelta(days=7),
        }
        return now + intervals[frequency] if frequency in intervals else None

    # ---------- 저장 ----------
    def _save(self, *, markdown, sources, review, audit, request_text,
              plan, query, title_hint, draft_id=None,
              revision_count=0, direction=None, research_items=None) -> Dict:
        now = datetime.now()
        if draft_id is None:
            draft_id = f"draft_{now:%Y%m%d_%H%M%S_%f}"

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
            "pipeline": ["keyword_search", "research", "newsletter", "review"],

            # 내부용 (응답에서는 빼고 내보낸다)
            "_request_text": request_text,
            "_query": query,
            "_keywords": (plan.keywords if plan else None),
            "_article_count": article_count,
            "_research_items": research_items or [],
            "_last_direction": direction,
        }
        store.save_draft(draft)
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

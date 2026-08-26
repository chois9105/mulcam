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

import os
import re
from datetime import datetime
from typing import Dict, List, Optional

from langchain_core.prompts import ChatPromptTemplate

from adapters import extract_summary, extract_title, to_research_sources
from html_render import to_dashboard_html
from polisher import Polisher
import store
from mailer import send_draft
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
    def create(self, request_text: str) -> Dict:
        """요청 문장 -> 요약본 한 건"""
        # 1. 요청 분석
        plan = self.analyzer.analyze(request_text)
        query = self.analyzer.to_query(plan)

        # 2. 기사 검색 + 3. 기사별 요약
        result = self.rag.summarize(query, style=DEFAULT_STYLE,
                                    k=plan.article_count,
                                    keywords=plan.keywords)
        markdown = result["newsletter"]
        sources = result["sources"]

        # 관련 기사가 하나도 없으면 억지로 만들지 않는다.
        # (검색은 항상 최소 몇 건을 돌려주므로, 관련성 판단은 작성 모델이 한다)
        if "NO_RELEVANT_NEWS" in markdown:
            raise ValueError(
                f"'{query}' 와 관련된 뉴스를 찾지 못했습니다. "
                "다른 키워드로 시도하거나, 뉴스를 먼저 수집해 주세요."
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
        )

    # ---------- ② 수정 요청 ----------
    def revise(self, draft_id: str, direction: str) -> Dict:
        """화면 ②의 '이렇게 바꾸어주세요' 한 칸을 받아 다시 쓴다."""
        draft = store.get_draft(draft_id)

        # 원래 근거 기사를 그대로 다시 쓴다 (검색을 다시 하지 않는다)
        kws = draft.get("_keywords") or draft["_query"].split()
        docs = self.rag.search_multi(kws, k=draft["_article_count"])
        context = self.rag._format_context(docs)

        # 기존 요약에 항목이 몇 개였는지 세어, 그 수를 유지하라고 알려준다.
        # (쉽게 써 달라는 요청에 모델이 기사를 통째로 버리는 일이 있었다)
        item_count = len(re.findall(r"^\*\*.+\*\*", draft["markdown"], flags=re.M)) or len(docs)

        markdown = (REVISE_PROMPT | self.rag.llm).invoke({
            "context": context,
            "previous": draft["markdown"],
            "direction": direction,
            "item_count": item_count,
        }).content

        markdown = self.polisher.polish(markdown)

        markdown, sources = self._used_sources(markdown, self.rag._sources(docs))
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
        draft = store.get_draft(draft_id)
        now = datetime.now()

        draft["status"] = "approved"
        draft["approved_at"] = now.strftime("%Y.%m.%d %H:%M")
        draft["frequency"] = frequency
        draft["frequency_label"] = FREQUENCY_LABEL.get(frequency, frequency)

        store.mark_approved(draft_id, frequency)

        # 주기 등록. once 면 반복하지 않는다.
        schedule_id = self._next_schedule_id
        self._next_schedule_id += 1
        self._schedules[schedule_id] = {
            "schedule_id": schedule_id,
            "draft_id": draft_id,
            "request_text": draft.get("_request_text"),
            "frequency": frequency,
            "recipients": recipients or [],
            "is_active": frequency != "once",
            "created_at": now.strftime("%Y.%m.%d %H:%M"),
        }
        draft["schedule_id"] = schedule_id

        # 승인했으니 바로 한 통 보낸다.
        # MAIL_DRY_RUN=true 면 실제로 나가지 않고 보낼 내용만 알려준다.
        result = send_draft(draft, to=(recipients or [None])[0])
        draft["send_result"] = result
        if result.get("sent"):
            draft["status"] = "sent"
            store.mark_sent(draft_id)
        elif not result.get("dry_run"):
            store.mark_sent(draft_id, error=result.get("reason"))

        return draft

    def schedules(self) -> List[Dict]:
        return list(self._schedules.values())

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
            "_keywords": (plan.keywords if plan else None),
            "_article_count": article_count,
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

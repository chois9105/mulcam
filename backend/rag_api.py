"""
RAG 뉴스레터 API 라우터

엔드포인트 설계 원칙:
  수집(느림) 과 조회/생성(빠름) 을 분리한다.
  RSS 수집 + 본문 크롤링 + 임베딩은 1~2분 걸리므로 매 요청마다 하면 안 된다.
  한 번 /rag/build 로 색인을 만들어두고, 그 뒤 /rag/ask 나 /rag/summarize 를
  여러 번 빠르게 호출하는 구조.

  POST /rag/build      뉴스 수집 -> 본문 크롤링 -> 색인 (준비 단계, 하루 1~2회)
  GET  /rag/status     색인이 준비됐는지 확인
  POST /rag/ask        리서치 - 질문에 기사 근거로 답변
  POST /rag/summarize  요약 - 3가지 스타일 중 선택
  GET  /rag/styles     사용 가능한 요약 스타일 목록
  GET  /rag/news       수집된 원본 뉴스 JSON (링크 포함, 상세페이지 이동용)
  POST /rag/draft      요약+검수 -> 프론트엔드 NewsletterDraft 형식으로 반환
  GET  /rag/drafts     생성된 초안 목록
  GET  /rag/drafts/{id} 초안 상세
"""

from datetime import datetime
from typing import List, Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from adapters import build_draft
from article_fetcher import enrich
from rag_engine import STYLE_INFO, NewsRAG
from reviewer import NewsletterReviewer
from rss_collector import DEFAULT_FEEDS, RSSCollector

router = APIRouter(prefix="/rag", tags=["RAG 뉴스레터"])

# 마지막 수집 결과를 메모리에 보관 (원본 JSON 조회용)
_state = {"news": [], "built_at": None, "count": 0, "full_text_ok": 0, "drafts": {}}


# ---------- 요청 모델 ----------
class BuildRequest(BaseModel):
    limit_per_feed: int = Field(15, ge=1, le=50, description="피드당 가져올 기사 수")
    fetch_full_text: bool = Field(True, description="링크를 따라가 본문까지 가져올지")


class AskRequest(BaseModel):
    question: str = Field(..., description="질문", examples=["오늘 반도체 관련 소식은?"])
    k: int = Field(5, ge=1, le=20, description="근거로 쓸 기사 수")


class SummarizeRequest(BaseModel):
    topic: str = Field(..., description="주제", examples=["오늘의 IT 뉴스"])
    style: Literal["brief", "newsletter", "deep"] = Field(
        "newsletter", description="brief=짧은브리핑 / newsletter=표준 / deep=심층분석"
    )
    k: Optional[int] = Field(None, description="비우면 스타일별 권장값 사용")


class DraftRequest(BaseModel):
    """프론트엔드 대시보드용 초안 생성 요청"""
    topic: str = Field(..., description="주제 또는 키워드", examples=["AI 반도체"])
    style: Literal["brief", "newsletter", "deep"] = Field("newsletter")
    keywords: List[str] = Field(default_factory=list, description="태그로 붙일 키워드")
    frequency: Literal["daily", "weekly", "biweekly", "monthly"] = Field("daily")
    review: bool = Field(True, description="검수 에이전트를 돌릴지 (끄면 빠르지만 점수 없음)")


# ---------- 엔드포인트 ----------
@router.get("/styles", summary="요약 스타일 목록")
async def get_styles():
    return {"styles": STYLE_INFO}


@router.get("/status", summary="색인 준비 상태")
async def status():
    return {
        "ready": _state["built_at"] is not None,
        "built_at": _state["built_at"],
        "news_count": _state["count"],
        "full_text_count": _state["full_text_ok"],
        "feeds": list(DEFAULT_FEEDS.keys()),
    }


@router.post("/build", summary="뉴스 수집 + 본문 크롤링 + 색인 생성")
async def build(req: BuildRequest):
    try:
        collector = RSSCollector()
        news = collector.fetch_all_news(limit_per_feed=req.limit_per_feed)
        if not news:
            raise HTTPException(400, "수집된 뉴스가 없습니다. (모두 중복이거나 피드 오류)")

        full = {"ok": 0, "fail": 0}
        if req.fetch_full_text:
            full = enrich(news)

        rag = NewsRAG()
        indexed = rag.build(news)

        _state.update({
            "news": news,
            "built_at": datetime.now().isoformat(),
            "count": indexed,
            "full_text_ok": full["ok"],
        })
        return {
            "success": True,
            "collected": len(news),
            "indexed": indexed,
            "full_text": full,
            "built_at": _state["built_at"],
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"색인 생성 실패: {e}")


@router.get("/news", summary="수집된 원본 뉴스 (링크 포함)")
async def get_news(limit: int = 50, source: Optional[str] = None):
    items = _state["news"]
    if source:
        items = [n for n in items if source in n.get("source", "")]
    return {"count": len(items), "news": items[:limit]}


@router.post("/ask", summary="리서치 - 기사 근거 답변")
async def ask(req: AskRequest):
    try:
        rag = NewsRAG()
        return rag.ask(req.question, k=req.k)
    except RuntimeError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"답변 생성 실패: {e}")


@router.post("/summarize", summary="요약 - 3가지 스타일")
async def summarize(req: SummarizeRequest):
    try:
        rag = NewsRAG()
        return rag.summarize(req.topic, style=req.style, k=req.k)
    except ValueError as e:
        raise HTTPException(422, str(e))
    except RuntimeError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"요약 생성 실패: {e}")


@router.post("/draft", summary="초안 생성 (프론트엔드 NewsletterDraft 형식)")
async def create_draft(req: DraftRequest):
    """
    요약 + 검수를 한 번에 돌려, 프론트엔드가 그대로 화면에 꽂을 수 있는
    NewsletterDraft 형식으로 돌려준다.

    프론트엔드 agent_graph.py 의 가짜 데이터를 이 응답으로 바꾸면 된다.
    """
    try:
        rag = NewsRAG()
        result = rag.summarize(req.topic, style=req.style)

        review = audit = None
        if req.review:
            reviewer = NewsletterReviewer()
            review = reviewer.review(result["newsletter"], result["sources"])
            audit = reviewer.audit_report(review)

        draft_id = f"draft_{datetime.now():%Y%m%d_%H%M%S}"
        draft = build_draft(
            draft_id=draft_id,
            result=result,
            review=review,
            audit=audit,
            frequency=req.frequency,
            keywords=req.keywords or [req.topic],
        )
        _state["drafts"][draft_id] = draft
        return draft
    except RuntimeError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"초안 생성 실패: {e}")


@router.get("/drafts", summary="생성된 초안 목록")
async def list_drafts(status: str = "all"):
    items = list(_state["drafts"].values())
    if status != "all":
        items = [d for d in items if d.get("status") == status]
    return {"count": len(items), "drafts": items}


@router.get("/drafts/{draft_id}", summary="초안 상세")
async def get_draft(draft_id: str):
    draft = _state["drafts"].get(draft_id)
    if not draft:
        raise HTTPException(404, f"초안을 찾을 수 없습니다: {draft_id}")
    return draft


@router.post("/summarize/compare", summary="3가지 스타일 한번에 비교")
async def summarize_compare(topic: str):
    try:
        rag = NewsRAG()
        return rag.summarize_all_styles(topic)
    except RuntimeError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"비교 생성 실패: {e}")

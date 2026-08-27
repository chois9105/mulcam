"""
화면 연동 API — 엔드포인트 3개

AgentLetter Compact 화면의 버튼 세 개에 하나씩 대응한다.

    ① [뉴스레터 요청]  POST /api/newsletter/request
    ② [수정 요청]      POST /api/drafts/{id}/revise
    ③ [최종 승인]      POST /api/drafts/{id}/approve   (주기 포함)

주기는 화면에서 [최종 승인] 옆에 있으므로 승인 요청에 함께 담아 받는다.
"""

from __future__ import annotations

from datetime import datetime
import logging
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

import scheduler
from newsletter_service import FREQUENCY_LABEL, service

router = APIRouter(prefix="/api", tags=["화면 연동"])
logger = logging.getLogger(__name__)

Frequency = Literal["every_30_minutes", "hourly", "daily", "weekly"]
DraftStatus = Literal["all", "pending", "approved", "rejected", "sent"]


# ------------------------------------------------------------------
# 요청 모델
# ------------------------------------------------------------------
class NewsletterRequest(BaseModel):
    """① 뉴스레터 요청"""
    request_text: str = Field(
        ...,
        min_length=2,
        description="원하는 뉴스레터 내용. 키워드도 되고 문장도 된다.",
        examples=["생성형 AI와 LangGraph의 이번 주 주요 뉴스를 실무자 관점에서 5개 정도 정리해 주세요."],
    )


class ReviseRequest(BaseModel):
    """② 수정 요청 — 화면의 '이렇게 바꾸어주세요' 한 칸"""
    direction: str = Field(
        ...,
        min_length=2,
        description="어떻게 바꿔달라는 요청",
        examples=["너무 기술적인 표현은 줄이고, 핵심 뉴스 5개를 먼저 보여준 뒤 각 항목을 실무자가 이해하기 쉽게 설명해 주세요."],
    )


class ApproveRequest(BaseModel):
    """③ 최종 승인 — 주기를 함께 받는다"""
    frequency: Frequency = Field("daily", description="자동 생성 주기")
    approved_template: Optional[str] = Field(
        default=None,
        description="사용자가 승인한 최종 HTML. 비우면 현재 초안의 HTML을 저장한다.",
    )


# ------------------------------------------------------------------
# ① 뉴스레터 요청
# ------------------------------------------------------------------
@router.post("/newsletter/request", summary="① 뉴스레터 요청")
async def create_newsletter(req: NewsletterRequest):
    """
    입력한 내용으로 뉴스를 찾아 요약본을 만든다.

    요청 분석 → 기사 검색 → 기사별 요약 → 한국어 다듬기 → 검수 → 저장
    10~20초 걸린다.
    """
    try:
        draft = service.create(req.request_text)
        return service.to_response(draft)
    except RuntimeError as e:
        # 색인이 없거나 API 키가 없는 경우
        raise HTTPException(409, str(e))
    except ValueError as e:
        raise HTTPException(404, f"관련 뉴스를 찾지 못했습니다: {e}")
    except Exception as e:
        logger.exception("뉴스레터 생성 실패")
        raise HTTPException(500, "생성에 실패했습니다. 잠시 후 다시 시도해 주세요.") from e


# ------------------------------------------------------------------
# ② 수정 요청
# ------------------------------------------------------------------
@router.post("/drafts/{draft_id}/revise", summary="② 수정 요청")
async def revise_newsletter(draft_id: str, req: ReviseRequest):
    """
    요청대로 다시 쓴다. 기사를 새로 찾지 않고 같은 근거로 다시 작성한다.
    응답은 ① 과 같은 모양이라 화면은 카드만 갈아끼우면 된다.
    """
    try:
        draft = service.get(draft_id)
        if not draft:
            raise HTTPException(404, f"요약본을 찾을 수 없습니다: {draft_id}")
        if draft["status"] in ("approved", "sent"):
            raise HTTPException(409, "이미 승인된 요약본은 수정할 수 없습니다.")
        updated = service.revise(draft_id, req.direction)
        return service.to_response(updated)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("뉴스레터 수정 실패: %s", draft_id)
        raise HTTPException(500, "수정에 실패했습니다. 잠시 후 다시 시도해 주세요.") from e


# ------------------------------------------------------------------
# ③ 최종 승인 (주기 설정 + 발송 등록)
# ------------------------------------------------------------------
@router.post("/drafts/{draft_id}/approve", summary="③ 최종 승인 + 주기 설정")
async def approve_newsletter(draft_id: str, req: ApproveRequest):
    """
    승인하고 발송 주기를 저장한다.
    이후 그 주기마다 같은 요청으로 뉴스를 새로 모아 n8n 발송 대기에 올린다.
    승인 API 자체에서는 메일을 보내지 않는다.
    """
    try:
        draft = service.get(draft_id)
        if not draft:
            raise HTTPException(404, f"요약본을 찾을 수 없습니다: {draft_id}")
        if draft["status"] in ("approved", "sent"):
            # Streamlit 재실행이나 네트워크 재시도로 같은 승인 요청이 다시
            # 들어와도 실패로 보지 않는다. 최초 승인 결과를 그대로 돌려준다.
            res = service.to_response(draft)
            res["already_approved"] = True
            res["message"] = (
                "이미 승인된 요약본입니다. 기존 승인 상태를 유지합니다."
            )
            return res
        approved = service.approve(draft_id, req.frequency, req.approved_template)
        res = service.to_response(approved)
        res["message"] = (
            f"승인되었습니다. 주기: {FREQUENCY_LABEL.get(req.frequency, req.frequency)}"
        )
        return res
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("뉴스레터 승인 실패: %s", draft_id)
        raise HTTPException(500, "승인에 실패했습니다. 잠시 후 다시 시도해 주세요.") from e


# ------------------------------------------------------------------
# 보조 (버튼은 아니지만 화면이 쓰면 편한 것)
# ------------------------------------------------------------------
@router.get("/drafts", summary="요약본 목록 (② 드롭다운·③ 목록용)")
async def list_drafts(status: DraftStatus = "all"):
    try:
        items = [service.to_response(d) for d in service.list_drafts(status)]
        return {"count": len(items), "drafts": items}
    except Exception as e:
        logger.exception("뉴스레터 목록 조회 실패")
        raise HTTPException(500, "목록을 불러오지 못했습니다.") from e


@router.get("/drafts/{draft_id}", summary="요약본 상세")
async def get_draft(draft_id: str):
    try:
        draft = service.get(draft_id)
        if not draft:
            raise HTTPException(404, f"요약본을 찾을 수 없습니다: {draft_id}")
        return service.to_response(draft)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("뉴스레터 상세 조회 실패: %s", draft_id)
        raise HTTPException(500, "요약본을 불러오지 못했습니다.") from e


class DispatchResultRequest(BaseModel):
    sent: bool = Field(..., description="외부 메일 API 발송 성공 여부")
    error: Optional[str] = Field(None, max_length=500, description="실패 사유")


@router.get("/dispatches/pending", summary="n8n용 미발송 뉴스레터 목록")
async def list_pending_dispatches():
    """최초 승인 또는 정기 생성 후 아직 발송 완료되지 않은 건을 돌려준다."""
    try:
        items = [
            service.to_dispatch_response(d)
            for d in service.pending_dispatches()
        ]
        return {"count": len(items), "dispatches": items}
    except Exception as e:
        logger.exception("미발송 목록 조회 실패")
        raise HTTPException(500, "미발송 목록을 불러오지 못했습니다.") from e


@router.post("/dispatches/{draft_id}/result", summary="n8n 발송 결과 기록")
async def record_dispatch_result(draft_id: str, req: DispatchResultRequest):
    """메일 API 호출 뒤 n8n이 성공/실패를 기록한다. 이 API는 메일을 보내지 않는다."""
    try:
        draft = service.record_dispatch_result(
            draft_id, sent=req.sent, error=req.error
        )
        return service.to_response(draft)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e
    except Exception as e:
        logger.exception("발송 결과 기록 실패: %s", draft_id)
        raise HTTPException(500, "발송 결과를 기록하지 못했습니다.") from e


# ------------------------------------------------------------------
# 운영 확인용 (버튼은 아니지만 상태를 볼 수 있어야 한다)
# ------------------------------------------------------------------
@router.get("/status", summary="백엔드 상태 (저장소·스케줄러·수집 현황)")
async def backend_status():
    try:
        return {
            "storage": service.storage_mode(),
            "scheduler": scheduler.status(),
            "drafts": len(service.list_drafts()),
            "schedules": len(service.schedules()),
        }
    except Exception as e:
        logger.exception("백엔드 상태 조회 실패")
        raise HTTPException(503, "DB 또는 스케줄러 상태를 확인하지 못했습니다.") from e


@router.post("/news/collect", summary="뉴스 수집을 지금 실행 (평소엔 스케줄러가 함)")
async def collect_now(limit_per_feed: int = Query(12, ge=1, le=50)):
    """1~2분 걸린다. 요청 버튼과 분리해 둔 이유다."""
    return scheduler.collect_news(limit_per_feed=limit_per_feed)


# ------------------------------------------------------------------
# LangGraph 파이프라인 (과제 요구사항 시연용)
#
# 위의 3개 엔드포인트와 하는 일은 같다. 다만 실행을 LangGraph 로 하여
# 과제가 요구한 두 가지를 실제로 보여준다.
#   - Conditional Edges : 검수 미달이면 작성 단계로 되돌아가는 순환
#   - Human-in-the-Loop : 승인 전까지 그래프를 멈추고 상태를 저장
# ------------------------------------------------------------------
class GraphStartRequest(BaseModel):
    request_text: str = Field(..., min_length=2)
    thread_id: Optional[str] = Field(None, description="비우면 자동 생성")


class GraphResumeRequest(BaseModel):
    action: Literal["approve", "revise", "reject"]
    feedback: str = Field("", description="revise 일 때 어떻게 바꿀지")
    frequency: Frequency = Field("daily")


@router.post("/graph/start", summary="[LangGraph] 실행 - 인간 승인 노드에서 멈춘다")
async def graph_start(req: GraphStartRequest):
    import graph_pipeline as gp
    tid = req.thread_id or f"thread_{datetime.now():%Y%m%d_%H%M%S}"
    try:
        return gp.start(req.request_text, tid)
    except Exception as e:
        logger.exception("그래프 실행 실패: %s", tid)
        raise HTTPException(500, "그래프 실행에 실패했습니다.") from e


@router.post("/graph/{thread_id}/resume", summary="[LangGraph] 사람의 결정으로 이어서 실행")
async def graph_resume(thread_id: str, req: GraphResumeRequest):
    import graph_pipeline as gp
    try:
        return gp.resume(thread_id, req.action, req.feedback, req.frequency)
    except Exception as e:
        logger.exception("그래프 재개 실패: %s", thread_id)
        raise HTTPException(500, "그래프 재개에 실패했습니다.") from e


@router.get("/graph/{thread_id}", summary="[LangGraph] 지금 어느 노드에서 멈춰 있나")
async def graph_state(thread_id: str):
    import graph_pipeline as gp
    return gp.state_of(thread_id)

# ------------------------------------------------------------------
# 요청 다듬기 도우미
#
# 초보자는 무엇을 어떻게 적어야 할지 모른다. '로봇' 이라고만 적으면
# 결과가 뭉뚱그려진다. 편집장이 데스크에서 묻듯 되물어 준다.
# ------------------------------------------------------------------
class AdviseRequest(BaseModel):
    keyword: str = Field(..., min_length=1,
                         description="사용자가 적은 주제나 키워드",
                         examples=["로봇"])


@router.post("/newsletter/advise", summary="① 보조 - 되묻기 3가지 + 추천 요청문 3가지")
async def advise_request(req: AdviseRequest):
    """
    키워드를 넣으면 무엇을 보고 싶은지 좁히도록 돕는다.

    - questions   : 생각을 정리하도록 돕는 질문 3개
    - suggestions : 그대로 넣으면 되는 요청문 3개
    - note        : 한 줄 안내
    """
    try:
        import advisor
        a = advisor.advise(req.keyword)
        return {
            "keyword": req.keyword,
            "questions": a.questions,
            "suggestions": a.suggestions,
            "note": a.note,
        }
    except RuntimeError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        logger.exception("요청문 제안 생성 실패")
        raise HTTPException(500, "제안 생성에 실패했습니다.") from e

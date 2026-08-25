"""
화면 연동 API — 엔드포인트 3개

AgentLetter Compact 화면의 버튼 세 개에 하나씩 대응한다.

    ① [뉴스레터 요청]  POST /api/newsletter/request
    ② [수정 요청]      POST /api/drafts/{id}/revise
    ③ [최종 승인]      POST /api/drafts/{id}/approve   (주기 포함)

주기는 화면에서 [최종 승인] 옆에 있으므로 승인 요청에 함께 담아 받는다.
"""

from __future__ import annotations

from typing import List, Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

import scheduler
from newsletter_service import FREQUENCY_LABEL, service

router = APIRouter(prefix="/api", tags=["화면 연동"])

Frequency = Literal["once", "daily", "weekly", "biweekly", "monthly"]


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
    frequency: Frequency = Field("daily", description="발송 주기")
    recipients: Optional[List[str]] = Field(
        default=None, description="받는 사람 메일. 비우면 .env 기본값을 쓴다."
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
        raise HTTPException(500, f"생성에 실패했습니다: {e}")


# ------------------------------------------------------------------
# ② 수정 요청
# ------------------------------------------------------------------
@router.post("/drafts/{draft_id}/revise", summary="② 수정 요청")
async def revise_newsletter(draft_id: str, req: ReviseRequest):
    """
    요청대로 다시 쓴다. 기사를 새로 찾지 않고 같은 근거로 다시 작성한다.
    응답은 ① 과 같은 모양이라 화면은 카드만 갈아끼우면 된다.
    """
    draft = service.get(draft_id)
    if not draft:
        raise HTTPException(404, f"요약본을 찾을 수 없습니다: {draft_id}")
    if draft["status"] == "approved":
        raise HTTPException(409, "이미 승인된 요약본은 수정할 수 없습니다.")

    try:
        updated = service.revise(draft_id, req.direction)
        return service.to_response(updated)
    except Exception as e:
        raise HTTPException(500, f"수정에 실패했습니다: {e}")


# ------------------------------------------------------------------
# ③ 최종 승인 (주기 설정 + 발송 등록)
# ------------------------------------------------------------------
@router.post("/drafts/{draft_id}/approve", summary="③ 최종 승인 + 주기 설정")
async def approve_newsletter(draft_id: str, req: ApproveRequest):
    """
    승인하고 발송 주기를 저장한다.
    주기가 `once` 가 아니면, 이후 그 주기마다 같은 요청으로 뉴스를 새로 모아
    요약본을 만들어 승인 대기에 올린다.
    """
    draft = service.get(draft_id)
    if not draft:
        raise HTTPException(404, f"요약본을 찾을 수 없습니다: {draft_id}")
    if draft["status"] == "approved":
        raise HTTPException(409, "이미 승인된 요약본입니다.")

    try:
        approved = service.approve(draft_id, req.frequency, req.recipients)
        res = service.to_response(approved)
        res["message"] = (
            f"승인되었습니다. 주기: {FREQUENCY_LABEL.get(req.frequency, req.frequency)}"
        )
        return res
    except Exception as e:
        raise HTTPException(500, f"승인에 실패했습니다: {e}")


# ------------------------------------------------------------------
# 보조 (버튼은 아니지만 화면이 쓰면 편한 것)
# ------------------------------------------------------------------
@router.get("/drafts", summary="요약본 목록 (② 드롭다운·③ 목록용)")
async def list_drafts(status: str = "all"):
    items = [service.to_response(d) for d in service.list_drafts(status)]
    return {"count": len(items), "drafts": items}


@router.get("/drafts/{draft_id}", summary="요약본 상세")
async def get_draft(draft_id: str):
    draft = service.get(draft_id)
    if not draft:
        raise HTTPException(404, f"요약본을 찾을 수 없습니다: {draft_id}")
    return service.to_response(draft)


# ------------------------------------------------------------------
# 운영 확인용 (버튼은 아니지만 상태를 볼 수 있어야 한다)
# ------------------------------------------------------------------
@router.get("/status", summary="백엔드 상태 (저장소·스케줄러·수집 현황)")
async def backend_status():
    return {
        "storage": service.storage_mode(),
        "scheduler": scheduler.status(),
        "drafts": len(service.list_drafts()),
        "schedules": len(service.schedules()),
    }


@router.post("/news/collect", summary="뉴스 수집을 지금 실행 (평소엔 스케줄러가 함)")
async def collect_now(limit_per_feed: int = 12):
    """1~2분 걸린다. 요청 버튼과 분리해 둔 이유다."""
    return scheduler.collect_news(limit_per_feed=limit_per_feed)

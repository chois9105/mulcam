"""
main.py
FastAPI 기반 맞춤형 AI 뉴스레터 제작 및 자동 검수 에이전트 백엔드 서버

기능:
1. 구독 키워드 및 발송 주기 관리 API
2. LangGraph 멀티 에이전트 뉴스레터 생성 파이프라인 트리거 API
3. 뉴스레터 초안 헤드 목록 및 상세 조회 API
4. Human-in-the-Loop(HITL) 최종 승인 및 피드백 수정 요청 API
5. Apple HIG 프론트엔드 정적 파일 서빙
"""

import os
from typing import List, Dict, Any
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

from models import (
    KeywordSubscription,
    ScheduleConfig,
    NewsletterDraft,
    RevisionRequest,
    BatchApprovalRequest,
    FrequencyEnum,
    StatusEnum
)
from agent_graph import workflow_engine

# FastAPI 애플리케이션 초기화
app = FastAPI(
    title="AgentLetter Pro API",
    description="LangGraph 기반 맞춤형 뉴스레터 제작 및 자동 검수 멀티 에이전트 백엔드",
    version="1.0.0"
)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------------------------------------------
# 인메모리 저장소 초기화 (초기 데이터 등록)
# -------------------------------------------------------------
active_keywords: List[str] = [
    "LangGraph",
    "Human-in-the-Loop",
    "FastAPI",
    "AWS EventBridge",
    "Multi-Agent"
]

current_schedule: Dict[str, Any] = {
    "frequency": "daily",
    "dispatch_time": "08:30",
    "days_of_week": ["mon", "wed", "fri"]
}

# 초기 뉴스레터 초안 4건 자동 로드
newsletter_store: Dict[str, Dict[str, Any]] = {}


def _seed_initial_drafts():
    """초기 Mock 초안 데이터베이스 시딩"""
    initial_samples = [
        {
            "id": "draft-001",
            "title": "LangGraph 기반 멀티 에이전트 오케스트레이션과 실무 적용 가이드",
            "summary": "리서치, 작성, 검수 에이전트가 협업하는 순환형 파이프라인 구조와 Conditional Edges를 통한 품질 자동 보정 메커니즘을 심층 분석합니다.",
            "tags": ["LangGraph", "Multi-Agent", "StateCheckpoint"],
            "date": "2026.08.24 08:30",
            "frequency": "daily",
            "status": "pending",
            "score": 96,
            "score_grade": "A+ 우수",
            "author_agent": "작성 에이전트 v2.4 (Claude 3.5 Sonnet)",
            "inspector_agent": "검수 에이전트 v3.1 (GPT-4o)",
            "selected": False,
            "article_html": """
              <div class="article-hero-box">
                <div class="article-hero-title">💡 이번 호 핵심 요약 (Executive Summary)</div>
                <div class="article-hero-text">
                  단일 프롬프트 생성의 한계를 넘어, <strong>리서치-작성-검수-인간 승인</strong>으로 이어지는 LangGraph 그래프 아키텍처가 엔터프라이즈 생성 파이프라인의 표준으로 자리잡고 있습니다.
                </div>
              </div>
              <h2>1. 왜 단일 LLM 대신 멀티 에이전트인가?</h2>
              <p>복잡한 뉴스레터나 전문 리포트를 생성할 때 단일 LLM은 환각(Hallucination)과 맥락 누락의 문제를 겪습니다. LangGraph는 각 에이전트에게 명확한 역할을 부여하고 상태를 중앙에서 보존(Checkpoint)하여 고품질을 보장합니다.</p>
              <h2>2. Conditional Edges를 통한 순환 품질 검수</h2>
              <p>검수 에이전트가 초안의 신뢰도를 진단하여 90점 미만일 경우 작성 에이전트 노드로 되돌아가는 조건부 분기를 실행합니다.</p>
            """,
            "sources": [
                {"title": "LangGraph Multi-Agent Architecture Whitepaper 2026", "domain": "docs.langchain.com", "summary": "멀티 에이전트 상태 전이 제어 및 HITL 체크포인트 설계 공식 가이드"}
            ],
            "audit_report": {
                "readability": 98,
                "fact_accuracy": 95,
                "coherence": 96,
                "reviewer_comment": "타겟 독자에게 적절한 어조와 명확한 다이어그램 코드 예시가 포함되어 검수를 우수하게 통과하였습니다.",
                "loop_count": "1회 순환 후 통과 (최초 84점 -> 보완 후 96점)"
            }
        },
        {
            "id": "draft-002",
            "title": "FastAPI와 LangGraph State Checkpoint를 연동한 실시간 HITL 시스템",
            "summary": "FastAPI의 REST API와 웹소켓을 통해 LangGraph의 interrupt_before 이벤트를 브라우저에 실시간 스트리밍하고 승인/반려하는 아키텍처를 소개합니다.",
            "tags": ["FastAPI", "Human-in-the-Loop", "WebSockets"],
            "date": "2026.08.24 07:15",
            "frequency": "daily",
            "status": "pending",
            "score": 93,
            "score_grade": "A 우수",
            "author_agent": "작성 에이전트 v2.4 (Claude 3.5 Sonnet)",
            "inspector_agent": "검수 에이전트 v3.1 (GPT-4o)",
            "selected": False,
            "article_html": """
              <div class="article-hero-box">
                <div class="article-hero-title">💡 이번 호 핵심 요약 (Executive Summary)</div>
                <div class="article-hero-text">
                  에이전트가 백그라운드에서 작업을 처리하다가 사람이 검토해야 할 시점에 정확히 멈추고(interrupt), 웹 UI에서 원클릭으로 이어받아 실행하는 파이프라인을 다룹니다.
                </div>
              </div>
              <h2>1. 비동기 인터럽트와 상태 체크포인트의 필요성</h2>
              <p>AI가 생성한 뉴스레터 초안을 즉시 발송하지 않고 관리자가 웹 UI에서 검토 후 승인할 수 있도록 FastAPI 백엔드는 LangGraph의 thread_id를 기반으로 진행 상태를 유지합니다.</p>
            """,
            "sources": [
                {"title": "FastAPI Human-in-the-Loop Integration Recipes", "domain": "github.com/fastapi/hitl-example", "summary": "FastAPI 백그라운드 태스크 및 LangGraph 체크포인트 연동 오픈소스"}
            ],
            "audit_report": {
                "readability": 94,
                "fact_accuracy": 92,
                "coherence": 93,
                "reviewer_comment": "API 엔드포인트 구조 설명이 명확하며, 프론트엔드 연동 설명이 잘 작성되었습니다.",
                "loop_count": "0회 (초기 작성 즉시 93점 통과)"
            }
        },
        {
            "id": "draft-003",
            "title": "AWS EventBridge & Lambda 기반 정기 뉴스레터 서버리스 발송 자동화",
            "summary": "CloudWatch Events와 EventBridge 크론 스케줄을 통해 매일/매주 정해진 시각에 뉴스레터 에이전트 파이프라인을 구동하고 SES로 대량 발송하는 클라우드 아키텍처.",
            "tags": ["AWS EventBridge", "CloudWatch", "Lambda", "SES"],
            "date": "2026.08.23 18:30",
            "frequency": "weekly",
            "status": "approved",
            "score": 98,
            "score_grade": "A+ 최우수",
            "author_agent": "작성 에이전트 v2.4 (Claude 3.5 Sonnet)",
            "inspector_agent": "검수 에이전트 v3.1 (GPT-4o)",
            "selected": True,
            "article_html": """
              <div class="article-hero-box">
                <div class="article-hero-title">💡 이번 호 핵심 요약 (Executive Summary)</div>
                <div class="article-hero-text">
                  매일 오전 8시 30분, AWS EventBridge가 람다 트리거를 작동시켜 리서치 에이전트를 깨우고, 생성된 뉴스레터는 사람이 승인하는 즉시 Amazon SES를 통해 발송됩니다.
                </div>
              </div>
              <h2>1. 서버리스 크론 스케줄러 설계</h2>
              <p>AWS EventBridge Rule을 활용하여 사용자가 웹 화면에서 설정한 주기(매일, 매주 월/수/금 등)에 맞춰 정확한 타임존(KST)으로 트리거 이벤트를 발행합니다.</p>
            """,
            "sources": [
                {"title": "AWS EventBridge Scheduling Patterns for AI Agents", "domain": "aws.amazon.com/blogs/architecture", "summary": "AWS 공식 아키텍처 블로그: 생성형 AI 워크플로우를 위한 스케줄링 가이드"}
            ],
            "audit_report": {
                "readability": 99,
                "fact_accuracy": 98,
                "coherence": 97,
                "reviewer_comment": "완벽한 클라우드 아키텍처 다이어그램 및 비용 분석이 포함되어 최고점을 부여하였습니다.",
                "loop_count": "0회 (초기 작성 즉시 98점 통과)"
            }
        }
    ]

    for item in initial_samples:
        newsletter_store[item["id"]] = item
        # 워크플로우 엔진에도 체크포인트 상태 등록
        workflow_engine.checkpoints[item["id"]] = {
            "draft_id": item["id"],
            "keywords": item["tags"],
            "frequency": item["frequency"],
            "title": item["title"],
            "summary": item["summary"],
            "article_html": item["article_html"],
            "tags": item["tags"],
            "date": item["date"],
            "score": item["score"],
            "score_grade": item["score_grade"],
            "author_agent": item["author_agent"],
            "inspector_agent": item["inspector_agent"],
            "status": item["status"],
            "selected": item["selected"],
            "research_sources": item["sources"],
            "audit_report": item["audit_report"],
            "step_log": ["초기 시딩 완료"]
        }


_seed_initial_drafts()


# -------------------------------------------------------------
# 1. 키워드 및 구독 주기 관련 API
# -------------------------------------------------------------
@app.get("/api/keywords", summary="구독 중인 관심 키워드 목록 조회")
def get_keywords():
    return {"keywords": active_keywords}


@app.post("/api/keywords", summary="새 관심 키워드 추가")
def add_keyword(sub: KeywordSubscription):
    clean = sub.keyword.strip().replace("#", "")
    if not clean:
        raise HTTPException(status_code=400, detail="키워드를 입력해주세요.")
    if clean in active_keywords:
        raise HTTPException(status_code=409, detail="이미 등록된 키워드입니다.")
    active_keywords.append(clean)
    return {"message": f"'{clean}' 키워드가 등록되었습니다.", "keywords": active_keywords}


@app.delete("/api/keywords/{keyword}", summary="관심 키워드 삭제")
def delete_keyword(keyword: str):
    clean = keyword.strip().replace("#", "")
    if clean in active_keywords:
        active_keywords.remove(clean)
        return {"message": f"'{clean}' 키워드가 삭제되었습니다.", "keywords": active_keywords}
    raise HTTPException(status_code=404, detail="해당 키워드를 찾을 수 없습니다.")


@app.get("/api/schedule", summary="발송 주기 설정 조회")
def get_schedule():
    return current_schedule


@app.post("/api/schedule", summary="발송 주기 설정 변경")
def update_schedule(config: ScheduleConfig):
    current_schedule["frequency"] = config.frequency.value
    current_schedule["dispatch_time"] = config.dispatch_time
    current_schedule["days_of_week"] = config.days_of_week
    return {"message": "발송 주기가 업데이트되었습니다.", "schedule": current_schedule}


# -------------------------------------------------------------
# 2. 뉴스레터 초안 헤드 목록 및 상세 조회 API
# -------------------------------------------------------------
@app.get("/api/drafts", summary="뉴스레터 초안 헤드 목록 조회")
def list_drafts(status: str = "all"):
    drafts_list = list(newsletter_store.values())
    if status != "all":
        drafts_list = [d for d in drafts_list if d.get("status") == status]
    return {"total": len(drafts_list), "drafts": drafts_list}


@app.get("/api/drafts/{draft_id}", summary="뉴스레터 초안 상세 조회")
def get_draft_detail(draft_id: str):
    if draft_id not in newsletter_store:
        raise HTTPException(status_code=404, detail="해당 초안을 찾을 수 없습니다.")
    return newsletter_store[draft_id]


# -------------------------------------------------------------
# 3. LangGraph 파이프라인 트리거 & Human-in-the-Loop API
# -------------------------------------------------------------
@app.post("/api/generate", summary="LangGraph 멀티 에이전트 뉴스레터 생성 트리거")
def trigger_generation():
    """
    [사용자 입력] -> [리서치 에이전트] -> [작성 에이전트] -> [검수 에이전트] -> [인간 승인 대기(interrupt_before)]
    """
    new_id = f"draft-{len(newsletter_store) + 1:03d}"
    keywords = active_keywords if active_keywords else ["AI 에이전트"]
    frequency = current_schedule.get("frequency", "daily")

    # LangGraph 워크플로우 실행
    result = workflow_engine.run_pipeline(new_id, keywords, frequency)
    newsletter_store[new_id] = result

    return {
        "message": "LangGraph 멀티 에이전트 파이프라인이 성공적으로 실행되어 인간 승인 대기 노드에 도달했습니다.",
        "draft": result
    }


@app.post("/api/drafts/{draft_id}/approve", summary="Human-in-the-Loop 최종 승인 및 발송 확정")
def approve_draft(draft_id: str):
    """
    관리자가 승인 시 FastAPI interrupt_before 체크포인트를 재개(Resume)하여 발송 노드로 진행
    """
    if draft_id not in newsletter_store:
        raise HTTPException(status_code=404, detail="해당 초안을 찾을 수 없습니다.")

    updated = workflow_engine.resume_approval(draft_id)
    newsletter_store[draft_id] = updated

    return {
        "message": f"'{updated['title']}' 뉴스레터가 최종 승인되어 AWS EventBridge 발송 큐에 등록되었습니다.",
        "draft": updated
    }


@app.post("/api/drafts/{draft_id}/revise", summary="Human-in-the-Loop 수정 요청 (에이전트 재작성 루프)")
def request_revision(draft_id: str, req: RevisionRequest):
    """
    사용자 피드백을 전달하여 작성 에이전트 및 검수 에이전트를 재실행(Conditional Loop)
    """
    if draft_id not in newsletter_store:
        raise HTTPException(status_code=404, detail="해당 초안을 찾을 수 없습니다.")

    updated = workflow_engine.resume_revision(draft_id, req.feedback)
    newsletter_store[draft_id] = updated

    return {
        "message": "수정 피드백이 작성 에이전트로 전달되어 재작성 및 재검수가 완료되었습니다.",
        "draft": updated
    }


@app.post("/api/drafts/batch-approve", summary="선택된 초안 헤드 일괄 승인")
def batch_approve(req: BatchApprovalRequest):
    approved_count = 0
    for draft_id in req.draft_ids:
        if draft_id in newsletter_store:
            updated = workflow_engine.resume_approval(draft_id)
            newsletter_store[draft_id] = updated
            approved_count += 1

    return {
        "message": f"총 {approved_count}건의 뉴스레터가 일괄 승인되었습니다.",
        "approved_ids": req.draft_ids
    }


# -------------------------------------------------------------
# 4. 프론트엔드 정적 파일 서빙
# -------------------------------------------------------------
base_dir = os.path.dirname(os.path.abspath(__file__))


@app.get("/", summary="Apple HIG 대시보드 웹 메인")
def serve_index():
    return FileResponse(os.path.join(base_dir, "index.html"))


# CSS, JS 등 정적 리소스 서빙
if os.path.exists(os.path.join(base_dir, "styles.css")):
    @app.get("/styles.css")
    def serve_css():
        return FileResponse(os.path.join(base_dir, "styles.css"), media_type="text/css")

if os.path.exists(os.path.join(base_dir, "app.js")):
    @app.get("/app.js")
    def serve_js():
        return FileResponse(os.path.join(base_dir, "app.js"), media_type="application/javascript")

if os.path.exists(os.path.join(base_dir, "mockData.js")):
    @app.get("/mockData.js")
    def serve_mock():
        return FileResponse(os.path.join(base_dir, "mockData.js"), media_type="application/javascript")


if __name__ == "__main__":
    import uvicorn
    print("=" * 70)
    print("🚀 AgentLetter Pro FastAPI 서버 시작: http://localhost:8000")
    print("🍎 Apple HIG 대시보드 웹 화면: http://localhost:8000/")
    print("📖 Swagger API 대화형 문서: http://localhost:8000/docs")
    print("=" * 70)
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

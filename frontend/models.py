"""
models.py
뉴스레터 제작 및 자동 검수 멀티 에이전트 시스템 Pydantic 데이터 모델
"""

from typing import List, Optional, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field
from datetime import datetime


class FrequencyEnum(str, Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    BIWEEKLY = "biweekly"
    MONTHLY = "monthly"


class StatusEnum(str, Enum):
    PENDING = "pending"       # 인간 승인 대기 (interrupt_before)
    APPROVED = "approved"     # 최종 승인 및 발송 완료
    REVISION = "revision"     # 품질 미달 또는 피드백으로 인한 수정 중


class KeywordSubscription(BaseModel):
    keyword: str
    created_at: str = Field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M"))


class ScheduleConfig(BaseModel):
    frequency: FrequencyEnum = FrequencyEnum.DAILY
    dispatch_time: str = "08:30"
    days_of_week: List[str] = ["mon", "wed", "fri"]


class ResearchSource(BaseModel):
    title: str
    domain: str
    summary: str
    url: Optional[str] = None


class AuditReport(BaseModel):
    readability: int = 95
    fact_accuracy: int = 94
    coherence: int = 96
    reviewer_comment: str
    loop_count: str = "0회"


class NewsletterDraft(BaseModel):
    id: str
    title: str
    summary: str
    tags: List[str]
    date: str = Field(default_factory=lambda: datetime.now().strftime("%Y.%m.%d %H:%M"))
    frequency: FrequencyEnum = FrequencyEnum.DAILY
    status: StatusEnum = StatusEnum.PENDING
    score: int = 95
    score_grade: str = "A+ 우수"
    author_agent: str = "작성 에이전트 v2.4 (Claude 3.5 Sonnet)"
    inspector_agent: str = "검수 에이전트 v3.1 (GPT-4o)"
    selected: bool = False
    article_html: str
    sources: List[ResearchSource] = []
    audit_report: AuditReport


class RevisionRequest(BaseModel):
    feedback: str
    preset_option: Optional[str] = None


class BatchApprovalRequest(BaseModel):
    draft_ids: List[str]

"""
MySQL 테이블 정의 (SQLAlchemy ORM)

ARCHITECTURE.md 의 ERD 를 그대로 옮긴 것이다. 테이블 10개.

    subscribers        뉴스레터 받을 사람
    keywords           관심 키워드
    templates          템플릿 3종 (a/b/c)
    schedules          언제 어떤 템플릿으로 보낼지
    articles           수집한 기사 + 본문
    drafts             생성된 뉴스레터 초안
    draft_sources      초안 <-> 근거 기사 연결
    review_guidelines  검수 지침
    audit_reports      검수 점수
    dispatch_logs      발송 이력
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON, BigInteger, Boolean, CHAR, Column, DateTime, ForeignKey, Index,
    Integer, String, Text, Time, UniqueConstraint,
)
from sqlalchemy.dialects.mysql import MEDIUMTEXT
from sqlalchemy.orm import relationship

from database import Base


def _pk():
    return Column(BigInteger, primary_key=True, autoincrement=True)


def _now():
    return Column(DateTime, default=datetime.now)


# ------------------------------------------------------------------
# 구독자 / 키워드
# ------------------------------------------------------------------
class Subscriber(Base):
    __tablename__ = "subscribers"

    id = _pk()
    email = Column(String(255), unique=True, nullable=False)
    name = Column(String(100))
    is_active = Column(Boolean, default=True)
    created_at = _now()

    keywords = relationship("Keyword", back_populates="subscriber",
                            cascade="all, delete-orphan")
    schedules = relationship("Schedule", back_populates="subscriber",
                             cascade="all, delete-orphan")


class Keyword(Base):
    __tablename__ = "keywords"
    __table_args__ = (UniqueConstraint("subscriber_id", "keyword", name="uq_sub_keyword"),)

    id = _pk()
    subscriber_id = Column(BigInteger, ForeignKey("subscribers.id", ondelete="CASCADE"))
    keyword = Column(String(100), nullable=False)
    created_at = _now()

    subscriber = relationship("Subscriber", back_populates="keywords")


# ------------------------------------------------------------------
# 템플릿
# ------------------------------------------------------------------
class Template(Base):
    """뉴스레터 출력 형태. 기본 3종(a/b/c)은 templates_seed.py 에서 넣는다."""
    __tablename__ = "templates"

    id = _pk()
    code = Column(CHAR(1), unique=True, nullable=False)      # a / b / c
    name = Column(String(50), nullable=False)                # 짧은 브리핑 ...
    description = Column(String(255))
    style = Column(String(20), nullable=False)               # brief/newsletter/deep
    prompt_body = Column(Text, nullable=False)               # 작성 지시문
    article_count = Column(Integer, default=8)               # 참고 기사 수
    is_default = Column(Boolean, default=True)               # 코드에서 온 기본값인가
    created_at = _now()
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


# ------------------------------------------------------------------
# 스케줄
# ------------------------------------------------------------------
class Schedule(Base):
    __tablename__ = "schedules"

    id = _pk()
    subscriber_id = Column(BigInteger, ForeignKey("subscribers.id", ondelete="CASCADE"))
    template_id = Column(BigInteger, ForeignKey("templates.id"))
    frequency = Column(String(20), default="daily")          # daily/weekly/biweekly/monthly
    dispatch_time = Column(Time)                             # 08:30
    days_of_week = Column(String(50), default="mon,wed,fri")
    is_active = Column(Boolean, default=True)
    last_run_at = Column(DateTime)

    subscriber = relationship("Subscriber", back_populates="schedules")
    template = relationship("Template")


# ------------------------------------------------------------------
# 기사
# ------------------------------------------------------------------
class Article(Base):
    __tablename__ = "articles"
    __table_args__ = (Index("ix_articles_collected", "collected_at"),)

    id = _pk()
    url_hash = Column(CHAR(32), unique=True, nullable=False)  # 중복 수집 방지
    title = Column(String(500), nullable=False)
    link = Column(String(1000), nullable=False)               # 상세페이지 주소
    description = Column(Text)                                # RSS 가 준 짧은 요약
    content = Column(MEDIUMTEXT)                              # 크롤링한 본문
    source = Column(String(100))                              # 연합뉴스 ...
    published_at = Column(String(100))                        # RSS 원본 형식 그대로
    has_full_text = Column(Boolean, default=False)
    collected_at = _now()


# ------------------------------------------------------------------
# 초안
# ------------------------------------------------------------------
class Draft(Base):
    __tablename__ = "drafts"
    __table_args__ = (Index("ix_drafts_status", "status"),)

    id = _pk()
    draft_code = Column(String(50), unique=True)              # draft_20260825_161929
    template_id = Column(BigInteger, ForeignKey("templates.id"))
    topic = Column(String(255))
    title = Column(String(500))
    summary = Column(String(1000))
    markdown = Column(MEDIUMTEXT)                             # 원본
    article_html = Column(MEDIUMTEXT)                         # 화면용
    status = Column(String(20), default="pending")            # pending/approved/revision/rejected
    score = Column(Integer, default=0)
    score_grade = Column(String(20))
    revision_count = Column(Integer, default=0)
    human_feedback = Column(Text)
    created_at = _now()
    approved_at = Column(DateTime)

    template = relationship("Template")
    sources = relationship("DraftSource", back_populates="draft",
                           cascade="all, delete-orphan")
    audit = relationship("AuditReport", back_populates="draft",
                         uselist=False, cascade="all, delete-orphan")


class DraftSource(Base):
    """초안이 근거로 삼은 기사. 본문의 [1], [2] 번호와 이어진다."""
    __tablename__ = "draft_sources"

    id = _pk()
    draft_id = Column(BigInteger, ForeignKey("drafts.id", ondelete="CASCADE"))
    article_id = Column(BigInteger, ForeignKey("articles.id"))
    ref_no = Column(Integer)

    draft = relationship("Draft", back_populates="sources")
    article = relationship("Article")


# ------------------------------------------------------------------
# 검수
# ------------------------------------------------------------------
class ReviewGuideline(Base):
    """
    검수 지침.
    회의: "지침을 줘서 참고해서 검수할 때 이럴 때 이렇게 해라"
    """
    __tablename__ = "review_guidelines"

    id = _pk()
    name = Column(String(100), nullable=False)
    content = Column(Text, nullable=False)                    # 지침 본문
    weights = Column(JSON)                                    # {"사실성":35, "출처":25, ...}
    pass_score = Column(Integer, default=80)
    is_active = Column(Boolean, default=True)
    created_at = _now()


class AuditReport(Base):
    __tablename__ = "audit_reports"

    id = _pk()
    draft_id = Column(BigInteger, ForeignKey("drafts.id", ondelete="CASCADE"))
    guideline_id = Column(BigInteger, ForeignKey("review_guidelines.id"))
    total_score = Column(Integer)
    passed = Column(Boolean, default=False)
    readability = Column(Integer)                             # 가독성
    fact_accuracy = Column(Integer)                           # 사실 정확도
    coherence = Column(Integer)                               # 일관성
    reviewer_comment = Column(Text)
    loop_count = Column(String(20), default="0회")
    created_at = _now()

    draft = relationship("Draft", back_populates="audit")
    guideline = relationship("ReviewGuideline")


# ------------------------------------------------------------------
# 발송 이력
# ------------------------------------------------------------------
class DispatchLog(Base):
    __tablename__ = "dispatch_logs"

    id = _pk()
    draft_id = Column(BigInteger, ForeignKey("drafts.id"))
    subscriber_id = Column(BigInteger, ForeignKey("subscribers.id"))
    email = Column(String(255))
    status = Column(String(20))                               # sent / failed
    error_message = Column(String(500))
    sent_at = _now()

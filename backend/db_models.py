"""
MySQL 테이블 정의 — 2개

처음에는 10개로 설계했으나, 프로젝트를 간단하게 가기로 하면서 줄였다.

    로그인 없음        -> subscribers, keywords 불필요
    수신자 한 명       -> .env 의 MAIL_TO 한 줄이면 충분, dispatch_logs 불필요
    출력 형태 1종      -> templates 불필요 (templates_seed.py 상수로 충분)
    검수 지침 1개      -> review_guidelines 불필요 (templates_seed.py 상수)
    근거 기사·검수 점수 -> drafts 안에 컬럼·JSON 으로 넣으면 충분

남은 것은 두 개다.

    articles  수집한 기사
    drafts    만들어진 요약본 (검수 점수·근거 기사 포함)
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON, BigInteger, Boolean, CHAR, Column, DateTime, Index,
    Integer, String, Text,
)
from sqlalchemy.dialects.mysql import MEDIUMTEXT

from database import Base


class Article(Base):
    """수집한 기사. RSS 목록 + 크롤링한 본문."""
    __tablename__ = "articles"
    __table_args__ = (Index("ix_articles_collected", "collected_at"),)

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    url_hash = Column(CHAR(32), unique=True, nullable=False)   # 중복 수집 방지
    title = Column(String(500), nullable=False)
    link = Column(String(1000), nullable=False)                # 상세페이지 주소
    description = Column(Text)                                 # RSS 가 준 짧은 요약
    content = Column(MEDIUMTEXT)                               # 크롤링한 본문
    source = Column(String(100))                               # 연합뉴스 ...
    published = Column(String(100))                            # RSS 원본 형식 그대로
    has_full_text = Column(Boolean, default=False)
    collected_at = Column(DateTime, default=datetime.now)


class Draft(Base):
    """
    만들어진 요약본.

    검수 점수와 근거 기사를 따로 테이블로 빼지 않고 여기에 담았다.
    요약본 하나에 검수 결과는 하나뿐이고, 근거 기사는 화면에 그대로 뿌리기만 하므로
    JSON 한 칸이면 충분하다.
    """
    __tablename__ = "drafts"
    __table_args__ = (Index("ix_drafts_status", "status"),)

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    draft_code = Column(String(50), unique=True, nullable=False)   # draft_20260825_173946

    # 요청
    request_text = Column(Text)          # 사용자가 입력한 문장 그대로
    search_query = Column(String(255))   # 문장에서 뽑아낸 검색어

    # 결과물
    title = Column(String(500))
    summary = Column(String(1000))
    markdown = Column(MEDIUMTEXT)        # 원본
    article_html = Column(MEDIUMTEXT)    # 화면용
    sources = Column(JSON)               # 근거 기사 목록 (제목·매체·원문링크)

    # 검수 (audit_reports 테이블을 흡수)
    score = Column(Integer, default=0)
    score_grade = Column(String(20))
    readability = Column(Integer)        # 가독성
    fact_accuracy = Column(Integer)      # 사실 정확도
    coherence = Column(Integer)          # 일관성
    reviewer_comment = Column(Text)

    # 상태와 발송 (schedules, dispatch_logs 를 흡수)
    status = Column(String(20), default="pending")   # pending/approved/rejected/sent
    revision_count = Column(Integer, default=0)
    last_direction = Column(Text)                    # 마지막 수정 요청 문구
    frequency = Column(String(20))                   # once/daily/weekly/biweekly/monthly
    created_at = Column(DateTime, default=datetime.now)
    approved_at = Column(DateTime)
    sent_at = Column(DateTime)
    send_error = Column(String(500))                 # 발송 실패 사유

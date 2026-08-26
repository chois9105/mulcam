"""
요청 문장 분석

화면 ① 은 키워드가 아니라 문장을 받는다.

    "생성형 AI와 LangGraph의 이번 주 주요 뉴스를 실무자 관점에서 5개 정도 정리해 주세요."

이 문장에서 검색에 쓸 키워드와 독자·개수를 뽑아낸다.
팀원(moonlight)의 newsletter.py 에 있는 analyze_input() 과 같은 역할이며,
구조화 출력 방식도 그대로 따랐다.
"""

from __future__ import annotations

import os
from typing import List

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

load_dotenv()


class RequestPlan(BaseModel):
    """요청 문장에서 뽑아낸 것"""
    keywords: List[str] = Field(
        min_length=1,
        description="뉴스 검색에 쓸 짧은 표현. 2~4개. 중복 제거",
    )
    audience: str = Field(description="누가 읽는가. 예: 실무자, 일반 독자")
    article_count: int = Field(
        default=8, ge=3, le=15, description="다룰 기사 수. 문장에 없으면 8",
    )
    title_hint: str = Field(description="뉴스레터 제목으로 쓸 짧은 문구")


# 검색어로 쓰면 안 되는 일반적인 낱말.
# '2026년 8월 26일 대한민국 로봇 관련 정보' 에서 '대한민국' 이 검색어로 들어가
# 김치 경연대회·총선 기사까지 끌어오는 일이 있었다.
GENERIC = {
    "대한민국", "한국", "국내", "우리나라", "전국", "세계", "글로벌",
    "오늘", "최신", "이번주", "이번 주", "요즘", "현재", "올해", "내년",
    "뉴스", "기사", "소식", "정보", "관련", "주요", "동향", "이슈", "정리",
}


def drop_generic(keywords: List[str]) -> List[str]:
    """
    너무 일반적인 낱말을 검색어에서 뺀다.
    전부 빠지면 원래 목록을 그대로 쓴다(아무것도 못 찾는 것보다 낫다).
    """
    kept = []
    for kw in keywords:
        k = (kw or "").strip()
        if not k or k in GENERIC:
            continue
        # '대한민국 로봇' 처럼 붙어 있으면 일반적인 부분만 떼어낸다
        parts = [w for w in k.split() if w not in GENERIC]
        kept.append(" ".join(parts) if parts else k)
    kept = [k for k in kept if k and k not in GENERIC]
    return kept or keywords


SYSTEM = (
    "당신은 뉴스레터 기획자다. 사용자의 요청 문장을 분석해 검색에 쓸 정보를 뽑는다.\n"
    "- keywords: 검색 가능한 짧은 표현으로 만든다. 문장을 그대로 넣지 않는다.\n"
    "  '생성형 AI와 LangGraph의 이번 주 뉴스' -> ['생성형 AI', 'LangGraph']\n"
    "- 사용자가 키워드만 짧게 적었으면 그것을 그대로 쓴다.\n"
    "- **너무 일반적인 낱말은 넣지 않는다.**\n"
    "  '대한민국', '한국', '오늘', '최신', '뉴스', '정보', '관련' 같은 말은 뺀다.\n"
    "  '2026년 8월 26일 대한민국 로봇 관련 정보' -> ['로봇'] 만 남긴다.\n"
    "  날짜도 검색어에 넣지 않는다.\n"
    "- article_count: '5개 정도' 처럼 적혀 있으면 그 수를, 없으면 8.\n"
    "- title_hint: 화면에 뜰 제목. 예) 'LangGraph 맞춤형 뉴스 브리핑'\n"
    "- 한국어로 답한다."
)


class RequestAnalyzer:
    def __init__(self, model: str = None):
        if not os.getenv("OPENAI_API_KEY"):
            raise RuntimeError("OPENAI_API_KEY 가 없습니다. backend/.env 를 확인하세요.")
        self.llm = ChatOpenAI(
            model=model or os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            temperature=0,
        ).with_structured_output(RequestPlan)

    def analyze(self, request_text: str) -> RequestPlan:
        plan = self.llm.invoke([("system", SYSTEM), ("human", request_text)])
        # 모델이 그래도 일반적인 낱말을 넣는 경우가 있어 한 번 더 거른다
        plan.keywords = drop_generic(plan.keywords)
        return plan

    @staticmethod
    def to_query(plan: RequestPlan) -> str:
        """검색에 넣을 한 줄로 합친다."""
        return " ".join(plan.keywords)

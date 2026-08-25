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


SYSTEM = (
    "당신은 뉴스레터 기획자다. 사용자의 요청 문장을 분석해 검색에 쓸 정보를 뽑는다.\n"
    "- keywords: 검색 가능한 짧은 표현으로 만든다. 문장을 그대로 넣지 않는다.\n"
    "  '생성형 AI와 LangGraph의 이번 주 뉴스' -> ['생성형 AI', 'LangGraph']\n"
    "- 사용자가 키워드만 짧게 적었으면 그것을 그대로 쓴다.\n"
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
        return self.llm.invoke([("system", SYSTEM), ("human", request_text)])

    @staticmethod
    def to_query(plan: RequestPlan) -> str:
        """검색에 넣을 한 줄로 합친다."""
        return " ".join(plan.keywords)

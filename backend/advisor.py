"""
요청 다듬기 도우미

초보자는 무엇을 어떻게 적어야 할지 모른다.
'로봇' 이라고만 적으면 산업용인지 서비스용인지, 기업 소식인지 기술 동향인지
알 수 없어 결과가 뭉뚱그려진다.

그래서 편집장이 데스크에서 기자에게 묻듯이, 되묻는 질문 3가지와
바로 쓸 수 있는 요청문 3가지를 함께 돌려준다.

    입력: "로봇"

    되묻기
      1. 산업용 로봇과 서비스 로봇 중 어느 쪽이 궁금하신가요?
      2. 기업 소식(투자·수주)과 기술 개발 중 어느 쪽을 보고 싶으신가요?
      3. 국내 기업 중심으로 볼까요, 해외 동향도 넣을까요?

    바로 쓸 수 있는 요청문
      - 국내 로봇 기업의 최근 투자와 수주 소식을 정리해 주세요
      - 의료·수술 로봇 기술 개발 동향을 정리해 주세요
      - 물류·제조 현장에 들어간 로봇 사례를 정리해 주세요

사용자는 질문을 읽고 스스로 다듬거나, 요청문 하나를 눌러 바로 만들 수 있다.
"""

from __future__ import annotations

import os
from typing import List

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from rag_engine import PERSONA

load_dotenv()


class Advice(BaseModel):
    """되묻기와 추천 요청문"""
    questions: List[str] = Field(
        min_length=3, max_length=3,
        description="독자가 원하는 바를 좁히도록 돕는 질문 3개",
    )
    suggestions: List[str] = Field(
        min_length=3, max_length=3,
        description="그대로 넣으면 되는 구체적인 요청문 3개",
    )
    note: str = Field(description="한 줄 안내. 왜 이렇게 좁히면 좋은지")


SYSTEM = (
    PERSONA +
    "지금은 독자가 막연하게 던진 주제를 데스크에서 다듬어 주는 상황이다.\n\n"
    "할 일:\n"
    "1. questions - 독자가 원하는 바를 좁히도록 돕는 질문 3개.\n"
    "   서로 다른 각도로 묻는다. 예) 분야 / 관점 / 범위\n"
    "   '~중 어느 쪽이 궁금하신가요?' 처럼 고르기 쉽게 묻는다.\n"
    "   답을 강요하지 말고, 읽기만 해도 생각이 정리되게 쓴다.\n\n"
    "2. suggestions - 그대로 복사해 넣으면 되는 요청문 3개.\n"
    "   각각 다른 방향이어야 한다. 서로 겹치면 안 된다.\n"
    "   '~를 정리해 주세요' 로 끝나는 한 문장으로 쓴다.\n"
    "   실제 뉴스에 있을 법한 구체적인 주제로 쓴다.\n\n"
    "3. note - 왜 이렇게 좁히면 좋은지 한 줄로. 30자 안팎.\n\n"
    "모두 한국어로 쓴다. 독자는 기자가 아니라 일반인이다."
)


class RequestAdvisor:
    def __init__(self, model: str = None):
        if not os.getenv("OPENAI_API_KEY"):
            raise RuntimeError("OPENAI_API_KEY 가 없습니다. backend/.env 를 확인하세요.")
        self.llm = ChatOpenAI(
            model=model or os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            temperature=0.4,
        ).with_structured_output(Advice)

    def advise(self, keyword: str) -> Advice:
        return self.llm.invoke([
            ("system", SYSTEM),
            ("human", f"독자가 이렇게 적었습니다: \"{keyword}\"\n"
                      "이 사람이 정말 무엇을 보고 싶은지 좁혀 주세요."),
        ])


_advisor = None


def advise(keyword: str) -> Advice:
    global _advisor
    if _advisor is None:
        _advisor = RequestAdvisor()
    return _advisor.advise(keyword)

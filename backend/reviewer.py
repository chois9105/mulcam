"""
검수 에이전트

생성된 뉴스레터가 근거 기사에 충실한지 별도의 LLM이 채점한다.
작성한 모델이 스스로 채점하면 후한 점수를 주기 때문에, 작성과 검수를 나눈다.

채점 기준은 팀원(moonlight)이 만든 newsletter.py 의 review_newsletter() 를 따른다.
    사실성 35 / 출처 25 / 구성 20 / 독자 적합성 20  = 100점
    80점 이상이면 통과

프론트엔드(frontend/models.py)의 AuditReport 는 아래 3개를 요구하므로 함께 낸다.
    readability(가독성) / fact_accuracy(사실 정확도) / coherence(일관성)
"""

from __future__ import annotations

import json
import os
from typing import Dict, List

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

load_dotenv()

PASS_SCORE = int(os.getenv("REVIEW_PASS_SCORE", "80"))


class ReviewResult(BaseModel):
    """검수 결과 (LLM 이 이 형식으로 답하도록 강제한다)"""
    passed: bool = Field(description="80점 이상이면 true")
    score: int = Field(ge=0, le=100, description="총점")
    fact_accuracy: int = Field(ge=0, le=100, description="사실 정확도 - 기사에 없는 내용을 지어내지 않았는가")
    readability: int = Field(ge=0, le=100, description="가독성 - 문장이 읽기 쉬운가")
    coherence: int = Field(ge=0, le=100, description="일관성 - 구성이 매끄럽고 주제가 흐트러지지 않는가")
    feedback: List[str] = Field(description="구체적인 개선 의견. 통과해도 1개 이상 적는다")


SYSTEM_PROMPT = (
    "당신은 엄격한 뉴스레터 편집장이다. "
    "사실성 35, 출처 25, 구성 20, 독자 적합성 20점으로 총점을 매긴다. "
    "근거 기사로 뒷받침되지 않는 주장이나 출처 번호 누락이 있으면 통과시키지 않는다. "
    f"{PASS_SCORE}점 이상만 passed=true 다.\n"
    "총점과 별개로 fact_accuracy(사실 정확도), readability(가독성), "
    "coherence(일관성)를 각각 100점 만점으로 매긴다.\n"
    "feedback 은 한국어로, 무엇을 어떻게 고치라는 식의 구체적인 문장으로 쓴다."
)


class NewsletterReviewer:
    def __init__(self, model: str = None):
        if not os.getenv("OPENAI_API_KEY"):
            raise RuntimeError("OPENAI_API_KEY 가 없습니다. backend/.env 를 확인하세요.")
        self.llm = ChatOpenAI(
            model=model or os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            temperature=0,
        ).with_structured_output(ReviewResult)

    def review(self, newsletter: str, sources: List[Dict]) -> ReviewResult:
        """뉴스레터 초안과 근거 기사를 함께 넘겨 채점한다."""
        # 채점에 필요한 정보만 추린다 (본문 전체를 넣으면 토큰이 낭비된다)
        brief = [
            {
                "n": s.get("n"),
                "title": s.get("title", ""),
                "source": s.get("source", ""),
                "link": s.get("link", ""),
            }
            for s in sources
        ]
        return self.llm.invoke([
            ("system", SYSTEM_PROMPT),
            ("human",
             "근거 기사:\n" + json.dumps(brief, ensure_ascii=False, indent=1)
             + "\n\n검수할 뉴스레터:\n" + newsletter),
        ])

    @staticmethod
    def to_grade(score: int) -> str:
        """점수를 프론트엔드가 표시하는 등급 문구로 바꾼다."""
        if score >= 95:
            return "A+ 우수"
        if score >= 90:
            return "A 양호"
        if score >= 80:
            return "B 통과"
        if score >= 70:
            return "C 보완 필요"
        return "D 재작성 권장"

    def audit_report(self, result: ReviewResult, loop_count: int = 0) -> Dict:
        """프론트엔드 AuditReport 형식으로 변환한다."""
        return {
            "readability": result.readability,
            "fact_accuracy": result.fact_accuracy,
            "coherence": result.coherence,
            "reviewer_comment": " / ".join(result.feedback) if result.feedback else "특이사항 없음",
            "loop_count": f"{loop_count}회",
        }

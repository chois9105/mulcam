"""
한국어 다듬기 (윤문)

회의 결정:
    "요약되어 나온 한국어가 이상한 부분을 잘 맞게 고쳐주는 것을 적용해서
     이쁘게 잘 나오게 해주는 것으로 해라"

AI가 쓴 글에는 번역투나 어색한 표현이 섞인다.
    "~에 대한 논의가 이루어졌다"  ->  "~를 논의했다"
    "~할 것으로 예상되어진다"     ->  "~할 전망이다"

내용은 건드리지 않고 문장만 다듬는다.
근거 번호 [1] 과 마크다운 구조는 반드시 그대로 둔다.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

load_dotenv()

POLISH_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "당신은 한국어 교열 담당자입니다. 아래 뉴스레터의 문장만 자연스럽게 다듬으세요.\n\n"
     "반드시 지킬 것:\n"
     "1. 사실을 바꾸지 않는다. 숫자·기관명·인용은 그대로 둔다.\n"
     "2. 근거 번호 [1] [2] 는 위치까지 그대로 유지한다.\n"
     "3. 마크다운 구조(#, **, 줄바꿈)를 바꾸지 않는다.\n"
     "4. 내용을 요약하거나 늘리지 않는다. 길이를 비슷하게 유지한다.\n"
     "5. 없던 문장을 새로 만들지 않는다.\n\n"
     "이렇게 고친다:\n"
     "- 번역투를 자연스러운 한국어로 (\"~에 대한 논의가 이루어졌다\" -> \"~를 논의했다\")\n"
     "- 이중 피동을 없앤다 (\"예상되어진다\" -> \"예상된다\")\n"
     "- 한 문장이 너무 길면 두 문장으로 나눈다\n"
     "- 같은 단어가 연달아 반복되면 바꾼다\n"
     "- 조사·띄어쓰기 오류를 고친다\n\n"
     "다듬은 글만 출력한다. 설명이나 인사말은 붙이지 않는다."),
    ("human", "{draft}"),
])


class Polisher:
    def __init__(self, model: str = None):
        if not os.getenv("OPENAI_API_KEY"):
            raise RuntimeError("OPENAI_API_KEY 가 없습니다. backend/.env 를 확인하세요.")
        self.llm = ChatOpenAI(
            model=model or os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            temperature=0.2,
        )
        self.enabled = os.getenv("POLISH_ENABLED", "true").lower() != "false"

    def polish(self, draft: str) -> str:
        """
        문장을 다듬어 돌려준다.
        실패하면 원문을 그대로 돌려준다 - 다듬기 때문에 전체가 멈추면 안 된다.
        """
        if not self.enabled or not draft.strip():
            return draft
        try:
            result = (POLISH_PROMPT | self.llm).invoke({"draft": draft}).content

            # 안전장치: 결과가 지나치게 짧아졌으면 요약해버린 것이므로 원문을 쓴다
            if len(result) < len(draft) * 0.6:
                return draft
            return result
        except Exception:
            return draft

"""
RAG 엔진 - 수집한 RSS 뉴스를 근거로 답변을 생성한다.

흐름:
    RSS 수집 -> JSON -> 문서로 변환 -> 임베딩 -> FAISS 색인
    질문 -> 관련 기사 검색 -> LLM이 그 기사만 근거로 답변

RAG(Retrieval-Augmented Generation, 검색증강생성)를 쓰는 이유:
    LLM은 학습 시점 이후의 뉴스를 모른다. 오늘 수집한 기사를 직접 찾아서
    프롬프트에 넣어주면, 모델이 지어내지 않고 실제 기사에 근거해 답한다.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List, Optional

from dotenv import load_dotenv
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from html_render import to_dashboard_html

load_dotenv()

DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
DEFAULT_EMBED_MODEL = os.getenv("OPENAI_EMBED_MODEL", "text-embedding-3-small")
INDEX_DIR = os.getenv("RAG_INDEX_DIR", "faiss_index")


ANSWER_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "당신은 뉴스 리서처입니다. 아래 [기사]에 적힌 내용만 근거로 답하세요.\n"
     "규칙:\n"
     "1. 기사의 제목과 내용 모두 근거로 쓸 수 있다. 제목만으로 알 수 있는 사실도 답한다.\n"
     "2. 확인되지 않는 수치·인용은 지어내지 않는다. 관련 기사가 하나도 없을 때만\n"
     "   '수집된 기사에는 없습니다'라고 답한다.\n"
     "3. 문장 끝에 근거 기사 번호를 [1], [2] 형태로 표시한다.\n"
     "4. 한국어로, 사실 위주로 간결하게 쓴다.\n\n"
     "[기사]\n{context}"),
    ("human", "{question}"),
])

# ---------------- 요약 3종 ----------------
# 사용자가 style 로 골라 쓴다. 공통 규칙은 아래 COMMON_RULES.

COMMON_RULES = (
    "규칙:\n"
    "- 아래 [기사]에 있는 내용만 쓴다. 없는 사실·수치는 지어내지 않는다.\n"
    "- 각 항목 끝에 근거 기사 번호를 [1], [2] 형태로 붙인다.\n"
    "- 마크다운, 한국어로 작성한다.\n\n"
    "[기사]\n{context}"
)

STYLE_PROMPTS = {
    # 1) 짧게 훑기 - 출퇴근길 3줄 요약
    "brief": ChatPromptTemplate.from_messages([
        ("system",
         "당신은 뉴스 큐레이터입니다. '{topic}' 주제로 아주 짧은 브리핑을 만듭니다.\n"
         "형식:\n"
         "- 오늘의 한 줄 (헤드라인 1문장)\n"
         "- 핵심 3가지, 각 한 문장 [n]\n"
         "전체 200자 이내로 압축한다.\n" + COMMON_RULES),
        ("human", "'{topic}' 짧은 브리핑을 작성해주세요."),
    ]),

    # 2) 표준 뉴스레터 - 기본값
    "newsletter": ChatPromptTemplate.from_messages([
        ("system",
         "당신은 뉴스레터 편집자입니다. '{topic}' 주제의 뉴스레터를 작성합니다.\n"
         "형식:\n"
         "- # 제목 (한 줄 헤드라인)\n"
         "- 핵심 이슈 3~5개. 각 항목은 **소제목** + 2~3문장 설명 [n]\n"
         "- 마지막에 '오늘의 한 줄' 정리\n" + COMMON_RULES),
        ("human", "'{topic}' 뉴스레터를 작성해주세요."),
    ]),

    # 3) 심층 분석 - 배경과 맥락까지
    "deep": ChatPromptTemplate.from_messages([
        ("system",
         "당신은 뉴스 분석가입니다. '{topic}' 주제를 깊이 있게 정리합니다.\n"
         "형식:\n"
         "- # 제목\n"
         "- ## 무슨 일이 있었나 : 사실관계 정리 [n]\n"
         "- ## 왜 중요한가 : 기사에 드러난 파급효과·이해관계 [n]\n"
         "- ## 함께 볼 흐름 : 서로 연결되는 기사들을 묶어 설명 [n]\n"
         "- ## 참고 기사 : 제목과 링크 목록\n"
         "해석을 덧붙이되, 근거는 반드시 기사 안에서 찾는다.\n" + COMMON_RULES),
        ("human", "'{topic}' 심층 분석을 작성해주세요."),
    ]),
}

STYLE_INFO = {
    "brief":      {"name": "짧은 브리핑", "설명": "200자 이내 3줄 요약", "권장_기사수": 5},
    "newsletter": {"name": "표준 뉴스레터", "설명": "이슈 3~5개 + 정리", "권장_기사수": 8},
    "deep":       {"name": "심층 분석", "설명": "사실·의미·흐름·참고기사", "권장_기사수": 12},
}


class NewsRAG:
    def __init__(self, model: str = DEFAULT_MODEL, index_dir: str = INDEX_DIR):
        if not os.getenv("OPENAI_API_KEY"):
            raise RuntimeError(
                "OPENAI_API_KEY가 없습니다. backend/.env 파일에 키를 넣어주세요."
            )
        self.index_dir = index_dir
        self.embeddings = OpenAIEmbeddings(model=DEFAULT_EMBED_MODEL)
        self.llm = ChatOpenAI(model=model, temperature=0)
        self.store: Optional[FAISS] = None

    # ---------- 색인 ----------
    @staticmethod
    def _to_documents(news_items: List[Dict]) -> List[Document]:
        """RSS JSON 한 건 -> 검색용 문서 한 건"""
        docs = []
        for n in news_items:
            # 본문(content)을 가져왔으면 본문을, 못 가져왔으면 RSS 요약을 쓴다
            body_text = n.get("content") or n.get("description", "")
            title = n.get("title", "")

            # 검색용 글과 근거용 글을 나눈다.
            #
            # 본문 900자를 통째로 임베딩하면 주제가 희석돼서 검색이 망가진다.
            # 실제로 "AI 반도체"를 검색했을 때 폭염주의보·의료폐기물 기사가
            # 상위로 올라왔다. 제목과 첫 문단이 기사 주제를 가장 잘 나타내므로
            # 그 부분만 임베딩하고, 본문 전체는 metadata 에 넣어두었다가
            # LLM 에 근거로 넘길 때 쓴다.
            search_text = f"{title}. {body_text[:200]}"
            docs.append(Document(
                page_content=search_text,
                metadata={
                    "title": title,
                    "body": body_text[:1500],      # LLM 에 넘길 근거 본문
                    "link": n.get("link", ""),
                    "source": n.get("source", ""),
                    "published": n.get("published", ""),
                    "has_full_text": n.get("has_full_text", False),
                },
            ))
        return docs

    def build(self, news_items: List[Dict]) -> int:
        """뉴스 JSON을 임베딩해서 FAISS 색인을 만들고 저장한다."""
        docs = self._to_documents(news_items)
        if not docs:
            raise ValueError("색인할 뉴스가 없습니다.")
        self.store = FAISS.from_documents(docs, self.embeddings)
        self.store.save_local(self.index_dir)
        return len(docs)

    def load(self) -> bool:
        """저장해둔 색인을 불러온다. 없으면 False."""
        if not Path(self.index_dir).exists():
            return False
        self.store = FAISS.load_local(
            self.index_dir, self.embeddings, allow_dangerous_deserialization=True
        )
        return True

    def _require_store(self):
        if self.store is None and not self.load():
            raise RuntimeError("색인이 없습니다. 먼저 build()를 실행하세요.")

    # ---------- 검색 ----------
    def search(self, question: str, k: int = 5, min_keep: int = 3) -> List[Document]:
        """
        관련 기사를 찾는다.

        k개를 무조건 채우면, 주제와 상관없는 기사까지 근거로 들어가
        요약 품질이 떨어진다("AI 반도체"를 물었는데 병원 기사가 섞이는 문제).
        그래서 가장 잘 맞는 기사보다 크게 뒤처지는 것은 버린다(RAG_DISTANCE_MARGIN).
        다만 전부 버리면 답을 못 만드니 최소 min_keep개는 남긴다.
        """
        self._require_store()
        scored = self.store.similarity_search_with_score(question, k=k)
        if not scored:
            return []

        # FAISS 기본 거리(L2): 값이 작을수록 비슷하다.
        # 절대 기준을 정하기 어렵다(질문 길이에 따라 값이 통째로 달라진다).
        # 그래서 "가장 잘 맞는 기사"를 기준 삼아 상대적으로 판단한다.
        margin = float(os.getenv("RAG_DISTANCE_MARGIN", "0.08"))
        best, worst = scored[0][1], scored[-1][1]

        # 1등과 꼴등의 차이가 거의 없다 = 딱 맞는 기사가 따로 없다는 뜻.
        # 이럴 때 걸러봐야 의미가 없으므로 전부 쓴다.
        if worst - best <= margin:
            return [doc for doc, _ in scored]

        # 특정 주제를 물은 경우: 1등보다 크게 뒤처지는 기사는 버린다
        kept = [doc for doc, dist in scored if dist <= best + margin]
        if len(kept) < min_keep:
            kept = [doc for doc, _ in scored[:min_keep]]
        return kept

    @staticmethod
    def _format_context(docs: List[Document]) -> str:
        lines = []
        for i, d in enumerate(docs, 1):
            m = d.metadata
            lines.append(
                f"[{i}] 출처: {m.get('source','')} / {m.get('published','')}\n"
                f"    제목: {m.get('title','')}\n"
                # 검색은 짧은 글로 했지만, 근거로는 본문 전체를 넘긴다
                f"    본문: {(m.get('body') or d.page_content).strip()[:800]}\n"
                f"    링크: {m.get('link','')}"
            )
        return "\n\n".join(lines)

    @staticmethod
    def _sources(docs: List[Document]) -> List[Dict]:
        return [
            {
                "n": i,
                "title": d.metadata.get("title", ""),
                "source": d.metadata.get("source", ""),
                "link": d.metadata.get("link", ""),
                "published": d.metadata.get("published", ""),
                "has_full_text": d.metadata.get("has_full_text", False),
            }
            for i, d in enumerate(docs, 1)
        ]

    # ---------- 생성 ----------
    def ask(self, question: str, k: int = 5) -> Dict:
        """리서치: 질문에 대해 수집한 기사만 근거로 답한다."""
        docs = self.search(question, k=k)
        chain = ANSWER_PROMPT | self.llm
        answer = chain.invoke({
            "context": self._format_context(docs),
            "question": question,
        }).content
        return {"question": question, "answer": answer, "sources": self._sources(docs)}

    def summarize(self, topic: str, style: str = "newsletter", k: int = None) -> Dict:
        """
        요약: 주제 관련 기사를 모아 뉴스레터를 만든다.

        style : "brief"(짧은 브리핑) | "newsletter"(표준) | "deep"(심층 분석)
        k     : 참고할 기사 수. 생략하면 style 별 권장값을 쓴다.
        """
        if style not in STYLE_PROMPTS:
            raise ValueError(
                f"style 은 {list(STYLE_PROMPTS)} 중 하나여야 합니다. 받은 값: {style}"
            )
        if k is None:
            k = STYLE_INFO[style]["권장_기사수"]

        # 요약은 소재가 어느 정도 있어야 하므로 최소 절반은 남긴다.
        # (리서치용 ask() 는 정확도가 우선이라 min_keep 을 낮게 둔다)
        docs = self.search(topic, k=k, min_keep=max(3, k // 2))
        chain = STYLE_PROMPTS[style] | self.llm
        newsletter = chain.invoke({
            "context": self._format_context(docs),
            "topic": topic,
        }).content
        sources = self._sources(docs)
        return {
            "topic": topic,
            "style": style,
            "style_name": STYLE_INFO[style]["name"],
            "newsletter": newsletter,                 # 마크다운 원문
            # 프론트엔드 대시보드가 그대로 쓸 수 있는 HTML 조각
            "article_html": to_dashboard_html(newsletter, sources),
            "sources": sources,
        }

    def summarize_all_styles(self, topic: str) -> Dict[str, Dict]:
        """3가지 버전을 한 번에 만들어 비교용으로 돌려준다."""
        return {s: self.summarize(topic, style=s) for s in STYLE_PROMPTS}

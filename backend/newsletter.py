from __future__ import annotations

#1. 라이브러리 불러오기
import argparse
import html
import json
import os
import re
import smtplib
import sqlite3
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
from typing import Literal, TypedDict
from urllib.parse import quote_plus

import feedparser
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from pydantic import BaseModel, Field

# 2. 환경변수 읽기 / 프로그램이 실행될 때 현재 폴더의 .env 파일을 읽음.
load_dotenv()

# 3. 상태 State 정의
# 기사 한 건의 구조
class ResearchItem(TypedDict):
    title: str
    summary: str
    url: str
    source: str
    published: str

# 전체 뉴스레터 상태
class NewsletterState(TypedDict, total=False):
    keywords: list[str]
    audience: str
    tone: str
    max_articles: int
    research_items: list[ResearchItem]
    draft: str
    review_passed: bool
    review_score: int
    review_feedback: list[str]
    human_decision: str
    human_feedback: str
    revision_count: int
    status: str
    output_path: str

# 4. LLM 구조화 출력
#입력 분석 결과
class InputPlan(BaseModel):
    keywords: list[str] = Field(min_length=1)
    audience: str
    tone: str

class ReviewResult(BaseModel):
    passed: bool
    score: int = Field(ge=0, le=100)
    feedback: list[str]

# 5. LLM 생성 함수 / .env의 OPENAI_MODEL을 사용, 설정이 없으면 gpt-4.1-mini 사용
def get_llm(temperature: float = 0.2) -> ChatOpenAI:
    return ChatOpenAI(
        model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
        temperature=temperature,
    )

# 6. 입력 분석 에이전트 / 사용자가 입력한 관심 키워드, 독자, 문체를 정리
def analyze_input(state: NewsletterState) -> dict:
    """사용자 입력을 뉴스 검색에 알맞은 구조로 정리한다."""
    plan = get_llm().with_structured_output(InputPlan).invoke(
        [
            ("system", "당신은 뉴스레터 기획자다. 키워드는 중복을 제거하고 검색 가능한 짧은 표현으로 정리하라."),
            (
                "human",
                f"키워드: {state['keywords']}\n독자: {state.get('audience', '일반 독자')}\n"
                f"문체: {state.get('tone', '친절하고 전문적')}",
            ),
        ]
    )
    return {"keywords": plan.keywords, "audience": plan.audience, "tone": plan.tone}

# 7. HTML 정리 함수
def clean_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html.unescape(text or ""))
    return re.sub(r"\s+", " ", text).strip()

# 8. 리서치 에이전트
def research_news(state: NewsletterState) -> dict:
    """Google News RSS에서 키워드별 최신 기사를 수집하고 URL 기준으로 중복 제거한다."""
    collected: list[ResearchItem] = []
    seen: set[str] = set()
    per_keyword = max(3, state.get("max_articles", 8))

    for keyword in state["keywords"]:
        rss_url = (
            "https://news.google.com/rss/search?q=" + quote_plus(keyword)
            + "&hl=ko&gl=KR&ceid=KR:ko"
        )
        feed = feedparser.parse(rss_url)
        for entry in feed.entries[:per_keyword]:
            url = entry.get("link", "")
            if not url or url in seen:
                continue
            seen.add(url)
            source = entry.get("source", {})
            collected.append(
                {
                    "title": clean_html(entry.get("title", "")),
                    "summary": clean_html(entry.get("summary", "")),
                    "url": url,
                    "source": source.get("title", "Google News") if isinstance(source, dict) else "Google News",
                    "published": entry.get("published", "날짜 미상"),
                }
            )

    limit = state.get("max_articles", 8)
    return {"research_items": collected[:limit], "status": "research_complete"}


#9. 작성 Aigents
def write_newsletter(state: NewsletterState) -> dict:
    """수집된 근거만 사용해 뉴스레터 초안 또는 수정본을 작성한다."""
    sources = json.dumps(state.get("research_items", []), ensure_ascii=False, indent=2)  # 기사 목록을 JSON으로 변환
    revision = state.get("human_feedback") or ""                  # 수정에 필요한 정보
    reviewer = "\n".join(state.get("review_feedback", []))        # 자동 검수 의견
    previous = state.get("draft", "")                             # 이전 뉴스레터 초안
    prompt = f"""
독자: {state.get('audience', '일반 독자')}
문체: {state.get('tone', '친절하고 전문적')}
관심 키워드: {', '.join(state['keywords'])}

수집 기사(JSON):
{sources}

이전 초안:
{previous}

검수 의견: {reviewer}
사람의 수정 요청: {revision}

한국어 Markdown 뉴스레터를 작성하라.
요구 형식: 제목, 3줄 요약, 주요 뉴스(기사별 핵심·의미·출처 링크), 인사이트, 마무리.
수집 기사에 없는 사실은 단정하지 말고, 모든 주요 사실에는 제공된 URL을 링크하라.
"""
    result = get_llm(0.5).invoke(
        [("system", "당신은 정확성과 가독성을 중시하는 뉴스레터 전문 작성자다."), ("human", prompt)]
    )
    return {                                            # 작성 결과 저장 / 수정 요청을 반영한 후 human_feedback을 초기화 함.
        "draft": result.content,
        "revision_count": state.get("revision_count", 0) + (1 if previous else 0),
        "human_feedback": "",
        "status": "draft_complete",
    }

#10. 검수 에이전트
def review_newsletter(state: NewsletterState) -> dict:            
    """사실 근거, 출처, 구조, 문체, 과장 여부를 별도 에이전트가 평가한다."""
    result = get_llm().with_structured_output(ReviewResult).invoke(
        [
            (
                "system",
                "당신은 엄격한 뉴스레터 편집장이다. 사실성 35, 출처 25, 구성 20, 독자 적합성 20점으로 평가한다. "
                "기사 목록으로 뒷받침되지 않는 주장이나 출처 링크 누락이 있으면 통과시키지 않는다. 80점 이상만 passed=true다.",
            ),
            (
                "human",
                "근거 기사:\n"
                + json.dumps(state.get("research_items", []), ensure_ascii=False)
                + "\n\n초안:\n"
                + state["draft"],
            ),
        ]
    )
    return {
        "review_passed": result.passed,
        "review_score": result.score,
        "review_feedback": result.feedback,
        "status": "review_complete",
    }

#11. 자동 수정 조건
def route_after_review(state: NewsletterState) -> Literal["write_newsletter", "human_approval"]:
    # 무한 수정 방지: 자동 수정은 최대 2회, 이후 사람이 판단한다.
    if not state.get("review_passed", False) and state.get("revision_count", 0) < 2:
        return "write_newsletter"
    return "human_approval"

# Human-in-the-loop
def human_approval(state: NewsletterState) -> dict:
    """그래프를 영속적으로 중단하고 approve/revise/reject 결정을 기다린다."""
    decision = interrupt(
        {
            "message": "뉴스레터를 확인해 주세요.",
            "draft": state["draft"],
            "review_score": state.get("review_score"),
            "review_feedback": state.get("review_feedback", []),
            "choices": ["approve", "revise", "reject"],
        }
    )
    if isinstance(decision, str):
        decision = {"action": decision, "feedback": ""}
    return {
        "human_decision": decision.get("action", "reject"),
        "human_feedback": decision.get("feedback", ""),
        "status": "human_decided",
    }

# 사람 결정에 따른 분기
def route_human_decision(state: NewsletterState) -> Literal["write_newsletter", "publish", "rejected"]:
    action = state.get("human_decision", "reject")
    if action == "approve":
        return "publish"
    if action == "revise":
        return "write_newsletter"
    return "rejected"

# 발행 노드
def publish(state: NewsletterState) -> dict:
    """승인된 원고만 로컬에 저장하고, 설정된 경우 이메일로 발송한다."""
    output_dir = Path("output")                      # 파일 저장 / output 폴더가 없으면 자동 생성함.
    output_dir.mkdir(exist_ok=True)
    path = output_dir / f"newsletter_{datetime.now():%Y%m%d_%H%M%S}.md"
    path.write_text(state["draft"], encoding="utf-8")

# 이메일 발송
    email_to = os.getenv("EMAIL_TO")
    if email_to:
        required = ["SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "EMAIL_FROM"]
        missing = [name for name in required if not os.getenv(name)]
        if missing:
            raise RuntimeError("이메일 환경변수 누락: " + ", ".join(missing))
        msg = EmailMessage()
        msg["Subject"] = f"맞춤 뉴스레터: {', '.join(state['keywords'])}"
        msg["From"] = os.environ["EMAIL_FROM"]
        msg["To"] = email_to
        msg.set_content(state["draft"])
        with smtplib.SMTP(os.environ["SMTP_HOST"], int(os.getenv("SMTP_PORT", "587"))) as smtp:
            smtp.starttls()
            smtp.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
            smtp.send_message(msg)

    return {"status": "published", "output_path": str(path.resolve())}


def rejected(_: NewsletterState) -> dict:
    return {"status": "rejected"}

# 그래프 구성
def build_graph(checkpointer: SqliteSaver):
    builder = StateGraph(NewsletterState)

    # 노드 등록 / 함수 하나가 에이전트 또는 작업 노드 하나에 해당함.
    builder.add_node("analyze_input", analyze_input)
    builder.add_node("research_news", research_news)
    builder.add_node("write_newsletter", write_newsletter)
    builder.add_node("review_newsletter", review_newsletter)
    builder.add_node("human_approval", human_approval)
    builder.add_node("publish", publish)
    builder.add_node("rejected", rejected)

    # 일반 에지 / 정해진 순서대로 이동
    builder.add_edge(START, "analyze_input")
    builder.add_edge("analyze_input", "research_news")
    builder.add_edge("research_news", "write_newsletter")
    builder.add_edge("write_newsletter", "review_newsletter")
    builder.add_conditional_edges("review_newsletter", route_after_review)   # 조건부 에지
    builder.add_conditional_edges("human_approval", route_human_decision)
    builder.add_edge("publish", END)
    builder.add_edge("rejected", END)
    return builder.compile(checkpointer=checkpointer)                       # 체크포인터 연결


def print_result(result: dict) -> None:
    if "__interrupt__" in result:
        payload = result["__interrupt__"][0].value
        print("\n" + "=" * 70)
        print(payload["draft"])
        print("\n검수 점수:", payload.get("review_score"))
        print("검수 의견:", *payload.get("review_feedback", []), sep="\n- ")
    else:
        print("\n처리 상태:", result.get("status"))
        if result.get("output_path"):
            print("저장 위치:", result["output_path"])

# 메인 프로그램
def main() -> None:
    parser = argparse.ArgumentParser(description="사용자 맞춤형 뉴스레터 멀티 에이전트")
    parser.add_argument("--thread", default="newsletter-001", help="재개 가능한 작업 ID")     # 실행옵션 
    parser.add_argument("--resume", action="store_true", help="승인 대기 중인 작업 재개")     # 실행옵션
    args = parser.parse_args()
    config = {"configurable": {"thread_id": args.thread}}

# SQLite 연결
    connection = sqlite3.connect("newsletter_state.db", check_same_thread=False)  # 현재 상태가 newsletter_state.db에 저장
    graph = build_graph(SqliteSaver(connection))

    if not args.resume:
        keywords = [x.strip() for x in input("관심 키워드(쉼표 구분): ").split(",") if x.strip()]
        initial: NewsletterState = {                                               # 초기 START
            "keywords": keywords,
            "audience": input("대상 독자 [일반 독자]: ").strip() or "일반 독자",
            "tone": input("문체 [친절하고 전문적]: ").strip() or "친절하고 전문적",
            "max_articles": 8,
            "revision_count": 0,
        }
        result = graph.invoke(initial, config=config)       # 같은 thread_id를 사용해야 이전 상태를 정확히 불러올 수 있음
        print_result(result)
        if "__interrupt__" in result:
            print(f"\n재개: python newsletter.py --thread {args.thread} --resume")
        return

# 승인 대기 작업 재개
    action = input("결정(approve/revise/reject): ").strip().lower()
    feedback = input("수정 의견(없으면 Enter): ").strip()
    result = graph.invoke(Command(resume={"action": action, "feedback": feedback}), config=config)
    print_result(result)
    if "__interrupt__" in result:
        print(f"\n수정본 재승인: python newsletter.py --thread {args.thread} --resume")


if __name__ == "__main__":                             # main()이 현재 프로그램의 백엔드 실행 시작점
    main()


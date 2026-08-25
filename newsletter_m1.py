from __future__ import annotations

import argparse
import html
import json
import os
import re
import smtplib
import sqlite3
import urllib.error
import urllib.request
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
from typing import Literal, TypedDict
from urllib.parse import quote_plus

import feedparser
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from pydantic import BaseModel, Field

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "newsletter.db"
CONFIG_PATH = BASE_DIR / "config.json"
OUTPUT_DIR = BASE_DIR / "output"
load_dotenv(BASE_DIR / ".env")


class ResearchItem(TypedDict):
    title: str
    summary: str
    url: str
    source: str
    published: str


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
    sent_count: int
    failed_count: int


class InputPlan(BaseModel):
    keywords: list[str] = Field(min_length=1)
    audience: str
    tone: str


class ReviewResult(BaseModel):
    passed: bool
    score: int = Field(ge=0, le=100)
    feedback: list[str]


def db_connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """수신자, 기사 캐시, 뉴스레터, 발송 이력 테이블을 만든다."""
    with db_connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS recipients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL DEFAULT '',
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS articles (
                url TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                summary TEXT NOT NULL DEFAULT '',
                source TEXT NOT NULL DEFAULT '',
                published TEXT NOT NULL DEFAULT '',
                collected_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS newsletters (
                thread_id TEXT PRIMARY KEY,
                subject TEXT NOT NULL,
                body TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                approved_at TEXT,
                output_path TEXT
            );
            CREATE TABLE IF NOT EXISTS deliveries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                thread_id TEXT NOT NULL,
                recipient_id INTEGER NOT NULL,
                status TEXT NOT NULL,
                error_message TEXT NOT NULL DEFAULT '',
                sent_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(thread_id, recipient_id)
            );
            """
        )


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"설정 파일이 없습니다: {CONFIG_PATH}")
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def get_llm(temperature: float = 0.2) -> ChatOpenAI:
    return ChatOpenAI(
        model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
        temperature=temperature,
    )


def clean_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html.unescape(text or ""))
    return re.sub(r"\s+", " ", text).strip()


def analyze_input(state: NewsletterState) -> dict:
    plan = get_llm().with_structured_output(InputPlan).invoke(
        [
            ("system", "뉴스레터 기획자로서 중복 키워드를 제거하고 짧은 검색어로 정리하라."),
            (
                "human",
                f"키워드: {state['keywords']}\n독자: {state['audience']}\n문체: {state['tone']}",
            ),
        ]
    )
    return {"keywords": plan.keywords, "audience": plan.audience, "tone": plan.tone}


def google_news_url(keyword: str, domain: str = "") -> str:
    query = f"{keyword} site:{domain}" if domain else keyword
    return (
        "https://news.google.com/rss/search?q="
        + quote_plus(query)
        + "&hl=ko&gl=KR&ceid=KR:ko"
    )


def parse_rss(url: str, source_name: str, limit: int) -> list[ResearchItem]:
    feed = feedparser.parse(url)
    results: list[ResearchItem] = []
    for entry in feed.entries[:limit]:
        item_url = entry.get("link", "")
        if not item_url:
            continue
        source = entry.get("source", {})
        detected = source.get("title", source_name) if isinstance(source, dict) else source_name
        results.append(
            {
                "title": clean_html(entry.get("title", "")),
                "summary": clean_html(entry.get("summary", entry.get("description", ""))),
                "url": item_url,
                "source": detected or source_name,
                "published": entry.get("published", entry.get("updated", "날짜 미상")),
            }
        )
    return results


def search_naver(keyword: str, limit: int) -> list[ResearchItem]:
    """NAVER_CLIENT_ID/SECRET이 있을 때만 네이버 뉴스 검색 API를 사용한다."""
    client_id = os.getenv("NAVER_CLIENT_ID")
    client_secret = os.getenv("NAVER_CLIENT_SECRET")
    if not client_id or not client_secret:
        return []
    url = (
        "https://openapi.naver.com/v1/search/news.json?query="
        + quote_plus(keyword)
        + f"&display={min(limit, 100)}&sort=date"
    )
    request = urllib.request.Request(
        url,
        headers={"X-Naver-Client-Id": client_id, "X-Naver-Client-Secret": client_secret},
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        print(f"[경고] 네이버 뉴스 검색 실패: {exc}")
        return []
    return [
        {
            "title": clean_html(item.get("title", "")),
            "summary": clean_html(item.get("description", "")),
            "url": item.get("originallink") or item.get("link", ""),
            "source": "네이버 뉴스 검색",
            "published": item.get("pubDate", "날짜 미상"),
        }
        for item in payload.get("items", [])
        if item.get("originallink") or item.get("link")
    ]


def save_articles(items: list[ResearchItem]) -> None:
    with db_connect() as conn:
        conn.executemany(
            """
            INSERT INTO articles(url, title, summary, source, published)
            VALUES(:url, :title, :summary, :source, :published)
            ON CONFLICT(url) DO UPDATE SET
                title=excluded.title, summary=excluded.summary,
                source=excluded.source, published=excluded.published
            """,
            items,
        )


def research_news(state: NewsletterState) -> dict:
    """10대 일간지·Google News·네이버·IT RSS를 통합 수집한다."""
    config = load_config()
    collected: list[ResearchItem] = []
    per_source = int(config.get("articles_per_source", 3))

    for keyword in state["keywords"]:
        for source in config["sources"]:
            if not source.get("enabled", True):
                continue
            mode = source["mode"]
            if mode == "google_news":
                url = google_news_url(keyword, source.get("domain", ""))
                collected.extend(parse_rss(url, source["name"], per_source))
            elif mode == "rss":
                collected.extend(parse_rss(source["url"], source["name"], per_source))
            elif mode == "naver_api":
                collected.extend(search_naver(keyword, per_source))

    unique: list[ResearchItem] = []
    seen: set[str] = set()
    for item in collected:
        if item["url"] not in seen:
            seen.add(item["url"])
            unique.append(item)
    selected = unique[: state.get("max_articles", 30)]
    save_articles(selected)
    return {"research_items": selected, "status": "research_complete"}


def write_newsletter(state: NewsletterState) -> dict:
    sources = json.dumps(state.get("research_items", []), ensure_ascii=False, indent=2)
    previous = state.get("draft", "")
    prompt = f"""
독자: {state['audience']}
문체: {state['tone']}
관심 키워드: {', '.join(state['keywords'])}
수집 기사: {sources}
이전 초안: {previous}
자동 검수 의견: {'; '.join(state.get('review_feedback', []))}
사람의 수정 요청: {state.get('human_feedback', '')}

한국어 Markdown 뉴스레터를 작성하라.
형식: 제목, 3줄 요약, 주요 뉴스, 매체별 관점 비교, 실무 인사이트, 마무리.
수집 기사 이외의 사실을 단정하지 말고 모든 주요 기사에 출처 링크를 넣어라.
"""
    result = get_llm(0.5).invoke(
        [("system", "정확성과 균형을 중시하는 뉴스레터 전문 작성자다."), ("human", prompt)]
    )
    return {
        "draft": str(result.content),
        "revision_count": state.get("revision_count", 0) + (1 if previous else 0),
        "human_feedback": "",
        "status": "draft_complete",
    }


def review_newsletter(state: NewsletterState) -> dict:
    result = get_llm().with_structured_output(ReviewResult).invoke(
        [
            (
                "system",
                "엄격한 편집장이다. 사실성35·출처25·구성20·독자적합성20점으로 평가하고 "
                "80점 이상만 통과시켜라. 근거 없는 주장이나 링크 누락은 미통과다.",
            ),
            (
                "human",
                "근거 기사:\n"
                + json.dumps(state.get("research_items", []), ensure_ascii=False)
                + "\n초안:\n"
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


def route_after_review(state: NewsletterState) -> Literal["write_newsletter", "human_approval"]:
    if not state.get("review_passed", False) and state.get("revision_count", 0) < 2:
        return "write_newsletter"
    return "human_approval"


def human_approval(state: NewsletterState) -> dict:
    decision = interrupt(
        {
            "message": "뉴스레터를 확인해 주세요. 승인 전에는 발송되지 않습니다.",
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


def route_human_decision(state: NewsletterState) -> Literal["write_newsletter", "publish", "rejected"]:
    return {
        "approve": "publish",
        "revise": "write_newsletter",
        "reject": "rejected",
    }.get(state.get("human_decision", "reject"), "rejected")


def smtp_settings() -> dict:
    names = ["SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "EMAIL_FROM"]
    missing = [name for name in names if not os.getenv(name)]
    if missing:
        raise RuntimeError("이메일 환경변수 누락: " + ", ".join(missing))
    return {name: os.environ[name] for name in names}


def publish(state: NewsletterState, config) -> dict:
    """활성 수신자에게 한 명씩 발송하고 개인 주소 노출을 방지한다."""
    thread_id = config["configurable"]["thread_id"]
    OUTPUT_DIR.mkdir(exist_ok=True)
    path = OUTPUT_DIR / f"newsletter_{datetime.now():%Y%m%d_%H%M%S}.md"
    path.write_text(state["draft"], encoding="utf-8")
    subject = f"맞춤 뉴스레터: {', '.join(state['keywords'])}"

    with db_connect() as conn:
        conn.execute(
            """INSERT INTO newsletters(thread_id, subject, body, status, approved_at, output_path)
               VALUES(?, ?, ?, 'approved', CURRENT_TIMESTAMP, ?)
               ON CONFLICT(thread_id) DO UPDATE SET subject=excluded.subject,
               body=excluded.body, status='approved', approved_at=CURRENT_TIMESTAMP,
               output_path=excluded.output_path""",
            (thread_id, subject, state["draft"], str(path)),
        )
        recipients = conn.execute(
            "SELECT id, email, name FROM recipients WHERE active=1 ORDER BY id"
        ).fetchall()

    settings = smtp_settings() if recipients else {}
    sent = failed = 0
    for recipient in recipients:
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = settings["EMAIL_FROM"]
        message["To"] = recipient["email"]
        greeting = f"{recipient['name']}님,\n\n" if recipient["name"] else ""
        message.set_content(greeting + state["draft"])
        status, error = "sent", ""
        try:
            with smtplib.SMTP(settings["SMTP_HOST"], int(os.getenv("SMTP_PORT", "587"))) as smtp:
                smtp.starttls()
                smtp.login(settings["SMTP_USER"], settings["SMTP_PASSWORD"])
                smtp.send_message(message)
            sent += 1
        except Exception as exc:  # 개별 실패가 전체 발송을 중단하지 않게 기록
            status, error = "failed", str(exc)
            failed += 1
        with db_connect() as conn:
            conn.execute(
                """INSERT INTO deliveries(thread_id, recipient_id, status, error_message)
                   VALUES(?, ?, ?, ?)
                   ON CONFLICT(thread_id, recipient_id) DO UPDATE SET
                   status=excluded.status, error_message=excluded.error_message,
                   sent_at=CURRENT_TIMESTAMP""",
                (thread_id, recipient["id"], status, error),
            )

    return {
        "status": "published",
        "output_path": str(path.resolve()),
        "sent_count": sent,
        "failed_count": failed,
    }


def rejected(_: NewsletterState) -> dict:
    return {"status": "rejected"}


def build_graph(checkpointer: SqliteSaver):
    builder = StateGraph(NewsletterState)
    for name, node in [
        ("analyze_input", analyze_input),
        ("research_news", research_news),
        ("write_newsletter", write_newsletter),
        ("review_newsletter", review_newsletter),
        ("human_approval", human_approval),
        ("publish", publish),
        ("rejected", rejected),
    ]:
        builder.add_node(name, node)
    builder.add_edge(START, "analyze_input")
    builder.add_edge("analyze_input", "research_news")
    builder.add_edge("research_news", "write_newsletter")
    builder.add_edge("write_newsletter", "review_newsletter")
    builder.add_conditional_edges("review_newsletter", route_after_review)
    builder.add_conditional_edges("human_approval", route_human_decision)
    builder.add_edge("publish", END)
    builder.add_edge("rejected", END)
    return builder.compile(checkpointer=checkpointer)


def graph_instance():
    connection = sqlite3.connect(DB_PATH, check_same_thread=False)
    return build_graph(SqliteSaver(connection))


def initial_state(keywords: list[str] | None = None) -> NewsletterState:
    config = load_config()
    return {
        "keywords": keywords or config["default_newsletter"]["keywords"],
        "audience": config["default_newsletter"]["audience"],
        "tone": config["default_newsletter"]["tone"],
        "max_articles": config["default_newsletter"].get("max_articles", 30),
        "revision_count": 0,
    }


def show_result(result: dict, thread_id: str) -> None:
    if "__interrupt__" in result:
        payload = result["__interrupt__"][0].value
        print("\n" + "=" * 70 + "\n" + payload["draft"])
        print("\n검수 점수:", payload.get("review_score"))
        print("검수 의견:", *payload.get("review_feedback", []), sep="\n- ")
        print(f"\n승인: python newsletter.py approve --thread {thread_id} --action approve")
    else:
        print("상태:", result.get("status"))
        print("성공/실패:", result.get("sent_count", 0), "/", result.get("failed_count", 0))
        if result.get("output_path"):
            print("저장 위치:", result["output_path"])


def run_newsletter(thread_id: str, keywords: list[str] | None = None) -> None:
    result = graph_instance().invoke(
        initial_state(keywords), {"configurable": {"thread_id": thread_id}}
    )
    show_result(result, thread_id)


def scheduled_job() -> None:
    thread_id = f"scheduled-{datetime.now():%Y%m%d-%H%M%S}"
    try:
        run_newsletter(thread_id)
    except Exception as exc:
        print(f"[오류] 예약 뉴스레터 생성 실패: {exc}")


def run_scheduler() -> None:
    config = load_config()
    scheduler = BlockingScheduler(timezone=config.get("timezone", "Asia/Seoul"))
    for time_text in config["schedule_times"]:
        hour, minute = map(int, time_text.split(":"))
        scheduler.add_job(
            scheduled_job,
            CronTrigger(hour=hour, minute=minute),
            id=f"newsletter-{hour:02d}{minute:02d}",
            replace_existing=True,
            misfire_grace_time=1800,
        )
    print("예약 실행 시작:", ", ".join(config["schedule_times"]))
    print("주의: 예약 실행은 초안을 만들며, 승인 후에만 이메일이 발송됩니다.")
    scheduler.start()


def recipient_command(args) -> None:
    with db_connect() as conn:
        if args.recipient_action == "add":
            conn.execute(
                """INSERT INTO recipients(email, name, active) VALUES(?, ?, 1)
                   ON CONFLICT(email) DO UPDATE SET name=excluded.name, active=1""",
                (args.email.strip().lower(), args.name or ""),
            )
            print("수신자 등록:", args.email)
        elif args.recipient_action == "remove":
            conn.execute("UPDATE recipients SET active=0 WHERE email=?", (args.email.lower(),))
            print("수신자 비활성화:", args.email)
        elif args.recipient_action == "list":
            rows = conn.execute(
                "SELECT id, email, name, active, created_at FROM recipients ORDER BY id"
            ).fetchall()
            for row in rows:
                print(dict(row))


def main() -> None:
    init_db()
    parser = argparse.ArgumentParser(description="예약형 맞춤 뉴스레터 멀티 에이전트")
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="즉시 뉴스레터 초안 생성")
    run_p.add_argument("--thread", default=f"manual-{datetime.now():%Y%m%d-%H%M%S}")
    run_p.add_argument("--keywords", help="쉼표로 구분한 키워드")

    approve_p = sub.add_parser("approve", help="승인 대기 작업 재개")
    approve_p.add_argument("--thread", required=True)
    approve_p.add_argument("--action", choices=["approve", "revise", "reject"], required=True)
    approve_p.add_argument("--feedback", default="")

    sub.add_parser("scheduler", help="매일 08:00, 18:00 예약 실행")

    recipient_p = sub.add_parser("recipient", help="이메일 수신자 관리")
    recipient_sub = recipient_p.add_subparsers(dest="recipient_action", required=True)
    add_p = recipient_sub.add_parser("add")
    add_p.add_argument("--email", required=True)
    add_p.add_argument("--name", default="")
    remove_p = recipient_sub.add_parser("remove")
    remove_p.add_argument("--email", required=True)
    recipient_sub.add_parser("list")

    args = parser.parse_args()
    if args.command == "run":
        keywords = [x.strip() for x in args.keywords.split(",")] if args.keywords else None
        run_newsletter(args.thread, keywords)
    elif args.command == "approve":
        result = graph_instance().invoke(
            Command(resume={"action": args.action, "feedback": args.feedback}),
            {"configurable": {"thread_id": args.thread}},
        )
        show_result(result, args.thread)
    elif args.command == "scheduler":
        run_scheduler()
    elif args.command == "recipient":
        recipient_command(args)


if __name__ == "__main__":
    main()


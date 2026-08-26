"""
LangGraph 파이프라인

과제 설명서(프로젝트주제_예시.pptx 슬라이드 2)가 요구하는 두 가지를 구현한다.

    [사용자 입력] -> [리서치] -> [작성] -> [검수] -> [인간 승인 대기] -> [발송/저장]
                                    ▲                    │
                                    └── 품질 미달 ────────┘

    1) Conditional Edges
       검수 에이전트가 "품질 미달"로 판정하면 작성 단계로 되돌아가는 순환 구조.
       무한 반복을 막기 위해 자동 재작성은 최대 2회까지만 한다.

    2) Human-in-the-Loop (State Checkpoint)
       사람이 승인 버튼을 누르기 전까지 그래프를 멈춘다.
       interrupt() 로 중단하고, 체크포인트에 상태를 저장해 두었다가
       Command(resume=...) 로 그 자리에서 이어서 실행한다.

각 노드의 실제 일은 newsletter_service 가 이미 갖고 있는 것을 부른다.
그래프는 "순서와 분기"만 책임진다.
"""

from __future__ import annotations

import os
import re
from typing import Dict, List, Literal, TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

PASS_SCORE = int(os.getenv("REVIEW_PASS_SCORE", "80"))
MAX_AUTO_REVISION = int(os.getenv("MAX_AUTO_REVISION", "2"))


# ------------------------------------------------------------------
# 상태 - 노드끼리 주고받는 값
# ------------------------------------------------------------------
class NewsletterState(TypedDict, total=False):
    request_text: str          # 사용자가 입력한 문장
    keywords: List[str]        # 분석해서 뽑은 검색어
    query: str
    article_count: int
    title_hint: str

    sources: List[Dict]        # 근거 기사
    research_items: List[Dict] # 실시간 검색과 색인 보강을 합친 원본
    context: str               # LLM 에 넘길 근거 본문 묶음
    markdown: str              # 뉴스레터 본문
    article_html: str
    send_result: Dict          # 발송 결과

    score: int                 # 검수 총점
    passed: bool
    audit: Dict
    feedback: List[str]

    revision_count: int        # 자동 재작성 횟수
    human_decision: str        # approve / revise / reject
    human_feedback: str
    frequency: str

    draft_id: str
    status: str


# ------------------------------------------------------------------
# 노드
# ------------------------------------------------------------------
def _svc():
    from newsletter_service import service
    return service


def analyze_node(state: NewsletterState) -> Dict:
    """[1] 사용자 입력 분석 - 문장에서 검색어·독자·개수를 뽑는다."""
    plan = _svc().analyzer.analyze(state["request_text"])
    return {
        "keywords": plan.keywords,
        "query": " ".join(plan.keywords),
        "article_count": plan.article_count,
        "title_hint": plan.title_hint,
        "revision_count": state.get("revision_count", 0),
        "status": "analyzed",
    }


def research_node(state: NewsletterState) -> Dict:
    """[2] 리서치 에이전트 - 실시간 검색 후 저장 색인으로 보강한다."""
    import compose

    svc = _svc()
    items = svc.research(
        state.get("keywords", []), state.get("article_count", 8)
    )
    if not items:
        raise ValueError(f"'{state['query']}' 와 관련된 뉴스를 찾지 못했습니다.")
    return {
        "research_items": items,
        "sources": compose.items_to_sources(items),
        "context": compose.format_items(items),
        "status": "researched",
    }


def write_node(state: NewsletterState) -> Dict:
    """
    [3] 작성 에이전트 - 기사별로 요약을 쓴다.

    검수에서 되돌아온 경우에는 검수 의견을 반영해 다시 쓴다.
    """
    from rag_engine import DEFAULT_STYLE, STYLE_PROMPTS

    svc = _svc()
    feedback = state.get("feedback") or []
    human = state.get("human_feedback") or ""

    if state.get("markdown") and (feedback or human):
        # 재작성 - 무엇이 부족했는지 알려주고 고쳐 쓰게 한다
        from newsletter_service import REVISE_PROMPT
        note = "\n".join(f"- {f}" for f in feedback)
        direction = (human or "") + ("\n[검수 의견]\n" + note if note else "")
        item_count = len(re.findall(r"^\*\*.+\*\*", state["markdown"], flags=re.M)) \
            or len(state.get("sources", []))
        md = (REVISE_PROMPT | svc.rag.llm).invoke({
            "context": state["context"],
            "previous": state["markdown"],
            "direction": direction,
            "item_count": item_count,
        }).content
    else:
        # 첫 작성
        md = (STYLE_PROMPTS[DEFAULT_STYLE] | svc.rag.llm).invoke({
            "context": state["context"],
            "topic": state["query"],
        }).content

    # [4] 한국어 다듬기
    md = svc.polisher.polish(md)
    return {"markdown": md, "human_feedback": "", "status": "written"}


def review_node(state: NewsletterState) -> Dict:
    """[5] 검수 에이전트 - 다른 모델이 채점한다."""
    svc = _svc()
    result = svc.reviewer.review(state["markdown"], state.get("sources", []))
    return {
        "score": result.score,
        "passed": result.passed,
        "feedback": result.feedback,
        "audit": svc.reviewer.audit_report(result, state.get("revision_count", 0)),
        "status": "reviewed",
    }


def route_after_review(state: NewsletterState) -> Literal["write", "human_approval"]:
    """
    조건부 분기 (Conditional Edge)

    품질 미달이면 작성 단계로 되돌아간다.
    다만 자동 재작성은 MAX_AUTO_REVISION 회까지만 하고,
    그 뒤에는 사람이 판단하게 넘긴다.
    """
    if not state.get("passed") and state.get("revision_count", 0) < MAX_AUTO_REVISION:
        return "write"
    return "human_approval"


def bump_revision(state: NewsletterState) -> Dict:
    """되돌아갈 때 횟수를 센다."""
    return {"revision_count": state.get("revision_count", 0) + 1}


def human_approval_node(state: NewsletterState) -> Dict:
    """
    [6] 인간 승인 대기 (Human-in-the-Loop)

    여기서 그래프가 멈춘다. 상태는 체크포인트에 저장된다.
    사용자가 화면에서 버튼을 누르면 Command(resume=...) 로 이어서 실행된다.
    """
    decision = interrupt({
        "message": "뉴스레터를 확인해 주세요.",
        "title": state.get("title_hint"),
        "markdown": state.get("markdown"),
        "score": state.get("score"),
        "audit": state.get("audit"),
        "sources": state.get("sources"),
        "choices": ["approve", "revise", "reject"],
    })

    if isinstance(decision, str):
        decision = {"action": decision}
    return {
        "human_decision": decision.get("action", "reject"),
        "human_feedback": decision.get("feedback", ""),
        "frequency": decision.get("frequency", "daily"),
        "status": "human_decided",
    }


def route_human(state: NewsletterState) -> Literal["write", "send", "rejected"]:
    action = state.get("human_decision", "reject")
    if action == "approve":
        return "send"
    if action == "revise":
        return "write"
    return "rejected"


def send_node(state: NewsletterState) -> Dict:
    """[7] 발송 - 승인된 것만 보낸다."""
    from mailer import send_draft

    draft = {
        "title": state.get("title_hint", "뉴스레터"),
        "markdown": state.get("markdown", ""),
        "sources": [
            {"title": s.get("title", ""), "summary": s.get("source", ""),
             "url": s.get("link", "")}
            for s in state.get("sources", [])
        ],
    }
    res = send_draft(draft)
    return {"status": "sent" if res.get("sent") else "approved", "send_result": res}


def rejected_node(state: NewsletterState) -> Dict:
    return {"status": "rejected"}


# ------------------------------------------------------------------
# 그래프 만들기
# ------------------------------------------------------------------
def build_graph():
    g = StateGraph(NewsletterState)

    g.add_node("analyze", analyze_node)
    g.add_node("research", research_node)
    g.add_node("write", write_node)
    g.add_node("review", review_node)
    g.add_node("bump", bump_revision)
    g.add_node("human_approval", human_approval_node)
    g.add_node("send", send_node)
    g.add_node("rejected", rejected_node)

    g.add_edge(START, "analyze")
    g.add_edge("analyze", "research")
    g.add_edge("research", "write")
    g.add_edge("write", "review")

    # 조건부 분기 - 품질 미달이면 bump 를 거쳐 write 로 되돌아간다
    g.add_conditional_edges("review", route_after_review,
                            {"write": "bump", "human_approval": "human_approval"})
    g.add_edge("bump", "write")

    # 사람이 판단한 뒤의 분기
    g.add_conditional_edges("human_approval", route_human,
                            {"write": "bump", "send": "send", "rejected": "rejected"})

    g.add_edge("send", END)
    g.add_edge("rejected", END)

    # 체크포인트 - 승인 대기 상태를 저장해 두었다가 이어서 실행한다
    return g.compile(checkpointer=MemorySaver())


_graph = None


def graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph


# ------------------------------------------------------------------
# 바깥에서 쓰는 함수
# ------------------------------------------------------------------
def start(request_text: str, thread_id: str) -> Dict:
    """
    그래프를 시작한다. 인간 승인 노드에서 멈추고 그 상태를 돌려준다.
    thread_id 는 이어서 실행할 때 쓰는 열쇠다.
    """
    cfg = {"configurable": {"thread_id": thread_id}}
    result = graph().invoke({"request_text": request_text, "revision_count": 0}, config=cfg)
    return _unpack(result, thread_id)


def resume(thread_id: str, action: str, feedback: str = "", frequency: str = "daily") -> Dict:
    """멈춰 있던 그래프를 사람의 결정으로 이어서 실행한다."""
    cfg = {"configurable": {"thread_id": thread_id}}
    result = graph().invoke(
        Command(resume={"action": action, "feedback": feedback, "frequency": frequency}),
        config=cfg,
    )
    return _unpack(result, thread_id)


def _unpack(result: Dict, thread_id: str) -> Dict:
    """멈춘 상태인지, 끝난 상태인지 구분해서 돌려준다."""
    if "__interrupt__" in result:
        payload = result["__interrupt__"][0].value
        return {"waiting": True, "thread_id": thread_id, **payload}

    snap = graph().get_state({"configurable": {"thread_id": thread_id}})
    return {"waiting": False, "thread_id": thread_id, **dict(snap.values)}


def state_of(thread_id: str) -> Dict:
    """지금 어느 노드에서 멈춰 있는지 본다."""
    snap = graph().get_state({"configurable": {"thread_id": thread_id}})
    return {
        "thread_id": thread_id,
        "next": list(snap.next),
        "status": snap.values.get("status"),
        "score": snap.values.get("score"),
        "revision_count": snap.values.get("revision_count"),
    }

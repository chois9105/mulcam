"""
기사 목록으로 요약 만들기

색인에서 찾은 기사와 실시간으로 받아온 기사를 함께 쓰려면
Document 가 아니라 평범한 dict 목록으로 다루는 편이 낫다.

    색인 결과(Document)  ─┐
                          ├─→ dict 목록 → [기사] 묶음 → 요약
    실시간 결과(dict)    ─┘
"""

from __future__ import annotations

from typing import Dict, List

from langchain_core.documents import Document

from html_render import to_dashboard_html
from rag_engine import DEFAULT_STYLE, STYLE_INFO, STYLE_PROMPTS


def docs_to_items(docs: List[Document]) -> List[Dict]:
    """색인 검색 결과 -> 기사 dict 목록"""
    items = []
    for d in docs:
        m = d.metadata
        items.append({
            "title": m.get("title", ""),
            "link": m.get("link", ""),
            "source": m.get("source", ""),
            "published": m.get("published", ""),
            "content": m.get("body", "") or d.page_content,
            "has_full_text": m.get("has_full_text", False),
            "live": False,
        })
    return items


def format_items(items: List[Dict]) -> str:
    """기사 dict 목록 -> LLM 에 넘길 [기사] 묶음"""
    blocks = []
    for i, it in enumerate(items, 1):
        body = (it.get("content") or it.get("description") or "").strip()
        mark = "" if it.get("has_full_text") else "  (제목만 확인됨)"

        lines = [
            f"[{i}] 출처: {it.get('source', '')} / {it.get('published', '')}{mark}",
            f"    제목: {it.get('title', '')}",
        ]
        if body:
            lines.append(f"    본문: {body[:800]}")
        lines.append(f"    링크: {it.get('link', '')}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def items_to_sources(items: List[Dict]) -> List[Dict]:
    """기사 dict 목록 -> 응답에 담을 근거 목록"""
    return [{
        "n": i,
        "title": it.get("title", ""),
        "source": it.get("source", ""),
        "link": it.get("link", ""),
        "published": it.get("published", ""),
        "has_full_text": it.get("has_full_text", False),
        "live": it.get("live", False),
    } for i, it in enumerate(items, 1)]


def summarize_items(llm, topic: str, items: List[Dict],
                    style: str = DEFAULT_STYLE) -> Dict:
    """정해진 기사 목록으로 요약을 만든다."""
    if style not in STYLE_PROMPTS:
        raise ValueError(f"style 은 {list(STYLE_PROMPTS)} 중 하나여야 합니다.")

    newsletter = (STYLE_PROMPTS[style] | llm).invoke({
        "context": format_items(items),
        "topic": topic,
    }).content

    sources = items_to_sources(items)
    return {
        "topic": topic,
        "style": style,
        "style_name": STYLE_INFO[style]["name"],
        "newsletter": newsletter,
        "article_html": to_dashboard_html(newsletter, sources),
        "sources": sources,
    }

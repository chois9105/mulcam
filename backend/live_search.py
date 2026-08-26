"""
실시간 뉴스 검색

사용자가 키워드를 넣는 순간, 그 키워드로 뉴스를 찾아온다.

미리 모아둔 기사(articles 색인)만 쓰면 문제가 있다.
수집은 주제와 상관없이 전 매체를 훑기 때문에, 특정 키워드 기사가
그 안에 없을 수 있다. 실제로 '전기차 배터리' 를 넣었을 때
오늘 수집분에 없어서 만들지 못했다.

그래서 두 곳을 함께 쓴다.

    1) 미리 모아둔 색인   국내 16곳 · 본문 900자 확보 · 원문 링크
    2) 구글뉴스 검색      키워드로 실시간 · 제목과 출처만 · 구글 경유 링크

1번이 품질이 좋고, 2번이 빠짐없이 찾아준다. 합치면 둘 다 얻는다.

구글뉴스 링크에 대해:
    news.google.com/rss/articles/... 형태라 프로그램이 본문을 못 긁는다.
    다만 사람이 브라우저에서 누르면 원문으로 잘 넘어간다.
    그래서 본문 없이 제목·출처만 쓰고, 링크는 그대로 둔다.
"""

from __future__ import annotations

import html as html_mod
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List
from urllib.parse import quote_plus

import feedparser

GOOGLE_NEWS = ("https://news.google.com/rss/search"
               "?q={q}&hl=ko&gl=KR&ceid=KR:ko")


def _clean(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = html_mod.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _split_title(raw: str) -> tuple[str, str]:
    """
    구글뉴스 제목은 '기사 제목 - 출처' 형태다.
    뒤의 출처를 떼어내 따로 돌려준다.
    """
    raw = _clean(raw)
    if " - " in raw:
        head, _, tail = raw.rpartition(" - ")
        if head and len(tail) < 30:
            return head.strip(), tail.strip()
    return raw, ""


def search_keyword(keyword: str, limit: int = 8) -> List[Dict]:
    """키워드 하나로 구글뉴스를 검색한다."""
    try:
        feed = feedparser.parse(GOOGLE_NEWS.format(q=quote_plus(keyword)))
    except Exception:
        return []

    items = []
    for e in feed.entries[:limit]:
        title, from_title = _split_title(e.get("title", ""))
        if not title:
            continue
        src = e.get("source")
        source = ""
        if isinstance(src, dict):
            source = src.get("title", "")
        source = source or from_title or "구글뉴스"

        items.append({
            "title": title,
            "link": e.get("link", ""),
            # 구글뉴스 description 은 제목을 감싼 링크라 본문이 없다.
            # 요약에 쓸 내용이 없으므로 비워 둔다.
            "description": "",
            "content": "",
            "has_full_text": False,
            "published": e.get("published", ""),
            "source": source,
            "live": True,          # 실시간으로 가져온 것
            "keyword": keyword,
        })
    return items


def search(keywords: List[str], per_keyword: int = 8,
           max_total: int = 24) -> List[Dict]:
    """
    여러 키워드를 동시에 검색해 합친다.
    같은 기사가 여러 키워드에 걸리면 한 번만 담는다.
    """
    terms = []
    for kw in keywords:
        kw = (kw or "").strip()
        if not kw:
            continue
        terms.append(kw)
        # 'AI 반도체' 처럼 붙은 키워드는 낱말로도 한 번 더 찾는다
        parts = [w for w in kw.split() if len(w) >= 2]
        if len(parts) > 1:
            terms.extend(parts)

    seen_t, uniq = set(), []
    for t in terms:
        if t not in seen_t:
            seen_t.add(t)
            uniq.append(t)
    if not uniq:
        return []

    with ThreadPoolExecutor(min(6, len(uniq))) as ex:
        results = list(ex.map(lambda k: search_keyword(k, per_keyword), uniq))

    seen, merged = set(), []
    for group in results:
        for item in group:
            key = _norm(item["title"])
            if key in seen:
                continue
            seen.add(key)
            merged.append(item)
    return merged[:max_total]


def _norm(title: str) -> str:
    """제목이 조금 달라도 같은 기사로 보기 위해 기호·공백을 없앤다."""
    return re.sub(r"[^\w가-힣]", "", title).lower()[:40]


def merge_with_indexed(indexed: List[Dict], live: List[Dict],
                       limit: int = 10, indexed_share: float = 0.4) -> List[Dict]:
    """
    실시간 검색 결과와 미리 모아둔 기사를 합친다.

    실시간 결과를 먼저 넣는다. 키워드로 직접 찾은 것이라 확실히 관련 있다.
    색인 결과는 뜻으로 찾은 것이라 느슨하게 걸릴 수 있어 뒤에 둔다.

    (색인을 앞에 두었더니 무관한 기사가 자리를 다 차지해서,
     '전기차 배터리' 로 실시간 12건을 찾아놓고도 1건만 들어갔다.)

    다만 색인 기사에는 본문 900자가 있어 요약이 깊어진다.
    그래서 자리의 일부(indexed_share)는 본문 있는 기사에 남겨 둔다.
    """
    seen, merged = set(), []

    def add(item) -> bool:
        key = _norm(item.get("title", ""))
        if not key or key in seen:
            return False
        seen.add(key)
        merged.append(item)
        return True

    # 본문이 있는 색인 기사를 위해 남겨둘 자리
    keep_for_indexed = min(len(indexed), int(limit * indexed_share))
    live_room = max(1, limit - keep_for_indexed)

    for item in live:
        if len(merged) >= live_room:
            break
        add(item)

    for item in indexed:
        if len(merged) >= limit:
            break
        add(item)

    # 실시간 결과가 적어 자리가 남으면 마저 채운다
    for item in live:
        if len(merged) >= limit:
            break
        add(item)

    return merged[:limit]

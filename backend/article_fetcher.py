"""
기사 본문 추출기

RSS는 제목과 짧은 요약(연합뉴스 기준 60자)만 준다.
요약 품질을 높이려면 link 를 따라가 실제 기사 본문을 가져와야 한다.

사용:
    from article_fetcher import fetch_article
    text = fetch_article("https://www.yna.co.kr/view/AKR...")
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9",
}

# 언론사별 본문 영역 (앞에서부터 시도)
SELECTORS = [
    "article",
    "#articleBodyContents",      # 네이버 계열
    ".article-txt", ".article_txt", ".article-body", ".article_body",
    "#article-view-content-div", # 다수 언론사 공통 CMS
    "#newsct_article",
    ".news_cnt_detail_wrap",     # 뉴시스
    "#CmAdContent",              # 조선
    ".art_body", "#dic_area",
]

# 본문에 섞여 나오는 잡음
NOISE = re.compile(
    r"(무단\s*전재|재배포\s*금지|저작권자|ⓒ|Copyright|기자\s*=|이메일|구독하기|"
    r"관련기사|많이 본 뉴스|광고)"
)


def _clean(text: str) -> str:
    text = re.sub(r"\s+", " ", text)
    parts = [p.strip() for p in text.split(". ") if not NOISE.search(p)]
    return ". ".join(parts).strip()


def fetch_article(url: str, timeout: int = 8, max_chars: int = 2000) -> Optional[str]:
    """기사 URL에서 본문 텍스트를 뽑는다. 실패하면 None."""
    if not url or "news.google.com" in url:
        # 구글뉴스 링크는 자바스크립트 리다이렉트라 본문을 못 가져온다
        return None
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        r.raise_for_status()
        r.encoding = r.apparent_encoding or r.encoding
        soup = BeautifulSoup(r.text, "lxml")

        for tag in soup(["script", "style", "aside", "nav", "footer", "figure"]):
            tag.decompose()

        for sel in SELECTORS:
            node = soup.select_one(sel)
            if node:
                body = _clean(node.get_text(" ", strip=True))
                if len(body) > 150:
                    return body[:max_chars]

        # 마지막 수단: og:description
        og = soup.find("meta", property="og:description")
        if og and og.get("content"):
            return _clean(og["content"])[:max_chars]
        return None
    except Exception:
        return None


def enrich(news_items: List[Dict], workers: int = 8, max_chars: int = 2000) -> Dict:
    """
    뉴스 목록에 'content'(본문)를 채워 넣는다.
    반환: {'ok': 성공건수, 'fail': 실패건수}
    """
    def work(n: Dict):
        body = fetch_article(n.get("link", ""), max_chars=max_chars)
        n["content"] = body or ""
        n["has_full_text"] = bool(body)
        return bool(body)

    with ThreadPoolExecutor(workers) as ex:
        results = list(ex.map(work, news_items))
    return {"ok": sum(results), "fail": len(results) - sum(results)}

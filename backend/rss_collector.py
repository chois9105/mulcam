"""
RSS 뉴스 수집기

- 2026-08-25 기준 실제 응답을 확인한 국내 언론사 피드만 등록했다.
- 구글뉴스는 제외했다. 링크가 news.google.com/rss/articles/... 리다이렉트라
  상세 페이지로 바로 갈 수 없고 본문도 못 가져오기 때문이다.
- 네이버 RSS(rss.naver.com)는 서비스가 종료되어 도메인 자체가 없다.
"""

import hashlib
import html as html_mod
import json
import re
from pathlib import Path
from typing import Dict, List

import feedparser

# 실제 응답 + 원문 링크 제공이 확인된 피드
DEFAULT_FEEDS = {
    "연합뉴스":     "https://www.yna.co.kr/rss/news.xml",
    "연합뉴스_경제": "https://www.yna.co.kr/rss/economy.xml",
    "한겨레":       "https://www.hani.co.kr/rss/",
    "경향신문":     "https://www.khan.co.kr/rss/rssdata/total_news.xml",
    "동아일보":     "https://rss.donga.com/total.xml",
    "조선일보":     "https://www.chosun.com/arc/outboundfeeds/rss/?outputType=xml",
    "서울신문":     "https://www.seoul.co.kr/xml/rss/rss_politics.xml",
    "매일경제":     "https://www.mk.co.kr/rss/30000001/",
    "매일경제_경제": "https://www.mk.co.kr/rss/30100041/",
    "머니투데이":   "https://rss.mt.co.kr/mt_news.xml",
    "뉴시스":       "https://newsis.com/RSS/health.xml",
    "전자신문":     "https://rss.etnews.com/Section901.xml",
    "전자신문_IT":  "https://rss.etnews.com/Section902.xml",
    "ZDNet코리아":  "https://feeds.feedburner.com/zdkorea",
    "노컷뉴스":     "https://rss.nocutnews.co.kr/nocutnews.xml",
    "오마이뉴스":   "http://rss.ohmynews.com/rss/ohmynews.xml",
}


# 뉴스레터에 쓸모없는 정형 기사 (부고·인사·헤드라인 목록 등)
# 이런 제목이 '오늘의 주요 뉴스' 같은 검색어에 걸려 요약을 망친다
SKIP_TITLE = re.compile(
    r"(오늘의\s*부고|부고\s*-|오늘의\s*인사|인사\s*-|이\s*시각\s*헤드라인|"
    r"헤드라인\s*모음|다시보기|오늘의\s*날씨|주요\s*일정|포토\s*뉴스|"
    r"\[부고\]|\[인사\]|\[포토\]|\[카드뉴스\])"
)


class RSSCollector:
    def __init__(self, cache_file: str = "news_cache.json", feeds: Dict[str, str] = None):
        self.cache_file = cache_file
        self.cache = self._load_cache()
        self.feeds = dict(feeds) if feeds else dict(DEFAULT_FEEDS)

    # ---------- 중복 방지 캐시 ----------
    def _load_cache(self) -> set:
        if Path(self.cache_file).exists():
            try:
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    return set(json.load(f).get("urls", []))
            except Exception:
                return set()
        return set()

    def _save_cache(self):
        with open(self.cache_file, "w", encoding="utf-8") as f:
            json.dump({"urls": list(self.cache)}, f, ensure_ascii=False)

    @staticmethod
    def _hash(url: str) -> str:
        return hashlib.md5(url.encode()).hexdigest()

    def _is_duplicate(self, url: str) -> bool:
        return self._hash(url) in self.cache

    def _add_to_cache(self, url: str):
        self.cache.add(self._hash(url))

    # ---------- 수집 ----------
    @staticmethod
    def _clean(text: str) -> str:
        """description 이 HTML 인 경우가 있어 태그를 걷어낸다."""
        if not text:
            return ""
        text = re.sub(r"<[^>]+>", " ", text)
        text = html_mod.unescape(text)
        return re.sub(r"\s+", " ", text).strip()

    def fetch_from_feed(self, feed_name: str, feed_url: str, limit: int = 20) -> List[Dict]:
        try:
            feed = feedparser.parse(feed_url)
            items = []
            for entry in feed.entries[:limit]:
                link = entry.get("link", "")
                if not link or self._is_duplicate(link):
                    continue
                title = self._clean(entry.get("title", ""))
                if SKIP_TITLE.search(title):
                    self._add_to_cache(link)   # 다시 안 보도록 캐시에만 넣음
                    continue
                items.append({
                    "title": title,
                    "link": link,
                    "description": self._clean(entry.get("description", "") or entry.get("summary", "")),
                    "content": "",            # article_fetcher.enrich() 로 채움
                    "has_full_text": False,
                    "published": entry.get("published", ""),
                    "source": feed_name,
                })
                self._add_to_cache(link)
            return items
        except Exception as e:
            print(f"[수집 실패] {feed_name}: {e}")
            return []

    def fetch_all_news(self, limit_per_feed: int = 20) -> List[Dict]:
        all_news = []
        for name, url in self.feeds.items():
            all_news.extend(self.fetch_from_feed(name, url, limit_per_feed))
        self._save_cache()
        return sorted(all_news, key=lambda x: x.get("published", ""), reverse=True)

    # ---------- 피드 관리 ----------
    def add_custom_feed(self, name: str, url: str):
        self.feeds[name] = url

    def remove_feed(self, name: str):
        self.feeds.pop(name, None)

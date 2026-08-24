import feedparser
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional

class RSSCollector:
    def __init__(self, cache_file: str = "news_cache.json"):
        self.cache_file = cache_file
        self.cache = self._load_cache()

        self.feeds = {
            "google_news": "https://news.google.com/rss?hl=ko&gl=KR&ceid=KR:ko",
            "naver_tech": "https://rss.naver.com/tech.xml",
        }

    def _load_cache(self) -> set:
        if Path(self.cache_file).exists():
            try:
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return set(data.get('urls', []))
            except:
                return set()
        return set()

    def _save_cache(self):
        with open(self.cache_file, 'w', encoding='utf-8') as f:
            json.dump({'urls': list(self.cache)}, f, ensure_ascii=False)

    def _get_url_hash(self, url: str) -> str:
        return hashlib.md5(url.encode()).hexdigest()

    def _is_duplicate(self, url: str) -> bool:
        url_hash = self._get_url_hash(url)
        return url_hash in self.cache

    def _add_to_cache(self, url: str):
        url_hash = self._get_url_hash(url)
        self.cache.add(url_hash)
        self._save_cache()

    def fetch_from_feed(self, feed_url: str) -> List[Dict]:
        try:
            feed = feedparser.parse(feed_url)
            news_items = []

            for entry in feed.entries[:20]:  # 최신 20개만
                if self._is_duplicate(entry.link):
                    continue

                news = {
                    'title': entry.get('title', ''),
                    'link': entry.link,
                    'description': entry.get('description', ''),
                    'published': entry.get('published', ''),
                    'source': feed.feed.get('title', 'Unknown'),
                }
                news_items.append(news)
                self._add_to_cache(entry.link)

            return news_items
        except Exception as e:
            print(f"Error fetching feed {feed_url}: {e}")
            return []

    def fetch_all_news(self) -> List[Dict]:
        all_news = []
        for feed_name, feed_url in self.feeds.items():
            news = self.fetch_from_feed(feed_url)
            all_news.extend(news)

        return sorted(all_news, key=lambda x: x.get('published', ''), reverse=True)

    def add_custom_feed(self, name: str, url: str):
        self.feeds[name] = url

    def remove_feed(self, name: str):
        if name in self.feeds:
            del self.feeds[name]

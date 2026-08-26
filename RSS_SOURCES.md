# 뉴스 수집처 목록

마지막 확인: 2026-08-26 · 백엔드: 노희선

이 프로그램은 뉴스를 **두 곳**에서 가져온다.

| 구분 | 언제 | 어디서 | 본문 | 링크 |
|---|---|---|---|---|
| **① 실시간 검색** | 사용자가 키워드를 넣는 순간 | 구글뉴스 검색 | 없음 (제목·출처만) | 구글뉴스 경유 |
| **② 미리 수집** | 스케줄러 (07·12·18시) | 국내 언론사 16곳 RSS | **있음 (평균 900자)** | 원문 직접 |

①이 빠짐없이 찾아주고, ②가 본문으로 요약을 깊게 만든다. 둘을 합쳐 쓴다.

---

## ① 실시간 검색 — 구글뉴스

사용자가 넣은 키워드로 그 자리에서 검색한다.

```
https://news.google.com/rss/search?q={키워드}&hl=ko&gl=KR&ceid=KR:ko
```

구현: `backend/live_search.py`

### 동작 방식

1. 요청 문장에서 키워드를 뽑는다 (`request_analyzer.py`)
   - `"2026년 8월 26일 대한민국 로봇 관련 정보"` → `["로봇"]`
   - `대한민국`, `오늘`, `최신`, `뉴스`, `정보` 같은 일반적인 낱말은 뺀다
2. 키워드마다 동시에 검색한다 (`AI 반도체` → `AI 반도체`, `AI`, `반도체` 세 갈래)
3. 제목 기준으로 중복을 없앤다

### 특징

- **키워드 하나로 100건 넘게** 찾아온다. 국내 거의 모든 매체가 걸린다
- 제목이 `기사 제목 - 출처` 형태라 출처를 분리해 쓴다
- **본문은 못 가져온다.** 링크가 `news.google.com/rss/articles/...` 리다이렉트라
  프로그램이 원문에 접근할 수 없다
- 다만 **사람이 브라우저에서 누르면 원문으로 잘 넘어간다.** 그래서 링크는 그대로 쓴다

---

## ② 미리 수집 — 국내 언론사 16곳

구현: `backend/rss_collector.py` · 상수 `DEFAULT_FEEDS`

| # | 매체 | 주소 |
|---|---|---|
| 1 | 연합뉴스 | `https://www.yna.co.kr/rss/news.xml` |
| 2 | 연합뉴스 경제 | `https://www.yna.co.kr/rss/economy.xml` |
| 3 | 한겨레 | `https://www.hani.co.kr/rss/` |
| 4 | 경향신문 | `https://www.khan.co.kr/rss/rssdata/total_news.xml` |
| 5 | 동아일보 | `https://rss.donga.com/total.xml` |
| 6 | 조선일보 | `https://www.chosun.com/arc/outboundfeeds/rss/?outputType=xml` |
| 7 | 서울신문 | `https://www.seoul.co.kr/xml/rss/rss_politics.xml` |
| 8 | 매일경제 | `https://www.mk.co.kr/rss/30000001/` |
| 9 | 매일경제 경제 | `https://www.mk.co.kr/rss/30100041/` |
| 10 | 머니투데이 | `https://rss.mt.co.kr/mt_news.xml` |
| 11 | 뉴시스 | `https://newsis.com/RSS/health.xml` |
| 12 | 전자신문 | `https://rss.etnews.com/Section901.xml` |
| 13 | 전자신문 IT | `https://rss.etnews.com/Section902.xml` |
| 14 | ZDNet 코리아 | `https://feeds.feedburner.com/zdkorea` |
| 15 | 노컷뉴스 | `https://rss.nocutnews.co.kr/nocutnews.xml` |
| 16 | 오마이뉴스 | `http://rss.ohmynews.com/rss/ohmynews.xml` |

### 이 16곳을 고른 과정

국내 언론사 **25곳을 실제로 호출해** 응답이 오는 것만 남겼다.

**살아있음 (16곳)** — 위 표

**안 되는 곳 (9곳)**

| 매체 | 시도한 주소 | 결과 |
|---|---|---|
| 중앙일보 | `rss.joins.com/joins_news_list.xml` | 응답 0건 |
| 한국경제 | `hankyung.com/feed/all-news` | 응답 0건 |
| 이데일리 | `rss.edaily.co.kr/edaily_news.xml` | 응답 0건 |
| KBS | `news.kbs.co.kr/news/GetRssNewsList.do` | 응답 0건 |
| SBS | `news.sbs.co.kr/news/RssFeed.do` | 응답 0건 |
| MBC | `imnews.imbc.com/rss/news/news_00.xml` | 응답 0건 |
| YTN | `ytn.co.kr/_comm/rss_check.php` | 응답 0건 |
| 연합뉴스 IT | `yna.co.kr/rss/it.xml` | 응답 0건 |
| JTBC | `fs.jtbc.co.kr/RSS/newsflash.xml` | 뉴스룸 다시보기 영상만 |

---

## 쓰지 않기로 한 곳

### 네이버 뉴스 — 서비스 종료

```
rss.naver.com  →  도메인 자체가 존재하지 않음
                  (urlopen error [Errno 11001] getaddrinfo failed)
```

네이버가 RSS 서비스를 종료했다. 뉴스 검색 API는 있으나 별도 신청과 키가 필요하다.

### 구글뉴스 — 미리 수집용으로는 제외

미리 수집할 때는 쓰지 않는다. 실시간 검색에만 쓴다.

| 이유 | 내용 |
|---|---|
| 링크 | `news.google.com/rss/articles/...` 리다이렉트라 **원문 URL을 알 수 없다** |
| 본문 | 그래서 크롤링이 불가능하다 |
| description | 본문이 아니라 제목을 감싼 `<a>` 태그 덩어리다 |

미리 수집은 **본문 확보**가 목적이므로 국내 16곳만 쓴다.

---

## 왜 본문을 따로 가져오나

RSS 는 본문을 주지 않는다. 직접 재본 값이다.

| 매체 | RSS 가 주는 길이 |
|---|---|
| 연합뉴스 | **63자** |
| 한겨레 | 464자 |
| ZDNet | 1,233자 |

63자로는 요약을 만들 수 없다. 그래서 `article_fetcher.py` 가 링크를 따라가
본문을 긁어온다. 언론사마다 본문 태그가 달라 후보 12개를 순서대로 시도한다.

**성공률 99~100%** · 평균 458자 → **900자**

조선일보·머니투데이 일부 기사는 봇 차단으로 실패하는데,
그때는 RSS 요약으로 대체한다.

---

## 걸러내는 기사

뉴스레터에 쓸모없는 정형 기사는 수집 단계에서 뺀다.
(`rss_collector.py` 의 `SKIP_TITLE`)

```
오늘의 부고 · 부고 - · 오늘의 인사 · 인사 -
이 시각 헤드라인 · 헤드라인 모음 · 다시보기
오늘의 날씨 · 주요 일정 · 포토 뉴스
[부고] [인사] [포토] [카드뉴스]
```

이런 기사가 `오늘의 주요 뉴스` 같은 검색어에 걸려 요약을 망친 적이 있다.

---

## 수집 규모 (2026-08-26 기준)

```
한 번 수집   135~181건
본문 확보    99~100%
누적 저장    284건 (MySQL articles 테이블)
수집 시각    매일 07:00 · 12:00 · 18:00
```

---

## 직접 확인하는 법

### 지금 수집 실행

```bash
curl -X POST "http://127.0.0.1:8001/api/news/collect?limit_per_feed=10"
```

### 어떤 피드가 살아있는지 다시 점검

```python
import feedparser
from rss_collector import DEFAULT_FEEDS

for name, url in DEFAULT_FEEDS.items():
    f = feedparser.parse(url)
    print(f"{name:16} {len(f.entries):3}건")
```

### 실시간 검색만 따로 해보기

```python
import live_search
for item in live_search.search(["로봇"], per_keyword=6):
    print(item["title"], "|", item["source"])
```

---

## 관련 파일

| 파일 | 역할 |
|---|---|
| `backend/live_search.py` | 실시간 구글뉴스 검색 |
| `backend/rss_collector.py` | 국내 16곳 수집 · 정형 기사 필터 |
| `backend/article_fetcher.py` | 링크를 따라가 본문 추출 |
| `backend/scheduler.py` | 07·12·18시 자동 수집 |
| `backend/compose.py` | 실시간 + 미리 수집 결과 합치기 |

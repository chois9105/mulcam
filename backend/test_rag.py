"""
RAG 뉴스레터 전체 검증 스크립트

확인 항목
  1) RSS 수집 -> JSON 이 실제로 나오는가 (매체별 건수)
  2) RSS 가 본문을 주는가 / 링크를 따라가 본문을 채울 수 있는가
  3) 색인 생성
  4) 리서치 - 질문에 기사 근거로 답하는가
  5) 요약 3종 - brief / newsletter / deep
  6) 환각 방지 - 없는 걸 물으면 없다고 하는가

실행:  python test_rag.py
"""

import io
import json
import sys
import time

from article_fetcher import enrich
from rag_engine import STYLE_INFO, NewsRAG
from rss_collector import RSSCollector


def line(t):
    print("\n" + "=" * 72)
    print(t)
    print("=" * 72)


def main():
    t0 = time.time()

    # 1. 수집
    line("1. RSS 수집 -> JSON")
    collector = RSSCollector(cache_file="test_cache.json")
    news = collector.fetch_all_news(limit_per_feed=10)
    print(f"수집 {len(news)}건 / 피드 {len(collector.feeds)}개")
    by = {}
    for n in news:
        by[n["source"]] = by.get(n["source"], 0) + 1
    for k, v in sorted(by.items(), key=lambda x: -x[1]):
        print(f"   {v:3}건  {k}")
    if not news:
        print("수집 0건 - 중단")
        return 1

    # 2. 본문 확보
    line("2. 본문 확보 (RSS 요약 vs 링크 크롤링)")
    desc_avg = sum(len(n["description"]) for n in news) / len(news)
    print(f"RSS 가 주는 요약 평균 길이 : {desc_avg:.0f}자  -> 요약 재료로는 부족")
    print("링크를 따라가 본문 수집 중...")
    r = enrich(news)
    ok_items = [n for n in news if n["has_full_text"]]
    body_avg = (sum(len(n["content"]) for n in ok_items) / len(ok_items)) if ok_items else 0
    print(f"본문 성공 {r['ok']}건 / 실패 {r['fail']}건  (성공률 {r['ok']/len(news)*100:.0f}%)")
    print(f"본문 평균 길이 : {body_avg:.0f}자")
    fail_src = {}
    for n in news:
        if not n["has_full_text"]:
            fail_src[n["source"]] = fail_src.get(n["source"], 0) + 1
    if fail_src:
        print("본문 실패 매체:", ", ".join(f"{k}({v})" for k, v in sorted(fail_src.items(), key=lambda x: -x[1])))

    io.open("rss_sample.json", "w", encoding="utf-8").write(
        json.dumps(news[:5], ensure_ascii=False, indent=2))
    print("샘플 JSON 저장: rss_sample.json")

    # 3. 색인
    line("3. 색인 생성")
    rag = NewsRAG()
    print(f"색인 완료: {rag.build(news)}개 문서")

    # 4. 리서치
    line("4. 리서치 - 기사 근거 답변")
    for q in ["오늘 반도체·AI 관련 소식은?", "오늘 경제 주요 뉴스 정리해줘"]:
        res = rag.ask(q, k=5)
        print(f"\n[질문] {q}")
        print(f"[답변] {res['answer']}")
        print("[근거]")
        for s in res["sources"][:3]:
            mark = "본문O" if s["has_full_text"] else "제목만"
            print(f"   [{s['n']}]({mark}) {s['title'][:45]}")
            print(f"        {s['link']}")

    # 5. 요약 3종
    line("5. 요약 3종 비교")
    for style, info in STYLE_INFO.items():
        res = rag.summarize("오늘의 주요 뉴스", style=style)
        print(f"\n{'-'*72}\n[{info['name']}] ({style}) - {info['설명']} / 기사 {len(res['sources'])}건\n{'-'*72}")
        print(res["newsletter"])

    # 6. 환각 방지
    line("6. 환각 방지")
    res = rag.ask("2030년 화성 이주 계획의 총예산은?", k=3)
    print(f"[답변] {res['answer']}")

    line(f"검증 완료 ({time.time()-t0:.0f}초)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

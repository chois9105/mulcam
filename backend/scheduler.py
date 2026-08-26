"""
자동 실행 스케줄러

두 가지 일을 정해진 시각에 돌린다.

    1. 뉴스 모으기   기사 수집 -> 본문 크롤링 -> 색인
                     1~2분 걸리는 일이라 미리 해둔다.
                     그래야 사용자가 요청 버튼을 눌렀을 때 몇 초 만에 답이 나온다.

    2. 정기 생성     승인할 때 주기를 정해둔 요청을 30분마다 확인하고,
                     도래한 건을 새로 만들어 n8n 발송 대기에 올린다.

서버가 켜져 있는 동안만 돈다. FastAPI 안에서 함께 돈다.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Dict, List

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# 뉴스 수집 시각 (기본: 매일 07:00, 12:00, 18:00)
COLLECT_HOURS = os.getenv("COLLECT_HOURS", "7,12,18")
DAY_MAP = {"mon": "mon", "tue": "tue", "wed": "wed",
           "thu": "thu", "fri": "fri", "sat": "sat", "sun": "sun"}

_scheduler: BackgroundScheduler | None = None
_last_collect: Dict = {"at": None, "collected": 0, "full_text": 0, "error": None}


# ------------------------------------------------------------------
# 작업 1 — 뉴스 모으기
# ------------------------------------------------------------------
def collect_news(limit_per_feed: int = 12) -> Dict:
    """기사 수집 -> 본문 크롤링 -> 색인. 스케줄러와 API 둘 다 쓴다."""
    global _last_collect
    try:
        import store
        from article_fetcher import enrich
        from rag_engine import NewsRAG
        from rss_collector import RSSCollector

        logger.info("뉴스 수집 시작")
        collector = RSSCollector()
        news = collector.fetch_all_news(limit_per_feed=limit_per_feed)
        if not news:
            _last_collect = {"at": datetime.now().isoformat(), "collected": 0,
                             "full_text": 0, "error": "새로 수집된 기사가 없습니다."}
            return _last_collect

        full = enrich(news)
        indexed = NewsRAG().build(news)
        saved = store.save_articles(news)

        _last_collect = {
            "at": datetime.now().isoformat(),
            "collected": len(news),
            "indexed": indexed,
            "full_text": full["ok"],
            "saved_to_db": saved,
            "error": None,
        }
        logger.info("뉴스 수집 완료: %s건", len(news))
        return _last_collect
    except Exception as e:
        logger.error("뉴스 수집 실패: %s", e)
        _last_collect = {"at": datetime.now().isoformat(), "collected": 0,
                         "full_text": 0, "error": str(e)[:200]}
        return _last_collect


def last_collect() -> Dict:
    return _last_collect


# ------------------------------------------------------------------
# 작업 2 — 정기 생성
# ------------------------------------------------------------------
def run_scheduled_dispatch() -> List[Dict]:
    """
    도래한 승인 요청으로 최신 뉴스를 만들고 n8n 발송 대기에 올린다.
    실제 이메일 발송은 하지 않는다.
    """
    from newsletter_service import service

    results = []
    now = datetime.now()
    for sch in service.due_schedules(now):
        if not sch.get("is_active"):
            continue
        try:
            draft = service.prepare_dispatch(sch)
            service.mark_schedule_run(sch["draft_id"], sch["frequency"], now)
            results.append({
                "schedule_id": sch["schedule_id"],
                "new_draft_id": draft["id"],
                "score": draft["score"],
                "status": "발송 대기",
            })
            logger.info("정기 생성 완료: %s", draft["id"])
        except Exception as e:
            results.append({"schedule_id": sch["schedule_id"], "error": str(e)[:200]})
            logger.error("정기 생성 실패: %s", e)
    return results


# ------------------------------------------------------------------
# 스케줄러 시작 / 종료
# ------------------------------------------------------------------
def start() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is not None:
        return _scheduler

    _scheduler = BackgroundScheduler(timezone="Asia/Seoul")

    # 뉴스 모으기
    _scheduler.add_job(
        collect_news, CronTrigger(hour=COLLECT_HOURS, minute=0),
        id="collect_news", replace_existing=True,
    )

    # n8n 조회 주기와 같은 30분 간격으로 도래한 정기 건을 생성한다.
    _scheduler.add_job(
        run_scheduled_dispatch, CronTrigger(minute="*/30"),
        id="scheduled_dispatch", replace_existing=True,
    )

    _scheduler.start()
    logger.info("스케줄러 시작 - 수집 %s시, 정기 생성 30분 간격", COLLECT_HOURS)
    return _scheduler


def stop():
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None


def status() -> Dict:
    if _scheduler is None:
        return {"running": False, "jobs": []}
    return {
        "running": True,
        "timezone": "Asia/Seoul",
        "jobs": [
            {
                "id": j.id,
                "다음_실행": j.next_run_time.strftime("%Y-%m-%d %H:%M") if j.next_run_time else None,
            }
            for j in _scheduler.get_jobs()
        ],
        "last_collect": _last_collect,
    }

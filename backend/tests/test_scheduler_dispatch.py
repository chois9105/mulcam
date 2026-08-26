from datetime import datetime, timedelta
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import newsletter_service as ns
import scheduler


def test_supported_frequency_intervals():
    now = datetime(2026, 8, 26, 10, 0)

    assert ns.NewsletterService._next_run(now, "every_30_minutes") == now + timedelta(minutes=30)
    assert ns.NewsletterService._next_run(now, "hourly") == now + timedelta(hours=1)
    assert ns.NewsletterService._next_run(now, "daily") == now + timedelta(days=1)
    assert ns.NewsletterService._next_run(now, "weekly") == now + timedelta(days=7)


def test_scheduler_prepares_due_dispatch_without_sending(monkeypatch):
    schedule = {
        "schedule_id": 1,
        "draft_id": "draft_parent",
        "request_text": "AI 뉴스",
        "frequency": "hourly",
        "is_active": True,
    }
    calls = []

    monkeypatch.setattr(ns.service, "due_schedules", lambda now: [schedule])
    monkeypatch.setattr(ns.service, "prepare_dispatch", lambda item: {
        "id": "draft_child", "score": 91, "status": "approved"
    })
    monkeypatch.setattr(
        ns.service,
        "mark_schedule_run",
        lambda draft_id, frequency, now: calls.append((draft_id, frequency)),
    )

    result = scheduler.run_scheduled_dispatch()

    assert result[0]["new_draft_id"] == "draft_child"
    assert result[0]["status"] == "발송 대기"
    assert calls == [("draft_parent", "hourly")]

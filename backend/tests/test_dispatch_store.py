from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import store


def test_pending_dispatches_include_initial_and_scheduled_approvals(monkeypatch):
    monkeypatch.setattr(store, "_detect", lambda: "memory")
    monkeypatch.setattr(store, "_memory", {
        "initial": {
            "id": "initial", "status": "approved",
            "approved_at": "2026.08.27 10:00",
            "user_email": "contact@1435.co.kr", "sent_at": None,
        },
        "scheduled": {
            "id": "scheduled", "status": "approved",
            "approved_at": "2026.08.27 10:30",
            "user_email": "contact@1435.co.kr", "sent_at": None,
            "schedule_parent_code": "initial",
        },
        "not_approved": {
            "id": "not_approved", "status": "pending",
            "user_email": None, "sent_at": None,
        },
        "already_sent": {
            "id": "already_sent", "status": "sent",
            "approved_at": "2026.08.27 09:00",
            "user_email": "contact@1435.co.kr",
            "sent_at": "2026.08.27 09:01",
        },
    })

    pending = store.list_pending_dispatches()

    assert [item["id"] for item in pending] == ["initial", "scheduled"]

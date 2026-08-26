import sys
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import api_v1


class FakeService:
    def __init__(self):
        self.draft = {
            "id": "draft_1", "title": "제목", "status": "pending",
            "markdown": "본문", "article_html": "<p>본문</p>",
            "sources": [], "score": 90,
        }
        self.calls = []

    def create(self, request_text):
        self.calls.append(("create", request_text))
        return self.draft.copy()

    def revise(self, draft_id, direction):
        self.calls.append(("revise", draft_id, direction))
        return self.draft.copy()

    def approve(self, draft_id, frequency, approved_template):
        self.calls.append(("approve", draft_id, frequency, approved_template))
        return {**self.draft, "status": "approved", "frequency": frequency}

    def get(self, draft_id):
        return self.draft.copy() if draft_id == "draft_1" else None

    def list_drafts(self, status="all"):
        return [self.draft.copy()]

    def schedules(self):
        return []

    def pending_dispatches(self):
        return [{**self.draft, "id": "draft_dispatch",
                 "status": "approved", "schedule_parent_code": "draft_1"}]

    def record_dispatch_result(self, draft_id, sent, error):
        self.calls.append(("dispatch_result", draft_id, sent, error))
        return {**self.draft, "id": draft_id,
                "status": "sent" if sent else "approved"}

    def storage_mode(self):
        return {"mode": "memory", "persistent": False}

    @staticmethod
    def to_response(draft):
        return draft


def client_with_fakes(monkeypatch):
    service = FakeService()
    monkeypatch.setattr(api_v1, "service", service)
    monkeypatch.setattr(api_v1.scheduler, "status", lambda: {"running": False})
    monkeypatch.setattr(api_v1.scheduler, "collect_news",
                        lambda limit_per_feed: {"collected": limit_per_feed})
    app = FastAPI()
    app.include_router(api_v1.router)
    return TestClient(app), service


def test_primary_newsletter_endpoints_are_connected(monkeypatch):
    client, service = client_with_fakes(monkeypatch)

    created = client.post("/api/newsletter/request",
                          json={"request_text": "생성형 AI"})
    revised = client.post("/api/drafts/draft_1/revise",
                          json={"direction": "더 간결하게"})
    approved = client.post("/api/drafts/draft_1/approve", json={
        "frequency": "weekly", "approved_template": "<article>승인본</article>"
    })
    listed = client.get("/api/drafts")
    detail = client.get("/api/drafts/draft_1")
    status = client.get("/api/status")
    collected = client.post("/api/news/collect?limit_per_feed=3")
    pending_dispatches = client.get("/api/dispatches/pending")
    dispatch_result = client.post("/api/dispatches/draft_dispatch/result", json={
        "sent": True
    })

    assert [r.status_code for r in
            (created, revised, approved, listed, detail, status, collected,
             pending_dispatches, dispatch_result)] == [200] * 9
    assert ("create", "생성형 AI") in service.calls
    assert ("revise", "draft_1", "더 간결하게") in service.calls
    assert ("approve", "draft_1", "weekly", "<article>승인본</article>") in service.calls
    assert approved.json()["status"] == "approved"
    assert collected.json()["collected"] == 3
    assert pending_dispatches.json()["count"] == 1
    assert ("dispatch_result", "draft_dispatch", True, None) in service.calls


def test_approve_is_idempotent_for_an_already_approved_draft(monkeypatch):
    client, service = client_with_fakes(monkeypatch)
    service.draft.update({"status": "approved", "frequency": "daily"})

    response = client.post("/api/drafts/draft_1/approve", json={
        "frequency": "daily", "approved_template": "<article>승인본</article>"
    })

    assert response.status_code == 200
    assert response.json()["already_approved"] is True
    assert not any(call[0] == "approve" for call in service.calls)


def test_graph_endpoints_are_connected_without_explicit_thread_id(monkeypatch):
    client, _ = client_with_fakes(monkeypatch)
    graph = SimpleNamespace(
        start=lambda request_text, thread_id: {
            "waiting": True, "request_text": request_text, "thread_id": thread_id,
        },
        resume=lambda thread_id, action, feedback, frequency: {
            "thread_id": thread_id, "action": action, "frequency": frequency,
        },
        state_of=lambda thread_id: {"thread_id": thread_id, "status": "reviewed"},
    )
    monkeypatch.setitem(sys.modules, "graph_pipeline", graph)

    started = client.post("/api/graph/start", json={"request_text": "AI 뉴스"})
    thread_id = started.json()["thread_id"]
    resumed = client.post(f"/api/graph/{thread_id}/resume",
                          json={"action": "approve", "frequency": "daily"})
    state = client.get(f"/api/graph/{thread_id}")

    assert started.status_code == 200
    assert thread_id.startswith("thread_")
    assert resumed.status_code == 200
    assert state.status_code == 200


def test_advise_endpoint_is_connected(monkeypatch):
    client, _ = client_with_fakes(monkeypatch)
    advisor = SimpleNamespace(advise=lambda keyword: SimpleNamespace(
        questions=["어떤 관점인가요?"], suggestions=[f"{keyword} 주요 뉴스"], note="안내"
    ))
    monkeypatch.setitem(sys.modules, "advisor", advisor)

    response = client.post("/api/newsletter/advise", json={"keyword": "로봇"})

    assert response.status_code == 200
    assert response.json()["keyword"] == "로봇"

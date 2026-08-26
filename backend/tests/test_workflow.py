from datetime import datetime
from pathlib import Path
import sys
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import newsletter_service as ns


class FakeReview:
    score = 90
    passed = True
    feedback = []


class FakeReviewer:
    def review(self, markdown, sources):
        return FakeReview()

    def audit_report(self, review, loop_count):
        return {"readability": 90, "fact_accuracy": 90, "coherence": 90,
                "reviewer_comment": "ok", "loop_count": f"{loop_count}회"}

    def to_grade(self, score):
        return "A 양호"


class FakePolisher:
    def polish(self, markdown):
        return markdown


class FakeRag:
    llm = object()

    def search_multi(self, keywords, k):
        raise RuntimeError("색인이 없습니다")


def test_create_uses_live_search_without_prebuilt_index(monkeypatch):
    service = ns.NewsletterService()
    service._analyzer = SimpleNamespace(
        analyze=lambda text: SimpleNamespace(
            keywords=["AI"], article_count=1, title_hint="AI 뉴스"
        ),
        to_query=lambda plan: "AI",
    )
    service._rag = FakeRag()
    service._reviewer = FakeReviewer()
    service._polisher = FakePolisher()

    researched = [{"title": "기사", "link": "https://example.com/1",
                   "source": "example", "content": "근거", "live": True}]
    monkeypatch.setattr(ns.live_search, "search", lambda *args, **kwargs: researched)
    monkeypatch.setattr(ns.live_search, "merge_with_indexed",
                        lambda indexed, live, limit: live)
    monkeypatch.setattr(ns.compose, "summarize_items", lambda *args, **kwargs: {
        "newsletter": "**기사** [1]\n근거 요약",
        "sources": ns.compose.items_to_sources(researched),
    })
    saved = {}
    monkeypatch.setattr(ns.store, "save_draft", lambda draft: saved.update(draft))

    draft = service.create("AI")

    assert draft["pipeline"] == ["keyword_search", "research", "newsletter", "review"]
    assert saved["_research_items"] == researched


def test_revise_reuses_stored_research_without_search(monkeypatch):
    service = ns.NewsletterService()
    service._rag = FakeRag()
    service._reviewer = FakeReviewer()
    service._polisher = FakePolisher()
    research = [{"title": "원래 기사", "link": "https://example.com/1",
                 "source": "example", "content": "원래 근거"}]
    original = {
        "id": "draft_1", "title": "원래 제목", "status": "pending",
        "markdown": "**원래 기사** [1]\n원래 답변", "sources": [],
        "revision_count": 0, "_request_text": "AI", "_query": "AI",
        "_article_count": 1, "_research_items": research,
    }
    monkeypatch.setattr(ns.store, "get_draft", lambda draft_id: original)
    monkeypatch.setattr(ns.store, "save_draft", lambda draft: None)
    monkeypatch.setattr(ns.live_search, "search",
                        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("재검색됨")))

    class Chain:
        def invoke(self, values):
            assert "원래 근거" in values["context"]
            assert values["previous"] == original["markdown"]
            return SimpleNamespace(content="**원래 기사** [1]\n수정된 답변")

    class Prompt:
        def __or__(self, llm):
            return Chain()

    monkeypatch.setattr(ns, "REVISE_PROMPT", Prompt())
    updated = service.revise("draft_1", "더 간결하게")

    assert updated["revision_count"] == 1
    assert updated["_research_items"] == research


def test_approve_persists_fixed_user_template_and_frequency(monkeypatch):
    service = ns.NewsletterService()
    draft = {"id": "draft_1", "title": "제목", "article_html": "<p>초안</p>",
             "_request_text": "AI", "status": "pending"}
    persisted = {}
    monkeypatch.setattr(ns.store, "get_draft", lambda draft_id: draft.copy())
    monkeypatch.setattr(ns.store, "mark_approved",
                        lambda draft_id, frequency, **kwargs: persisted.update(
                            draft_id=draft_id, frequency=frequency, **kwargs))
    monkeypatch.setattr(ns.store, "mark_sent", lambda *args, **kwargs: None)
    monkeypatch.setattr(ns, "send_draft", lambda draft, to: {"dry_run": True, "to": [to]})

    approved = service.approve("draft_1", "weekly", "<article>승인본</article>")

    assert persisted["frequency"] == "weekly"
    assert persisted["user_email"] == "contact@1435.co.kr"
    assert persisted["approved_template"] == "<article>승인본</article>"
    assert persisted["next_run_at"] > datetime.now()
    assert approved["user_email"] == "contact@1435.co.kr"

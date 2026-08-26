import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import database


def test_missing_draft_columns_detects_all_new_orm_fields():
    missing = database.missing_draft_columns({"id", "draft_code", "title"})

    assert missing == [
        "research_items", "user_email", "approved_template",
        "next_run_at", "last_scheduled_at",
    ]


def test_ensure_schema_adds_missing_columns_and_verifies(monkeypatch):
    existing = ["id", "draft_code"]
    completed = existing + list(database.DRAFT_COLUMN_MIGRATIONS)
    inspections = iter([existing, completed])
    executed = []

    class Inspector:
        def get_columns(self, table):
            assert table == "drafts"
            return [{"name": name} for name in next(inspections)]

    class Connection:
        def execute(self, statement):
            executed.append(str(statement))

    class Begin:
        def __enter__(self):
            return Connection()

        def __exit__(self, exc_type, exc, tb):
            return False

    class Engine:
        def begin(self):
            return Begin()

    fake_engine = Engine()
    monkeypatch.setattr(database, "engine", fake_engine)
    monkeypatch.setattr(database, "inspect", lambda engine: Inspector())
    monkeypatch.setattr(database.Base.metadata, "create_all", lambda engine: None)

    result = database.ensure_schema()

    assert result["ok"] is True
    assert result["applied"] == list(database.DRAFT_COLUMN_MIGRATIONS)
    assert len(executed) == len(database.DRAFT_COLUMN_MIGRATIONS)
    assert all("ALTER TABLE `drafts` ADD COLUMN" in sql for sql in executed)


def test_application_startup_migrates_connected_database(monkeypatch):
    import main
    import store

    calls = []
    monkeypatch.setattr(database, "check_connection", lambda: {"ok": True})
    monkeypatch.setattr(database, "ensure_schema",
                        lambda: calls.append("ensure_schema") or {
                            "ok": True, "applied": ["research_items"], "missing": []
                        })
    monkeypatch.setattr(store, "reset_mode", lambda: calls.append("reset_mode"))
    monkeypatch.setattr(store, "mode", lambda: {
        "mode": "mysql", "note": "MySQL 에 저장됩니다."
    })
    monkeypatch.setenv("SCHEDULER_ENABLED", "false")

    main._on_startup()

    assert calls == ["ensure_schema", "reset_mode"]

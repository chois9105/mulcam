"""
MySQL 연결

접속 정보는 .env 에서 읽는다. 코드에 비밀번호를 적지 않는다.

    MYSQL_HOST=127.0.0.1
    MYSQL_PORT=3306
    MYSQL_USER=root
    MYSQL_PASSWORD=본인_비밀번호
    MYSQL_DB=newsletter

팀원마다 각자 로컬 MySQL 을 쓰기로 했으므로, .env 만 각자 채우면 된다.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from urllib.parse import quote_plus

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker

load_dotenv()

HOST = os.getenv("MYSQL_HOST", "127.0.0.1")
PORT = int(os.getenv("MYSQL_PORT", "3306"))
USER = os.getenv("MYSQL_USER", "root")
PASSWORD = os.getenv("MYSQL_PASSWORD", "")
DB_NAME = os.getenv("MYSQL_DB", "newsletter")

Base = declarative_base()


def _url(db: str | None) -> str:
    """접속 주소를 만든다. db 가 None 이면 데이터베이스를 지정하지 않는다."""
    # 비밀번호에 @ 나 # 같은 기호가 있어도 깨지지 않도록 인코딩한다
    pw = quote_plus(PASSWORD)
    tail = f"/{db}" if db else ""
    return f"mysql+pymysql://{USER}:{pw}@{HOST}:{PORT}{tail}?charset=utf8mb4"


# 실제로 쓸 엔진 (newsletter DB 에 연결)
engine = create_engine(
    _url(DB_NAME),
    pool_pre_ping=True,     # 끊어진 연결을 자동으로 되살린다
    pool_recycle=3600,
    echo=False,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@contextmanager
def session_scope():
    """with 로 열고 닫는 세션. 오류가 나면 되돌린다."""
    s = SessionLocal()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


def get_session():
    """FastAPI 의존성 주입용"""
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def create_database_if_missing() -> bool:
    """
    newsletter 데이터베이스가 없으면 만든다.
    (DB 자체가 없으면 연결이 안 되므로, DB 를 지정하지 않고 접속해서 만든다)
    """
    root = create_engine(_url(None), pool_pre_ping=True)
    with root.connect() as conn:
        conn.execute(text(
            f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}` "
            "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
        ))
        conn.commit()
    root.dispose()
    return True


def check_connection() -> dict:
    """접속이 되는지 확인한다. 문제가 있으면 원인을 알려준다."""
    if not PASSWORD:
        return {
            "ok": False,
            "reason": "MYSQL_PASSWORD 가 비어 있습니다. backend/.env 에 입력하세요.",
        }
    try:
        with engine.connect() as conn:
            ver = conn.execute(text("SELECT VERSION()")).scalar()
        return {"ok": True, "host": HOST, "port": PORT, "db": DB_NAME, "version": ver}
    except Exception as e:
        msg = str(e)
        if "Access denied" in msg:
            hint = "계정 또는 비밀번호가 틀립니다."
        elif "Can't connect" in msg or "Connection refused" in msg:
            hint = "MySQL 서비스가 꺼져 있습니다. MYSQL84 서비스를 시작하세요."
        elif "Unknown database" in msg:
            hint = f"'{DB_NAME}' 데이터베이스가 없습니다. python init_db.py 를 실행하세요."
        else:
            hint = "접속 정보를 확인하세요."
        return {"ok": False, "reason": hint, "detail": msg[:200]}

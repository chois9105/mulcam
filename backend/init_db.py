"""
데이터베이스 초기화

하는 일
    1. newsletter 데이터베이스가 없으면 만든다
    2. 테이블 2개(articles, drafts)를 만든다

실행
    python init_db.py

미리 준비할 것
    - MySQL 서비스 실행 (윈도우 서비스 MYSQL84)
    - backend/.env 에 MYSQL_PASSWORD 입력

출력 형태와 검수 지침은 DB 에 넣지 않는다.
각각 한 종류뿐이라 templates_seed.py 의 상수로 두는 편이 간단하다.
"""

from __future__ import annotations

import sys

from sqlalchemy import inspect, text

from database import (
    Base, DB_NAME, check_connection, create_database_if_missing, engine, session_scope,
)
from db_models import Article, Draft  # noqa: F401  (import 해야 테이블이 등록된다)


def step(msg: str):
    print(f"\n>>> {msg}")


def main() -> int:
    # 1. 접속 확인 --------------------------------------------------
    step("1. MySQL 접속 확인")
    from database import PASSWORD
    if not PASSWORD:
        print("  [중단] MYSQL_PASSWORD 가 비어 있습니다.")
        print("         backend/.env 파일을 열어 MySQL 비밀번호를 넣어주세요.")
        return 1

    # 2. 데이터베이스 생성 -------------------------------------------
    step(f"2. 데이터베이스 '{DB_NAME}' 준비")
    try:
        create_database_if_missing()
        print("  준비 완료")
    except Exception as e:
        msg = str(e)
        print(f"  [실패] {msg[:200]}")
        if "Access denied" in msg:
            print("         계정 또는 비밀번호가 틀립니다. .env 를 확인하세요.")
        elif "Can't connect" in msg:
            print("         MySQL 서비스가 꺼져 있습니다.")
            print("         관리자 권한 PowerShell 에서:  Start-Service MYSQL84")
        return 1

    info = check_connection()
    if not info["ok"]:
        print(f"  [실패] {info['reason']}")
        return 1
    print(f"  MySQL {info['version']} @ {info['host']}:{info['port']}/{info['db']}")

    # 3. 테이블 생성 -------------------------------------------------
    step("3. 테이블 생성")
    Base.metadata.create_all(engine)
    # create_all은 기존 테이블에 새 컬럼을 추가하지 않으므로 가벼운 인라인
    # 마이그레이션을 수행한다. 이미 컬럼이 있으면 건너뛴다.
    draft_columns = {c["name"] for c in inspect(engine).get_columns("drafts")}
    migrations = {
        "research_items": "ADD COLUMN research_items JSON NULL",
        "user_email": "ADD COLUMN user_email VARCHAR(255) NULL",
        "approved_template": "ADD COLUMN approved_template MEDIUMTEXT NULL",
        "next_run_at": "ADD COLUMN next_run_at DATETIME NULL",
        "last_scheduled_at": "ADD COLUMN last_scheduled_at DATETIME NULL",
    }
    with engine.begin() as conn:
        for name, ddl in migrations.items():
            if name not in draft_columns:
                conn.execute(text(f"ALTER TABLE drafts {ddl}"))
    tables = sorted(inspect(engine).get_table_names())
    print(f"  테이블 {len(tables)}개")
    for t in tables:
        print(f"    - {t}")

    # 4. 확인 -------------------------------------------------------
    step("4. 확인")
    with session_scope() as s:
        print(f"  기사   : {s.query(Article).count()}건")
        print(f"  요약본 : {s.query(Draft).count()}건")

    print("\n초기화 완료.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

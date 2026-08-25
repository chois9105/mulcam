"""
데이터베이스 초기화

하는 일
    1. newsletter 데이터베이스가 없으면 만든다
    2. 테이블 10개를 만든다 (이미 있으면 건너뛴다)
    3. 기본 템플릿 3종(a/b/c)과 기본 검수 지침을 넣는다

실행
    python init_db.py

미리 준비할 것
    - MySQL 서비스 실행 (윈도우 서비스 MYSQL84)
    - backend/.env 에 MYSQL_PASSWORD 입력
"""

from __future__ import annotations

import sys

from sqlalchemy import inspect

from database import Base, DB_NAME, check_connection, create_database_if_missing, engine, session_scope
from db_models import (  # noqa: F401  (import 해야 테이블이 등록된다)
    Article, AuditReport, DispatchLog, Draft, DraftSource,
    Keyword, ReviewGuideline, Schedule, Subscriber, Template,
)
from templates_seed import DEFAULT_GUIDELINE, DEFAULT_TEMPLATES


def step(msg: str):
    print(f"\n>>> {msg}")


def main() -> int:
    # 1. 접속 확인 --------------------------------------------------
    step("1. MySQL 접속 확인")
    from database import PASSWORD
    if not PASSWORD:
        print("  [중단] MYSQL_PASSWORD 가 비어 있습니다.")
        print("         backend/.env 파일을 열어 MySQL 비밀번호를 넣어주세요.")
        print("         예) MYSQL_PASSWORD=내비밀번호")
        return 1

    # 2. 데이터베이스 생성 -------------------------------------------
    step(f"2. 데이터베이스 '{DB_NAME}' 준비")
    try:
        create_database_if_missing()
        print(f"  준비 완료")
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
    tables = sorted(inspect(engine).get_table_names())
    print(f"  테이블 {len(tables)}개")
    for t in tables:
        print(f"    - {t}")

    # 4. 기본 템플릿 넣기 --------------------------------------------
    step("4. 기본 템플릿 3종 넣기")
    with session_scope() as s:
        for t in DEFAULT_TEMPLATES:
            found = s.query(Template).filter_by(code=t["code"]).first()
            if found:
                print(f"    [{t['code']}] {t['name']} - 이미 있음 (건너뜀)")
                continue
            s.add(Template(**t, is_default=True))
            print(f"    [{t['code']}] {t['name']} - 추가")

    # 5. 기본 검수 지침 넣기 ------------------------------------------
    step("5. 기본 검수 지침 넣기")
    with session_scope() as s:
        found = s.query(ReviewGuideline).filter_by(name=DEFAULT_GUIDELINE["name"]).first()
        if found:
            print(f"    '{DEFAULT_GUIDELINE['name']}' - 이미 있음 (건너뜀)")
        else:
            s.add(ReviewGuideline(**DEFAULT_GUIDELINE, is_active=True))
            print(f"    '{DEFAULT_GUIDELINE['name']}' - 추가")

    # 6. 결과 확인 ---------------------------------------------------
    step("6. 확인")
    with session_scope() as s:
        print(f"  템플릿      : {s.query(Template).count()}건")
        print(f"  검수 지침   : {s.query(ReviewGuideline).count()}건")
        print(f"  구독자      : {s.query(Subscriber).count()}건")
        print(f"  기사        : {s.query(Article).count()}건")
        print(f"  초안        : {s.query(Draft).count()}건")

    print("\n초기화 완료.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

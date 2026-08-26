"""
drafts 테이블에 빠진 컬럼을 채운다.

SQLAlchemy 의 create_all() 은 없는 테이블만 만들고,
이미 있는 테이블에 컬럼을 더하지는 못한다.
그래서 모델에 컬럼이 추가되면 이 스크립트를 한 번 돌려야 한다.

실행:  python migrate_add_columns.py
"""

from sqlalchemy import inspect, text

import db_models  # noqa: F401  (모델 등록)
from database import Base, engine

# 컬럼 종류 -> MySQL 타입
TYPE_MAP = {
    "MEDIUMTEXT": "MEDIUMTEXT",
    "TEXT": "TEXT",
    "JSON": "JSON",
    "DATETIME": "DATETIME NULL",
    "INTEGER": "INT",
    "BOOLEAN": "TINYINT(1)",
}


def sql_type(col) -> str:
    t = str(col.type).upper()
    if t.startswith("VARCHAR"):
        return t
    if t.startswith("CHAR"):
        return t
    for key, val in TYPE_MAP.items():
        if key in t:
            return val
    return "TEXT"


def main() -> int:
    insp = inspect(engine)
    total_added = 0

    for table_name, table in Base.metadata.tables.items():
        if table_name not in insp.get_table_names():
            print(f"[{table_name}] 테이블이 없습니다. init_db.py 를 먼저 실행하세요.")
            continue

        have = {c["name"] for c in insp.get_columns(table_name)}
        missing = [c for c in table.columns if c.name not in have]

        if not missing:
            print(f"[{table_name}] 빠진 컬럼 없음")
            continue

        print(f"[{table_name}] 컬럼 {len(missing)}개 추가")
        with engine.connect() as conn:
            for col in missing:
                ddl = f"ALTER TABLE `{table_name}` ADD COLUMN `{col.name}` {sql_type(col)}"
                try:
                    conn.execute(text(ddl))
                    conn.commit()
                    print(f"    + {col.name}  ({sql_type(col)})")
                    total_added += 1
                except Exception as e:
                    print(f"    ! {col.name} 실패: {str(e)[:120]}")

    print(f"\n완료. 컬럼 {total_added}개 추가.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

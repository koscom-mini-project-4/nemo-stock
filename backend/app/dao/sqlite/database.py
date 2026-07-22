"""SQLAlchemy 엔진/세션 팩토리."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from app.dao.sqlite.models import Base


def make_engine(database_url: str):
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    return create_engine(database_url, connect_args=connect_args)


def init_db(engine) -> None:
    Base.metadata.create_all(engine)
    _add_missing_columns(engine)


def _add_missing_columns(engine) -> None:
    """`create_all()`은 없는 테이블만 새로 만들 뿐, 이미 존재하는 테이블에 ORM 모델이 새로
    추가한 컬럼은 반영해주지 않는다(예: backtest_results.daily_runs_json). Alembic을 도입하기
    전까지는 ORM 모델에는 있지만 실제 테이블에는 없는 컬럼을 ALTER TABLE ADD COLUMN으로
    보정하는 가벼운 방식으로 기존 로컬 DB(nemo_stock.db)와의 호환성을 유지한다.
    """
    inspector = inspect(engine)
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if not inspector.has_table(table.name):
                continue
            existing_columns = {col["name"] for col in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in existing_columns:
                    continue
                col_type = column.type.compile(engine.dialect)
                conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {col_type}'))


def make_session_factory(engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


@contextmanager
def session_scope(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

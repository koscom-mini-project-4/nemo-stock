"""AI 추출 변수 캐시. JSON / SQLite 두 방식 모두 지원(동일 인터페이스).

"기존에 만들어 둔 캐시가 없으면 빠르게 AI로 변수 추출" 요구사항을 위해, url_hash 단위로
조회/저장하고 미스일 때만 AI를 호출하는 패턴(app/ai/scoring_cache.py의 캐시 패턴과 동일한 사상).
"""

from __future__ import annotations

import json
import sqlite3
from abc import ABC, abstractmethod
from pathlib import Path

from config import JSON_CACHE_PATH, SQLITE_CACHE_PATH
from schemas import ClusterInfo, NewsVariables, TickerImpact


class CacheStore(ABC):
    @abstractmethod
    def get_variables(self, url_hash: str) -> NewsVariables | None: ...

    @abstractmethod
    def set_variables(self, variables: NewsVariables) -> None: ...

    def bulk_set_variables(self, items: list[NewsVariables]) -> None:
        for item in items:
            self.set_variables(item)

    @abstractmethod
    def all_variables(self) -> list[NewsVariables]: ...

    @abstractmethod
    def get_clusters(self) -> list[ClusterInfo]: ...

    @abstractmethod
    def save_clusters(self, clusters: list[ClusterInfo]) -> None: ...


def _impacts_to_list(impacts: list[TickerImpact]) -> list[dict]:
    return [
        {"ticker": t.ticker, "direction": t.direction, "grade": t.grade, "reason": t.reason} for t in impacts
    ]


def _impacts_from_raw(raw: object) -> list[TickerImpact]:
    """ticker_impacts를 복원한다. 구 스키마(related_tickers = 문자열 배열)도 읽어준다."""
    if not raw:
        return []
    impacts: list[TickerImpact] = []
    for item in raw:
        if isinstance(item, str):  # 구 스키마: 종목명만 있고 종목별 판단이 없음
            impacts.append(TickerImpact(ticker=item, direction=None, grade=None))
        else:
            impacts.append(
                TickerImpact(
                    ticker=item["ticker"],
                    direction=item.get("direction"),
                    grade=item.get("grade"),
                    reason=item.get("reason", ""),
                )
            )
    return impacts


def _variables_to_dict(v: NewsVariables) -> dict:
    return {
        "url_hash": v.url_hash,
        "published_at": v.published_at,
        "depth1": v.depth1,
        "depth2": v.depth2,
        "depth3": v.depth3,
        "scope_type": v.scope_type,
        "ticker_impacts": _impacts_to_list(v.ticker_impacts),
        "related_industries": v.related_industries,
        "impact_grade": v.impact_grade,
        "time_horizon": v.time_horizon,
        "confidence": v.confidence,
        "reasoning": v.reasoning,
        "cluster_id": v.cluster_id,
        "model": v.model,
        "prompt_version": v.prompt_version,
    }


def _variables_from_dict(d: dict) -> NewsVariables:
    return NewsVariables(
        url_hash=d["url_hash"],
        published_at=d["published_at"],
        depth1=d.get("depth1", ""),
        depth2=d.get("depth2", "중립"),
        depth3=d.get("depth3", ""),
        scope_type=d.get("scope_type", "시장전체"),
        ticker_impacts=_impacts_from_raw(d.get("ticker_impacts") or d.get("related_tickers")),
        related_industries=d.get("related_industries", []),
        impact_grade=d.get("impact_grade", 5),
        time_horizon=d.get("time_horizon", "단기"),
        confidence=d.get("confidence", "보통"),
        reasoning=d.get("reasoning", ""),
        cluster_id=d.get("cluster_id"),
        model=d.get("model", ""),
        prompt_version=d.get("prompt_version", ""),
    )


def _cluster_to_dict(c: ClusterInfo) -> dict:
    return {
        "cluster_id": c.cluster_id,
        "representative_url_hash": c.representative_url_hash,
        "representative_title": c.representative_title,
        "centroid": c.centroid,
        "member_url_hashes": c.member_url_hashes,
        "related_tickers": c.related_tickers,
        "related_industries": c.related_industries,
        "first_published_at": c.first_published_at,
    }


def _cluster_from_dict(d: dict) -> ClusterInfo:
    return ClusterInfo(
        cluster_id=d["cluster_id"],
        representative_url_hash=d["representative_url_hash"],
        representative_title=d["representative_title"],
        centroid=d["centroid"],
        member_url_hashes=d["member_url_hashes"],
        related_tickers=d.get("related_tickers", []),
        related_industries=d.get("related_industries", []),
        first_published_at=d["first_published_at"],
    )


class JSONCacheStore(CacheStore):
    def __init__(self, path: Path = JSON_CACHE_PATH) -> None:
        self._path = path
        if self._path.exists():
            with open(self._path, encoding="utf-8") as f:
                raw = json.load(f)
        else:
            raw = {"variables": {}, "clusters": []}
        self._variables: dict[str, dict] = raw.get("variables", {})
        self._clusters: list[dict] = raw.get("clusters", [])

    def _flush(self) -> None:
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump({"variables": self._variables, "clusters": self._clusters}, f, ensure_ascii=False, indent=2)

    def get_variables(self, url_hash: str) -> NewsVariables | None:
        raw = self._variables.get(url_hash)
        return _variables_from_dict(raw) if raw else None

    def set_variables(self, variables: NewsVariables) -> None:
        self._variables[variables.url_hash] = _variables_to_dict(variables)
        self._flush()

    def bulk_set_variables(self, items: list[NewsVariables]) -> None:
        for item in items:
            self._variables[item.url_hash] = _variables_to_dict(item)
        self._flush()

    def all_variables(self) -> list[NewsVariables]:
        return [_variables_from_dict(v) for v in self._variables.values()]

    def get_clusters(self) -> list[ClusterInfo]:
        return [_cluster_from_dict(c) for c in self._clusters]

    def save_clusters(self, clusters: list[ClusterInfo]) -> None:
        self._clusters = [_cluster_to_dict(c) for c in clusters]
        self._flush()


class SQLiteCacheStore(CacheStore):
    def __init__(self, path: Path = SQLITE_CACHE_PATH) -> None:
        self._path = path
        self._conn = sqlite3.connect(str(path))
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS news_variables (
                url_hash TEXT PRIMARY KEY,
                published_at TEXT NOT NULL,
                depth1 TEXT,
                depth2 TEXT,
                depth3 TEXT,
                scope_type TEXT,
                ticker_impacts_json TEXT NOT NULL,
                related_industries_json TEXT NOT NULL,
                impact_grade INTEGER,
                time_horizon TEXT,
                confidence TEXT,
                reasoning TEXT,
                cluster_id TEXT,
                model TEXT,
                prompt_version TEXT
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS clusters (
                cluster_id TEXT PRIMARY KEY,
                representative_url_hash TEXT NOT NULL,
                representative_title TEXT NOT NULL,
                centroid_json TEXT NOT NULL,
                member_url_hashes_json TEXT NOT NULL,
                related_tickers_json TEXT NOT NULL,
                related_industries_json TEXT NOT NULL,
                first_published_at TEXT NOT NULL
            )
            """
        )
        self._migrate_ticker_impacts()
        self._conn.commit()

    def _migrate_ticker_impacts(self) -> None:
        """구 스키마(related_tickers_json = 종목명 배열)로 만들어진 DB를 종목별 영향 스키마로 옮긴다.

        구 데이터에는 종목별 방향/등급 판단이 없으므로 값은 그대로 옮기고(_impacts_from_raw가
        direction/grade=None으로 복원), 재채점은 PROMPT_VERSION 상향으로 유도한다.
        """
        columns = {row[1] for row in self._conn.execute("PRAGMA table_info(news_variables)")}
        if "ticker_impacts_json" in columns or "related_tickers_json" not in columns:
            return
        self._conn.execute("ALTER TABLE news_variables ADD COLUMN ticker_impacts_json TEXT NOT NULL DEFAULT '[]'")
        self._conn.execute("UPDATE news_variables SET ticker_impacts_json = related_tickers_json")

    _VARIABLE_COLUMNS = (
        "url_hash, published_at, depth1, depth2, depth3, scope_type, ticker_impacts_json, "
        "related_industries_json, impact_grade, time_horizon, confidence, reasoning, "
        "cluster_id, model, prompt_version"
    )

    def _row_to_variables(self, row: tuple) -> NewsVariables:
        return NewsVariables(
            url_hash=row[0],
            published_at=row[1],
            depth1=row[2] or "",
            depth2=row[3] or "중립",
            depth3=row[4] or "",
            scope_type=row[5] or "시장전체",
            ticker_impacts=_impacts_from_raw(json.loads(row[6])),
            related_industries=json.loads(row[7]),
            impact_grade=row[8] if row[8] is not None else 5,
            time_horizon=row[9] or "단기",
            confidence=row[10] or "보통",
            reasoning=row[11] or "",
            cluster_id=row[12],
            model=row[13] or "",
            prompt_version=row[14] or "",
        )

    def get_variables(self, url_hash: str) -> NewsVariables | None:
        row = self._conn.execute(
            f"SELECT {self._VARIABLE_COLUMNS} FROM news_variables WHERE url_hash = ?", (url_hash,)
        ).fetchone()
        return self._row_to_variables(row) if row is not None else None

    def set_variables(self, variables: NewsVariables) -> None:
        self._conn.execute(
            """
            INSERT INTO news_variables
                (url_hash, published_at, depth1, depth2, depth3, scope_type, ticker_impacts_json,
                 related_industries_json, impact_grade, time_horizon, confidence, reasoning,
                 cluster_id, model, prompt_version)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(url_hash) DO UPDATE SET
                published_at=excluded.published_at, depth1=excluded.depth1, depth2=excluded.depth2,
                depth3=excluded.depth3, scope_type=excluded.scope_type,
                ticker_impacts_json=excluded.ticker_impacts_json,
                related_industries_json=excluded.related_industries_json,
                impact_grade=excluded.impact_grade, time_horizon=excluded.time_horizon,
                confidence=excluded.confidence, reasoning=excluded.reasoning,
                cluster_id=excluded.cluster_id, model=excluded.model, prompt_version=excluded.prompt_version
            """,
            (
                variables.url_hash,
                variables.published_at,
                variables.depth1,
                variables.depth2,
                variables.depth3,
                variables.scope_type,
                json.dumps(_impacts_to_list(variables.ticker_impacts), ensure_ascii=False),
                json.dumps(variables.related_industries, ensure_ascii=False),
                variables.impact_grade,
                variables.time_horizon,
                variables.confidence,
                variables.reasoning,
                variables.cluster_id,
                variables.model,
                variables.prompt_version,
            ),
        )
        self._conn.commit()

    def bulk_set_variables(self, items: list[NewsVariables]) -> None:
        for item in items:
            self.set_variables(item)

    def all_variables(self) -> list[NewsVariables]:
        rows = self._conn.execute(f"SELECT {self._VARIABLE_COLUMNS} FROM news_variables").fetchall()
        return [self._row_to_variables(r) for r in rows]

    def get_clusters(self) -> list[ClusterInfo]:
        rows = self._conn.execute(
            "SELECT cluster_id, representative_url_hash, representative_title, centroid_json, "
            "member_url_hashes_json, related_tickers_json, related_industries_json, first_published_at "
            "FROM clusters"
        ).fetchall()
        return [
            ClusterInfo(
                cluster_id=r[0],
                representative_url_hash=r[1],
                representative_title=r[2],
                centroid=json.loads(r[3]),
                member_url_hashes=json.loads(r[4]),
                related_tickers=json.loads(r[5]),
                related_industries=json.loads(r[6]),
                first_published_at=r[7],
            )
            for r in rows
        ]

    def save_clusters(self, clusters: list[ClusterInfo]) -> None:
        self._conn.execute("DELETE FROM clusters")
        for c in clusters:
            self._conn.execute(
                """
                INSERT INTO clusters
                    (cluster_id, representative_url_hash, representative_title, centroid_json,
                     member_url_hashes_json, related_tickers_json, related_industries_json, first_published_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    c.cluster_id,
                    c.representative_url_hash,
                    c.representative_title,
                    json.dumps(c.centroid),
                    json.dumps(c.member_url_hashes),
                    json.dumps(c.related_tickers, ensure_ascii=False),
                    json.dumps(c.related_industries, ensure_ascii=False),
                    c.first_published_at,
                ),
            )
        self._conn.commit()


def get_store(kind: str) -> CacheStore:
    if kind == "json":
        return JSONCacheStore()
    if kind == "sqlite":
        return SQLiteCacheStore()
    raise ValueError(f"unknown store kind: {kind!r} (use 'json' or 'sqlite')")

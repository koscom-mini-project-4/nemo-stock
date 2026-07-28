"""SQLite 저장소.

클러스터는 별도 테이블로 두고 first_seen_at 에 인덱스를 건다.
-> "원하는 날짜 사이의 클러스터 개수"는 COUNT + BETWEEN 한 줄로 끝난다.
뉴스는 cluster_id 로 클러스터를 참조하므로 클러스터별 뉴스 개수도 GROUP BY 로 나온다.
"""
import sqlite3
from datetime import datetime, timedelta

from .config import DB_PATH, CLUSTER_RETENTION_DAYS, DATE_FMT

SCHEMA = """
CREATE TABLE IF NOT EXISTS clusters (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    representative_title TEXT NOT NULL,
    first_seen_at        TEXT NOT NULL,   -- 'YYYY-MM-DD HH:MM:SS'
    strength             REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_clusters_first_seen ON clusters(first_seen_at);

CREATE TABLE IF NOT EXISTS news (
    url_hash     TEXT PRIMARY KEY,
    url          TEXT,
    title        TEXT,
    published_at TEXT NOT NULL,
    cluster_id   INTEGER NOT NULL REFERENCES clusters(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_news_cluster    ON news(cluster_id);
CREATE INDEX IF NOT EXISTS idx_news_published  ON news(published_at);

-- 한 뉴스에서 종목/섹터/거시지표 조합이 여러 개면 여러 행이 된다.
CREATE TABLE IF NOT EXISTS classifications (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    url_hash             TEXT NOT NULL,
    title                TEXT,             -- 입력으로 들어온 원본 뉴스 제목
    stock                TEXT,
    sector               TEXT,
    macro                TEXT,
    date                 TEXT NOT NULL,
    strength             REAL NOT NULL,
    cluster_id           INTEGER NOT NULL REFERENCES clusters(id) ON DELETE CASCADE,
    representative_title TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cls_hash    ON classifications(url_hash);
CREATE INDEX IF NOT EXISTS idx_cls_cluster ON classifications(cluster_id);
CREATE INDEX IF NOT EXISTS idx_cls_date    ON classifications(date);

-- 그룹 테이블: classifications 를 키 기준으로 흩뿌린 것.
--   A = 종목명 키, B = 섹터명 키, C = 거시지표명 키
-- 한 뉴스가 (삼성전자,정보기술,null) + (삼성전자,null,금융) 처럼 두 행으로 나와도
-- A 입장에서는 "삼성전자 뉴스 1건"이므로 UNIQUE(url_hash, key) 로 한 번만 넣는다.
CREATE TABLE IF NOT EXISTS group_a (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    key        TEXT NOT NULL,                    -- 종목명
    date       TEXT NOT NULL,
    cluster_id INTEGER NOT NULL REFERENCES clusters(id) ON DELETE CASCADE,
    strength   REAL NOT NULL,
    url_hash   TEXT NOT NULL,
    UNIQUE(url_hash, key)
);
CREATE INDEX IF NOT EXISTS idx_a_key_date ON group_a(key, date);
CREATE INDEX IF NOT EXISTS idx_a_cluster  ON group_a(cluster_id);

CREATE TABLE IF NOT EXISTS group_b (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    key        TEXT NOT NULL,                    -- 섹터명
    date       TEXT NOT NULL,
    cluster_id INTEGER NOT NULL REFERENCES clusters(id) ON DELETE CASCADE,
    strength   REAL NOT NULL,
    url_hash   TEXT NOT NULL,
    UNIQUE(url_hash, key)
);
CREATE INDEX IF NOT EXISTS idx_b_key_date ON group_b(key, date);
CREATE INDEX IF NOT EXISTS idx_b_cluster  ON group_b(cluster_id);

CREATE TABLE IF NOT EXISTS group_c (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    key        TEXT NOT NULL,                    -- 거시지표명
    date       TEXT NOT NULL,
    cluster_id INTEGER NOT NULL REFERENCES clusters(id) ON DELETE CASCADE,
    strength   REAL NOT NULL,
    url_hash   TEXT NOT NULL,
    UNIQUE(url_hash, key)
);
CREATE INDEX IF NOT EXISTS idx_c_key_date ON group_c(key, date);
CREATE INDEX IF NOT EXISTS idx_c_cluster  ON group_c(cluster_id);

-- 크롤링 원장. news 와 별개로 두는 이유:
--   news 는 클러스터가 보관기간(7일)을 넘기면 같이 삭제된다. 그걸 중복 판정 기준으로
--   쓰면 지워진 기사를 다시 크롤링하고 다시 AI에 넣게 된다(= 돈이 두 번 나간다).
--   crawled 는 훨씬 오래(기본 90일) 남겨서 "이미 본 URL"을 기억한다.
-- classified=0 인 행은 크롤링은 됐는데 아직 분류 안 된 기사 -> 다음 갱신 때 이어서 처리.
CREATE TABLE IF NOT EXISTS crawled (
    url_hash     TEXT PRIMARY KEY,
    url          TEXT,
    title        TEXT,
    content      TEXT,
    summary      TEXT,
    published_at TEXT,
    crawled_at   TEXT NOT NULL,
    classified   INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_crawled_at    ON crawled(crawled_at);
CREATE INDEX IF NOT EXISTS idx_crawled_flag  ON crawled(classified);

-- 마지막 갱신 시각 등 잡다한 상태값
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""

# 그룹 -> (테이블, classifications 의 어느 컬럼에서 키를 뽑는지, 지표 이름)
GROUPS = {
    "A": ("group_a", "종목",   "종목 영향 지표"),
    "B": ("group_b", "섹터",   "섹터 영향 지표"),
    "C": ("group_c", "거시지표", "거시 영향 지표"),
}


def connect(path: str = None) -> sqlite3.Connection:
    conn = sqlite3.connect(path or DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    _migrate(conn)
    return conn


def _migrate(conn) -> None:
    """예전 DB에 없던 컬럼을 채워 넣는다."""
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(classifications)")}
    if "title" not in cols:
        conn.execute("ALTER TABLE classifications ADD COLUMN title TEXT")
        conn.execute("UPDATE classifications SET title = "
                     "(SELECT n.title FROM news n WHERE n.url_hash = classifications.url_hash)")
        conn.commit()

    # 그룹 테이블이 아직 안 채워진 예전 DB면 classifications 로부터 한 번 채운다.
    has_cls = conn.execute("SELECT 1 FROM classifications LIMIT 1").fetchone()
    has_grp = conn.execute("SELECT 1 FROM group_a LIMIT 1").fetchone() or \
              conn.execute("SELECT 1 FROM group_b LIMIT 1").fetchone() or \
              conn.execute("SELECT 1 FROM group_c LIMIT 1").fetchone()
    if has_cls and not has_grp:
        rebuild_groups(conn)


# ---------------------------------------------------------------- 기준 시각

def latest_timestamp(conn, fallback: str) -> str:
    """시스템이 알고 있는 가장 최근 시각. 보관기간/후보범위 계산의 기준."""
    row = conn.execute("SELECT MAX(first_seen_at) AS t FROM clusters").fetchone()
    newest = row["t"] if row and row["t"] else None
    if newest and newest > fallback:
        return newest
    return fallback


def _shift_days(ts: str, days: int) -> str:
    return (datetime.strptime(ts, DATE_FMT) - timedelta(days=days)).strftime(DATE_FMT)


# ---------------------------------------------------------------- 클러스터

def recent_clusters(conn, now: str, days: int = CLUSTER_RETENTION_DAYS) -> list:
    """프롬프트에 넣을 후보 클러스터 (최근 days 일)."""
    cutoff = _shift_days(now, days)
    rows = conn.execute(
        "SELECT id, representative_title, first_seen_at, strength "
        "FROM clusters WHERE first_seen_at >= ? ORDER BY first_seen_at DESC",
        (cutoff,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_cluster(conn, cluster_id: int):
    row = conn.execute("SELECT * FROM clusters WHERE id = ?", (cluster_id,)).fetchone()
    return dict(row) if row else None


def create_cluster(conn, title: str, first_seen_at: str, strength: float) -> int:
    cur = conn.execute(
        "INSERT INTO clusters (representative_title, first_seen_at, strength) VALUES (?, ?, ?)",
        (title, first_seen_at, strength),
    )
    conn.commit()
    return cur.lastrowid


def purge_old_clusters(conn, now: str, days: int = CLUSTER_RETENTION_DAYS) -> int:
    """보관기간이 지난 클러스터와 그에 딸린 뉴스/분류결과를 삭제."""
    cutoff = _shift_days(now, days)
    ids = [r["id"] for r in conn.execute(
        "SELECT id FROM clusters WHERE first_seen_at < ?", (cutoff,)).fetchall()]
    if not ids:
        return 0
    marks = ",".join("?" * len(ids))
    for table, _, _ in GROUPS.values():
        conn.execute(f"DELETE FROM {table} WHERE cluster_id IN ({marks})", ids)
    conn.execute(f"DELETE FROM classifications WHERE cluster_id IN ({marks})", ids)
    conn.execute(f"DELETE FROM news           WHERE cluster_id IN ({marks})", ids)
    conn.execute(f"DELETE FROM clusters       WHERE id         IN ({marks})", ids)
    conn.commit()
    return len(ids)


# ---------------------------------------------------------------- 뉴스 / 분류

def news_exists(conn, url_hash: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM news WHERE url_hash = ?", (url_hash,)).fetchone() is not None


def save_news(conn, news: dict, cluster_id: int) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO news (url_hash, url, title, published_at, cluster_id) "
        "VALUES (?, ?, ?, ?, ?)",
        (news["url_hash"], news.get("url"), news.get("title"),
         news["published_at"], cluster_id),
    )
    conn.commit()


def save_classifications(conn, url_hash: str, records: list) -> None:
    conn.executemany(
        "INSERT INTO classifications "
        "(url_hash, title, stock, sector, macro, date, strength, cluster_id, representative_title) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [(url_hash, r["제목"], r["종목"], r["섹터"], r["거시지표"], r["날짜"],
          r["스트렝스"], r["클러스터id"], r["대표제목"]) for r in records],
    )
    save_group_rows(conn, url_hash, records)
    conn.commit()


def save_group_rows(conn, url_hash: str, records: list) -> None:
    """분류 결과를 A/B/C 그룹 테이블로 흩뿌린다.

    한 레코드에 종목·섹터·거시지표가 셋 다 있으면 세 테이블 모두에,
    둘만 있으면 두 테이블에 각각 들어간다. cluster_id 는 어느 쪽에도 저장한다.
    """
    for table, field, _ in GROUPS.values():
        rows = [(r[field], r["날짜"], r["클러스터id"], r["스트렝스"], url_hash)
                for r in records if r.get(field)]
        if rows:
            conn.executemany(
                f"INSERT OR IGNORE INTO {table} (key, date, cluster_id, strength, url_hash) "
                "VALUES (?, ?, ?, ?, ?)", rows)


def rebuild_groups(conn) -> dict:
    """이미 쌓여 있는 classifications 로부터 A/B/C 테이블을 다시 만든다."""
    counts = {}
    for g, (table, field, _) in GROUPS.items():
        conn.execute(f"DELETE FROM {table}")
        col = {"종목": "stock", "섹터": "sector", "거시지표": "macro"}[field]
        conn.execute(
            f"INSERT OR IGNORE INTO {table} (key, date, cluster_id, strength, url_hash) "
            f"SELECT {col}, date, cluster_id, strength, url_hash FROM classifications "
            f"WHERE {col} IS NOT NULL AND {col} <> ''")
        counts[g] = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    conn.commit()
    return counts


def group_cluster_rows(conn, group: str, key: str, start: str, end: str) -> list:
    """A/B/C 테이블에서 key + 기간으로 뽑아 cluster_id 로 GROUP BY.

    각 클러스터의 뉴스 count, 최초 발생 날짜, strength 를 돌려준다.
    """
    table, _, _ = GROUPS[group]
    rows = conn.execute(
        f"SELECT g.cluster_id, COUNT(*) AS count, "
        f"       c.first_seen_at, c.strength, c.representative_title "
        f"FROM {table} g JOIN clusters c ON c.id = g.cluster_id "
        f"WHERE g.key = ? AND g.date BETWEEN ? AND ? "
        f"GROUP BY g.cluster_id ORDER BY c.first_seen_at",
        (key, start, end),
    ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------- 크롤링 원장

def seen_hashes(conn) -> set:
    """이미 크롤링한 url_hash 전체. 중복 수집을 막는 기준."""
    return {r[0] for r in conn.execute("SELECT url_hash FROM crawled")}


def mark_crawled(conn, items: list) -> int:
    """크롤링한 기사를 원장에 기록. 이미 있으면 무시한다."""
    if not items:
        return 0
    now = datetime.now().strftime(DATE_FMT)
    cur = conn.executemany(
        "INSERT OR IGNORE INTO crawled "
        "(url_hash, url, title, content, summary, published_at, crawled_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        [(i["url_hash"], i.get("url"), i.get("title"), i.get("content"),
          i.get("summary"), i.get("published_at"), now) for i in items],
    )
    conn.commit()
    return cur.rowcount


def pending_news(conn, limit: int = None) -> list:
    """크롤링은 됐는데 아직 분류 안 된 기사. 오래된 것부터."""
    sql = ("SELECT url_hash, url, title, content, summary, published_at "
           "FROM crawled WHERE classified = 0 ORDER BY published_at")
    if limit:
        sql += f" LIMIT {int(limit)}"
    return [dict(r) for r in conn.execute(sql)]


def mark_classified(conn, url_hashes: list) -> None:
    if not url_hashes:
        return
    conn.executemany("UPDATE crawled SET classified = 1 WHERE url_hash = ?",
                     [(h,) for h in url_hashes])
    conn.commit()


def purge_crawled(conn, days: int) -> int:
    """오래된 크롤링 원장 정리. 해시만 남는 게 아니라 본문도 지운다."""
    cutoff = _shift_days(datetime.now().strftime(DATE_FMT), days)
    cur = conn.execute("DELETE FROM crawled WHERE crawled_at < ?", (cutoff,))
    conn.commit()
    return cur.rowcount


def get_meta(conn, key: str, default=None):
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_meta(conn, key: str, value: str) -> None:
    conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
                 (key, str(value)))
    conn.commit()


# ---------------------------------------------------------------- 집계

def overview(conn) -> dict:
    """DB 전체 요약 통계."""
    one = lambda q: conn.execute(q).fetchone()[0]
    span = conn.execute(
        "SELECT MIN(first_seen_at) a, MAX(first_seen_at) b FROM clusters").fetchone()
    return {
        "뉴스": one("SELECT COUNT(*) FROM news"),
        "클러스터": one("SELECT COUNT(*) FROM clusters"),
        "분류행": one("SELECT COUNT(*) FROM classifications"),
        "기간": [span["a"], span["b"]],
        "strength분포": [(r["strength"], r["c"]) for r in conn.execute(
            "SELECT strength, COUNT(*) c FROM clusters GROUP BY strength ORDER BY strength")],
        "그룹행수": {g: one(f"SELECT COUNT(*) FROM {t}") for g, (t, _, _) in GROUPS.items()},
    }


def key_counts(conn, group: str, limit: int = 10) -> list:
    """그룹 테이블에서 많이 등장한 키 순으로."""
    table, _, _ = GROUPS[group]
    return [(r["key"], r["c"]) for r in conn.execute(
        f"SELECT key, COUNT(*) c FROM {table} GROUP BY key ORDER BY c DESC, key LIMIT ?",
        (limit,)).fetchall()]


def group_keys(conn, group: str, start: str, end: str) -> list:
    """기간 내에 데이터가 있는 키 목록."""
    table, _, _ = GROUPS[group]
    return [r[0] for r in conn.execute(
        f"SELECT DISTINCT key FROM {table} WHERE date BETWEEN ? AND ? ORDER BY key",
        (start, end)).fetchall()]


def get_classifications(conn, url_hash: str) -> list:
    rows = conn.execute(
        "SELECT title, stock, sector, macro, date, strength, cluster_id, representative_title "
        "FROM classifications WHERE url_hash = ? ORDER BY id", (url_hash,)).fetchall()
    return [{
        "종목": r["stock"], "섹터": r["sector"], "거시지표": r["macro"],
        "날짜": r["date"], "스트렝스": r["strength"],
        "클러스터id": r["cluster_id"], "대표제목": r["representative_title"],
        "제목": r["title"],
    } for r in rows]


# ---------------------------------------------------------------- 집계

def count_clusters(conn, start: str, end: str) -> int:
    """start~end 사이에 '최초 발생'한 클러스터 개수."""
    return conn.execute(
        "SELECT COUNT(*) FROM clusters WHERE first_seen_at BETWEEN ? AND ?",
        (start, end),
    ).fetchone()[0]


def cluster_stats(conn, start: str, end: str) -> list:
    """기간 내 클러스터 목록 + 각 클러스터에 묶인 뉴스 개수."""
    rows = conn.execute(
        "SELECT c.id, c.representative_title, c.first_seen_at, c.strength, "
        "       COUNT(n.url_hash) AS news_count "
        "FROM clusters c LEFT JOIN news n ON n.cluster_id = c.id "
        "WHERE c.first_seen_at BETWEEN ? AND ? "
        "GROUP BY c.id ORDER BY news_count DESC, c.first_seen_at DESC",
        (start, end),
    ).fetchall()
    return [dict(r) for r in rows]

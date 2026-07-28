"""뉴스 -> AI 분류 -> 검증 -> SQLite 저장."""
from . import db
from .classifier import call_ai
from .config import SECTORS, MACROS, STRENGTHS, CLUSTER_RETENTION_DAYS


def _snap_strength(value) -> float:
    """AI가 허용값 밖의 숫자를 주면 가장 가까운 허용값으로 붙인다."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return 0.0
    return min(STRENGTHS, key=lambda s: abs(s - v))


def _pick(value, allowed):
    """허용 목록에 없으면 null."""
    if isinstance(value, str):
        v = value.strip()
        if v in allowed:
            return v
    return None


def _clean_stock(value):
    if isinstance(value, str):
        v = value.strip()
        if v and v.lower() not in ("null", "none", "n/a", "없음"):
            return v
    return None


def classify_news(conn, news: dict, purge: bool = True,
                  model: str = None, api_key: str = None) -> list:
    """뉴스 1건을 분류하고 저장. 결과 레코드 리스트를 돌려준다.

    종목/섹터/거시지표 조합이 여러 개면 레코드도 여러 개 나온다.
    """
    url_hash = news["url_hash"]
    published_at = news["published_at"]

    # 이미 처리한 뉴스면 저장된 결과를 그대로 반환 (API 재호출 안 함)
    if db.news_exists(conn, url_hash):
        return db.get_classifications(conn, url_hash)

    now = db.latest_timestamp(conn, published_at)
    if purge:
        db.purge_old_clusters(conn, now, CLUSTER_RETENTION_DAYS)

    candidates = db.recent_clusters(conn, now, CLUSTER_RETENTION_DAYS)
    ai = call_ai(news, candidates, model=model, api_key=api_key)

    strength = _snap_strength(ai.get("strength"))

    # 클러스터 결정 -------------------------------------------------------
    cluster_id = ai.get("cluster_id")
    cluster = db.get_cluster(conn, cluster_id) if isinstance(cluster_id, int) else None

    if cluster:
        # 기존 클러스터에 합류: 같은 사건이므로 클러스터의 강도/대표제목을 따른다.
        cluster_id = cluster["id"]
        rep_title = cluster["representative_title"]
        strength = cluster["strength"]
    else:
        rep_title = (ai.get("representative_title") or "").strip() or news.get("title", "")
        cluster_id = db.create_cluster(conn, rep_title, published_at, strength)

    # 아이템 정리 ---------------------------------------------------------
    items = ai.get("items")
    if not isinstance(items, list) or not items:
        items = [{}]

    records, seen = [], set()
    for it in items:
        it = it if isinstance(it, dict) else {}
        rec = {
            "종목": _clean_stock(it.get("stock")),
            "섹터": _pick(it.get("sector"), SECTORS),
            "거시지표": _pick(it.get("macro"), MACROS),
            "날짜": published_at,
            "스트렝스": strength,
            "클러스터id": cluster_id,
            "대표제목": rep_title,
            "제목": news.get("title"),
        }
        key = (rec["종목"], rec["섹터"], rec["거시지표"])
        if key in seen:
            continue
        seen.add(key)
        records.append(rec)

    # 의미 있는 레코드가 하나라도 있으면 전부 null 인 빈 레코드는 버린다.
    meaningful = [r for r in records
                  if r["종목"] or r["섹터"] or r["거시지표"]]
    records = meaningful or records[:1]

    db.save_news(conn, news, cluster_id)
    db.save_classifications(conn, url_hash, records)
    return records


def classify_many(conn, news_list: list, purge: bool = True, progress=None,
                  model: str = None, api_key: str = None) -> list:
    """뉴스 여러 건. 오래된 것부터 처리해야 클러스터가 제대로 쌓인다."""
    out = []
    ordered = sorted(news_list, key=lambda n: n.get("published_at", ""))
    for i, news in enumerate(ordered, 1):
        out.extend(classify_news(conn, news, purge=purge,
                                 model=model, api_key=api_key))
        if progress:
            progress(i, len(ordered))
    return out

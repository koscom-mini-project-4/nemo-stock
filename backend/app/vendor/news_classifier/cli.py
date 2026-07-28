"""CLI.

  python -m news_classifier.cli classify news.json [-o result.json]
  python -m news_classifier.cli clusters --from 2026-07-21 --to 2026-07-28
  python -m news_classifier.cli count    --from 2026-07-21 --to 2026-07-28
  python -m news_classifier.cli purge
"""
import argparse
import json
import sys
from datetime import datetime

from . import db, indicator
from .config import CLUSTER_RETENTION_DAYS, DATE_FMT
from .pipeline import classify_many

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def _dump(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _day_start(d: str) -> str:
    return f"{d} 00:00:00" if len(d) == 10 else d


def _day_end(d: str) -> str:
    return f"{d} 23:59:59" if len(d) == 10 else d


def cmd_classify(args):
    with open(args.path, encoding="utf-8") as f:
        data = json.load(f)
    news_list = data if isinstance(data, list) else [data]

    def progress(i, total):
        print(f"\r분류 중 {i}/{total}", end="", file=sys.stderr, flush=True)
        if i == total:
            print(file=sys.stderr)

    conn = db.connect()
    results = classify_many(conn, news_list, purge=not args.no_purge,
                            progress=progress if len(news_list) > 1 else None)
    conn.close()

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"뉴스 {len(news_list)}건 -> 레코드 {len(results)}건 저장: {args.out}")
    else:
        _dump(results)


def cmd_clusters(args):
    conn = db.connect()
    rows = db.cluster_stats(conn, _day_start(args.start), _day_end(args.end))
    conn.close()
    _dump({
        "기간": [args.start, args.end],
        "클러스터개수": len(rows),
        "클러스터": [{
            "클러스터id": r["id"],
            "대표제목": r["representative_title"],
            "최초발생날짜": r["first_seen_at"],
            "strength": r["strength"],
            "뉴스개수": r["news_count"],
        } for r in rows],
    })


def cmd_count(args):
    conn = db.connect()
    n = db.count_clusters(conn, _day_start(args.start), _day_end(args.end))
    conn.close()
    _dump({"기간": [args.start, args.end], "클러스터개수": n})


def _print_table(r):
    """지표 하나를 클러스터별 점수 내역 표로 출력."""
    print(f"[{r['지표']}] {r['키']}  ({r['기간'][0][:10]} ~ {r['기간'][1][:10]})")
    if not r["클러스터"]:
        print("  해당 기간에 데이터 없음")
    else:
        print(f"  {'id':>5} {'count':>5} {'stre':>5} {'d':>3} {'점수':>9}  대표제목")
        for c in sorted(r["클러스터"], key=lambda x: x["점수"]):
            print(f"  {c['클러스터id']:>5} {c['count']:>5} {c['strength']:>5} "
                  f"{c['d']:>3} {c['점수']:>9.4f}  {c['대표제목']}")
    print(f"  합계 {r['합계']:.4f} / {r['클러스터수']}개 = 평균 {r['평균']:.4f}  ->  {r['판정']}")
    print()


def cmd_indicator(args):
    conn = db.connect()
    if args.key:
        out = indicator.compute(conn, args.group, args.key, args.start, args.period)
        rows = [out]
    else:
        out = indicator.compute_all_keys(conn, args.group, args.start, args.period)
        rows = out
    conn.close()

    if args.table:
        for r in rows:
            _print_table(r)
    else:
        _dump(out)


def cmd_update(args):
    from .api import NewsTrader
    t = NewsTrader(auto_update=False, crawl_days=args.days,
                   crawl_max_pages=args.pages,
                   max_classify_per_update=args.limit)

    def progress(n, msg):
        print(f"  [{n}] {msg}", file=sys.stderr)

    r = t.update(force=True, progress=progress if args.verbose else None)
    t.close()
    _dump(r)


def cmd_decide(args):
    from .api import NewsTrader
    t = NewsTrader(auto_update=not args.no_update, combine=args.combine,
                   signal_style=args.style, include_zero=not args.drop_zero)
    r = t.decide(stock=args.stock, sector=args.sector, macro=args.macro,
                 start=args.start, period=args.period, detail=args.detail)
    t.close()
    _dump(r)


def cmd_stats(args):
    conn = db.connect()
    o = db.overview(conn)
    print(f"뉴스 {o['뉴스']}건 / 클러스터 {o['클러스터']}개 / 분류행 {o['분류행']}행")
    print(f"기간 {o['기간'][0]} ~ {o['기간'][1]}")

    print("\n[strength 분포]")
    total = sum(c for _, c in o["strength분포"]) or 1
    for s, c in o["strength분포"]:
        print(f"  {s:>5}  {c:>4}건 ({c/total*100:>5.1f}%) {'#' * round(c / total * 50)}")

    print("\n[그룹별 행수]")
    for g, (_, _, name) in db.GROUPS.items():
        print(f"  {g} {name:12} {o['그룹행수'][g]:>5}행")

    for g, (_, _, name) in db.GROUPS.items():
        rows = db.key_counts(conn, g, args.top)
        print(f"\n[{name} — 상위 {len(rows)}개 키]")
        for k, c in rows:
            print(f"  {c:>4}건  {k}")
    conn.close()


def cmd_rebuild(args):
    conn = db.connect()
    counts = db.rebuild_groups(conn)
    conn.close()
    print(f"A(종목) {counts['A']}행 / B(섹터) {counts['B']}행 / C(거시) {counts['C']}행 재생성")


def cmd_purge(args):
    conn = db.connect()
    now = db.latest_timestamp(conn, datetime.now().strftime(DATE_FMT))
    n = db.purge_old_clusters(conn, now, args.days)
    conn.close()
    print(f"기준시각 {now} / 보관 {args.days}일 -> 클러스터 {n}개 삭제")


def main():
    p = argparse.ArgumentParser(prog="news_classifier")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("classify", help="뉴스 JSON 파일을 분류하고 저장")
    c.add_argument("path", help="뉴스 JSON (객체 하나 또는 배열)")
    c.add_argument("-o", "--out", help="결과를 저장할 JSON 경로")
    c.add_argument("--no-purge", action="store_true", help="오래된 클러스터 자동 삭제 안 함")
    c.set_defaults(func=cmd_classify)

    for name, fn, help_ in (("clusters", cmd_clusters, "기간 내 클러스터 목록+뉴스 개수"),
                            ("count", cmd_count, "기간 내 클러스터 개수만")):
        s = sub.add_parser(name, help=help_)
        s.add_argument("--from", dest="start", required=True, help="YYYY-MM-DD")
        s.add_argument("--to", dest="end", required=True, help="YYYY-MM-DD")
        s.set_defaults(func=fn)

    for name, group, key_help in (("stock",  "A", "종목명"),
                                  ("sector", "B", "섹터명"),
                                  ("macro",  "C", "거시지표명")):
        s = sub.add_parser(name, help=f"{db.GROUPS[group][2]} 계산")
        s.add_argument("key", nargs="?", help=f"{key_help} (생략하면 기간 내 전체 키)")
        s.add_argument("--from", dest="start", required=True, help="시작 날짜 YYYY-MM-DD")
        s.add_argument("--period", type=int, required=True, help="보고자 하는 기간(일)")
        s.add_argument("--table", action="store_true",
                       help="JSON 대신 클러스터별 점수 내역을 표로 출력")
        s.set_defaults(func=cmd_indicator, group=group)

    u = sub.add_parser("update", help="크롤링 -> 분류 -> 정리 한 번 돌리기")
    u.add_argument("--days", type=int, default=1, help="며칠치 목록을 훑을지")
    u.add_argument("--pages", type=int, default=5, help="날짜당 최대 목록 페이지")
    u.add_argument("--limit", type=int, default=100, help="한 번에 분류할 최대 건수")
    u.add_argument("-v", "--verbose", action="store_true", help="진행 상황 출력")
    u.set_defaults(func=cmd_update)

    d = sub.add_parser("decide", help="A/B/C 를 합쳐 매매 판단")
    d.add_argument("--stock", help="종목명")
    d.add_argument("--sector", help="섹터명")
    d.add_argument("--macro", help="거시지표명")
    d.add_argument("--from", dest="start", help="시작 날짜 (기본: 오늘)")
    d.add_argument("--period", type=int, help="기간(일). 기본 7")
    d.add_argument("--combine", default="weighted",
                   choices=["weighted", "vote", "stock_first"])
    d.add_argument("--style", default="tfn", choices=["tfn", "trade", "score"])
    d.add_argument("--drop-zero", action="store_true",
                   help="strength=0 클러스터를 분모에서 제외")
    d.add_argument("--detail", action="store_true", help="클러스터 내역까지 출력")
    d.add_argument("--no-update", action="store_true", help="자동 갱신 없이 계산만")
    d.set_defaults(func=cmd_decide)

    t = sub.add_parser("stats", help="DB 전체 통계 (strength 분포, 그룹별 키 순위)")
    t.add_argument("--top", type=int, default=10, help="그룹별로 보여줄 키 개수")
    t.set_defaults(func=cmd_stats)

    r = sub.add_parser("rebuild-groups", help="classifications 로부터 A/B/C 테이블 재생성")
    r.set_defaults(func=cmd_rebuild)

    g = sub.add_parser("purge", help="보관기간 지난 클러스터 삭제")
    g.add_argument("--days", type=int, default=CLUSTER_RETENTION_DAYS)
    g.set_defaults(func=cmd_purge)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

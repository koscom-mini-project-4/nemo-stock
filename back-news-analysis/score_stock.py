#!/usr/bin/env python
"""데모 CLI: 특정 종목의 as-of 시점 뉴스 기반 점수를 계산한다.

사용 예:
  ../backend/.venv/bin/python score_stock.py --company "SK하이닉스" --as-of 2026-07-18 --store sqlite
  ../backend/.venv/bin/python score_stock.py --company "삼성전자" --as-of 2026-07-10 --store json

캐시(build_pool.py로 미리 구축한 AI 풀)에 없는 뉴스는 extract_variables.ensure_variables()가
그 자리에서 즉시 AI로 채운 뒤 캐시에 반영한다.
"""

from __future__ import annotations

import argparse
from datetime import date, datetime

from aggregate import stock_score
from cache_store import get_store
from extract_variables import candidate_url_hashes, ensure_variables
from news_loader import load_news

# 참고용 종목코드 -> 뉴스 검색에 쓸 회사명 매핑 (backend 백테스트에서 검증된 두 종목).
SYMBOL_TO_COMPANY = {"005930": "삼성전자", "000660": "SK하이닉스"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--company", help="뉴스 검색에 쓸 회사명 (예: SK하이닉스)")
    group.add_argument("--symbol", help="종목코드 (예: 000660) — SYMBOL_TO_COMPANY 매핑을 통해 회사명으로 변환")
    parser.add_argument("--as-of", required=True, help="기준일 YYYY-MM-DD")
    parser.add_argument("--store", choices=["json", "sqlite"], default="sqlite")
    parser.add_argument("--lookback-days", type=int, default=14)
    args = parser.parse_args()

    company = args.company or SYMBOL_TO_COMPANY.get(args.symbol)
    if not company:
        raise SystemExit(f"알 수 없는 종목코드: {args.symbol} (SYMBOL_TO_COMPANY에 추가 필요)")

    as_of: date = datetime.strptime(args.as_of, "%Y-%m-%d").date()

    print(f"[score_stock] 뉴스 데이터 로딩...")
    records = load_news()
    records_by_hash = {r.url_hash: r for r in records}

    candidates = candidate_url_hashes(company, records, as_of, lookback_days=args.lookback_days)
    print(f"[score_stock] '{company}' 관련 후보 뉴스 {len(candidates)}건 (최근 {args.lookback_days}일)")

    store = get_store(args.store)
    ensure_variables(candidates, store, records_by_hash)

    clusters = store.get_clusters()
    variables_by_hash = {v.url_hash: v for v in store.all_variables()}
    score = stock_score(company, as_of, clusters, variables_by_hash)

    relevant_clusters = [c for c in clusters if company in c.related_tickers]
    print(f"[score_stock] 관련 이벤트 클러스터 {len(relevant_clusters)}건")
    for c in relevant_clusters:
        print(f"  - {c.cluster_id}: {c.representative_title[:50]} (뉴스 {c.source_count}건, 최초보도 {c.first_published_at})")

    print(f"\n[score_stock] {company} 기준일 {as_of} 최종 점수(정규화, -1~1): {score:.4f}")


if __name__ == "__main__":
    main()

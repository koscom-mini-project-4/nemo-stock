"""터미널에서 직접 시세(일봉/시간봉)를 수집해 sqlite에 저장하는 CLI.

백테스트 실행 시 자동 수집(app/data_ingestion/auto_ingest.py)과 별개로, 미리
데이터를 확보해 두고 싶을 때 수동으로 실행할 수 있다.

사용 예:
    cd backend
    ./.venv/bin/python -m app.cli.ingest_prices --symbol 005930 --start 2026-06-01 --end 2026-07-20
    ./.venv/bin/python -m app.cli.ingest_prices --symbol 005930,000660 --start 2026-06-01 --end 2026-07-20 --skip-intraday
"""

from __future__ import annotations

import argparse
from datetime import date

from app.config import get_settings
from app.dao.sqlite.database import init_db, make_engine, make_session_factory
from app.dao.sqlite.repositories import SqliteIntradayPriceBarRepository, SqlitePriceBarRepository
from app.data_ingestion.naver_price_client import NaverStockChartClient


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="네이버 차트 API로 일봉/시간봉을 수집해 저장한다.")
    parser.add_argument("--symbol", required=True, help="종목코드(6자리). 콤마로 여러 개 지정 가능: 005930,000660")
    parser.add_argument("--start", required=True, type=_parse_date, help="시작일 YYYY-MM-DD")
    parser.add_argument("--end", required=True, type=_parse_date, help="종료일 YYYY-MM-DD")
    parser.add_argument("--skip-intraday", action="store_true", help="시간봉(minute60) 수집을 건너뛴다")
    args = parser.parse_args(argv)

    symbols = [s.strip() for s in args.symbol.split(",") if s.strip()]

    settings = get_settings()
    engine = make_engine(settings.database_url)
    init_db(engine)
    session_factory = make_session_factory(engine)
    price_bar_repo = SqlitePriceBarRepository(session_factory)
    intraday_repo = SqliteIntradayPriceBarRepository(session_factory)

    with NaverStockChartClient() as client:
        for symbol in symbols:
            daily_bars = client.fetch_daily_bars(symbol, args.start, args.end)
            price_bar_repo.save_many(daily_bars)
            print(f"[{symbol}] 일봉 {len(daily_bars)}건 저장")

            if not args.skip_intraday:
                intraday_bars = client.fetch_hourly_bars(symbol, args.start, args.end)
                intraday_repo.save_many(intraday_bars)
                print(f"[{symbol}] 시간봉 {len(intraday_bars)}건 저장 (서버 lookback 한계로 일부 구간만 있을 수 있음)")


if __name__ == "__main__":
    main()

"""한국투자증권(KIS) Open API 기반 주문 실행 어댑터.

엔드포인트/필드명은 공식 GitHub(github.com/koreainvestment/open-trading-api)의 실제
동작하는 예제 코드(examples_llm/domestic_stock/{order_cash,order_rvsecncl,inquire_balance})
를 직접 대조해 확인했다. tr_id는 place_order 검증 중 원본 코드 대조로 정정된 값
(TTTC0011U=매도/TTTC0012U=매수, Toss 스켈레톤 작성 때 추정했던 TTTC0802U 등과 다름)을 쓴다.
주문/정정취소 API의 요청 body와 응답 output은 대문자 키(CANO, ODNO, ...)를 쓰고, 잔고조회
API의 응답 output은 소문자 키(pdno, hldg_qty, ...)를 쓴다 — 원본 예제 코드로 직접 확인한
KIS API 자체의 비일관성이며 어댑터 버그가 아니다. 실제 앱키 발급 전이라 실호출 검증은
못했다(§DESIGN.md 권장대로 사용자가 실제 모의투자 계좌로 재검증 권장).
"""

from __future__ import annotations

import httpx

from app.broker.base import Balance, OrderExecutionProvider, OrderRequest, OrderResult, Position
from app.broker.kis_auth import KISOAuthTokenProvider

ORDER_PATH = "/uapi/domestic-stock/v1/trading/order-cash"
CANCEL_PATH = "/uapi/domestic-stock/v1/trading/order-rvsecncl"
BALANCE_PATH = "/uapi/domestic-stock/v1/trading/inquire-balance"

TR_ORDER_SELL = "TTTC0011U"
TR_ORDER_BUY = "TTTC0012U"
TR_CANCEL = "TTTC0013U"
TR_BALANCE = "TTTC8434R"

ORD_DVSN_LIMIT = "00"
ORD_DVSN_MARKET = "01"
RVSE_CNCL_CANCEL = "02"


class KISOrderExecutionProvider(OrderExecutionProvider):
    def __init__(
        self,
        app_key: str,
        app_secret: str,
        base_url: str,
        account_no: str,
        is_paper: bool = True,
        http_client: httpx.Client | None = None,
        timeout: float = 10.0,
    ) -> None:
        if not app_key or not app_secret:
            raise ValueError(
                "KISOrderExecutionProvider 사용에는 KIS_APP_KEY/KIS_APP_SECRET 설정이 필요합니다."
            )
        if not account_no or "-" not in account_no:
            raise ValueError(
                "KISOrderExecutionProvider 사용에는 '12345678-01' 형식의 KIS_ACCOUNT_NO 설정이 필요합니다."
            )
        self._cano, self._acnt_prdt_cd = account_no.split("-", 1)
        self._base_url = base_url.rstrip("/")
        self._is_paper = is_paper
        self._owns_client = http_client is None
        self._client = http_client or httpx.Client(timeout=timeout)
        self._auth = KISOAuthTokenProvider(app_key, app_secret, base_url, http_client=self._client)
        # order_id -> (거래소코드 KRX_FWDG_ORD_ORGNO, 주문구분 ORD_DVSN). cancel_order가 사용.
        self._order_meta: dict[str, tuple[str, str]] = {}

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def place_order(self, order: OrderRequest) -> OrderResult:
        ord_dvsn = ORD_DVSN_MARKET if order.order_type == "market" else ORD_DVSN_LIMIT
        ord_unpr = "0" if order.order_type == "market" else str(int(order.limit_price or 0))
        body = {
            "CANO": self._cano,
            "ACNT_PRDT_CD": self._acnt_prdt_cd,
            "PDNO": order.symbol,
            "ORD_DVSN": ord_dvsn,
            "ORD_QTY": str(order.qty),
            "ORD_UNPR": ord_unpr,
            "EXCG_ID_DVSN_CD": "KRX",
            "SLL_TYPE": "01" if order.side == "sell" else "",
            "CNDT_PRIC": "",
        }
        tr_id = TR_ORDER_SELL if order.side == "sell" else TR_ORDER_BUY
        response = self._client.post(
            f"{self._base_url}{ORDER_PATH}",
            json=body,
            headers=self._auth.auth_headers(tr_id, self._is_paper),
        )
        response.raise_for_status()
        data = response.json()

        if data.get("rt_cd") != "0":
            return OrderResult(
                order_id="",
                symbol=order.symbol,
                side=order.side,
                order_type=order.order_type,
                qty=order.qty,
                price=0.0,
                status="rejected",
                filled_at=None,
                reason=data.get("msg1"),
            )

        output = data.get("output", {})
        order_id = str(output.get("ODNO", ""))
        self._order_meta[order_id] = (str(output.get("KRX_FWDG_ORD_ORGNO", "")), ord_dvsn)
        # KIS 주문 API는 접수 응답만 주고 실제 체결 확인은 별도 조회(inquire-balance 등)가
        # 필요하므로, Toss 스켈레톤처럼 "filled"로 단정하지 않고 "pending"으로 반환한다.
        return OrderResult(
            order_id=order_id,
            symbol=order.symbol,
            side=order.side,
            order_type=order.order_type,
            qty=order.qty,
            price=order.limit_price or order.ref_price or 0.0,
            status="pending",
            filled_at=None,
        )

    def cancel_order(self, order_id: str) -> None:
        meta = self._order_meta.get(order_id)
        if meta is None:
            raise ValueError(
                f"주문 {order_id}의 원주문 정보(거래소코드/주문구분)를 찾을 수 없습니다. "
                "이 프로세스에서 place_order로 접수한 주문만 취소할 수 있습니다."
            )
        krx_fwdg_ord_orgno, ord_dvsn = meta
        body = {
            "CANO": self._cano,
            "ACNT_PRDT_CD": self._acnt_prdt_cd,
            "KRX_FWDG_ORD_ORGNO": krx_fwdg_ord_orgno,
            "ORGN_ODNO": order_id,
            "ORD_DVSN": ord_dvsn,
            "RVSE_CNCL_DVSN_CD": RVSE_CNCL_CANCEL,
            "ORD_QTY": "0",
            "ORD_UNPR": "0",
            "QTY_ALL_ORD_YN": "Y",
            "EXCG_ID_DVSN_CD": "KRX",
            "CNDT_PRIC": "",
        }
        response = self._client.post(
            f"{self._base_url}{CANCEL_PATH}",
            json=body,
            headers=self._auth.auth_headers(TR_CANCEL, self._is_paper),
        )
        response.raise_for_status()
        data = response.json()
        if data.get("rt_cd") != "0":
            raise RuntimeError(f"KIS 주문 취소 실패: {data.get('msg1')}")

    def _fetch_balance(self) -> dict:
        params = {
            "CANO": self._cano,
            "ACNT_PRDT_CD": self._acnt_prdt_cd,
            "AFHR_FLPR_YN": "N",
            "OFL_YN": "",
            "INQR_DVSN": "02",
            "UNPR_DVSN": "01",
            "FUND_STTL_ICLD_YN": "N",
            "FNCG_AMT_AUTO_RDPT_YN": "N",
            "PRCS_DVSN": "00",
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": "",
        }
        response = self._client.get(
            f"{self._base_url}{BALANCE_PATH}",
            params=params,
            headers=self._auth.auth_headers(TR_BALANCE, self._is_paper),
        )
        response.raise_for_status()
        return response.json()

    def get_balance(self) -> Balance:
        data = self._fetch_balance()
        summary_rows = data.get("output2", [])
        summary = summary_rows[0] if summary_rows else {}
        return Balance(
            cash=float(summary.get("dnca_tot_amt", 0) or 0),
            equity=float(summary.get("tot_evlu_amt", 0) or 0),
        )

    def get_positions(self) -> list[Position]:
        data = self._fetch_balance()
        return [
            Position(
                symbol=row["pdno"],
                qty=int(row.get("hldg_qty", 0) or 0),
                avg_price=float(row.get("pchs_avg_pric", 0) or 0),
            )
            for row in data.get("output1", [])
            if int(row.get("hldg_qty", 0) or 0) > 0
        ]

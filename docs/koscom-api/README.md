# KOSCOM CHECK-API 조사 결과 (2026-07-15)

`https://checkapi.koscom.co.kr` (CHECK API)를 Playwright로 실제 렌더링해 확인한 내용을 정리한다.
원본 페이지는 JS SPA라 `WebFetch`로는 빈 내용만 나오므로, 헤드리스 브라우저로 사이드바를 클릭해
가며 엔드포인트 상세 문서를 직접 캡처했다. 각 엔드포인트의 원문 추출 텍스트는 같은 폴더의
`raw-*.txt`에 그대로 보관한다.

## 서비스 성격

- **CHECK-API는 코스콤 "CHECK 단말"(유료 금융정보 단말) 고객을 위한 REST API 서비스다.**
  data.go.kr/OpenDART처럼 누구나 즉시 발급받는 공개 API가 아니라, CHECK 단말 구독자에게 제공되는
  `고객ID(cust_id)`/`인증키(auth_key)`가 있어야 호출할 수 있다. 미구독자는 "CHECK 단말 사용신청"을
  통해 별도 신청해야 한다.
- 이용요금제에 따라 사용량이 제한되며, **데이터 조회는 1초당 1회를 초과할 수 없다**(공식 문서 명시).
- 보안상 GET/HTTP는 제공하지 않고 **HTTPS + POST만 지원**한다("고객번호/인증키 유출위험으로 http 및
  GET 서비스는 제공하지 않습니다").
- 이번 조사 시점 기준 실제 발급받은 `cust_id`/`auth_key`가 없어 **실제 호출 검증은 하지 못했다**
  (Toss증권 어댑터와 동일한 성격의 제약).

## 공통 요청 방식

```
HOST https://checkapi.koscom.co.kr
POST <경로>
Content-Type: application/x-www-form-urlencoded   (예제 코드가 requests의 data=payload 사용 — JSON 아님)
```

공통 파라미터:

| 이름 | 타입 | 설명 | 필수 |
| --- | --- | --- | --- |
| `cust_id` | String | CHECK 단말 고객번호 10자리 (예: `NS00000001`) | O |
| `auth_key` | String | API 인증키 | O |
| `data_list` | String | 조회할 필드코드 콤마 리스트(예: `F16013,F15001`). 생략 시 전체 Data Set | X |
| `jcode` | String | 조회 대상 종목단축코드 6자리 (예: `005930`) | O(종목 조회 시) |

공통 응답 포맷:

```json
{"success": true, "results": [ /* Data Set 필드들 */ ]}
```
```json
{"success": false, "message": {"errmsg": "access_denied", "desc": "User denied access"}}
```

에러 코드: `access_denied`(고객번호/인증키 무효), `jcode_denied`(종목코드 무효).

## 이번 PoC에서 사용하는 3개 엔드포인트 (KOSPI/거래소 종목 기준)

### 1) 현재가 등 기본정보 — `POST /stock/m001/basic_info`

추가 파라미터 없음(공통 파라미터만). 주요 응답 필드:

| 필드코드 | 설명 |
| --- | --- |
| `F15001` | 현재가 |
| `F15472` | 대비(전일 대비 변동폭) → `전일종가 = F15001 - F15472`로 역산 |
| `F15004` | 등락율 |
| `F15015` | 거래량 |
| `F15023` | 거래대금 |
| `F15009` / `F15010` / `F15011` | 시가 / 고가 / 저가 |

### 2) 호가 정보 — `POST /stock/m001/hoga_info`

추가 파라미터 없음. 매도/매수 1~10단계 호가·잔량을 제공:

| 필드코드 패턴 | 설명 |
| --- | --- |
| `F14501`~`F14510` | 매도호가 1~10단계 |
| `F14531`~`F14540` | 매수호가 1~10단계 |
| `F14511`~`F14520` | 매도호가잔량 1~10단계 |
| `F14541`~`F14550` | 매수호가잔량 1~10단계 |

PoC 어댑터는 1단계(최우선호가)만 사용해 `OrderBookLevel`을 구성한다(필요 시 10단계까지 확장 가능).

### 3) 일별(과거) 정보 — `POST /stock/m001/hist_info`

추가 파라미터: `sdate`, `edate` (YYYYMMDD, 필수). 주요 응답 필드:

| 필드코드 | 설명 |
| --- | --- |
| `F12506` | 입회일(거래일자) |
| `F15009` / `F15010` / `F15011` / `F15001` | 시가 / 고가 / 저가 / 종가(현재가) |
| `F15015` | 거래량 |

`response.results`는 조회 기간의 일별 배열로 추정된다(문서상 단건 예시만 확인, 배열 여부는 실제
호출 검증 전까지 최선 추정).

### (참고) 체결 정보(당일) — `POST /stock/m001/tick_info`

당일 틱 단위 체결 이력(장중 실시간 체결 스트림에 가까움). 이번 PoC 어댑터는 우선 위 3개
엔드포인트만 구현하고, `tick_info`는 원문만 보관(`raw-tick_info.txt`) 후 필요 시 확장한다.

## 구현 결정

- `app/market_data/koscom_adapter.py`에 `KoscomMarketDataProvider(MarketDataProvider)` 구현.
  Toss 어댑터와 마찬가지로 **미검증(실제 자격증명 없음)** 스켈레톤이지만, 이번에는 렌더링된 공식
  문서에서 엔드포인트/필드명을 직접 확인했으므로 Toss보다 신뢰도가 높다.
- 문서에 명시된 **1초당 1회 제한**을 실제로 지키도록 클라이언트에 최소 요청 간격(1.0초) 스로틀을
  넣는다(레이트리밋 위반으로 실제 계약이 정지되는 사고를 막기 위한 보수적 조치).
- 인증 파라미터는 POST 폼 바디(`data=`)로 전송한다(JSON 바디 아님 — 공식 예제 코드 기준).
- `MARKET_DATA_PROVIDER=koscom` 옵션을 추가해 dummy/historical/toss와 동일한 방식으로
  Container가 선택하도록 배선한다. `KOSCOM_CUST_ID`/`KOSCOM_AUTH_KEY`/`KOSCOM_BASE_URL` 설정을
  `.env`에 채우면 사용할 수 있다(실 계약 후).

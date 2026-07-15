# KOSCOM CHECK-API 조사 결과 (2026-07-15, 실계정 검증 완료)

`https://checkapi.koscom.co.kr` (CHECK API)를 Playwright로 실제 렌더링해 확인한 내용을 정리한다.
원본 페이지는 JS SPA라 `WebFetch`로는 빈 내용만 나오므로, 헤드리스 브라우저로 사이드바를 클릭해
가며 문서를 직접 캡처했다.

- **전체 사이트 문서(751개 리프 페이지, 6개 카테고리, 84개 그룹)**는 재사용 가능한 크롤러
  (`crawler/koscom_crawler.js`)로 전수 크롤링했다 — 목록/링크는 [`pages/INDEX.md`](pages/INDEX.md) 참고.
  카테고리별 실패 0건(리프당 최대 2회 시도, 100% 성공).
- 최초 수작업 조사 시점의 원문 추출본(`raw-*.txt`)도 참고용으로 남겨둔다.
- **`app/market_data/koscom_adapter.py`는 2026-07-15 발급받은 실제 `cust_id`/`auth_key`
  (`backend/.env`에 보관, 저장소에는 커밋하지 않음)로 `get_price`/`get_orderbook`/`get_ohlcv`
  3개 메서드 모두 실제 호출까지 검증 완료했다** (삼성전자 005930 / SK하이닉스 000660 기준).
  더 이상 미검증 스켈레톤이 아니다. 라이브 검증 테스트는
  `backend/tests/integration/test_koscom_live.py` (자격증명 없으면 자동 skip).

## 서비스 성격

- **CHECK-API는 코스콤 "CHECK 단말"(유료 금융정보 단말) 고객을 위한 REST API 서비스다.**
  data.go.kr/OpenDART처럼 누구나 즉시 발급받는 공개 API가 아니라, CHECK 단말 구독자에게 제공되는
  `고객ID(cust_id)`/`인증키(auth_key)`가 있어야 호출할 수 있다.
- 이용요금제에 따라 사용량이 제한되며, **데이터 조회는 1초당 1회를 초과할 수 없다**(공식 문서 명시).
  어댑터는 이를 실제로 지키도록 최소 요청 간격(1.0초) 스로틀을 강제한다.
- 보안상 GET/HTTP는 제공하지 않고 **HTTPS + POST만 지원**한다("고객번호/인증키 유출위험으로 http 및
  GET 서비스는 제공하지 않습니다").

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

에러 코드는 엔드포인트마다 다르며 대표적으로 `access_denied`(고객번호/인증키 무효),
`jcode_denied`(종목코드 무효), `date_denied`(날짜 무효) 등이 있다.

## 사이트 전체 구조 (751페이지)

사이드바는 6개 최상위 카테고리 → 그룹 → 리프(개별 엔드포인트 문서) 3단 구조다.

| 카테고리 | 그룹 수 | 페이지 수 | 저장 경로 |
| --- | --- | --- | --- |
| 주식-API | 19 | 243 | `pages/01-stock-api/` |
| 파생-API | 28 | 334 | `pages/02-derivative-api/` |
| 채권-API | 17 | 72 | `pages/03-bond-api/` |
| 해외-API (license) | 11 | 64 | `pages/04-overseas-api/` |
| 뉴스/공시-API | 2 | 7 | `pages/05-news-disclosure-api/` |
| 기타-API | 7 | 31 | `pages/06-etc-api/` |
| **합계** | **84** | **751** | |

전체 카테고리/그룹/페이지 링크 목록은 [`pages/INDEX.md`](pages/INDEX.md)에 있다.

## 이번 PoC 어댑터가 사용하는 3개 엔드포인트 (KOSPI/거래소 종목 기준)

`pages/01-stock-api/거래소 종목/` 그룹 문서에 상세가 있다. 요약:

### 1) 현재가 등 기본정보 — `POST /stock/m001/basic_info`

| 필드코드 | 설명 |
| --- | --- |
| `F15001` | 현재가 |
| `F15472` | 대비(전일 대비 변동폭) → `전일종가 = F15001 - F15472`로 역산 |
| `F15004` | 등락율 |
| `F15015` | 거래량 |
| `F15023` | 거래대금 |
| `F15009` / `F15010` / `F15011` | 시가 / 고가 / 저가 |

### 2) 호가 정보 — `POST /stock/m001/hoga_info`

| 필드코드 패턴 | 설명 |
| --- | --- |
| `F14501`~`F14510` | 매도호가 1~10단계 |
| `F14531`~`F14540` | 매수호가 1~10단계 |
| `F14511`~`F14520` | 매도호가잔량 1~10단계 |
| `F14541`~`F14550` | 매수호가잔량 1~10단계 |

PoC 어댑터는 1단계(최우선호가)만 사용해 `OrderBookLevel`을 구성한다(필요 시 10단계까지 확장 가능).

### 3) 일별(과거) 정보 — `POST /stock/m001/hist_info`

추가 파라미터: `sdate`, `edate` (YYYYMMDD, 필수).

| 필드코드 | 설명 |
| --- | --- |
| `F12506` | 입회일(거래일자) |
| `F15009` / `F15010` / `F15011` / `F15001` | 시가 / 고가 / 저가 / 종가(현재가) |
| `F15015` | 거래량 |

실제 호출로 확인: `results`는 조회 기간의 일별 배열이 맞다(2026-07-15 라이브 검증에서 확인).

## 뉴스/공시-API (`pages/05-news-disclosure-api/`)

향후 뉴스/공시 노드·리포지토리 확장 후보. 7개 페이지, 2개 그룹(뉴스/공시).

- **뉴스**: 일자별 목록(`news_list`), 본문조회(`news_body`) 등 — `cust_id`/`auth_key` + `ndate`(일자)
  + `ncode`(뉴스코드 12자리) 조합으로 특정 뉴스 본문을 조회한다.
- **공시**: 공시 목록/본문 조회 계열 엔드포인트. 상세는 `pages/05-news-disclosure-api/공시/` 참고.

현재 PoC는 이 엔드포인트들을 아직 `NewsRepository`/`DisclosureRepository`에 연결하지 않았다
(data.go.kr/OpenDART 기반 기존 파이프라인과 별개 소스로, 필요 시 추가 통합 가능).

## 구현 결정

- `app/market_data/koscom_adapter.py`에 `KoscomMarketDataProvider(MarketDataProvider)` 구현,
  **실계정으로 검증 완료**.
- 문서에 명시된 **1초당 1회 제한**을 실제로 지키도록 클라이언트에 최소 요청 간격(1.0초) 스로틀을
  넣는다(레이트리밋 위반으로 실제 계약이 정지되는 사고를 막기 위한 보수적 조치).
- 인증 파라미터는 POST 폼 바디(`data=`)로 전송한다(JSON 바디 아님 — 공식 예제 코드 기준).
- `MARKET_DATA_PROVIDER=koscom` 옵션을 추가해 dummy/historical/toss와 동일한 방식으로
  Container가 선택하도록 배선한다. `KOSCOM_CUST_ID`/`KOSCOM_AUTH_KEY`/`KOSCOM_BASE_URL` 설정을
  `.env`에 채우면 사용할 수 있다.

## 크롤러 (`crawler/koscom_crawler.js`)

Node + Playwright 스크립트. checkapi.koscom.co.kr에 로그인 없이 접속해 사이드바를 DOM 쿼리로
탐색(시각적으로 접혀 있어도 구조를 읽어냄) → 카테고리/그룹/리프를 순서대로 클릭 → 각 리프의
`.contents` 영역 텍스트를 추출해 `docs/koscom-api/pages/<category-slug>/<group>/<NN-leaf>.md`로
저장한다. 실패 시 리프당 최대 2회 재시도. 진행 로그는 `pages/_crawl-log.jsonl`에 누적된다.

```bash
cd docs/koscom-api/crawler
npm install playwright   # 최초 1회
node koscom_crawler.js "주식-API" "파생-API" "채권-API" "해외-API (license)" "뉴스/공시-API" "기타-API"
```

카테고리 이름은 사이트 사이드바 텍스트와 정확히 일치해야 한다.

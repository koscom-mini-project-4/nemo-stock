# nemo-stock (네모네모매매) PoC 설계 문서

> 이 문서는 `nemo-stock.md`(사업 기획서)와 `prompt.md`(구현 지시사항)를 바탕으로 PoC의 기술 설계를 정의한다.
> 확정 필요 사항은 사용자 확인을 거쳤으며(아래 "확정된 의사결정" 참조), 이후 구현은 이 문서를 기준으로 진행한다.

## 0. 확정된 의사결정 (2026-07-14 사용자 확인)

| 항목 | 결정 |
| --- | --- |
| AI 자연어 전략 초안 생성 | **포함**. 자연어 입력 → AI가 노드 워크플로(JSON) 초안을 생성. 사용자가 검토/수정 후 저장. |
| 인증 범위 | **단일 계정 JWT 로그인**. 회원가입/다중 사용자 불필요. 계정은 서버 `.env`/부트스트랩으로 1개 생성. |
| Toss증권 실거래 연동 | **더미 구현 + Toss 어댑터 스켈레톤(미검증)**. `MarketDataProvider`/`OrderExecutionProvider` 인터페이스를 정의하고 더미 구현을 기본으로 사용. Toss Open API(OAuth2 Client Credentials, REST: 시세/호가/캔들/잔고/주문) 문서 구조를 반영한 어댑터 클래스는 작성하되, 실제 승인된 키가 없으므로 호출 검증은 하지 않는다. |

## 0-1. 추가 확정 사항 (2026-07-17 사용자 확인)

| 항목 | 결정 |
| --- | --- |
| 캔버스 AI 챗봇 | **통합 채팅창**. 노드 수정 지시("손절 5%로 바꿔줘")와 진행 상황 설명 질문("지금 뭐하는거야?")을 하나의 채팅 UI(`ChatPanel.vue`, 캔버스 우측 "AI 챗봇" 탭)로 처리. 백엔드 `/ai/workflow-chat` 한 엔드포인트가 AI 응답의 `changed` 플래그로 두 경우를 구분(§7.5). |
| 수정 제안 적용 방식 | **미리보기 후 적용**. AI가 그래프 수정을 제안하면 채팅 말풍선 아래 "노드 N개·엣지 N개로 변경" 요약과 적용/취소 버튼만 표시하고, 사용자가 "적용"을 눌러야 캔버스(`flowNodes`/`flowEdges`)에 반영됨. 초안 생성 플로우(§7.2)와 동일하게 자동 저장/활성화하지 않음. |
| 진행 상황 설명 범위 | **그래프 구조 + 최근 실행 결과**. 채팅 요청 시 현재 그래프와 함께 마지막 "테스트 실행" 결과(`status`/`events`/`final_symbols`, 있는 경우)를 프롬프트에 포함. |
| 노드 추가 방식 확장 | 기존 팔레트 클릭 추가에 더해 **드래그 앤 드롭**으로도 추가 가능(`NodePalette.vue` 아이템 `draggable` + 캔버스 `dragover`/`drop`, Vue Flow `screenToFlowCoordinate`로 드롭 좌표를 노드 위치로 사용). |
| AI 전략 생성 진입 장벽 완화 | `AIGenerateView.vue`에 예시 투자 아이디어 템플릿 버튼(4개)을 추가해 클릭 시 텍스트영역에 자동 채움(제출은 사용자가 직접). |
| OpenAI 모델 | `gpt-4o-mini` → **`gpt-5.6-luna`**로 상향(2026-07 출시된 GPT-5.6 3단계 모델군 중 최저가/최속 티어, Sol/Terra보다 한 단계 아래지만 기존 대비 품질 우수). reasoning 계열 특성상 기본값(1) 외의 `temperature`를 거부하므로, `OpenAIClient.complete_json`이 `BadRequestError(param="temperature")`를 감지하면 `temperature` 파라미터 없이 1회 재시도하도록 방어 로직 추가(§7.1). |

## 0-2. 추가 확정 사항 (2026-07-22 사용자 확인)

| 항목 | 결정 |
| --- | --- |
| 백테스트 시세 자동 수집 | `POST /backtest` 실행 시 요청된 종목에 해당 기간 데이터가 하나도 없으면 자동으로 수집·저장(`ensure_price_data`, §8-1). 일부라도 있으면 건드리지 않음(부분 공백을 정교하게 채우지 않는 의도된 단순화). `Settings.auto_ingest_prices`(기본 true, 테스트는 false)로 on/off. |
| 시간봉(장중) 데이터 | 공공데이터포털/KOSCOM CHECK-API는 모두 일봉만 제공하므로, 네이버 증권의 비공식 차트 API(`api.stock.naver.com`, 별도 인증 불필요, 실측 확인)로 일봉+시간봉(60분)을 모두 수집(§8-1). 시간봉은 서버 자체가 최근 약 8거래일치(56봉)만 제공하는 실측 한계가 있어 "가능한 범위까지 저장"하는 부가 데이터로 취급하고, 백테스트 엔진 자체는 계속 일봉 기준으로 동작. |
| 종목코드 입력 | 프론트 백테스트 폼(`BacktestResultView.vue`)에 이미 콤마 구분 자유입력 텍스트필드(`대상 종목코드`)가 있어 별도 UI 추가 없이 임의 종목코드 입력이 가능했음 — 이번 작업은 백엔드 자동 수집만 추가. |
| 뉴스 AI 분석 파이프라인 | 별도 독립 프로젝트 `back-news-analysis/`(루트)로 구현. `naver_economy_news.json`(92,229건)에서 AI로 기사 단위 고정 스키마 필드를 추출하고, 임베딩 유사도 기반 이벤트 클러스터링 + decay/count_factor로 종목별 뉴스 영향도 점수를 계산(§16). OpenAI 키는 `backend/.env`를 그대로 재사용. |
| 대량 AI 호출 비용 절감 | 뉴스 스코어링/임베딩처럼 서로 독립적인 대량 요청은 OpenAI Batch API(50% 할인)로 처리. 단, "새 뉴스마다 기존 대표뉴스 전체와 비교해 판단"하는 이벤트 클러스터링은 순차 의존성이 있어 Batch API와 근본적으로 맞지 않아, 임베딩 유사도 기반 클러스터링으로 대체(§16.2). |
| 뉴스 영향도(impact) 등급 체계 | High/Medium/Low 3단계 대신 **1~9등급**(9등급=전쟁·내전 발발 등 국가적 충격) + 등급별 예시를 시스템 프롬프트에 명시해, AI가 등급 기준을 자체적으로 임의 판단하지 않고 고정 앵커에 맞춰 분류하도록 함(§16.1). |
| 원시 AI 변수와 점수 계산식 분리 | decay/count_factor/정규화 등 "점수 계산식"은 나중에 바뀔 수 있으므로, AI가 추출한 원시 변수(`NewsVariables`)만 캐시에 저장하고 최종 점수는 조회 시점에 캐시된 원시 변수로부터 매번 계산(`aggregate.py`). 계산식이 바뀌어도 캐시된 AI 호출 결과는 재사용 가능 — 단, 원시 변수 자체의 스키마(예: impact 등급 체계)가 바뀌면 해당 필드는 재추출 필요(§16.5). |

## 0-3. 추가 확정 사항 (2026-07-22 사용자 확인 — 포트폴리오 영속화)

| 항목 | 결정 |
| --- | --- |
| 포트폴리오(현금/보유종목) 영속성 | **실시간 반영형**. 매수/매도 체결마다 DB(`portfolio_cash`/`portfolio_positions`)의 현금/보유수량이 실제로 갱신되고 서버 재시작에도 유지된다(§6, §9.2). 기존 `DummyOrderExecutionProvider`는 컨테이너 생명주기 동안만 메모리에 잔고를 들고 있어(재시작 시 리셋) "보유 종목/자금 관리"가 사실상 불가능했던 문제를 해결. |
| 노드에서의 노출 방식 | **자동 주입**(새 노드 타입 아님). `scheduler.interval`이 종목 유니버스를 초기화하는 것처럼, `WorkflowEngine.execute()`가 런 시작 시점에 `held_qty`/`held_avg_price`/`cash`/`equity`를 모든 종목 데이터에 자동으로 채워 넣어 `logic.if_else`의 `expr` 등에서 배선 없이 바로 참조 가능(§3.1). |
| 백테스트와의 관계 | **독립 유지**. 백테스트는 지금처럼 사용자가 지정한 `initial_capital`·빈 포지션에서 시작하는 가상 실행을 유지(재현 가능한 실험이 목적)하되, 동일한 자동 주입 메커니즘으로 자신의 임시 `broker` 상태를 그대로 반영받는다 — 별도 백테스트 전용 코드 불필요(§8). |
| 백테스트 그래프 가시성 | 거래일마다 별도 `run_id`로 `RunRecord`/`NodeEventRecord`를 저장(§8-2)해, 결과 화면에서 특정 날짜를 골라 그날의 노드 그래프 실행을 "테스트 실행"과 동일한 디버그 패널로 재생 가능. |
| ABC 기반 다형성 | 나중에 실제 증권사 API로 교체 가능하도록, 신규 구현도 기존 `OrderExecutionProvider`/Repository 패턴을 그대로 따름 — `PersistentOrderExecutionProvider`는 `DummyOrderExecutionProvider`/`TossInvestOrderExecutionProvider`와 나란한 세 번째 구현체일 뿐이며, `PortfolioRepository`도 기존 Repository 인터페이스 패턴(SQLite/인메모리 구현체 분리)을 그대로 따른다(§9.1). |

추가로 조사를 통해 확인한 사실:
- **Toss증권 Open API**: `developers.tossinvest.com`에 실존. OAuth2 Client Credentials Grant, 계좌 API는 `X-Tossinvest-Account` 헤더 필요. 시세/호가/체결/캔들/가격제한/종목정보/환율/시장캘린더 + 계좌/자산/주문(생성·수정·취소·조회) 제공. 현재 사전신청 기반 단계적 오픈 중이라 즉시 발급이 어려움.
- **공공데이터포털 금융위원회_주식시세정보 API** (`data.go.kr`, 서비스키 필요, 무료): 종목코드+일자 기준 시가/종가/고가/저가/거래량 등 제공. **일 1회, 영업일 T+1 오후 갱신** (실시간 아님) → 백테스트용 일봉 데이터 소스로 적합. 1초/1분 단위 "실시간성"은 이 데이터로 재현 불가능하므로, 라이브/테스트 모드에서는 이 일봉을 시드로 한 더미 실시간 시세 생성기를 별도로 둔다 (§5.2).
- **OpenDART(공시)**: `opendart.fss.or.kr` API 키 발급 필요(무료). 공시 원문/공시목록 조회에 사용.

## 0-4. 추가 확정 사항 (2026-07-28 사용자 확인 — 조건 내장 지표 노드 + 판단 로그)

사용자 요청: 팀 원본 저장소 `koscom-mini-project-4/koscom_nemonemo`를 참고해 if문/조건 관련
기능을 늘리고 노드 편집을 쉽게 만들 것, "테스트 실행" 로그에 실행 결과뿐 아니라 각 노드의
판단 근거도 함께 보이게 할 것.

fork 저장소를 clone해 우리와 갈라진 지점(2026-07-19 `Initial commit`) 이후 커밋을 조사한 결과,
"계산 + 조건 내장" 지표 노드(원시 수식 대신 사람이 읽는 조건 프리셋 드롭다운으로 판단)라는
아이디어를 발견해 우리 아키텍처에 맞게 이식했다. fork에도 없던 "판단 근거를 로그에 표시"하는
기능은 이번에 새로 설계했다.

| 항목 | 결정 |
| --- | --- |
| 조건 내장 지표 노드 범위 | fork와 동일하게 **12종 전부** 포트(SMA/EMA/MACD/RSI매매신호/기간수익률/변동성/볼린저/ATR추적손절/52주최고가대비/MDD/거래량비율/거래량Z-score, §3.2). 값만 계산하던 기존 `indicator.moving_average`/`indicator.rsi`/`indicator.momentum`은 변경하지 않고 그대로 유지(하위호환). `indicator.rsi`와 타입이 겹치는 fork의 조건 내장 RSI는 `indicator.rsi_signal`로 개명해 충돌을 피함. |
| `logic.if_else` 처리 | **유지**(fork처럼 팔레트에서 숨기지 않음). 복합조건/OR 로직 등 프리셋으로 커버되지 않는 경우에 여전히 필요하기 때문. |
| 판단(judgment) 로그 | 모든 필터형 노드(`logic.if_else`/`logic.rank`/`risk.stop_loss`/조건 내장 지표 노드 12종)가 종목별 통과/탈락 근거를 `context.meta.decisions[node_id][symbol] = {"pass": bool, "reason": str, "metrics"?: dict}` 형태로 공통 기록(§3.1). 기존 `meta.filtered_out`(탈락 종목 코드 목록만 기록, `app/api/routers/ai.py`의 챗봇 컨텍스트가 참조)은 하위호환을 위해 그대로 유지하고 신규 필드만 추가. 프론트 `DebugPanel.vue`가 "테스트 실행" 시 이 값을 종목별 판단 테이블로 렌더링한다. |

## 0-5. 추가 확정 사항 (2026-07-28 사용자 확인 — newsstock-lib 통합)

사용자 요청: 팀이 만든 별도 저장소 `koscom-mini-project-4/newsstock-lib`(뉴스 기반 종목/섹터/
거시경제 매매 판단 라이브러리)를 포함시키거나 살짝 수정해서, 뉴스 기반 true/false 신호를
내는 노드를 추가할 것. 다른 기능에서도 필요하면 크롤링을 트리거할 수 있게 할 것.

| 항목 | 결정 |
| --- | --- |
| 통합 방식 | **vendoring**. `newsstock-lib`의 `news_classifier` 패키지(`NewsTrader` 파사드 — 조회 시 스스로 크롤링(네이버 경제뉴스)→AI 분류→클러스터 반영을 수행하고 종목/섹터/거시 3축의 t(호재)/n(중립)/f(악재) 판정을 계산하는 자체완결 라이브러리)를 `backend/app/vendor/news_classifier/`에 그대로 복사. 우리 `NewsRepository`/`ai.sentiment_score`(기존 뉴스 파이프라인)와는 독립된 별개 경로다. |
| 수정한 부분("혹은 살짝 수정해서") | `classifier.py::call_ai`가 OpenAI 호출 시 `temperature=0`을 하드코딩하는데, 우리 메인 모델 `gpt-5.6-luna`(reasoning 계열)는 기본값(1) 외의 temperature를 거부한다(§0-1, `app/ai/openai_client.py`와 동일 문제). `OpenAIClient.complete_json`과 동일한 "BadRequestError(param=temperature) 감지 시 temperature 없이 1회 재시도" 패턴을 적용. 그 외 파일은 원본 그대로. |
| Provider 배선 | `NewsTrader`는 스레드 세이프하지 않은 `sqlite3.Connection`을 내부에 물고 있어 `ai_client`처럼 공유 인스턴스 하나를 두면 `WorkerPool`의 여러 워커 스레드가 동시에 같은 연결을 건드릴 수 있다. 공유 인스턴스 대신 노드 실행마다 새 `NewsTrader`(새 sqlite 연결)를 만드는 **팩토리 콜러블**(`Container.news_trader_factory`)을 `node_providers()`로 주입한다. DB 파일은 `Settings.newsstock_db_path`(기본 `backend/newsstock.db`, `nemo_stock.db`와 별도)이고 API 키/모델은 기존 `openai_api_key`/`openai_model`을 재사용한다. |
| 신규 노드 | `ai.news_signal`(§3.2) — `params.axis`(종목/섹터/거시경제)에 따라 `NewsTrader.stock`/`sector`/`macro`를 호출해 `symbols[code]`에 `news_verdict`/`news_score`/`news_cluster_count`/`news_true`(bool)를 채우고 `params.pass_when` 기준으로 필터링하는 조건 내장형 노드(§0-4의 필터형 노드 패턴을 그대로 따름). axis="종목"이고 `key`를 안 주면 `app/market_data/symbol_master.py`로 종목코드→한글명 자동 매핑. |
| 다른 기능에서의 크롤링 트리거 | `ai.news_signal`은 `params.auto_update`(기본 true)로 실행 시점에 스스로 갱신을 트리거하지만(라이브러리 자체 30분 쓰로틀로 비용 제한), 이를 꺼둔 워크플로나 다른 기능(대시보드 등)이 독립적으로 트리거할 수 있도록 `POST /data/news/update`(§9) 엔드포인트를 추가해 `news_trader_factory`를 통한 수동 갱신을 노출한다. |
| 백테스트 시점 인식 | `NewsTrader.stock/sector/macro()`는 `start`를 안 주면 항상 "실제 오늘"을 기준으로 계산하므로, 백테스트가 과거 날짜로 `context.timestamp`를 바꿔가며 노드를 반복 실행해도 매 거래일이 전부 동일한(가장 최근) 결과를 받는 문제가 있었다. `ai.news_signal`이 `start=context.timestamp.date()`를 명시적으로 넘기도록 수정해 백테스트의 각 거래일이 그 날짜 시점의 뉴스 창을 보게 했다. |
| 백테스트 AI 호출량 제한 | 위 수정으로 백테스트 거래일마다 서로 다른 조회가 실제로 일어나게 되어, 기간이 길어질수록 OpenAI 호출(뉴스 분류)이 그만큼 늘어난다. 비용을 예측 가능한 범위로 묶기 위해 `ai.news_signal` 노드가 포함된 워크플로의 백테스트는 기간을 제한한다(`app/api/routers/backtest.py::NEWS_SIGNAL_BACKTEST_MAX_DAYS`, 초과 시 400. 최초 4일 → 7일 → 2026-07-28 사용자 확인으로 **14일**로 상향). |
| 크롤러 병렬 fetch | 실제 크롤링(`POST /data/news/update`)이 원본 순차 구현 기준 수분 이상 걸려, `crawler.py::crawl()`에 `workers` 파라미터(기본 `CRAWL_WORKERS=4`)를 추가해 페이지 안의 기사들을 `ThreadPoolExecutor`로 동시에 fetch하게 했다. 스레드마다 별도 `requests.Session`(별도 connection pool, `threading.local`)을 쓰고 지연은 워커별로 각자 넣어 정중함 정책은 유지한다. 목록 페이지 조회와 AI 분류(`pipeline.classify_many`, 오래된 뉴스부터 순서대로 처리해야 클러스터가 올바르게 쌓이는 순차 의존성)는 병렬화 대상에서 제외했다. |

## 0-6. 추가 확정 사항 (2026-07-28 사용자 확인 — fork 뉴스 신호 파이프라인 포트 + 백테스트/관리자 UX)

사용자가 실제로 백테스트를 돌려보며 발견한 문제(뉴스 마커가 안 뜸, 일봉만 나옴)와 fork
(`koscom_nemonemo`)에 우리가 아직 안 옮긴 노드가 많다는 지적을 계기로 진행한 후속 작업 묶음.

| 항목 | 결정 |
| --- | --- |
| `ai.news_signal` 파라미터 확장 | `NewsTrader`의 `threshold`/`decay_base`/`include_zero`/`decay_from`(전부 라이브러리 기본값과 동일한 기본값)을 노드 파라미터로 노출해 사용자가 직접 조절 가능하게 함(`Container.news_trader_factory`도 동일 kwargs를 받도록 확장). |
| 백테스트 뉴스 마커 버그 수정 | `/backtest/{id}/news/{used,all}`이 `data.news`/`NewsRepository`(구 파이프라인)만 알고 `ai.news_signal`이 쓰는 `newsstock.db`는 몰라, 그 노드만 쓰는 워크플로는 마커가 항상 비어 있었다(§0-5 도입 시 놓쳤던 버그). `GET /backtest/{id}/news/signal` 신규 추가 — 워크플로의 `ai.news_signal` 노드 파라미터로 조회해 `클러스터` 목록을 마커로 변환. 프론트는 기존 "참고 뉴스"와 별개 시각(보라 삼각형)으로 병렬 표시. |
| 백테스트 신규 폼 기본 기간 | `ai.news_signal` 노드가 포함된 워크플로를 선택하면 시작/종료일을 "최근 개장일 기준 4일"로 자동 설정(공휴일 캘린더 없이 주말만 건너뛰는 근사, 워크플로 변경 시에만 재적용). AI 호출량 상한(§0-5)과 별개로 UX 기본값만 다룬다. |
| 백테스트 AI 호출량 상한 재조정 | 4일 → 7일 → **14일**로 상향(`NEWS_SIGNAL_BACKTEST_MAX_DAYS`, 2026-07-28 사용자 재확인). |
| 판정 근거의 "주요 주제" 노출 | `ai.news_signal`이 판정에 가장 큰 영향을 준 뉴스 클러스터(`|점수|` 최대)를 `news_top_topic`/`news_top_topic_score`로 symbols에 채우고 `meta.decisions`의 판단 사유 문구에도 포함 — true/false 판정의 근거를 사람이 바로 확인 가능. |
| 백테스트 차트 시간봉 | `GET /backtest/{id}/prices`에 `interval`(기본 `day`, `minute60`) 파라미터를 추가해 기존 `intraday_price_bar_repo`를 노출. 프론트는 `minute60`을 먼저 시도하고 데이터가 있으면(§0-2 실측 한계로 최근 약 8거래일치만 존재) 그걸, 없으면 일봉으로 자동 폴백. 시간봉 모드에서는 매매/뉴스 마커·자산곡선을 "그 날짜의 마지막 봉"에 맞춰 매핑(라벨이 날짜+시각이라 기존 정확히-같은-문자열 매칭이 깨지므로). 백테스트 엔진 자체는 여전히 일봉 기준(§8-1 원칙 유지) — 이건 차트 표시 전용. |
| 관리자 페이지 신설 | `/admin`(프론트 `AdminView.vue`) — (1) 뉴스 분석 현황: `NewsTrader.stats()`/`clusters()`를 그대로 노출(`GET /data/news/{stats,clusters}`) + 수동 갱신 버튼, (2) 사용량 통계: 백테스트 실행 수 + AI 호출 수/토큰 수(목적별·모델별). 단일 관리자 계정 구조라 별도 권한 분기 없음. |
| AI 사용량 계측 | 신규 `AIUsageRecord`/`AIUsageRepository`(+sqlite 구현) — `OpenAIClient.complete_json()`에 `usage_repo`/`purpose` 파라미터 추가(둘 다 옵션, 하위호환), 응답의 `usage`(토큰수)를 저장한다. `app/vendor/news_classifier/classifier.py`(newsstock-lib 자체 OpenAI 호출 경로)도 `set_usage_sink()` 콜백으로 동일 로그에 남기도록 소폭 수정(VENDOR_NOTES.md 세 번째 항목). 기존 AI 호출부(workflow_draft/workflow_chat/scoring_cache/backtest_explain/news_classify)에 `purpose=` 라벨을 붙여 목적별 집계가 의미 있게 나오도록 함. `BacktestResultRepository.count()` 추가. |
| fork "뉴스 신호" 파이프라인 11종 포트 | fork를 다시 조사해 지표 노드(§0-4) 포트 때는 놓쳤던 완전히 별도인 3계층 파이프라인(AI 라벨링 → 충격량/시계열 집계 → 조건 내장 노드)을 발견 — 사용자가 전부 포트하기로 확정. `app/nodes/conditions.py`(§0-4 때 "필요 없다"고 안 옮겼던 큐레이션 프리셋 시스템 — 이번엔 11개 노드가 전부 씀), `app/news_signals/{sectors,themes,impact,aggregate,ingest}.py`, `app/ai/news_classify.py`(Depth1/2/3 분류, 우리 `AIScoreCacheRepository` 재사용), `NewsSignalRecord`/`NewsSignalRepository`(+sqlite/in-memory 구현), 노드 11종(`app/nodes/data/news_signal.py`, §3.2), `POST /data/ingest/news/classified` 신규 + `ingest_manual_news` 확장(AI 키 있으면 best-effort 신호 저장). 우리 저장소가 fork와 동일한 `Node`/`NodeContext`/`AIClient` 기반이라 vendoring이 아니라 일반 포트로 진행했고, `conditions.py::apply_condition()`에 우리 컨벤션인 `meta.decisions` 기록을 추가한 것 외엔 원본 그대로다. 프론트 코드 변경 없이(기존 select/option_labels/show_if/subcategory 렌더링 재사용) 팔레트에 바로 노출됨을 확인. |

## 0-7. 관리자 페이지: 클러스터 ↔ 종목/섹터/거시 상호 탐색 (2026-07-28 사용자 요청)

관리자 페이지의 "뉴스 분석 현황" 클러스터 목록이 대표제목/strength/뉴스건수만 보여줘 "이 주제가
정확히 어떤 종목/섹터/거시와 연결됐는지"를 알 수 없었다. 사용자 요청으로 양방향 탐색을 추가:
(1) 클러스터(주제) → 연결된 종목/섹터/거시 목록, (2) 반대로 종목/섹터/거시 키 → 그와 연결된
클러스터 목록.

- `app/vendor/news_classifier/db.py`: `cluster_tags(conn, cluster_id)` 신규(해당 클러스터의
  `classifications` 테이블에서 종목/섹터/거시지표 키를 중복 제거해 반환) + `cluster_stats()`가
  각 클러스터 행에 이 태그를 병합해 반환하도록 확장(응답 필드 추가뿐이라 하위호환).
- `app/vendor/news_classifier/api.py::NewsTrader`: `clusters_for_key(group, key, start, end)`
  (기존 `db.group_cluster_rows` 래핑 — 반대 방향 조회), `keys_in_range(group, start, end)`
  (기존 `db.group_keys` 래핑 — 탐색 드롭다운용 키 목록). `VENDOR_NOTES.md`에 기록.
- `app/api/routers/data.py`: `GET /data/news/topics?group=stock|sector|macro&start=&end=`(키
  목록), `GET /data/news/topics/clusters?group=&key=&start=&end=`(그 키에 연결된 클러스터
  목록) 신규. `GET /data/news/clusters`는 시그니처 변경 없이 응답에 `종목`/`섹터`/`거시지표`
  필드가 추가됨.
- 프론트(`AdminView.vue`): 클러스터 표에 태그 열 추가, "종목/섹터/거시로 클러스터 탐색"
  섹션 신규(축 선택 → 키 드롭다운 → 관련 클러스터 조회). 뉴스 분석 현황과 동일한 기간(날짜
  범위)을 공유해 별도 날짜 입력을 추가하지 않았다.
- 실 서버(`--reload`)에 curl로 라이브 검증: `/data/news/topics?group=stock`이 실제 종목명
  목록을 반환, `/data/news/clusters`의 클러스터가 실제 종목 태그를 포함, `/data/news/topics/
  clusters?group=stock&key=삼성전자`가 해당 종목이 언급된 실제 클러스터 7건을 정확히 반환.

## 0-8. AI 챗봇 노드 수정 제안: 전/후 비교 창 (2026-07-28 사용자 요청)

캔버스의 AI 챗봇(`ChatPanel.vue`)이 그래프 수정을 제안하면 지금까지는 "노드 N개, 엣지 N개"
요약과 적용/취소 버튼만 있어 실제로 뭐가 바뀌는지 알 수 없었다. 사용자 요청으로 전/후 비교
창을 추가하고, 그 안에서 다시 수정을 요청하거나 확정/확정취소할 수 있게 했다. 백엔드 변경
없음 — `app/ai/workflow_chat.py::chat_about_workflow()`가 이미 `graph` 인자를 그대로 받아
"현재 그래프"로 취급하므로, 프론트가 무엇을 넘기느냐만으로 이번 기능이 성립한다.

- `frontend/src/utils/graphDiff.ts` 신규 — 순수 함수 `diffGraphs(before, after)`. 노드는 id로
  매칭해 추가/삭제/변경(타입 또는 파라미터 중 하나라도 다르면 변경, 파라미터별로 이전/이후
  값 목록 포함)으로 분류하고, 엣지는 `from->to[:branch]` 키로 추가/삭제만 분류한다.
- `frontend/src/components/GraphDiffModal.vue` 신규 — `diffGraphs()` 결과를 노드별
  추가(초록)/삭제(빨강)/변경(노랑) 배지로, 엣지 변경은 별도 목록으로 보여준다. 노드 타입은
  `NodeTypeSchema.display_name`으로, 파라미터 키는 `param_schema[].label`로 사람이 읽는
  이름으로 표시(둘 다 프론트에 이미 있던 스키마 재사용, 신규 API 없음). 하단에 "다시 수정
  요청" 입력창 + "확정"/"확정 취소" 버튼.
- `frontend/src/components/ChatPanel.vue`: 기존 인라인 적용/취소 버튼을 "비교 검토"
  버튼(→ 모달 오픈)으로 교체. **"다시 수정" 시 핵심은 AI에게 넘기는 `graph`를 캔버스의
  현재 상태(`props.graph`)가 아니라 지금 검토 중인 제안(`pendingGraph`)으로 바꿔치기하는
  것** — 그래야 AI가 직전 제안 위에 이어서 고치지, 원래 캔버스 기준으로 처음부터 다시
  제안하지 않는다. 비교 창의 "before"는 항상 실제 캔버스 그래프로 고정해, 여러 번 "다시
  수정"을 거쳐도 최종 제안과 현재 캔버스의 전체 누적 차이를 계속 보여준다. AI가 그래프
  변경 없이 순수 답변만 한 경우(changed=false) 비교 창이 깨지지 않도록 기존 제안을 유지하고
  안내 문구만 띄운다.
- `frontend/src/views/StrategyBuilderView.vue`: 이미 보유 중이던 `nodeTypes`를
  `ChatPanel`에 prop으로 전달(라벨 표시용, 신규 fetch 없음).
- 검증: `vue-tsc -b` + `npm run build` 통과, 사용자 dev 서버(HMR)로 신규/변경 파일이 컴파일
  에러 없이 서빙됨을 curl로 확인. 이번 세션도 브라우저 자동화 도구가 없어 실제 클릭 동작은
  사용자가 `npm run dev`로 직접 확인 필요.

## 0-9. 자유 프롬프트 AI 판단 노드 + 뉴스신호 근거 보강 + 노드 단독 테스트 (2026-07-28 사용자 요청)

사용자 요청 3가지를 한 번에 처리: (1) 프롬프트/참고자료를 자유롭게 쓰는 통과·탈락 판단
AI 노드 신설(치환 또는 AI 스스로 도구 호출 중 워크플로 작성자가 선택), (2) "뉴스 관련 노드의
매수/매도 의견·이유가 json에 같이 안 넘어온다"는 제보 확인, (3) "if/else를 넘어가도 점수/의견이
계속 json으로 누적돼야 한다"는 아키텍처 우려 검토.

**(3) 조사 결과**: `app/nodes/base.py::NodeContext.symbols`는 이미 매 노드가 `clone()`
(deepcopy)해서 이어받고, `logic.if_else`/`app/nodes/conditions.py::apply_condition()` 둘 다
통과한 종목의 데이터 dict를 그대로 유지한다(탈락 종목만 제거, 필드를 지우지 않음) — 재현되지
않음. 새 아키텍처 불필요. **(2)의 실체**는 `app/nodes/data/news_signal.py`의 11개 조건 내장
뉴스신호 노드가 숫자 점수만 stamp하고 "어떤 뉴스가 그 점수를 만들었는지" 근거가 전혀 없던 것
— `ai.news_signal`엔 이미 있던 `top_topic` 패턴이 빠져 있었다. → Part D에서 이식.

- **Part A — `AIClient` 도구 호출(tool-calling) 지원**: `complete_with_tools(system_prompt,
  user_prompt, tools, tool_executor, max_rounds=4, ...)` ABC 메서드 신설.
  `OpenAIClient`에서 `tool_choice="auto"`로 반복 호출 → 도구 호출 시 `tool_executor`로 실행해
  `role="tool"` 메시지로 이어붙이고 재호출(최대 `max_rounds`, 과금 폭주 방지) → 더 이상 도구를
  안 부르거나 라운드 초과 시 도구 없이 마지막 1회로 최종 JSON을 강제. 기존 `complete_json`의
  `gpt-5.6-luna` temperature 재시도 로직을 `_create()` 헬퍼로 공유. `FakeAIClient`에
  `tool_scripts`(라운드별 스크립트) 지원 추가.
- **Part B — 신규 노드 `ai.free_prompt`**(`app/nodes/ai/free_prompt.py`): `prompt`/`reference`
  파라미터(신규 타입 `"prompt"`, 큰 textarea)에 `{{키}}`로 앞 노드가 채운 `symbols[code]`
  값을 자동 치환(예약 토큰 `{{symbol}}`/`{{date}}`). `params.data_mode`로 두 방식 중 선택
  (AskUserQuestion으로 사용자에게 확인 — "사용자가 선택할 수 있도록" 응답): **"치환"**(누락된
  키가 있는 종목은 AI를 호출하지 않고 즉시 탈락 — 이게 "정형검증"의 실체: 전체 그래프 정적
  타입분석이 아니라 실행 시점 심볼별 런타임 가드) | **"AI 직접 조회(도구 호출)"**(누락 값은
  AI가 뉴스/가격 조회 도구 4종 — `get_symbol_news_signal`/`get_sector_news_signal`/
  `get_macro_news_signal`/`get_price`, 전부 기존 `news_trader_factory`/`market_data`
  provider를 얇게 감싼 것 — 를 스스로 호출해 채울 수 있음). AI 응답
  `{"pass","opinion","confidence","reason"}`을 `symbols[code]`에 `{node_id}_pass/_opinion/
  _confidence/_reason`으로 네임스페이스(다중 인스턴스 충돌 방지)해 채우고 필터형 노드로
  동작, `meta.decisions`에도 기록(기존 컨벤션 그대로라 DebugPanel이 코드 변경 없이 판단
  내용을 보여줌 — "테스트 실행 때 내용이 나와야" 요건 충족). `validate_params()`에서
  `{{ }}` 짝 안 맞음 등 템플릿 문법 정적 검사. `backtest.py`의 기존 `ai.news_signal` 전용
  AI 호출량 기간 제한(`NEWS_SIGNAL_BACKTEST_MAX_DAYS`)을 `ai.free_prompt`까지 확장(캐시 없이
  심볼×거래일마다 실제 호출이 나가 동일한 비용 위험).
- **Part C — 노드 단독 테스트 실행**(`ai.free_prompt`뿐 아니라 모든 노드에 범용):
  `WorkflowGraph.ancestors_of(node_id)`(역방향 BFS) 신설, `WorkflowEngine.execute(...,
  target_node_id=...)`가 지정되면 그 노드와 조상만 실행하도록 위상 순서를 필터링,
  `RunOverride.target_node_id` 스키마 추가. 프론트 `PropertyPanel.vue`에 "▶ 이 노드까지
  테스트" 버튼(선택 노드가 있을 때) → 최신 파라미터를 먼저 저장한 뒤 그 노드까지만 실행해
  디버그 패널에 결과 표시.
- **Part D — 뉴스신호 11종 근거 보강**: `NewsSignalRecord`에 `title`(원문 제목) 필드 추가(+
  sqlite ORM은 `init_db()`의 기존 자동 컬럼 보정 로직으로 하위호환, in-memory 리포지토리는
  변경 불필요) + `ingest.py`/`data.py` 적재 경로에서 스레딩.
  `app/news_signals/aggregate.py::top_contributor(signals, as_of, window_days, predicate,
  score_fn)` 신규 — 각 지표 함수와 동일한 필터 조건으로 `|score_fn|` 최대인 신호 1건을 찾는다.
  `app/nodes/conditions.py::apply_condition()`에 선택적 `note_fn` 파라미터 추가(하위호환,
  없으면 기존과 동일) — 있으면 reason 끝에 근거 문구를 붙임. 11개 노드 전부 지표 계산 직후
  `top_contributor`로 근거를 찾아 `<field>_top_title`/`<field>_top_score`를 stamp하고
  `apply_condition(..., note_fn=...)`으로 판단 사유에 포함 — `ai.news_signal`의 `topic_note`와
  동일한 문구 스타일(`"주요 근거: '{title}' (기여점수 {score:+.4f})"`).
- 검증: 백엔드 pytest 261→267개 전부 통과. 실 서버(`--reload`)에 curl로 라이브 검증 —
  `GET /nodes`에 `ai.free_prompt` 노출 확인, 존재하지 않는 키를 참조하는 프롬프트로 테스트
  실행 시 AI 호출 없이(duration_ms로 확인) `meta.decisions`에 "누락된 키" 사유가 정확히
  기록됨을 확인, `target_node_id`로 하류 노드가 실행되지 않음을 확인.

## 0-10. 종목 마스터 캐시 — 종목코드↔종목명 매핑을 실제 전 종목으로 확장 (2026-07-28 사용자 요청)

`app/market_data/symbol_master.py`의 종목코드→종목명 매핑이 정적으로 하드코딩된 8개
종목뿐이라, `ai.news_signal`/`ai.free_prompt`가 종목코드로 뉴스를 조회할 때 이 8개 밖의
종목은 전부 "종목명 매핑 없음"으로 실패했다. 반면 관리자 페이지 뉴스 클러스터 검색(§0-7)은
`newsstock.db`(AI가 뉴스 기사에서 직접 추출한 종목명)를 그대로 노출해 80개 이상의 이름이
검색되는 등, 두 검색 경로가 서로 다른 데이터 소스를 써서 불일치했다. 이미 연동된 공공데이터
API(`DATA_GO_KR_SERVICE_KEY`, 금융위원회_주식시세정보)를 재사용해 실제 KOSPI/KOSDAQ 전
종목의 코드/종목명/시장구분을 캐싱하는 구조로 이 8개 하드코딩을 대체했다.

**범위 확정**: 종목코드→**섹터** 자동 매핑은 포함하지 않았다. 이미 연동된 공공데이터 API는
종목코드/종목명/시장구분만 주고 업종(섹터) 분류는 주지 않는다. 기존처럼 사용자가
`app/news_signals/sectors.py`의 큐레이션된 30개 섹터에서 직접 선택하는 구조를 유지한다.

- `app/data_ingestion/public_data_price.py::PublicDataPriceClient.fetch_market_snapshot(as_of,
  ...)` 신규 — 기존 `fetch_daily_prices`가 쓰는 것과 같은 엔드포인트(`GetStockSecuritiesInfoService/
  getStockPriceInfo`)를 `likeSrtnCd` 없이 호출하면 시장 전체가 반환되는 서버 동작(원래
  `fetch_daily_prices` 상단에 "버그"로 문서화돼 있던 것)을 "전 종목 목록을 한 번에 가져오는
  방법"으로 활용. 그날 데이터가 없으면(주말/공휴일) 최대 7일 전까지 물러나며 재시도.
- `SymbolMasterRecord`/`SymbolMasterRepository`(`app/dao/base.py`) + sqlite/in-memory
  구현체(기존 `NewsSignalRepository` 등과 동일 패턴) — durable 캐시.
- `app/market_data/symbol_master.py` 리팩터: 기존 8개 하드코딩 목록은 "캐시가 비어있을 때
  (최초 부팅/동기화 전/API 키 없음)"의 폴백 시드로만 남기고, `load_cache()`로 통째로 교체
  가능한 in-memory 캐시를 도입. `get_symbol_name()`/`search_symbols()`/`list_symbols()`는
  시그니처 그대로라 호출부(`ai/news_signal.py`, `ai/free_prompt.py`, `api/routers/backtest.py`,
  `api/routers/data.py`) 전혀 수정 없이 내부 구현만 교체됨.
- `app/dependencies.py::build_container()`가 부팅 시 직전 동기화 결과를 sqlite에서
  `load_cache()`로 즉시 복원(재시작해도 API 재호출 불필요). `POST /data/symbols/sync`(관리자
  트리거, `DATA_GO_KR_SERVICE_KEY` 없으면 400) + `GET /data/symbols/stats`(현재 캐시 크기/
  DB 저장 건수) 신규. `AdminView.vue`에 "종목 마스터" 카드(동기화 버튼 + 현황) 추가.
- **실 서버 라이브 검증 결과(중요)**: 구현 직후 실 서버에 `POST /data/symbols/sync`를 실제로
  트리거했으나 `synced: 0`이었다. 원인을 추적한 결과, 신규 코드의 문제가 아니라 **기존에
  이미 있던 `fetch_daily_prices`/`ingest_public_prices` 경로도 현재 `DATA_GO_KR_SERVICE_KEY`
  로는 같은 엔드포인트에서 항상 `totalCount: 0`(resultCode는 "00" 정상)을 받는다**는 것을
  확인했다(2025-01-02처럼 명백한 과거 영업일로 직접 curl해도 동일). data.go.kr 콘솔에서 이
  API("금융위원회_주식시세정보")에 대한 서비스키 활용 승인 상태를 확인해야 한다.

### 0-10-1. KOSCOM CHECK-API 폴백 (2026-07-28 후속 — 사용자 요청 "공공데이터에서 안되는건 check api에서받아오세요")

공공데이터포털 서비스키가 계속 빈 응답만 주는 상황이라, 이미 실제 자격증명으로 검증된
KOSCOM CHECK-API(`app/market_data/koscom_adapter.py::KoscomMarketDataProvider`, `get_price`/
`get_orderbook`/`get_ohlcv` 3개 엔드포인트가 2026-07-15 실호출 검증 완료돼 있음)를 동기화
대안 소스로 추가했다.

- `docs/koscom-api/pages/01-stock-api/{거래소,코스닥} 종목/01-코드 정보.md` 조사 결과,
  `POST /stock/m001/code_info`(거래소=KOSPI)와 `/stock/m003/code_info`(코스닥)가 `jcode`
  없이 그룹 전체를 한 번에 돌려주는 벌크 엔드포인트임을 확인 — 페이지네이션도 없고 시장당
  호출 1회(총 2회, 기존 "초당 1회" 레이트리밋 적용)로 전 종목 코드(`F16013`)/한글종목명
  (`F16002`)을 가져올 수 있다.
- `KoscomMarketDataProvider.fetch_symbol_master()` 신규 — 두 엔드포인트를 호출해
  `[{"symbol","name","market"}, ...]`로 합쳐 반환(§0-10의 `PublicDataPriceClient.
  fetch_market_snapshot()`과 동일한 반환 형태라 그대로 재사용 가능).
- `POST /data/symbols/sync`(`app/api/routers/data.py`)를 폴백 체인으로 변경: 공공데이터
  포털을 먼저 시도(무료, 현재 미승인으로 빈 응답) → 응답이 비어 있으면
  `KOSCOM_CUST_ID`/`KOSCOM_AUTH_KEY`가 설정돼 있을 때 KOSCOM CHECK-API로 자동 전환. 응답에
  `source`("data.go.kr" | "koscom") 필드 추가(관리자 페이지에서 어느 소스로 동기화됐는지
  확인 가능, 하위호환 — 기존 필드는 그대로 유지).
- **실 서버 라이브 검증**: `POST /data/symbols/sync` 실행 결과 `{"synced": 4297, "source":
  "koscom"}` — 4일 전(§0-10) 8개였던 매핑이 실제 KOSPI+KOSDAQ 전 종목(4,297개)으로 확장됨을
  확인. "기아"(000270)/"LG전자"(066570) 등 기존 8개 목록에 없던 종목도 정상 검색·매핑됨을
  실 서버에서 직접 확인.
- 섹터(업종) 정보도 `docs/koscom-api/pages/01-stock-api/거래소 종목/14-소속 업종 정보.md`
  (`/stock/m001/upjong_info`)로 조회 가능함을 확인했으나, 이 엔드포인트는 종목당 `jcode`가
  필요해(벌크 조회 불가) 초당 1회 제한상 전 종목 일괄 동기화에는 부적합하다 — §0-10에서
  범위 제외 결정한 "섹터 자동 매핑"은 이번에도 그대로 제외(필요하면 종목 단위 온디맨드
  조회로 추후 별도 구현 가능하다는 점만 기록).

## 0-11. 백테스트/AI 화면 실시간 진행률·로그·토큰 사용량 (2026-07-28 사용자 요청)

백테스트 실행(`POST /backtest`)은 완전히 동기 HTTP 요청이라, AI 노드가 포함된 워크플로가
여러 거래일에 걸쳐 실행되는 동안 프론트는 로딩 스피너만 보여줬다. AI 사용 화면(초안 생성/
챗봇/백테스트 설명)도 마찬가지였다. 조사 결과 **실시간 이벤트 스트리밍 인프라
(`app/workflow/events.py::EventBus` + `app/api/ws.py::/ws/runs/{run_id}` + 프론트
`frontend/src/api/ws.ts::subscribeRunEvents()`)가 이미 구현돼 있었지만 전혀 쓰이지 않고
있었다** — 이번 작업은 그 기존 인프라를 재사용하는 것이다.

- **Part A — 백테스트 진행률**: `BacktestRequest.progress_run_id`(프론트가 미리 생성한
  UUID)를 `BacktestRunner.run()`에 전달하면, 거래일 루프 시작 전 "시작" 이벤트(총 거래일수)
  + 매 거래일 처리 후 "진행" 이벤트(날짜/인덱스/주문건수/그날 AI 토큰 사용량 델타)를
  `event_bus.publish()`로 발행한다. 새 이벤트 스키마를 만들지 않고 기존
  `NodeExecutionEvent`를 "가상 노드"(`node_id="__progress__"`, `node_type=
  "backtest.progress"`)로 재사용해 `EventBus`/WS/`subscribeRunEvents()`를 전혀 안 건드리고
  값만 실어 보냈다. AI 토큰 델타는 `AIUsageRepository.list_since(그 거래일 시작 시각)`으로
  계산(§0-6 기존 조회 메서드 재사용, 새 계측 훅 없음). 완료/예외 양쪽 다 `finally`에서
  `close_run()`으로 스트림을 닫는다.
- **Part B — 프론트 진행 패널**: `frontend/src/components/BacktestProgressPanel.vue` 신규.
  `BacktestResultView.vue::submitRun()`이 POST 직전 `progress_run_id`를 생성해 먼저
  WS 구독을 걸고(시작 이벤트를 놓치지 않기 위해 POST보다 먼저), 응답이 오면 구독을 닫는다.
- **Part C — AI 사용 화면 토큰 표시**: `app/api/routers/ai.py`의 세 엔드포인트(초안 생성/
  챗봇/백테스트 설명)가 호출 전/후 `ai_usage_repo.list_since()` 델타를 계산해 응답에
  `usage: {prompt_tokens, completion_tokens, total_tokens} | null`을 추가(옵션 필드,
  하위호환). `AIGenerateView.vue`/`ChatPanel.vue`에 로딩 중 경과 시간 카운터 + 응답 후
  토큰 사용량 한 줄 표시.
- **실 서버 라이브 검증(중요)**: TestClient mock이 아니라 실제 실행 중이던 사용자의
  `--reload` 서버에 진짜 워크플로/백테스트를 만들고, 별도 파이썬 프로세스에서 실제
  WebSocket으로 `/ws/runs/{progress_run_id}`에 접속해 백테스트가 진행되는 동안 실시간으로
  이벤트 6건(시작 1 + 거래일 5)을 정확한 순서·내용으로 수신함을 확인 — mock을 거치지 않은
  end-to-end 검증.

## 0-12. 뉴스 키워드 크롤링 + 관리자 페이지 사이드바/뉴스 목록 (2026-07-28 사용자 요청)

사용자 요청 두 가지를 함께 처리: (1) "5일치 뉴스만, 하이닉스/반도체/삼성 글자가 들어간
것만" 당겨오기 — 크롤러(`app/vendor/news_classifier/crawler.py`)에 키워드 필터가 없어
매번 네이버 경제 섹션 전체를 무차별로 긁던 것을 좁힘. (2) 관리자 페이지(`AdminView.vue`)에
분석됨/미분석 뉴스 목록 섹션 추가 + 사이드바 탭 레이아웃으로 재구성 + 스타일/하단 여백 개선.

- `crawler.py::_list_page()`가 URL만 반환하던 것을 `list[tuple[url, title]]`로 바꿔(Naver
  목록 HTML의 `<a>` 텍스트가 곧 헤드라인이라 추가 네트워크 호출 없이 얻음) 본문을 가져오기
  전에 제목으로 먼저 걸러낼 수 있게 했다. `_matches_keywords(title, keywords)` +
  `crawl(..., keywords=None)` — "이 페이지 전부 이미 봤음" 조기중단 판단은 키워드와 무관하게
  전체 URL 기준(`unseen`)으로 하고, 본문을 실제로 가져올지(`fresh`)만 키워드로 추가
  필터링해 페이지네이션 로직이 깨지지 않게 했다. `Settings.crawl_keywords` +
  `NewsTrader.update(days=, keywords=)`(1회성 오버라이드, 전역 설정은 안 바꿈) +
  `NewsUpdateRequest.days/keywords` → `POST /data/news/update`로 노출.
- `db.py::count_pending`/`list_analyzed_news`(분류행을 url_hash로 GROUP BY해 종목/섹터/거시
  태그를 합침) + `NewsTrader.pending_news/pending_count/analyzed_news` +
  `GET /data/news/pending`, `GET /data/news/analyzed` 신규.
- `AdminView.vue`를 좌측 사이드바(6개 섹션: 사용량 통계/종목 마스터/뉴스 분석 현황/탐색/
  분석된 뉴스/미분석 뉴스) + 우측 단일 섹션 렌더링으로 재구성. "미분석 뉴스" 배지, "뉴스
  분석 현황" 섹션에 기간(일)/키워드 입력 필드를 갱신 버튼 옆에 추가(비우면 기존 전역
  동작과 동일). 카드에 `box-shadow`, 하단 `padding-bottom: 80px` 추가.

### 0-12-1. 실사용 발견 버그 — 발행일시 파싱 실패 시 "수집 시점"으로 잘못 채워짐

Part 4(실제 5일+키워드 크롤 트리거)를 실행하기 직전, 사용자가 지적: "기사가 수집될 때
수집시점 말고 뉴스 기사 등록 시점 기준으로 판단되어야하는데" — 확인 결과
`crawler.py::_article()`이 기사 페이지에서 발행일시(`DATE_SELECTOR`) 파싱에 실패하면
`datetime.now()`(그 순간, 즉 크롤링 실행 시각)로 채우고 있었다. **과거 날짜를 크롤링
중일 때(`days=5`처럼 여러 날짜를 훑을 때) 이 폴백이 걸리면, 실제로는 며칠 전 기사인데
"방금 발행됨"으로 잘못 찍혀** 날짜 기준 필터링(최근 N일 조회, 백테스트 시점 재현 등)이
전부 틀어지는 실질적인 버그였다.

- `_article(session, url, fallback_date_str=None)`에 `fallback_date_str`(크롤링 중인
  목록 날짜, `crawl()`의 `date_str`) 파라미터를 추가해 파싱 실패 시 "수집 시점"이 아니라
  "그 기사가 속한 목록 날짜"(정오로 근사)로 채우도록 수정. `_fetch_one`/
  `_fetch_page_articles`를 통해 `crawl()`의 `date_str`을 끝까지 threading. `fallback_date_str`
  을 안 주면(다른 호출부가 있을 경우 대비) 기존과 동일하게 `datetime.now()` 폴백 유지(하위호환).
- 이 버그를 실제 트리거 전에 잡아, 잘못된 타임스탬프로 5일치 데이터가 오염되는 사고를
  피했다 — 수정 후 재검증하고 나서 실제 크롤을 실행한다.

## 0-13. 한국투자증권(KIS) 연동 모드 + 주문 수량 비율(%) 설정 (2026-07-28 사용자 요청)

사용자 요청 두 가지를 함께 처리: (1) "한투증 모의투자 api 연결했는데 완료되면 한투증 api
연동 모드도 추가해주세요" — 기존 `MarketDataProvider`/`OrderExecutionProvider` 어댑터
패턴(Toss/KOSCOM과 동일)으로 KIS Open API를 추가. (2) "주문 수량을 주문 가능수량의 n% 로도
설정 가능하게 해줘(기본값 50%)" — `execution.market_order`에 비율 기반 수량 모드 추가.

- **엔드포인트/필드는 추정이 아니라 공식 GitHub(`github.com/koreainvestment/open-trading-api`,
  사용자가 직접 지정) `examples_llm/`의 실제 동작하는 예제 코드를 직접 대조해 확인**했다 —
  Toss 스켈레톤(사전신청 승인 대기라 전부 추정치)보다 신뢰도 높다. 확인 중 처음에 기억에
  의존해 추정했던 매수/매도 주문 tr_id(`TTTC0802U` 등)가 실제로는 `TTTC0012U`(매수)/
  `TTTC0011U`(매도)임을 원본 코드 대조로 정정했다(§ 아래).
- **모의/실전 전환 규칙**: 실전용 tr_id는 전부 `T`/`J`/`C`로 시작하고, 모의투자는 첫 글자만
  `V`로 바꾼 값을 그대로 쓴다(`app/broker/kis_auth.py::to_paper_tr_id`, 원본 레포
  `_url_fetch`의 실제 치환 규칙 그대로 이식). 시세 조회(`F`로 시작하는 tr_id)는 모의/실전
  구분 없이 동일 tr_id라 치환 대상이 아니다.
- `app/broker/kis_auth.py`(신규): `KISOAuthTokenProvider` — `POST /oauth2/tokenP` OAuth2
  Client Credentials 토큰 발급/캐싱(만료 30초 여유), `auth_headers(tr_id, is_paper)`가 공통
  헤더(`authorization`/`appkey`/`appsecret`/`tr_id`/`custtype: P`) 구성. `hashkey()`(
  `POST /uapi/hashkey`)는 원본 예제의 `order_cash.py`가 주석 처리해둔 것과 동일하게 기본
  비활성, 필요 시 호출부에서 선택적으로 쓸 수 있는 헬퍼로만 제공. market_data/broker 두
  어댑터가 공유한다.
- `app/market_data/kis_adapter.py`(신규): `KISMarketDataProvider` — 현재가(`inquire-price`,
  `FHKST01010100`), 일봉(`inquire-daily-itemchartprice`, `FHKST03010100`,
  `FID_ORG_ADJ_PRC="0"`=수정주가), 호가(`inquire-asking-price-exp-ccn`, `FHKST01010200`).
  `PriceTick.prev_close`는 응답에 직접 필드가 없어 `stck_prpr - prdy_vrss`로 역산(원본 응답
  확인 결과).
- `app/broker/kis_adapter.py`(신규): `KISOrderExecutionProvider` — `place_order`는
  `order-cash`(`TTTC0011U`=매도/`TTTC0012U`=매수, 요청 body는 `CANO`/`ACNT_PRDT_CD`/`PDNO`/
  `ORD_DVSN`/`ORD_QTY`/`ORD_UNPR`/`EXCG_ID_DVSN_CD="KRX"`/`SLL_TYPE`/`CNDT_PRIC` 전부
  대문자 키 — KIS POST API 자체 규칙) 호출 후 `rt_cd=="0"`이면 `status="pending"`(KIS
  주문 API는 접수 응답만 주므로 Toss 스켈레톤처럼 "filled"로 단정하지 않음), 실패면
  `status="rejected"` + `reason=msg1`. 성공한 주문의 `(KRX_FWDG_ORD_ORGNO, ORD_DVSN)`을
  인스턴스에 캐싱해 `cancel_order`(`order-rvsecncl`, `TTTC0013U`)가 재사용. `get_balance`/
  `get_positions`는 `inquire-balance`(`TTTC8434R`) 공유 호출의 `output2[0]`(잔고요약,
  `dnca_tot_amt`=현금/`tot_evlu_amt`=평가금액)/`output1`(보유종목 배열, `pdno`/`hldg_qty`/
  `pchs_avg_pric`)를 매핑. **필드 대소문자 비일관성 확인**: 주문/취소 API의 요청 body와
  응답 output은 대문자 키(`ODNO` 등), 잔고조회 응답 output은 소문자 키(`pdno` 등) —
  원본 예제 코드로 직접 확인한 KIS API 자체의 비일관성이며 어댑터 버그가 아님.
- `Settings`: `kis_app_key`/`kis_app_secret`/`kis_base_url`(기본값 모의투자 호스트
  `https://openapivts.koreainvestment.com:29443`)/`kis_is_paper=True`/`kis_account_no`
  (`"12345678-01"` 형식). `market_data_provider`/`order_provider`에 `"kis"` 옵션 추가.
  `.env`/`.env.example`에 사용자 요청대로 앱키/시크릿/계좌번호는 **빈 값**으로 추가(사용자가
  직접 채워 넣을 예정).
- **주문 수량 비율(%) 설정** (KIS와 독립적, 모든 broker provider 공통): `execution.
  market_order`에 `qty_mode`(select, 기본 "고정수량"|"가능수량 비율(%)")/`qty_pct`(number,
  기본 50, `show_if`로 비율 모드일 때만 노출) 파라미터 추가. 수량 결정 우선순위(하위호환
  유지): `target_qty`(상위 노드 지정, 기존 최우선) → 비율 모드면 매수는
  `cash/기준가*qty_pct/100`, 매도는 `held_qty*qty_pct/100`(둘 다 `WorkflowEngine.execute()`
  가 매 노드 실행 시 자동 주입하는 필드, §5 참조 — provider 종류와 무관하게 동작해야 해서
  KIS 전용 "매수가능조회" API를 쓰지 않고 이 필드를 재사용) → 기본(고정수량 모드)은 기존
  `params.qty` 그대로. `qty_mode`/`qty_pct`는 `required: False`로 둬야 기존 그래프(이
  파라미터를 지정하지 않은 저장된 워크플로)가 그래프 검증에서 깨지지 않는다(`required: True`
  로 처음 만들었다가 기존 테스트 그래프 다수가 검증 실패하는 것을 발견해 정정 — `get_param`
  이 스키마 `default`로 폴백하므로 required일 필요가 없었음).
- 실제 앱키 발급 전이라 실호출 검증은 못했다(`tests/unit/test_kis_adapter.py`가
  `httpx.MockTransport`로 구조/필드만 검증). 사용자가 `.env`에 앱키/시크릿/계좌번호를 채워
  넣은 뒤 실제 모의투자 계좌로 한 번 더 확인 권장.

## 0-14. 백테스트 매매 지점 클릭 → "왜 샀는지" 팝업 (2026-07-28 사용자 요청)

사용자 요청: "매수/매도가 어떤 로직으로 인해 발생했는지, 뉴스 노드가 true면 어떤 뉴스로
종합적으로 그렇게 됐는지 보여줬으면 좋겠다. 그래프에서 특정 지점을 클릭하면 팝업으로 흐름이
시각적으로 잘 보이면 좋겠고, AI api로 뉴스 이유를 요청해서 가져와도 된다."

조사 결과 관련 인프라(매매 마커 클릭 → 그래프 리플레이/DebugPanel, `POST /ai/backtest-explain`)
가 이미 있었지만 세 가지 사각지대가 있었다: (1) 팝업이 아니라 상시 패널이라 노드를 하나씩
클릭해야 사유를 봄, (2) `_build_backtest_selection()`이 `meta.decisions`(판단 사유, `ai.
news_signal`이면 참고 뉴스 제목까지 담김)를 AI 프롬프트에 전혀 안 실음, (3) `used_news`는
`data.news`(구 파이프라인)만 알고 `ai.news_signal`이 쓰는 newsstock.db 클러스터는 몰라
AI가 뉴스 근거를 볼 방법이 없었음(§0-6에서 마커 엔드포인트는 고쳤지만 AI-explain 쪽은 그때
안 고쳤던 사각지대).

- **Part A**: `app/api/routers/ai.py::_summarize_day_events()`가 이제 노드 타입과 무관하게
  `meta.decisions[node_id]`를 각 노드 요약에 포함한다(기존엔 `logic.if_else`/`execution.
  market_order`만 특수 처리). 이 한 줄로 `ai.news_signal`/`risk.stop_loss`/지표 조건 노드 등
  모든 필터형 노드의 판단 사유(뉴스 근거 텍스트 포함)가 AI 프롬프트에 자동으로 실린다.
- **Part B**: `get_backtest_news_signal()`(마커 엔드포인트, `backtest.py`)의 "워크플로의
  `ai.news_signal` 노드 파라미터로 축/키 결정 → `news_trader_factory`로 클러스터 조회" 로직을
  `app/nodes/ai/news_signal.py::resolve_news_signal_clusters()`로 추출해 `backtest.py`(마커)와
  `ai.py::_build_backtest_selection()`(AI 설명 근거, `selection["news_signal_clusters"]`)가
  공유하도록 리팩터링. `backtest_explain.py`의 시스템 프롬프트에도 이 필드를 명시해 AI가 실제
  뉴스 제목을 인용하도록 안내.
- **Part C**: `frontend/src/components/TradeExplainModal.vue` 신규 — 매매 마커 클릭 시 뜨는
  팝업. 열리면 `fetchRun(workflowId, trade.run_id)`로 그날의 노드 실행 이벤트를 가져와
  `trade.symbol`의 `decisions`를 순서대로 세로 스텝 타임라인(무료, AI 호출 없음, 즉시 표시)
  으로 보여준다. `DebugPanel.vue`가 이미 쓰던 `output_snapshot.meta.decisions` 추출 로직을
  `src/utils/decisions.ts`(`decisionsForEvent`/`decisionForSymbol`)로 공유 유틸로 뽑아 두
  컴포넌트가 재사용. 하단 "AI 종합 설명 요청" 버튼을 눌러야만(호출 비용 발생 지점) 기존
  `explainBacktest()`를 호출해 자연어 요약을 받아온다(Part A/B 덕분에 이제 실제 뉴스 근거를
  인용 가능).
- **Part D**: `BacktestChart.vue`에 `open-trade` emit 추가(매매 마커 클릭 시 기존 `select`/
  `select-day` emit과 나란히 발행 — 사이드 AskPanel·그래프 리플레이는 그대로 유지, 비파괴적
  추가). `BacktestResultView.vue`가 이를 받아 모달을 띄운다.

**검증**: `app/nodes/ai/news_signal.py::resolve_news_signal_clusters` 단위 테스트 3개(
`test_news_signal_node.py`) + `/ai/backtest-explain` 통합 테스트(`test_api_backtest_news_
signal_cap.py`, `FakeAIClient`로 캡처한 프롬프트에 뉴스 제목/`decisions`/`news_signal_
clusters`가 실제로 포함되는지 검증) 추가. 백엔드 pytest 336→340개 전부 통과, 리팩터링한
`get_backtest_news_signal` 기존 테스트도 그대로 통과(동작 불변 확인). `vue-tsc -b` 통과.
브라우저 자동화 도구가 이 환경에 없어 모달의 실제 클릭/렌더링은 라이브 검증 불가 — 기존
검증된 패턴(TestRunModal 모달 CSS, DebugPanel decisions 추출 로직)을 그대로 재사용해 리스크를
낮췄다.

## 0-15. .env로 AI 제공자(OpenAI ↔ Claude) 선택 (2026-07-29 사용자 요청)

사용자 요청: "`.env`를 사용해서 claude를 사용할지, openai를 사용할지 결정할 수 있도록 해
주세요." 이 저장소는 이미 AI 호출을 `app/ai/base.py::AIClient`(ABC, `complete_json`/
`complete_with_tools`)로 추상화해뒀고, 소비자(워크플로 초안/챗봇/백테스트 설명/`ai.free_
prompt`/`ai.sentiment_score`)는 전부 인터페이스로만 의존해 `app/dependencies.py::
build_container()`의 단 한 줄에서만 구체 구현을 생성한다 — `market_data_provider`/
`order_provider`와 동일한 "provider 문자열 선택 + 팩토리 분기" 패턴을 그대로 적용했다.

- `app/ai/claude_client.py`(신규): `ClaudeClient(AIClient)`. 엔드포인트/필드는 공식 문서
  (`platform.claude.com/docs/en/api/messages`)를 직접 대조해 확인(추정 아님) — `model`/
  `max_tokens`/`messages` 필수, `system`은 최상위 문자열 파라미터, 도구는
  `{"name","description","input_schema"}` 형태(OpenAI의 `{"type":"function","function":
  {...}}`와 달라 `_tool_to_anthropic()`으로 변환), 응답은 `content`(TextBlock/ToolUseBlock
  배열) + `usage.input_tokens`/`output_tokens`(`prompt_tokens`/`completion_tokens`로 매핑해
  기존 `AIUsageRecord`와 동일 계약 유지). `complete_json`은 Claude에 OpenAI의
  `response_format=json_object` 같은 강제 JSON 모드가 없어 텍스트 블록을 모아 마크다운
  코드펜스만 벗겨내고 `json.loads`. OpenAIClient의 temperature/reasoning_effort 특이
  재시도 로직(§0-1, §0-16 이전 항목)은 이식하지 않음 — Claude 표준 API는 그런 제약이 없어
  더 단순하게 유지.
- `Settings.ai_provider`(기본 `"openai"`, `openai|claude`) + `anthropic_api_key`/
  `anthropic_model`(기본 `"claude-sonnet-5"`) 추가. `app/dependencies.py::_build_ai_client()`
  로 인라인 생성 코드를 추출(`_build_market_data_provider`/`_build_order_provider`와 동일
  위치/패턴)해 `build_container()`가 호출. `.env`/`.env.example`에 `AI_PROVIDER=openai`,
  `ANTHROPIC_API_KEY=`(빈 값, 사용자가 직접 채워 넣음), `ANTHROPIC_MODEL=claude-sonnet-5`
  추가.
- **범위 밖(명시적 결정)**: `app/vendor/news_classifier`(newsstock-lib, `ai.news_signal`
  노드가 씀)는 자체 하드코딩된 OpenAI 클라이언트(`classifier.py::_client_once`/`call_ai`)를
  갖는 완전히 별개의 vendored 파이프라인이라 이 토글의 영향을 받지 않는다 — vendored 코드
  최소 수정 원칙(세션 전체에서 유지) + 사용량 로그만 콜백으로 같은 `ai_usage_repo`에 남기는
  기존 구조를 그대로 둠.
- **부수 발견/수정(테스트 인프라 버그)**: 전체 테스트 실행 중 `tests/conftest.py::app_client`
  픽스처가 toss/koscom 자격증명만 빈 값으로 강제하고 `market_data_provider`/`order_provider`
  선택 자체는 그대로 둬, 로컬 `.env`가 실사용을 위해 `koscom`/`kis` 등으로 설정돼 있으면
  `build_container()`가 크리덴셜 누락 `RuntimeError`를 내며 거의 모든 통합 테스트가 fixture
  단계에서 깨지는 문제를 실제로 겪고 발견 — `market_data_provider`/`order_provider`/
  `ai_provider`/KIS·Anthropic 크리덴셜도 함께 강제로 되돌리도록 수정(이 픽스처의 기존 주석에
  이미 명시된 "로컬 .env와 무관하게 결정적으로 동작해야 한다"는 의도를 완성한 것).

**검증**: `tests/unit/test_claude_client.py`(신규, `test_openai_client.py`와 동일한 형태 —
text/코드펜스 파싱, tool_use 라운드트립, max_rounds 폴백, 사용량 매핑, api_key 없을 때
`AIUnavailableError`) + `test_provider_selection.py`에 `_build_ai_client` 케이스 3개 추가.
백엔드 pytest 340→350개 전부 통과(`test_koscom_live.py`는 실 시장 상황에 따라 비결정적인
기존 라이브 테스트라 제외 — §0-15와 무관). `vue-tsc -b` 통과(프론트 변경 없음, 관리자 페이지
사용량 통계가 이미 provider 구분 없이 `model` 문자열 기준으로 집계해 그대로 동작). 실제
Anthropic API 호출 검증은 못함(사용자가 이후 `ANTHROPIC_API_KEY`를 직접 채워 넣을 예정) —
mock 기반 유닛 테스트로 구조/필드만 확인.

## 0-16. 관심종목 추가 + 보유 포지션 직접 관리 (2026-07-29 사용자 요청)

사용자가 대시보드 보유종목 카드에서 `PWTESTQ1`/`PWRESTART1`(정체불명 종목코드)를 발견하고
질문. 조사 결과: "테스트 실행"(`POST /workflows/{id}/runs`)이 백테스트와 달리 **실제 라이브
계좌(`container.broker`)를 그대로 공유**해(`app/api/routers/account.py` 자체 주석에 이미
명시된 단일 계좌 PoC 구조), 예전에 "대상 종목코드" 입력란에 임시 문자열을 넣고 매수 노드
포함 워크플로를 테스트 실행하면서 그게 그대로 `portfolio_positions`에 기록된 잔재였다.
사용자는 (1) 보유 여부와 무관한 관심종목 추적, (2) 보유 포지션 직접 추가/수정/삭제, (3) 두
잔재 데이터 정리를 모두 요청.

- `PortfolioRepository.upsert_position(user_id, symbol, qty, avg_price)`(기존)이 이미
  "qty<=0이면 삭제"까지 구현돼 있어 포지션 추가/수정/삭제 전부 새 repository 메서드 없이
  처리 — `PUT /account/positions/{symbol}`(생성/수정, qty<=0이면 400으로 명시적 거부)과
  `DELETE /account/positions/{symbol}`(내부적으로 `upsert_position(...,0,0)`) 두 엔드포인트로
  분리해 프론트가 "qty<=0이면 삭제"라는 구현 디테일을 몰라도 되게 함.
- `WatchlistRepository`(신규, `PortfolioRepository`와 동일한 3계층 패턴 — ABC(`app/dao/
  base.py`) → `SqliteWatchlistRepository`/`InMemoryWatchlistRepository`) + `watchlist_items`
  테이블(`Base.metadata.create_all()`로 자동 생성, 마이그레이션 불필요). `GET/POST /account/
  watchlist`, `DELETE /account/watchlist/{symbol}` — add/remove 둘 다 idempotent(중복
  추가·존재 안 하는 종목 삭제 모두 에러 없이 조용히 처리).
- `DashboardView.vue`: "보유 종목 시세" 카드에 수정(✏)/삭제(🗑) 버튼 + "종목 직접 추가"
  버튼(`PositionEditModal.vue` 신규, `TestRunModal.vue`와 동일 모달 CSS 패턴) 추가. 신규
  "관심 종목" 섹션(`SymbolAutocomplete` 재사용해 추가, 보유 종목과 겹치면 중복 표시 안 함).
  `loadPriceSeries()`가 보유종목∪관심종목 심볼로 캔들차트 조회 범위 확장.
- **데이터 정리**: 새 `DELETE /account/positions/{symbol}`을 실제 개발 서버에 두 번 호출해
  `PWTESTQ1`/`PWRESTART1` 제거 — 엔드포인트 실동작 검증을 겸함. sqlite로 직접 확인해 정상
  삭제됨을 확인(`GET /account/summary`는 이 시점 `ORDER_PROVIDER=kis`가 KIS 측 500 에러로
  막혀 있어 대신 사용 — §0-15 후속 미해결 이슈, 이번 작업과 무관).

**검증**: `tests/integration/test_api_account_watchlist_positions.py`(신규, §0-17에서 인증 관련
테스트 2개 제거 후 6개) — watchlist 추가/목록/중복추가(idempotent)/삭제(존재 안 하는 종목도
무해), position 생성/수정/qty<=0 거부/삭제(idempotent). 백엔드 pytest 351→359개 전부 통과.
`vue-tsc -b` 통과. 브라우저 자동화 도구가 없어 프론트 클릭 검증은 못함(기존 세션과 동일
제약) — curl로 API 자체는 라이브 검증(watchlist add/list, position delete 실제 호출·확인).

## 0-17. 인증 게이트 완전 제거 (2026-07-29 사용자 요청)

사용자 요청: "로그인 페이지 없애줘." 범위를 명확히 하기 위해 확인 질문("프론트만 자동
로그인" vs "인증 자체를 완전히 제거") → **인증 자체를 완전히 제거**로 확정.

- 백엔드: `POST /auth/login`(`app/api/routers/auth.py`) + `app/schemas/auth.py` 삭제,
  `app/main.py`에서 `auth.router` 등록 제거. 7개 라우터(`admin`/`workflows`/`backtest`/
  `data`/`ai`/`nodes`/`account`)의 `dependencies=[Depends(get_current_username)]` 게이트를
  전부 제거(각 라우터 자체는 그대로 — `get_container` 등 다른 의존성은 유지). `app/auth/
  security.py`를 `hash_password`(admin 계정 시드용으로만 남김) 하나로 축소하고
  `verify_password`/`create_access_token`/`decode_access_token`/`get_current_username`
  삭제. `Settings.jwt_secret`/`jwt_algorithm`/`jwt_expire_minutes`와 `pyproject.toml`의
  `pyjwt` 의존성도 함께 제거(더 이상 아무도 안 씀). `UserRepository`/admin 계정 시드 로직
  자체는 남겨둠(다른 곳에서 참조하지 않는 자족적 구조라 제거 범위 밖으로 판단).
- 프론트엔드: `LoginView.vue`/`stores/auth.ts` 삭제, `router/index.ts`의 `/login` 라우트와
  `beforeEach` 인증 가드 제거, `api/client.ts`의 Authorization 헤더 첨부/401 인터셉터 제거,
  `main.ts`의 `setUnauthorizedHandler` 배선 제거, `App.vue`의 로그아웃 버튼/`showNav` 조건부
  제거(항상 네비게이션 표시), `services.ts::login()` 제거.
- **부수 정리**: 기존 테스트 다수가 `headers=auth_headers`를 그대로 넘기고 있어(문법상 유지)
  `tests/conftest.py::auth_headers` 픽스처를 `/auth/login` 호출 대신 빈 dict를 반환하도록
  변경해 대부분의 기존 테스트는 무수정으로 통과하게 함. "인증 없이 401을 기대"하던 테스트
  9개(예: `test_unauthenticated_request_rejected`, `test_*_requires_auth`)는 이제 성립하지
  않는 주장이라 전부 삭제.

**검증**: `python -c "from app.main import create_app; ..."`로 앱 기동 + OpenAPI 경로 38개
정상 등록 확인. 백엔드 pytest 359→350개 전부 통과(인증-요구 테스트 9개 삭제 반영). `vue-tsc -b`
통과, `useAuthStore`/`stores/auth`/`LoginView`/`/auth/login` 잔여 참조 없음을 grep으로 재확인.

## 0-18. AI 배치 호출을 스트리밍으로 전환 (2026-07-29 사용자 요청)

사용자 요청: "현재 배치로 실행되는 ai 있으면 ai 전략 생성이나 대화 등 빠르게 요청받아야 하는
것들은 배치가 아닌 stream 등으로 바꿔 줘." 대상은 `POST /ai/generate-draft`(전략 생성)/
`workflow-chat`(캔버스 챗봇)/`backtest-explain`(§0-14 매매 근거 팝업) 셋 — 전부
`AIClient.complete_json()`으로 응답이 통째로 완성될 때까지 기다렸다 한 번에 받고 있었다.

**범위 확인(질문으로 확정)**: 이 세 엔드포인트의 AI 응답은 `{"reply", "changed", "name",
"nodes", "edges"}`가 하나의 JSON에 같이 담겨 있어, 답변 텍스트만 깔끔하게 스트리밍하려면
프롬프트 계약 자체를 바꿔야 해서(reply를 순수 텍스트로 먼저 뽑고 그래프 수정은 별도 호출로
분리) 기존 검증/재시도 로직(`WorkflowGraph.validate()` 실패 시 1회 재시도, 3곳에 이미 있음)
을 건드려야 하는 더 위험한 변경이 된다. 사용자가 **저위험 옵션(원문 텍스트 실시간
미리보기)**을 선택 — 생성 중인 원문(JSON 파싱 전)을 SSE로 실시간 전송해 "AI가 작성 중"
미리보기로 보여주고, 완료되면 기존과 동일하게 파싱된 결과로 전환한다. 검증/재시도 로직은
전혀 안 건드림.

- `app/ai/base.py::AIClient`에 새 추상 메서드 `complete_json_stream(..., on_chunk=None)` 추가
  — `complete_json`과 동일 계약(파싱된 dict 반환)에 `on_chunk`만 더함. `OpenAIClient`는
  `stream=True, stream_options={"include_usage": True}` + `delta.content` 누적(사용량은
  choices가 빈 마지막 청크에 실림). `ClaudeClient`는 공식 문서
  (`platform.claude.com/docs/en/api/messages-streaming`)로 확인한 패턴 그대로
  `with client.messages.stream(...) as stream: for text in stream.text_stream: ...`,
  `stream.get_final_message()`로 usage 포함 전체 Message. 둘 다 `_record_usage`를
  `response` 대신 `usage` 객체를 직접 받도록 소폭 리팩터링(스트림엔 단일 response가 없어서).
  `FakeAIClient`(테스트 더블)는 `responses` 큐를 그대로 재사용하되 `on_chunk`엔 최종 JSON을
  단일 청크로 한 번만 넘겨 인터페이스 계약만 만족.
- `generate_workflow_draft`/`chat_about_workflow`/`explain_backtest` 각각에 `on_chunk` 파라미터
  추가(기본 None → 기존 블로킹 동작 100% 그대로). **첫 번째** 시도만 `complete_json_stream`으로
  교체하고, 검증 실패 시의 재시도(repair) 호출은 드문 경로라 스트리밍하지 않고 기존
  `complete_json` 유지 — 리스크 최소화.
- `app/api/routers/ai.py`에 `_stream_sse(worker)` 헬퍼 신규: 별도 스레드에서
  `worker(on_chunk=queue.put)`을 실행하고, 메인 제너레이터가 큐에서 꺼내
  `chunk`/`result`/`error` SSE 프레임을 yield. FastAPI `StreamingResponse`가 동기 제너레이터를
  자동으로 스레드풀에서 돌려줘 `async def` 불필요. 기존 블로킹 엔드포인트 3개는 무수정 유지,
  `POST /ai/{generate-draft,workflow-chat,backtest-explain}/stream` 3개를 순수 추가.
- `frontend/src/api/sse.ts` 신규: `postSSE(url, body, {onChunk, onResult, onError})` — POST라
  네이티브 `EventSource`(GET 전용) 대신 `fetch()` + `getReader()`로 직접 스트림 파싱.
  `AIGenerateView.vue`는 스트리밍 중 누적 원문을 `<pre>` 미리보기로 보여주다 `result` 도착 시
  기존 카드로 전환. `ChatPanel.vue`/`BacktestAskPanel.vue`는 어시스턴트 말풍선에 스트리밍 중
  원문을 모노스페이스 스타일로 채워나가다 완료 시 `reply`로 교체 — TypeScript가 클로저 안에서만
  대입되는 변수의 control-flow narrowing을 못 해서(`onResult` 콜백 안에서만 값이 들어옴) `as`
  단언으로 우회.

**검증**: `test_openai_client.py`/`test_claude_client.py`에 스트리밍 유닛 테스트 추가(청크
전달/사용량 매핑/on_chunk 없이도 동작/api_key 없을 때 에러), `test_api_ai_flow.py`에
`/ai/generate-draft/stream` SSE 통합 테스트 추가(chunk 프레임들 + 마지막 result 프레임 검증).
백엔드 pytest 350→361개 전부 통과. `vue-tsc -b` 통과. `curl`/`TestClient.stream()`으로 실제
SSE 프레임(`chunk`→`result`)이 순서대로 오는 것을 라이브 확인. 브라우저 자동화 도구가 없어
실제 화면 렌더링 라이브 확인은 못함(기존 세션과 동일 제약).

## 0-19. 전략 생성 AI와 나머지 AI의 모델을 .env에서 별도 선택 (2026-07-29 사용자 요청)

사용자 요청: "전략 생성 ai랑 나머지 ai 에서 사용할 모델을 별도로 선택할 수 있도록 해 주세요.
.env에서 사용 모델을 각각 선택하고 싶어요." 기존 `AI_PROVIDER`+`OPENAI_MODEL`/
`ANTHROPIC_MODEL` 하나로 전략 생성(`POST /ai/generate-draft`)과 나머지 AI 기능(캔버스
챗봇/백테스트 설명/자유 프롬프트 노드 등)이 항상 같은 모델을 썼다 — 전략 생성만 더 고성능
모델을 쓰고 나머지는 저렴한 모델을 쓰는 식의 분리가 불가능했다.

- `app/dependencies.py::_build_ai_client(settings, ai_usage_repo, model_override=None)` —
  기존 팩토리 함수에 `model_override` 파라미터만 추가(없으면 기존과 동일하게
  `openai_model`/`anthropic_model` 사용). `Container`에 `strategy_ai_client: AIClient`
  필드를 신설하고, `build_container()`에서 `_build_ai_client`를 **두 번** 호출 —
  `ai_client`(기본 모델)와 `strategy_ai_client`(모델 오버라이드 있으면 그걸 사용, 없으면
  기본 모델과 동일한 클라이언트를 별도 인스턴스로 생성).
- `app/config.py::Settings.ai_model_strategy: str | None = None` 신규 — 비워두면
  `OPENAI_MODEL`/`ANTHROPIC_MODEL`과 동일 모델을 그대로 쓴다.
- `app/api/deps.py::get_strategy_ai_client` 신규 — `container.strategy_ai_client`를
  반환. `app/api/routers/ai.py`의 `generate_draft`/`generate_draft_stream`(블로킹 +
  스트림 둘 다) 두 엔드포인트만 `Depends(get_ai_client)` → `Depends(get_strategy_ai_client)`
  로 교체. `workflow_chat`/`workflow_chat_stream`/`backtest_explain`/
  `backtest_explain_stream`은 기존 그대로 `get_ai_client` 유지 — "전략 생성만 별도, 나머지는
  기본 모델" 요구사항 그대로 반영.
- `.env`/`.env.example`에 `AI_MODEL_STRATEGY=` 신규(빈 값 = 기본 모델과 동일, 주석으로
  용도 설명).

**검증**: `test_provider_selection.py`에 `_build_ai_client`의 `model_override` 동작
유닛 테스트 2개 추가(오버라이드 있을 때/없을 때). `test_api_ai_flow.py`의 기존
`/ai/generate-draft`(+`/stream`) 테스트 5개가 `dependency_overrides[get_ai_client]`를
쓰고 있었는데, 이제 이 두 엔드포인트가 `get_strategy_ai_client`를 쓰므로 오버라이드 키를
맞춰 수정(동작 자체가 아니라 테스트가 어느 의존성을 갈아끼워야 하는지만 바뀐 것). 새 통합
테스트 `test_generate_draft_uses_strategy_ai_client_not_default`로 두 클라이언트가 실제로
독립적으로 주입되는지(`get_strategy_ai_client`만 오버라이드하면 `/ai/generate-draft`는
성공하고 `/ai/workflow-chat`은 여전히 400) 확인. 백엔드 pytest 361→364개 전부 통과.
`vue-tsc -b` 통과(프론트 변경 없음).

## 0-20. 검색 기반 뉴스 딥 크롤러 + 뉴스 갱신 모델/페이지수 오버라이드 (2026-07-29 사용자 요청)

사용자 요청: "아이씨에이치"가 제목/본문에 들어간 뉴스 8일치를 크롤링해 gpt-5-nano로
DB에 추가. 기존 `POST /data/news/update`(`app/vendor/news_classifier/crawler.py`)로
시도했으나 **경제 섹션(news.naver.com, sid1=101) 헤드라인만 훑는 구조라 코스닥 소형주
뉴스가 0건**이었다(실측: 최근 크롤링된 1,192건 중 제목/본문 어디에도 "아이씨에이치"
없음). 사용자가 "검색어로 최신순 딥 서치"를 요청해 네이버 뉴스 검색(`search.naver.com`)
기반의 새 크롤 경로를 추가했다.

- `app/vendor/news_classifier/search_crawler.py`(신규): `crawl_search(conn, query, days,
  max_results, workers, progress)`. 검색 결과는 news.naver.com이 아니라 각 언론사
  자체 사이트로 연결되고, 네이버 검색 페이지 자체도 최근 컴포넌트 시스템
  (`fds-*`/`sds-comps-*`)으로 개편돼 클래스명이 빌드마다 바뀌는 해시라 셀렉터로
  기사를 구분할 수 없었다 — 대신 실측으로 확인한 안정적인 속성 조합(`nocr="1"` +
  경로 있음 + naver.com 아님)으로 기사 링크만 골라낸다. 언론사마다 HTML 구조가 달라
  `crawler.py`의 Naver 전용 셀렉터를 재사용할 수 없어, 다수 언론사(뉴스프라임/필드뉴스/
  이코노뉴스/컨슈머타임스/전자신문 등) 표본 조사로 확인한 범용 규칙(og:title/
  og:description + 흔한 본문 셀렉터 후보 목록 + `article:published_time` 메타 우선,
  없으면 본문 텍스트에서 날짜 정규식)으로 제네릭 추출한다. 제목/본문/**날짜** 중
  하나라도 못 찾으면 그 기사는 건너뛴다 — 날짜를 신뢰할 수 없는 기사를 억지로
  포함시키지 않는다(§0-12-1에서 겪은 "발행일시 파싱 실패 시 수집 시점으로 잘못
  채워짐" 사고를 반복하지 않기 위함). `crawler.py`는 그대로 유지(기존 30분 자동
  갱신/`ai.news_signal` 경로 무변경), 완전히 별도 파일로 추가해 회귀 위험을 없앴다.
- `app/cli/ingest_news_search.py`(신규): 위 크롤러 + `pipeline.classify_many`를 묶어
  터미널에서 바로 실행하는 CLI(`python -m app.cli.ingest_news_search --query <검색어>
  --days 8 --model gpt-5-nano`). `app/cli/ingest_prices.py`와 동일한 패턴(앱 컨테이너
  전체를 안 띄우고 필요한 리포지토리만 직접 구성). AI 사용량은 기존 사용량 로그
  (`AIUsageRepository`)에 동일하게 남도록 `newsstock_classifier.set_usage_sink()`를
  독립적으로 재등록.
- **모델/페이지수 1회성 오버라이드**: `Container.news_trader_factory`에 `model:
  str | None = None` 파라미터 추가(§0-19의 `model_override` 패턴과 동일 — 전역
  `openai_model`은 안 바꾸고 이번 팩토리 호출 1건만 다른 모델). `NewsTrader.update()`에
  `max_pages: int | None = None` 파라미터 추가(기존 `days`/`keywords`와 동일한
  1회성 오버라이드 패턴, §0-12). `NewsUpdateRequest`에 `model`/`max_pages` 필드 추가해
  `POST /data/news/update`로도 노출(경제 섹션 크롤을 계속 쓰고 싶은 경우를 위해 유지,
  이번 작업의 주 경로는 아님).
- **실사용 검증**: `crawl_search`를 임시 DB로 소규모 드라이런(15건 후보)해 13건 성공
  수집(진짜 "아이씨에이치" 관련 기사 — 삼성 폴더블 소재 공급 소식, 투자경고종목 지정
  등 실제 매매 판단에 쓸 만한 내용) 확인 후, 실제 `newsstock.db`에
  `--query 아이씨에이치 --days 8 --max-results 100 --model gpt-5-nano`로 본 실행 —
  신규 59건 수집, gpt-5-nano로 전부 분류 완료(pending=0), 이벤트 클러스터 23개가
  "아이씨에이치" 키로 태깅됨(2026-07-21~29). 내용은 김영훈 대표 책임경영 매수(+0.3~0.6),
  갤럭시 Z 폴더블/옵티머스·아틀라스 로봇 소재 공급 확정(+0.3~1.0, 상한가 다수),
  투자경고종목 지정(-0.3, -0.6) 등 실제 주가 변동과 연결되는 사건들로 구성돼 있어
  단순 홍보성 뉴스가 아니라 매매 판단에 쓸 만한 신호임을 확인. `trader.stock("아이씨에이치",
  start="2026-07-21", period=9)`로 조회하면 평균 0.0879(기본 threshold 0.1 미만이라
  판정은 "n" 중립이지만, 최근 3~4일 구간만 좁혀 보면 +1.0대 사건이 몰려 있어 단기
  모멘텀은 뚜렷함) — `ai.news_signal` 노드(axis=종목, code=368600 또는 key=아이씨에이치)로
  워크플로에서 바로 소비 가능한 상태.
- **클러스터링 확인**(사용자 질문에 대한 답): 종목코드(368600)가 아니라 AI가 기사에서
  추출한 종목명 문자열(`stock` 필드, 예: "아이씨에이치")을 키로 `group_a` 테이블에
  들어간다. `app/market_data/symbol_master.py`에 이미 `368600 ↔ 아이씨에이치` 매핑이
  있어(§0-10-1 KOSCOM 동기화로 4,297개 전 종목 확보) `ai.news_signal` 노드가 종목코드만
  받아도 자동으로 이름으로 변환해 같은 키를 조회한다.

**검증**: 백엔드 pytest 372개 전부 통과(기존 `FakeNewsTraderFactory`/
`test_news_signal_node.py` 두 곳이 `news_trader_factory` 시그니처 변경에 맞춰 `model`
키를 추가로 검증하도록 함께 수정). `vue-tsc -b`는 이 작업과 무관(백엔드 전용 변경).

## 0-21. 대시보드 일봉 조회 기간 90일→180일 + Docker 배포 버그 2건 수정 (2026-07-29 사용자 요청)

사용자 요청 두 가지: (1) 대시보드 보유/관심종목 캔들차트가 최근 90일치만 보여주는데
180일로 늘려달라, (2) `npm run build` 후 Docker로 띄우고 `/strategies/new`에서 F5(새로고침)
하면 404가 뜬다 — 원인 확인 후 다른 배포 문제도 같이 점검해달라는 후속 요청.

- **일봉 180일**: `frontend/src/api/services.ts::fetchPrices` 기본값과
  `frontend/src/views/DashboardView.vue::loadPriceSeries`의 호출 인자를 90→180으로,
  백엔드 `GET /data/prices/{symbol}`(`app/api/routers/data.py`)의 `days` 기본값도
  90→180으로 맞춰 변경(호출부가 명시적으로 180을 넘기므로 기본값 자체는 이 흐름에
  직접 영향 없지만, 다른 잠재 호출자를 위해 일관성 있게 맞춤). `PriceChart.vue`는
  캔들스틱 차트라 180개 포인트도 렌더링에 문제없음(차트 라이브러리 자체 스크롤/축
  처리).
- **SPA 새로고침 404**: 원인은 `frontend/Dockerfile`이 `serve dist -l 5173`로
  정적 파일을 서빙하는데, `frontend/src/router/index.ts`가 `createWebHistory()`
  (HTML5 히스토리 모드)를 쓰기 때문. 브라우저 클릭 이동은 Vue Router가 가로채 문제가
  안 보이지만, F5처럼 서버에 실제 요청이 가면 `serve`가 `dist/strategies/new`라는
  실재하지 않는 파일을 찾다 404를 낸다. `serve -s dist`(`-s`/`--single`: 없는 경로를
  전부 `index.html`로 리라이트)로 수정.
- **점검 중 추가로 발견한 배포 버그**: `frontend/Dockerfile`이 `COPY .env ./`로
  존재하지 않는 파일을 복사하려 해, `frontend/.env`가 로컬에 없는 새 클론
  환경에서는 **`docker build` 자체가 실패**하는 문제를 발견(`.env`는
  `frontend/.gitignore`에 등록돼 있어 저장소엔 `.env.development`만 커밋돼 있고
  프로덕션 빌드가 실제로 쓰는 `.env`/`.env.production`은 없음). `frontend/src/api/
  client.ts`에 이미 `VITE_API_BASE_URL` 없을 때의 안전한 기본값(`http://localhost:8000`,
  docker-compose 구성과 정확히 일치)이 있어 그냥 이 `COPY` 줄을 제거(`COPY . .`가
  실제로 존재하는 `.env*`는 알아서 포함하므로 사용자 정의 오버라이드 능력은 그대로
  유지).
- **부가 개선**: `backend/`, `frontend/` 둘 다 `.dockerignore`가 없어 `.venv`
  (macOS 컴파일 바이너리)/`node_modules`가 매번 통째로 빌드 컨텍스트로 올라가던
  문제 확인 → 각각 `.dockerignore` 신규 추가. `backend/Dockerfile`의 apt 캐시 정리
  경로 오타(`/var/lib/apt-get/lists/*` → 올바른 `/var/lib/apt/lists/*`, 원래도
  에러는 안 났지만 정리가 실제로는 아무 효과가 없었음)도 함께 수정.

**검증**: 백엔드 pytest 372개 전부 통과, 프론트 `vue-tsc -b` 통과. Docker 데몬이 이
환경(로컬 개발 세션)에 떠 있지 않아 `docker build`/실제 컨테이너 기동으로는 검증하지
못함 — 논리적 분석(Dockerfile 문법, Vite 환경변수 로딩 순서, `serve` 공식 옵션)으로만
확인했고, 사용자가 재배포 후 최종 확인 필요.

### 0-21-1. 정정 — `serve -s`가 `frontend/public/presentation/` 정적 페이지를 막는 부작용 발견 (2026-07-29 후속)

사용자가 "public/presentation은 /presentation으로 가면 index.html로 가버려서 볼 수
없을 것 같다"고 지적. `vercel/serve`/`serve-handler`의 실제 소스(`main.ts`/`index.js`,
GitHub에서 직접 확인)를 추적한 결과, `-s`/`--single`은 `rewrites: [{source: '**',
destination: '/index.html'}]`를 **최우선 규칙으로 주입**하고, 확장자 없는 경로는
`applyRewrites`가 원래 경로의 실제 파일 존재 여부를 아예 확인하지 않고 rewrite된
목적지(`/index.html`)만 시도하는 것을 확인했다(`findRelated()`가 `rewrittenPath`가
있으면 원래 경로 후보를 아예 안 만듦) — 즉 `-s`는 "실제로 없을 때만 폴백"이 아니라
확장자 없는 요청을 **전부 무조건** `index.html`로 바꿔버려, `/strategies/new` 새로고침
404는 고쳤지만 `public/presentation/index.html`처럼 실재하는 정적 서브패스도 함께
막는 부작용이 있었다.

- `frontend/Dockerfile`을 nginx 기반으로 교체(빌드 스테이지는 기존과 동일하게
  `node:20-alpine`으로 `npm run build`, 런타임 스테이지만 `nginx:alpine`으로 교체).
  `frontend/nginx.conf` 신규 — `location / { try_files $uri $uri/ /index.html; }`.
  nginx의 `try_files`는 "실제 파일 → 실제 디렉토리(index.html) → 폴백" 순서로 실제
  존재를 먼저 확인하므로, `serve -s`가 가진 "무조건 rewrite" 결함 없이 새로고침 404와
  정적 서브패스 접근을 동시에 만족한다. `serve` npm 전역 설치도 더 이상 불필요해 제거.
- **검증**: 이 환경에 Docker 데몬이 없어 실제 컨테이너로 확인하지 못함 —
  `serve-handler`의 `applyRewrites`/`findRelated` 소스 코드를 직접 읽고 로직을
  추적해 원인과 수정 방향을 확인했다(추측이 아니라 실제 GitHub 소스 대조). 사용자가
  재배포 후 `/strategies/new` 새로고침과 `/presentation` 둘 다 정상 동작하는지 최종
  확인 필요.

---

## 1. 목표와 PoC 범위

기획서 전체 기능 중 PoC는 다음에 집중한다.

**포함**
- 노드 기반 워크플로 정의(스케줄러 → 데이터 → 지표 → AI 해석 → 로직 → 리스크 → 실행)
- 위상 정렬 기반 워크플로 실행 엔진 + 트리거 큐 + 워커 풀
- 테스트 실행(임의 값 주입) 및 노드별 디버그 이벤트 스트리밍(프론트 블록 하이라이트)
- 과거 데이터 기반 백테스트(수익률/MDD/승률/손익비/거래횟수)
- AI 자연어 → 워크플로 초안 생성
- DART 공시 AI 점수화 + 캐싱
- 뉴스/공시 등 공공데이터를 sqlite에 적재하여 테스트/백테스트에 사용
- 단일 계정 JWT 인증
- 증권사 연동은 더미 + 인터페이스(Toss 스켈레톤)로 확장 지점만 마련

**제외 (실 서비스 단계로 이연)**
- 실계좌 실주문 연동 검증, 다중 사용자/구독과금/마켓플레이스, 실시간 웹소켓 시세(거래소/증권사 실연동), 정교한 리스크·컴플라이언스 체계, 배포/운영 인프라(쿠버네티스 등)

---

## 2. 전체 아키텍처

```
┌─────────────────────────┐        HTTP/WS        ┌──────────────────────────────────────────┐
│   Frontend (Vue 3)      │ ───────────────────── │   Backend (FastAPI, 단일 프로세스 PoC)     │
│  - 노드 캔버스(Vue Flow) │                        │                                            │
│  - 속성/검증/디버그 패널 │                        │  API 계층 (routers)                        │
│  - 백테스트 결과 차트    │                        │  Auth(JWT) / Workflow / AI / Backtest /    │
└─────────────────────────┘                        │  Data / Runs(WS)                           │
                                                    │                                            │
                                                    │  Workflow 엔진: 파싱→검증→위상정렬→실행     │
                                                    │  Trigger Queue(인터페이스) ← Scheduler      │
                                                    │  Worker Pool(ThreadPoolExecutor)           │
                                                    │  EventBus(인터페이스) → WS 브로드캐스트     │
                                                    │                                            │
                                                    │  Node 레지스트리 (ABC 기반, 플러그형)       │
                                                    │  MarketDataProvider / OrderExecutionProvider│
                                                    │   (인터페이스) — Dummy / Historical / Toss  │
                                                    │  AI 모듈 (OpenAI) — 워크플로 초안, 공시/뉴스 │
                                                    │   점수화(+캐시)                             │
                                                    │  Backtest 엔진                              │
                                                    │  DAO(Repository 인터페이스) → SQLite 구현   │
                                                    └──────────────────────────────────────────┘
                                                                     │
                                                          ┌──────────────────────┐
                                                          │ SQLite (nemo_stock.db)│
                                                          │ + 공공데이터 적재     │
                                                          └──────────────────────┘
```

설계 원칙(기획/지시사항 반영):
1. **인터페이스 우선**: Queue, EventBus, MarketDataProvider, OrderExecutionProvider, Repository는 모두 ABC로 정의하고 PoC 구현체(인메모리/SQLite/더미)를 갈아끼우는 구조. 추후 Redis/Kafka/실증권사/타 RDB로 교체 시 해당 구현체만 추가하면 된다.
2. **노드 = ABC 플러그인**: 모든 노드는 `Node` ABC를 상속. 레지스트리에 등록되며, 프론트 노드 팔레트는 백엔드 레지스트리를 조회해 동적으로 구성된다(새 노드 추가 시 프론트 수정 불필요).
3. **동일 실행 경로**: 라이브 실행/테스트 실행/백테스트가 동일한 `WorkflowEngine.execute()`를 사용하고, 데이터 소스(Provider)만 모드에 따라 교체된다. → 백테스트에서 검증한 로직이 실행 시점에도 동일하게 동작함을 보장.
4. **분리 가능한 배치 프로세스**: 스케줄러/워커는 FastAPI 프로세스 내 백그라운드 스레드로 시작하지만, `backend/app/batch/` 패키지로 격리하여 `python -m app.batch.worker`로 별도 프로세스 실행이 가능하도록 구성. 단, 현재 `InMemoryTriggerQueue`는 프로세스 경계를 넘지 못하므로 진짜 분리 실행은 Queue를 Redis 등으로 교체한 이후에 의미가 있음(문서화해 둠).

---

## 3. 노드 시스템

### 3.1 Node ABC

```python
# app/nodes/base.py
class NodeContext:
    run_id: str
    mode: Literal["live", "test", "backtest"]
    timestamp: datetime
    symbols: dict[str, dict[str, Any]]   # 종목코드 -> 누적 데이터(가격, 지표, 점수 등)
    meta: dict[str, Any]                 # 스케줄 정보, 사용자 오버라이드 값 등

class NodeParam(TypedDict):
    key: str; type: str; label: str; default: Any; required: bool  # 프론트 속성 패널 자동 생성용

class Node(ABC):
    type: ClassVar[str]          # 예: "data.price", "logic.if_else"
    category: ClassVar[str]      # scheduler|data|indicator|ai|logic|risk|execution
    display_name: ClassVar[str]
    description: ClassVar[str] = ""  # 역할 + symbols 입출력 키 설명(아래 참조)
    param_schema: ClassVar[list[NodeParam]]

    def __init__(self, node_id: str, params: dict[str, Any]): ...

    @abstractmethod
    def execute(self, context: NodeContext, inputs: list[NodeContext]) -> NodeContext:
        """inputs: 선행 노드(들)의 출력 컨텍스트. 반환값이 다음 노드로 전달된다."""

    def validate_params(self) -> list[str]:
        """오류 메시지 리스트 반환(빈 리스트=정상). 기본 구현은 param_schema 기반 필수값 체크."""
```

레지스트리:
```python
NODE_REGISTRY: dict[str, type[Node]] = {}
def register_node(cls: type[Node]) -> type[Node]:
    NODE_REGISTRY[cls.type] = cls
    return cls
```
`GET /nodes` 엔드포인트가 `NODE_REGISTRY`를 순회해 `type/category/display_name/description/param_schema`를 JSON으로 반환 → 프론트 노드 팔레트(툴팁)/속성 패널이 이를 렌더링. `description`은 각 노드가 `NodeContext.symbols`에서 무엇을 읽고 무엇을 쓰는지(입력/출력 키)까지 구체적으로 적어야 한다 — `app/ai/workflow_draft.py`/`app/ai/workflow_chat.py`가 `node_registry_schema()`를 그대로 AI 프롬프트에 주입하므로, 여기 적힌 문장이 AI가 노드 역할을 이해하는 유일한 근거다. 필수값은 아니며(빈 문자열 허용) 노드 추가 시 채워 넣는 것을 원칙으로 한다.

**포트폴리오 자동 주입 변수** (§0-3): `WorkflowEngine.execute()`가 런 시작 시점에 `broker.get_balance()`/`get_positions()`를 1회 조회해, 각 노드의 출력 컨텍스트가 만들어질 때마다 `symbols[code]`에 아직 없는 경우에 한해 `held_qty`(보유수량)/`held_avg_price`(평단가)/`cash`(현금)/`equity`(평가자산)를 채워 넣는다(`meta.cash`/`meta.equity`에도 동일 값 기록). 어떤 노드도 이 값을 배선하지 않으며, `logic.if_else`의 `expr`(`simpleeval`, `names=dict(symbols[code])`)에서 바로 참조 가능하다(예: `held_qty == 0 and cash > price * 10`). 값은 런 시작 시점 스냅샷이므로 해당 런 자신이 실행 도중 발생시킨 주문으로는 바뀌지 않는다 — `node_registry_schema()`에는 나타나지 않는 암묵적 변수이므로 AI 프롬프트(§7.2, §7.5)에 별도 문구로 고지한다.

**판단(judgment) 로그** (§0-4): 종목을 걸러내는 필터형 노드(`logic.if_else`/`logic.rank`/`risk.stop_loss`/조건 내장 지표 노드, §3.2)는 탈락 종목 코드 목록만 남기는 `meta.filtered_out[node_id]`와 별개로, 종목별 통과/탈락 근거를 `meta.decisions[node_id][symbol] = {"pass": bool, "reason": str, "metrics"?: dict}` 형태로 함께 기록한다. `NodeContext.snapshot()`이 `meta`를 그대로 실어 `NodeExecutionEvent.output_snapshot`으로 발행하므로 엔진 수정 없이 각 노드만 이 값을 채우면 되고, 프론트 `DebugPanel.vue`가 "테스트 실행" 결과에서 이를 종목별 판단 테이블(통과✅/탈락⛔ + 사유)로 렌더링한다.

### 3.2 PoC 기본 제공 노드 목록

| 카테고리 | type | 설명 |
| --- | --- | --- |
| scheduler | `scheduler.interval` | 주기(초) 트리거. 무료=60s 하한, 프로=1s 하한 (params로 강제) |
| data | `data.price` | 현재가/시세 조회 (MarketDataProvider) |
| data | `data.volume` | 거래량/거래대금 조회 |
| data | `data.news` | 종목 관련 최근 뉴스 조회(sqlite 적재분) |
| data | `data.disclosure` | 종목 관련 최근 공시 조회(OpenDART 적재분) |
| data(조건 내장, §0-6) | `data.sector_momentum`/`data.sector_linked_impact`/`data.sector_momentum_change`/`data.sector_buzz` | 뉴스 신호 — 섹터 단위 지표(모멘텀/업종 연관 영향/모멘텀 가속도/버즈 Z-Score), fork 포트, `app/nodes/conditions.py` 프리셋 |
| data(조건 내장, §0-6) | `data.macro_risk`/`data.macro_sentiment` | 뉴스 신호 — 매크로 공포지수/거시 심리지수(국내·해외) |
| data(조건 내장, §0-6) | `data.theme_zscore` | 뉴스 신호 — 테마 쏠림 Z-Score |
| data(조건 내장, §0-6) | `data.sentiment_ratio`/`data.event_density` | 뉴스 신호 — 감성 우위도(Bull-Bear)/이벤트 밀도(국면 탐지) |
| data(조건 내장, §0-6) | `data.symbol_news_score`/`data.symbol_direct_impact` | 뉴스 신호 — 종목별 뉴스 점수/직접 영향도(정규화) |
| indicator | `indicator.moving_average` | 이동평균 계산(값만 계산, 필터링 없음) |
| indicator | `indicator.rsi` | RSI 계산(값만 계산, 필터링 없음) |
| indicator | `indicator.momentum` | 모멘텀(N일 수익률) 계산(값만 계산, 필터링 없음) |
| indicator | `indicator.custom_formula` | 사용자 수식(안전한 표현식 평가, `simpleeval` 등 사용) — 미구현 |
| indicator(조건 내장, §0-4) | `indicator.sma`/`indicator.ema`/`indicator.macd` | 추세 — 계산+조건 판정을 자체 완결하는 필터형 노드(logic.if_else 내장) |
| indicator(조건 내장, §0-4) | `indicator.rsi_signal`/`indicator.period_return` | 모멘텀 — 위와 동일한 필터형 노드 |
| indicator(조건 내장, §0-4) | `indicator.volatility`/`indicator.bollinger`/`indicator.atr_stop` | 변동성 — 위와 동일한 필터형 노드 |
| indicator(조건 내장, §0-4) | `indicator.high_52w` | 가격 위치(52주 최고가 대비 낙폭) — 위와 동일한 필터형 노드 |
| indicator(조건 내장, §0-4) | `indicator.mdd` | 위험(최대낙폭) — 위와 동일한 필터형 노드 |
| indicator(조건 내장, §0-4) | `indicator.volume_ratio`/`indicator.volume_zscore` | 거래량 — 위와 동일한 필터형 노드 |
| ai | `ai.sentiment_score` | 뉴스/공시 텍스트 감성 점수화(캐시 적용) |
| ai | `ai.regime` | 시장 국면 판단(상승/하락/횡보) — 보조 판단용 |
| ai(조건 내장, §0-5) | `ai.news_signal` | 뉴스 신호(종목/섹터/거시경제) — `koscom-mini-project-4/newsstock-lib`(vendored) 기반, t/n/f 판정을 필터링(logic.if_else 내장) + news_true(bool) 출력 |
| ai(조건 내장, §0-9) | `ai.free_prompt` | 자유 프롬프트 판단 — 사용자가 프롬프트/참고자료를 직접 작성, `{{키}}`로 앞 노드 데이터 자동 치환 또는 AI가 뉴스/가격 조회 도구를 스스로 호출(택1), pass/opinion/confidence/reason 출력 + 필터링 |
| logic | `logic.if_else` | 조건식 분기 (True 경로만 컨텍스트 전달) |
| logic | `logic.filter` | 종목 목록 필터링 |
| logic | `logic.rank` | 조건별 상위 N 랭킹 |
| logic | `logic.switch` | 다중 분기 |
| risk | `risk.stop_loss` | 손절 기준 적용 |
| risk | `risk.position_limit` | 종목당/전략당 투자 한도 적용 |
| execution | `execution.market_order` | 시장가 매수/매도 (OrderExecutionProvider) |
| execution | `execution.limit_order` | 지정가 주문 |

각 노드는 `app/nodes/<category>/<name>.py`에 1노드 1파일로 구현하고 단위 테스트를 병행한다.

---

## 4. 워크플로 정의/실행 엔진

### 4.1 워크플로 JSON 스키마 (프론트-백엔드 공통)
```json
{
  "id": "wf_123",
  "name": "긍정뉴스+거래량 급증 매수",
  "nodes": [
    {"id": "n1", "type": "scheduler.interval", "params": {"interval_sec": 60}},
    {"id": "n2", "type": "data.price", "params": {"universe": "KOSPI_TOP100"}},
    {"id": "n3", "type": "logic.if_else", "params": {"expr": "volume_ratio > 2.0"}},
    {"id": "n4", "type": "data.news", "params": {}},
    {"id": "n5", "type": "ai.sentiment_score", "params": {"threshold": 0.6}},
    {"id": "n6", "type": "execution.market_order", "params": {"side": "buy", "qty_pct": 0.1}}
  ],
  "edges": [
    {"from": "n1", "to": "n2"}, {"from": "n2", "to": "n3"},
    {"from": "n3", "to": "n4", "branch": "true"}, {"from": "n4", "to": "n5"},
    {"from": "n5", "to": "n6", "branch": "true"}
  ]
}
```

### 4.2 검증 & 위상 정렬
`app/workflow/graph.py`
1. 스케줄러 노드는 정확히 1개, 진입 간선 없음(root).
2. 사이클 존재 시 오류(카안 알고리즘으로 위상 정렬 시도 중 큐가 비면 사이클로 판단).
3. 모든 노드는 스케줄러로부터 도달 가능해야 함(고아 노드 경고).
4. 결과: 실행 순서 리스트(위상 정렬 순서) — 워크플로 저장/활성화 시 1회 계산 후 캐시, 그래프 변경 시에만 재계산.

### 4.3 실행 (`app/workflow/engine.py`)
```python
class WorkflowEngine:
    def execute(self, workflow: WorkflowDef, mode: str, trigger_meta: dict,
                overrides: dict[str, Any] | None, market_data: MarketDataProvider,
                broker: OrderExecutionProvider, event_bus: EventBus) -> RunResult:
        order = workflow.topological_order()
        ctx_by_node: dict[str, NodeContext] = {}
        for node_id in order:
            node = workflow.get_node(node_id)
            inputs = [ctx_by_node[p] for p in workflow.predecessors(node_id) if predecessor_branch_matches]
            event_bus.publish(NodeExecutionEvent(run_id, node_id, status="running", ...))
            try:
                if overrides and node_id in overrides:      # 테스트 모드 임의 값 주입
                    out_ctx = node.apply_override(inputs, overrides[node_id])
                else:
                    out_ctx = node.execute(merge(inputs), providers=(market_data, broker))
                ctx_by_node[node_id] = out_ctx
                event_bus.publish(NodeExecutionEvent(..., status="success", output=out_ctx.snapshot()))
            except Exception as e:
                event_bus.publish(NodeExecutionEvent(..., status="error", error=str(e)))
                raise
        return RunResult(...)
```
- **다중 입력 병합**: 여러 선행 노드를 갖는 노드는 각 입력 컨텍스트의 `symbols` 딕셔너리를 종목코드 기준 병합(동일 키는 최신 값으로 덮어쓰되 이력은 `meta.history`에 append)한다.
- **분기(IF/Switch)**: 조건 불충족 경로는 하위 노드로 전파하지 않음(해당 하위 노드는 "skipped" 이벤트 발행) → 프론트에서 회색 처리로 표현 가능.
- **테스트 모드 오버라이드**: `POST /workflows/{id}/run {mode:"test", overrides:{"n2": {"005930": {"price": 71000}}}}` 형태로 특정 데이터 노드의 출력값을 사용자가 직접 지정 가능 (기획 요구사항 "임의의 값들을 사용해서 테스트").

### 4.4 이벤트 버스 (디버그 하이라이트)
```python
class EventBus(ABC):
    def publish(self, event: NodeExecutionEvent) -> None: ...
    def subscribe(self, run_id: str) -> Iterator[NodeExecutionEvent]: ...
class InMemoryEventBus(EventBus): ...  # asyncio.Queue per run_id
```
`WS /ws/runs/{run_id}`가 `EventBus.subscribe`를 소비해 프론트로 push → 프론트는 이벤트 수신 시 해당 노드를 즉시 하이라이트(깜빡임)하고 입력/출력 JSON을 디버그 패널에 표시. 모든 이벤트는 `node_events` 테이블에도 적재되어 실행 종료 후 "리플레이"가 가능하다(백테스트 결과 화면에서도 동일 컴포넌트 재사용).

---

## 5. 트리거 큐 / 스케줄러 / 워커 풀

### 5.1 인터페이스
```python
# app/trigger/queue.py
class TriggerQueue(ABC):
    def put(self, trigger: Trigger) -> None: ...
    def get(self, timeout: float | None = None) -> Trigger | None: ...
    def task_done(self, trigger: Trigger) -> None: ...

class InMemoryTriggerQueue(TriggerQueue):
    """queue.Queue 기반 PoC 구현. 추후 RedisTriggerQueue/KafkaTriggerQueue로 교체 가능."""
```

### 5.2 스케줄러 서비스
- 백그라운드 스레드(`SchedulerService`)가 1초 tick마다 `status=active`인 워크플로들을 순회, `next_fire_time <= now`이면 `Trigger(workflow_id, run_id=uuid4(), fired_at=now)`를 큐에 push하고 `next_fire_time += interval_sec` 갱신.
- **라이브 더미 시세**: `DummyMarketDataProvider`가 각 종목의 최근 종가(sqlite `price_bars`의 최신 일봉)를 시드로 삼아 초 단위 랜덤워크(seed 고정 가능)로 현재가를 생성 → 1초 스케줄러 테스트가 가능하게 함. 실제 서비스 연동 시 `TossInvestMarketDataProvider`로 교체.

### 5.3 워커 풀
- `ThreadPoolExecutor(max_workers=settings.WORKER_POOL_SIZE)`가 큐를 폴링하며 `WorkflowEngine.execute()` 호출.
- 노드 실행 자체는 프로세스/스레드 경계와 무관하게 순수 함수로 작성 → 추후 `ProcessPoolExecutor`로 교체 시 노드 입출력(NodeContext)이 pickle 가능해야 함(dict/기본타입만 사용하도록 강제).
- 워커는 실행 완료 후 `runs`, `node_events`, (실행 노드가 있으면) `orders` 테이블에 결과 기록.

### 5.4 배치 프로세스 분리 지점
`app/batch/worker.py`에 `SchedulerService` + 워커 풀 부트스트랩 로직을 두고, FastAPI `main.py`의 `startup` 이벤트에서 동일 함수를 호출하는 방식으로 구성 → 나중에 `python -m app.batch.worker`로 별도 프로세스 기동 시 API 서버와 분리 가능(단, Queue를 프로세스 간 공유 가능한 구현으로 교체해야 실질적 분리 효과가 있음을 §2 원칙 4에 명시).

---

## 6. 마켓데이터 / 주문 실행 어댑터

```python
# app/market_data/base.py
class MarketDataProvider(ABC):
    def get_price(self, symbol: str) -> PriceTick: ...
    def get_orderbook(self, symbol: str) -> OrderBook: ...
    def get_ohlcv(self, symbol: str, start: date, end: date) -> list[Bar]: ...

# app/broker/base.py
class OrderExecutionProvider(ABC):
    def place_order(self, order: OrderRequest) -> OrderResult: ...
    def cancel_order(self, order_id: str) -> None: ...
    def get_balance(self) -> Balance: ...
    def get_positions(self) -> list[Position]: ...
```

구현체:
| 구현체 | 용도 |
| --- | --- |
| `DummyMarketDataProvider` | 라이브/테스트 모드. sqlite 일봉 시드 + 랜덤워크로 초단위 시세 생성 |
| `HistoricalMarketDataProvider` | 백테스트 모드. sqlite `price_bars`를 날짜순으로 리플레이 |
| `TossInvestMarketDataProvider` | **스켈레톤(미검증)**. OAuth2 Client Credentials 토큰 발급 + 시세/호가/캔들 REST 호출부만 구현, `.env`에 키 없으면 초기화 시 명시적으로 비활성 처리 |
| `DummyOrderExecutionProvider` | 모의 체결(현재가 즉시 체결), 현금/포지션은 **순수 인메모리**(인스턴스 생명주기 동안만 유지) — 백테스트 전용, 매 백테스트마다 `initial_capital`로 새로 생성되어 독립적으로 시작(§0-3, §8) |
| `PersistentOrderExecutionProvider` | 모의 체결 계산은 `DummyOrderExecutionProvider`와 동일(`app/broker/fill_logic.py::apply_fill` 공유)하되, 현금/포지션을 매 체결마다 `PortfolioRepository`(sqlite `portfolio_cash`/`portfolio_positions`)에서 읽고 다시 써서 서버 재시작에도 유지 — 라이브/테스트(컨테이너 싱글턴 broker) 전용(§0-3) |
| `TossInvestOrderExecutionProvider` | **스켈레톤(미검증)**. 주문 생성/취소/조회 REST 호출부만 구현 |

Provider 선택은 `app/config.py`의 `MARKET_DATA_PROVIDER=dummy|historical|toss`, `ORDER_PROVIDER=dummy|toss` 환경변수로 결정하며, 실행 모드(live/test/backtest)에 따라 엔진이 자동으로 적절한 Provider를 주입한다(backtest는 항상 historical+dummy 강제, 라이브/테스트는 `ORDER_PROVIDER=dummy`면 `PersistentOrderExecutionProvider`).

백테스트 시세 자동 수집(네이버 차트 API로 일봉+시간봉 확보)은 §8-1 참조.

---

## 7. AI 모듈

### 7.1 공통
- `app/ai/openai_client.py`: `OPENAI_API_KEY`는 백엔드 `.env`에서만 읽음. 프론트는 AI 관련 API를 백엔드 라우터(`/ai/*`)로만 호출하며 키를 전달/노출하지 않음.
- 모든 AI 응답은 `model`, `prompt_version`을 함께 기록해 캐시 키에 포함(프롬프트 개선 시 캐시 무효화 자동 처리).
- 기본 모델은 `OPENAI_MODEL=gpt-5.6-luna`(§0-1). `chat.completions.create` 호출이 `temperature` 관련 `BadRequestError(param="temperature")`를 받으면 `temperature` 없이 1회 재시도 — gpt-5 계열 reasoning 모델은 기본값(1) 외의 temperature를 지원하지 않기 때문(모델 자체를 하드코딩해 분기하지 않고 오류 기반으로 대응해 향후 모델 교체에도 견고함).

### 7.5 캔버스 통합 챗봇 (`app/ai/workflow_chat.py`, `POST /ai/workflow-chat`)
1. 요청에 현재 워크플로 이름/그래프, 사용자 메시지, 최근 대화 이력(최대 12개), (있으면) 마지막 테스트 실행 결과(`status`/`events`/`final_symbols`)를 포함.
2. 시스템 프롬프트가 AI에게 요청을 "그래프 수정 지시" vs "구조/실행 결과 설명 질문" 중 하나로 분류하도록 지시하고, 응답 JSON의 `changed` 불리언으로 결과를 구분.
3. `changed=false`: `reply` 텍스트만 그대로 반환(그래프 검증 생략, 순수 Q&A).
4. `changed=true`: 응답의 `nodes`/`edges`를 `WorkflowGraph.validate()`로 검증(§4.2). 실패 시 오류를 포함해 1회 재시도, 그래도 실패하면 422로 원문+오류 반환(§7.2 초안 생성과 동일 패턴). 성공 시 `graph`+`disclaimer`를 함께 반환하되 **저장/캔버스 반영은 하지 않음** — 프론트가 미리보기로 보여주고 사용자가 "적용"해야 `flowNodes`/`flowEdges`에 반영(§0-1).

### 7.2 자연어 → 워크플로 초안 생성 (`app/ai/workflow_draft.py`)
1. 시스템 프롬프트에 `NODE_REGISTRY`의 사용 가능한 노드 타입/파라미터 스키마를 주입.
2. OpenAI Structured Output(`response_format={"type":"json_schema", ...}`)으로 §4.1 워크플로 JSON 스키마에 맞는 draft 생성 요청.
3. 생성된 JSON을 `WorkflowGraph` 검증기(§4.2)에 통과시킴. 실패 시 오류 메시지를 프롬프트에 포함해 1회 자동 재시도, 그래도 실패하면 사용자에게 원문 응답 + 오류를 함께 반환(수동 수정 유도).
4. 결과는 **자동 저장/활성화하지 않고** `status=draft`로 반환 — 사용자가 캔버스에서 검토 후 저장해야 함(기획서 "위험 고지" 요건 반영).

### 7.3 DART 공시 점수화 (`app/ai/disclosure_scoring.py`)
1. `data_ingestion/opendart_client.py`가 종목별 최근 공시 목록/원문을 가져와 `disclosures` 테이블에 적재.
2. `ai.sentiment_score`류 노드나 배치 작업이 공시를 스코어링할 때, 먼저 `ai_score_cache(subject_type='disclosure', subject_id=rcept_no, prompt_version, model)`를 조회.
3. 캐시 미스일 때만 OpenAI 호출 → 점수/요약 JSON을 캐시에 저장. 캐시 히트 시 AI 호출 없이 즉시 반환 → **AI 사용량 최소화** 요건 충족.

### 7.4 뉴스 감성 노드
동일한 캐시 전략을 `subject_type='news'`로 적용(§7.3과 로직 공유, `app/ai/scoring_cache.py`로 공통화).

---

## 8. 백테스트 엔진

`app/backtest/runner.py`
- 입력: `workflow_id`, 종목 유니버스, 시작/종료일, 초기자본, (선택) 리플레이 주기(일봉 기준 1일 1틱이 기본; 인트라데이는 PoC 범위 밖).
- `HistoricalMarketDataProvider`가 날짜를 순회하며 각 날짜를 하나의 트리거처럼 `WorkflowEngine.execute(mode="backtest")`에 공급.
- `DummyOrderExecutionProvider`가 각 날짜 종가 기준으로 가상 체결, 손익/보유내역을 누적.
- 종료 후 `app/backtest/metrics.py`가 계산:
  - 누적수익률/연환산수익률(CAGR)
  - 최대낙폭(MDD)
  - 승률, 손익비, 거래횟수, 변동성(일간 수익률 표준편차)
  - 자산곡선(equity curve, 시계열)
- 결과는 `backtest_results` 테이블에 저장, 노드 실행 이벤트도 `node_events`에 남아 프론트에서 "특정 시점 재생" 가능(§8-2).

### 8-1. 백테스트 자동 시세 수집 (`app/data_ingestion/naver_price_client.py`, `auto_ingest.py`)

`POST /backtest` 라우터가 `BacktestRunner` 실행 전, `universe`의 각 종목에 대해 요청 구간의
일봉이 하나도 없으면(§0-2) `NaverStockChartClient`로 일봉+시간봉을 수집해 각각
`price_bars`/`price_bars_intraday`에 저장한다(`ensure_price_data`). 일봉 수집이 실패하면
오류를 기록하고 계속 진행(이후 `BacktestRunner`가 데이터 없음으로 400 처리), 시간봉 수집
실패는 조용히 무시(백테스트 자체는 일봉만 필요).

`NaverStockChartClient`는 `stock.naver.com`이 프론트엔드에서 쓰는 비공식 공개 엔드포인트를
호출한다(별도 키/인증 불필요, 2026-07-22 실측 확인). `day`(일봉)는 기간 제한 없이 응답하지만,
`minute60`(시간봉)은 요청한 시작일과 무관하게 서버가 최근 영업일 기준 제한된 lookback만
반환한다(실측 약 8거래일치 56봉) — 오래된 시간봉은 이 소스로 확보할 수 없다는 한계를 인지하고
사용해야 한다.

터미널에서 수동으로 미리 적재하고 싶으면 `backend/app/cli/ingest_prices.py`를 직접 실행한다:
```bash
cd backend && ./.venv/bin/python -m app.cli.ingest_prices --symbol 005930,000660 --start 2026-06-01 --end 2026-07-20
```

### 8-2. 일자별 노드 그래프 재생 (§0-3)

`BacktestRunner`는 거래일마다 별도의 `run_id`를 생성해 `WorkflowEngine.execute(mode="backtest",
run_id=...)`에 넘기고, 실행 직후 `WorkerPool`(§5.3)과 동일한 방식으로 `RunRecord`(`mode="backtest"`)
+ 해당 run의 `NodeEventRecord`들을 저장한다(공용 헬퍼: `app/workflow/run_persistence.py::events_to_records`).
`BacktestResult.daily_runs`(날짜→run_id 목록)가 `backtest_results.daily_runs_json`에 함께 저장된다.

`GET /workflows/{workflow_id}/runs/{run_id}`(라이브/테스트/백테스트 run 공용 조회 엔드포인트)로
특정 날짜의 노드 실행 이벤트를 가져와, 프론트 `BacktestResultView.vue`가 "테스트 실행"과 동일한
`VueFlow` 캔버스 + `DebugPanel.vue` 조합으로 재생한다(날짜 `<select>`로 전환).

### 8-3. 매매 시점 시각화 + AI 진단/수정 제안 (2026-07-27 사용자 확인)

백테스트 결과 화면에서 매수/매도 시점을 그래프 위에 점으로 표시하고, 그 시점(또는 매매가 없는
구간)을 선택해 AI에게 "왜 이렇게 매매했는지/왜 매매가 없었는지"를 묻고 필요하면 수정 제안까지
받을 수 있어야 한다는 요청에 따라 추가.

**매매 시점 데이터**: `OrderResult.filled_at`은 실제 벽시계 시각(시뮬레이션 날짜 아님)이라
`BacktestRunner.run()`이 거래일 루프마다 `len(broker.orders)` 증가분을 그 날짜로 직접 태깅해
`BacktestResult.trades: list[(date, run_id, OrderResult)]`에 쌓는다. `BacktestResultRecord`에
`universe`/`trades`(JSON) 필드를 추가했고, 기존 `daily_runs_json` 때와 동일하게
`_add_missing_columns()`(§ DB 스키마 진화, `database.py`)가 컬럼을 자동 보정하므로 별도
마이그레이션이 필요 없었다.

**시세/보조지표**: 새 엔드포인트 `GET /backtest/{id}/prices?symbol=`이 해당 종목의 `price_bars`
OHLCV를 그대로 반환한다. 이동평균(5/20/60)·볼린저밴드(20, 2σ)·RSI(14)는 별도 데이터 수집/저장
없이 프론트(`frontend/src/utils/indicators.ts`)에서 종가만으로 계산한다 — 호가/체결 등 별도
데이터가 없어도 이미 있는 일봉 OHLCV(거래량 포함)로 계산 가능한 지표만 포함하기로 확정.

**뉴스 표시**: 두 계층으로 분리했다(사용자 확정 사항).
- `GET /backtest/{id}/news/used?symbol=` — 그 백테스트 실행 중 `data.news` 노드가 실제로 조회한
  뉴스만(`NodeEventRecord.output_json.symbols[symbol].news_id`를 `NewsRepository.get()`으로 복원),
  기본으로 표시되고 `/ai/backtest-explain`의 근거 데이터에도 포함된다.
- `GET /backtest/{id}/news/all?symbol=` — 워크플로 사용 여부와 무관하게 `news` 테이블 해당 기간
  전체(`NewsRepository.list_range()` 신규 메서드), 프론트 체크박스를 켰을 때만 옅게 추가 표시되는
  부가 기능이며 "무거우니" AI 프롬프트에는 포함하지 않는다.

**AI 진단/수정 제안**: `app/ai/backtest_explain.py::explain_backtest()`가
`app/ai/workflow_chat.py::chat_about_workflow()`와 동일한 계약(reply/changed/name/graph/disclaimer,
`changed=true`면 `WorkflowGraph.validate()` 검증 후 실패 시 1회 재시도)을 따르므로 프론트가 같은
"미리보기 후 적용" UI 패턴을 재사용할 수 있다. `POST /ai/backtest-explain`(`app/api/routers/ai.py`)이
`backtest_id`+`selection`(kind=point|range, symbol, 날짜/구간)을 받아 그 구간의 거래 내역·노드 실행
요약(전체 input/output 스냅샷 대신 `{node_id, node_type, status, symbols, filtered_out, orders}`로
축약해 프롬프트 크기 억제)·종가 시계열·"참고한 뉴스"를 조립해 넘긴다. 백테스트 결과 화면에는 저장할
캔버스가 없으므로, 수정 제안은 "적용" 대신 "전략 빌더에서 열기" 버튼으로 `draftStore`(신규
`targetWorkflowId` 필드)에 담아 `/strategies/{workflow_id}`로 이동시키고, `StrategyBuilderView.load()`
가 기존 워크플로 로드 후 그 draft가 자신을 대상으로 하면 캔버스에 덮어써 보여준다(저장은 사용자가
직접 — 미리보기 후 적용 원칙 유지).

**프론트 차트**(`frontend/src/components/BacktestChart.vue`, `EquityCurveChart.vue` 대체): Chart.js를
`<script setup>`에서 직접 `new Chart()`로 생성해(vue-chartjs 래퍼 대신) 듀얼축(자산/시세)에 매매
scatter(매수=녹색 삼각형-up, 매도=빨강 삼각형-down)·뉴스 마커·MA/볼린저 라인을 함께 그리고, RSI·
거래량은 같은 x축 라벨을 공유하는 보조 서브차트로 배치한다. 드래그 구간 선택은 별도 플러그인 없이
캔버스에 mousedown/mousemove/mouseup을 직접 붙여 `chart.scales.x.getValueForPixel()`로 픽셀↔날짜
인덱스를 변환하고 절대위치 오버레이 `<div>`로 표시하며, 매매 마커 클릭은
`chart.getElementsAtEventForMode(..., intersect:true)`로 판별해 드래그와 구분한다.

---

## 9. DAO / 데이터베이스

### 9.1 Repository 패턴
```python
class WorkflowRepository(ABC):
    def get(self, id: str) -> WorkflowDef | None: ...
    def save(self, wf: WorkflowDef) -> None: ...
    def list_by_user(self, user_id: str) -> list[WorkflowDef]: ...
# 동일 패턴: RunRepository, NodeEventRepository, PortfolioRepository, BacktestResultRepository,
#            PriceBarRepository, DisclosureRepository, NewsRepository, AIScoreCacheRepository, UserRepository
```
- SQLite 구현체: `app/dao/sqlite/*` (SQLAlchemy 2.0 ORM, 파일 `nemo_stock.db`). 다른 RDB(Postgres 등) 전환 시 `DATABASE_URL`만 변경 + 방언 차이가 있는 부분만 조정.
- 인메모리 구현체: `app/dao/memory/*` (dict 기반). 휘발성 테스트 실행(저장 불필요한 단발 테스트 run)이나 유닛테스트에서 사용, 동일 ABC를 구현하므로 서비스 계층은 구현체를 몰라도 됨.
- 어떤 구현체를 쓸지는 DI(간단한 팩토리 함수 + FastAPI `Depends`)로 주입.

### 9.2 주요 테이블
```
users(id, username, password_hash, created_at)
workflows(id, user_id, name, graph_json, status, schedule_interval_sec, created_at, updated_at)
runs(id, workflow_id, mode, status, started_at, finished_at)
node_events(id, run_id, node_id, node_type, status, input_json, output_json, error, started_at, finished_at)
portfolio_cash(user_id PK, cash, updated_at)  -- §0-3, PersistentOrderExecutionProvider 전용
portfolio_positions(id, user_id, symbol, qty, avg_price, updated_at, UNIQUE(user_id, symbol))  -- §0-3
backtest_results(id, run_id, workflow_id, start_date, end_date, initial_capital, final_equity,
                  cagr, mdd, win_rate, profit_loss_ratio, trade_count, equity_curve_json,
                  daily_runs_json, universe_json, trades_json)
                  -- daily_runs_json: [{"date":..., "run_id":...}, ...] (§8-2)
                  -- universe_json: ["005930", ...], trades_json: [{"date":..., "run_id":..., "order_id":...,
                  --   "symbol":..., "side":..., "qty":..., "price":..., "status":..., "reason":...,
                  --   "realized_pnl":...}, ...] (§8-3)
price_bars(symbol, date, open, high, low, close, volume, source, PRIMARY KEY(symbol, date))
price_bars_intraday(symbol, bar_datetime, interval, open, high, low, close, volume, source,
                     PRIMARY KEY(symbol, bar_datetime, interval))  -- §8-1, 네이버 시간봉(minute60)
disclosures(id, corp_code, symbol, rcept_no, title, disclosed_at, raw_text, source)
news(id, symbol, title, body, published_at, source)
ai_score_cache(id, subject_type, subject_id, prompt_version, model, score_json, created_at,
                UNIQUE(subject_type, subject_id, prompt_version, model))
```

---

## 10. 인증

- 단일 계정: 서버 최초 기동 시 `.env`의 `ADMIN_USERNAME`/`ADMIN_PASSWORD`(또는 해시)로 `users` 테이블에 1건 upsert.
- `POST /auth/login` → JWT(HS256, `JWT_SECRET` 환경변수) 발급, 만료시간 설정.
- 이후 모든 API(`/workflows`, `/ai`, `/backtest`, `/data`, WS 포함)는 `Authorization: Bearer <token>` 필요(FastAPI dependency).
- 프론트는 로그인 화면 → 토큰을 메모리(+`sessionStorage`)에 보관, axios interceptor로 자동 첨부.

---

## 11. API 설계 (요약)

| Method | Path | 설명 |
| --- | --- | --- |
| POST | /auth/login | 로그인, JWT 발급 |
| GET | /nodes | 노드 레지스트리(팔레트/속성 스키마) |
| GET/POST | /workflows | 목록/생성 |
| GET/PUT/DELETE | /workflows/{id} | 조회/수정/삭제 |
| POST | /workflows/{id}/validate | 그래프 검증(사이클/고아노드 등) |
| POST | /workflows/{id}/run | 테스트 실행(overrides 지원), run_id 반환 |
| POST | /workflows/{id}/activate / /deactivate | 라이브 스케줄 on/off |
| GET | /runs/{id} | 실행 요약 + 노드 이벤트 로그 |
| WS | /ws/runs/{id} | 실시간 노드 이벤트 스트림(디버그 하이라이트) |
| POST | /ai/generate-draft | 자연어 → 워크플로 초안 |
| POST | /backtest | 백테스트 실행 요청(비동기, run_id 반환) |
| GET | /backtest/{id} | 결과 조회(지표+자산곡선+거래내역) |
| POST | /data/ingest/prices | 공공데이터포털 일봉 수집→sqlite 적재(관리용) |
| POST | /data/ingest/disclosures | OpenDART 공시 수집→sqlite 적재(관리용) |

---

## 12. 프론트엔드 설계

- **스택**: Vue 3 + Vite + TypeScript, 상태관리 Pinia, 그래프 캔버스 **Vue Flow**(`@vue-flow/core`), 차트는 경량 라이브러리(자산곡선 등)로 Chart.js 사용, HTTP는 axios, 실시간은 네이티브 WebSocket.
- **화면 구성**:
  1. 로그인
  2. 대시보드(워크플로 목록, 상태, 빠른 실행)
  3. AI 전략 생성(자연어 입력 → 초안 미리보기 → "캔버스에서 편집" 이동, 위험 고지 문구 표시)
  4. 전략 빌더(캔버스 = 핵심 화면)
     - 좌: 노드 팔레트(카테고리별, `/nodes` 응답 기반 동적 렌더)
     - 중: Vue Flow 캔버스(노드 드래그/연결)
     - 우: 속성 패널(선택 노드의 `param_schema` 기반 동적 폼) + 검증 패널(`/workflows/{id}/validate` 결과)
     - 하단: 저장 / 테스트 실행(오버라이드 값 입력 모달) / 백테스트 실행 버튼
     - 테스트 실행 시 WS로 이벤트 수신 → 진행 중 노드 테두리 애니메이션(깜빡임) + 클릭 시 입력/출력 JSON 사이드패널 표시
  5. 백테스트 결과(지표 요약, 자산곡선 차트, 거래내역 테이블, 노드 실행 리플레이 — 전략 빌더 캔버스 컴포넌트 재사용)
  6. 라이브 모니터링(활성 전략 상태, 최근 실행/주문 내역, 긴급 정지 버튼)

---

## 13. 디렉토리 구조

```
nemo-stock/
  DESIGN.md
  nemo-stock.md
  backend/
    app/
      main.py
      config.py
      auth/
      nodes/{base.py, scheduler.py, data/, indicator/, ai/, logic/, risk/, execution/}
      workflow/{graph.py, engine.py, events.py}
      trigger/{queue.py, scheduler_service.py, worker_pool.py}
      batch/worker.py
      market_data/{base.py, dummy.py, historical.py, toss_adapter.py}
      broker/{base.py, dummy.py, toss_adapter.py}
      ai/{openai_client.py, workflow_draft.py, disclosure_scoring.py, news_sentiment.py, scoring_cache.py}
      backtest/{runner.py, metrics.py}
      data_ingestion/{public_data_price.py, opendart_client.py}
      dao/{base.py, sqlite/, memory/}
      api/{routers/*.py, ws.py}
      schemas/*.py
    tests/{unit/, integration/}
    pyproject.toml
    .env.example
  frontend/
    src/{views/, components/, api/, stores/}
    package.json
```

---

## 14. 테스트 전략

- **유닛(pytest)**: 노드별 `execute()` 동작, 위상 정렬/사이클 검증, TriggerQueue 인메모리 구현, Repository CRUD(임시 sqlite 파일), AIScoreCache 히트/미스(OpenAI 클라이언트 mock), 백테스트 지표 계산(합성 데이터로 기대값 고정), Dummy Provider 결정성(시드 고정).
- **통합**: 기획서 예시 시나리오(스케줄러→시세→[조건]→뉴스/공시→[긍정]→매수, `logic_sample.png` 참조)를 오버라이드 값으로 TEST 모드 실행 → 최종 매수 주문 발생 검증. 소규모 합성 가격 시계열로 백테스트 end-to-end 실행.
- **API**: FastAPI `TestClient`/httpx로 인증, 워크플로 CRUD, 실행, 백테스트 제출/조회 검증.
- **프론트**: 개발 서버 기동 후 실제로 전략 생성→캔버스 편집→테스트 실행(하이라이트 확인)→백테스트까지 수동 시나리오 확인(자동화 테스트는 PoC 범위상 핵심 플로우 위주로 최소화).

---

## 15. 개발 단계 (Phase)

1. **Phase 1 – 코어 실행 엔진**: Node ABC/레지스트리, WorkflowEngine(위상정렬/실행/이벤트), TriggerQueue+Scheduler+WorkerPool(인메모리), DAO(sqlite: users/workflows/runs/node_events), 기본 노드 5종(scheduler.interval, data.price[dummy], indicator.moving_average, logic.if_else, execution.market_order[dummy]), 워크플로 CRUD+테스트실행 API, 유닛/통합 테스트. → **이 시점에서 최초로 실행 가능한 테스트 확보**.
2. **Phase 2 – 백테스트 + 공공데이터**: 공공데이터포털 일봉 수집기, HistoricalMarketDataProvider, BacktestRunner+metrics, 백테스트 API/테스트.
3. **Phase 3 – AI 모듈**: OpenAI 클라이언트, 자연어→워크플로 초안, OpenDART 수집기, 공시/뉴스 점수화+캐시, AI 관련 노드(ai.sentiment_score, ai.regime).
4. **Phase 4 – 인증/이벤트버스/WS/Toss 스켈레톤**: JWT 로그인, EventBus+WS 브로드캐스트, TossInvest 어댑터 스켈레톤.
5. **Phase 5 – 프론트엔드**: Vue3+Vue Flow 캔버스, 노드 팔레트/속성/검증 패널, 테스트 실행 디버그 하이라이트, 백테스트 결과 대시보드, 로그인.
6. **Phase 6 – 통합 QA**: 기획서 예시 시나리오 E2E(백엔드+프론트), 회귀 점검, README 정리.

각 Phase 종료 시점마다 해당 범위의 테스트를 실행/통과시키고 다음 단계로 진행한다.

---

## 16. back-news-analysis — 뉴스 이벤트 분석 파이프라인 (독립 프로젝트, `back-news-analysis/`)

`backend/`·`frontend/`와 별도로 루트에 위치한 독립 Python 프로젝트. `naver_economy_news.json`(네이버
경제 뉴스 92,229건)을 AI로 분석해 종목별 백테스트에 쓸 수 있는 뉴스 영향도 변수를 산출한다.
`backend/.venv`(openai/dotenv 이미 설치됨)를 그대로 재사용하고, `OPENAI_API_KEY`도 `backend/.env`의
값을 그대로 읽는다(별도 키 보관 없음). 상세 사용법은 `back-news-analysis/README.md` 참조.

### 16.1 기사 단위 AI 라벨링 (고정 스키마 10개 필드)

뉴스 1건이 들어오면 AI(채팅 모델, 백엔드와 동일한 `gpt-5.6-luna`)가 다음 10개 필드를 JSON으로
추출한다(`scoring.py`): `depth1`(상위분류), `depth2`(긍정/중립/부정), `depth3`(세부 이벤트 유형),
`scope_type`(종목직접/업종전반/시장전체), `related_tickers`(관련 종목), `related_industries`(관련
업종), `impact_strength`(High/Medium/Low), `time_horizon`(단기/중기/장기), `confidence`(확실/보통/
불확실), `reasoning`(분류 근거). `sentiment`(+1/0/-1)와 `magnitude`(1.5/1.0/0.5)는 각각
`depth2`/`impact_strength`로부터 파생되는 계산값으로 별도 AI 호출 없이 도출한다(`schemas.py`).

### 16.2 이벤트 클러스터링

"뉴스가 들어올 때마다 기존 대표뉴스들과 함께 AI에 넣어서 판단, 새로 생기는지 판단"이라는 요구를
임베딩(`text-embedding-3-small`) 유사도로 구현했다(`clustering.py`). 순수 LLM 순차 판단 방식은
뉴스 건수만큼 서로 의존하는 호출이 필요해 아래 §16.3 Batch API(비용 절감)와 근본적으로 맞지 않기
때문이다. 시간순으로 뉴스를 훑으며, 임베딩이 기존 클러스터 대표(centroid)와 코사인 유사도
임계값(`CLUSTER_SIMILARITY_THRESHOLD`, 기본 0.62) 이상이면 편입하고 아니면 새 클러스터를 만든다.

### 16.3 대량 처리 비용 절감 — OpenAI Batch API

임베딩과 채팅(라벨링) 호출은 뉴스 1건당 완전히 독립적인 요청이라 Batch API(50% 할인,
`embeddings.py`/`scoring.py`의 `submit_*_batch`/`poll_*_batch`)로 대량 제출·완료 후 캐시에 반영한다
(`build_pool.py --submit` / `--poll`). 백테스트 등에서 캐시에 없는 뉴스가 필요할 때만
(`extract_variables.py`) 그 자리에서 동기 호출로 즉시 채워 넣는다(온디맨드 경로는 배치가 아닌
실시간 API 사용 — 속도가 우선이므로).

### 16.4 최종 점수 계산 (`aggregate.py`)

```
strength = sentiment(+1/0/-1) * magnitude(1.5/1.0/0.5)
decay(d) = 1 / (d + 1)                              # d = 이벤트 최초 보도일로부터 경과일
count_factor = 1 + 0.3 * log(source_count)          # source_count = 같은 이벤트를 다룬 뉴스 수
event_score = strength * decay(d) * count_factor
종목 점수 = 그 종목에 관련된 모든 이벤트의 event_score 합산 -> 평균 -> tanh로 [-1, 1] 정규화
```

### 16.5 캐시 — JSON / SQLite 이중 지원

`cache_store.py`가 `JSONCacheStore`/`SQLiteCacheStore` 두 구현을 동일 인터페이스(`CacheStore`)로
제공하며 `--store json sqlite`로 선택. `build_pool.py`가 약 1000건(기본값)을 미리 처리해 캐시를
채우는 "AI 풀" 빌더 역할을 한다(2026-07-22 최초 구축: 뉴스 1000건 처리 → 이벤트 클러스터 608개,
JSON/SQLite 양쪽에 저장 완료). `score_stock.py`는 특정 종목·기준일의 점수를 조회하는 데모 CLI로,
캐시에 없는 뉴스는 `extract_variables.ensure_variables()`가 즉시 채워 넣는다.

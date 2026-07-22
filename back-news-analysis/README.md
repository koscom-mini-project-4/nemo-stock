# back-news-analysis

`naver_economy_news.json`(네이버 경제 뉴스 92,229건)을 AI로 분석해 종목별 백테스트에 쓸 수 있는
변수를 뽑아내는 독립 파이프라인. `backend/`·`frontend/`와 별도 프로젝트지만 `backend/.venv`
(openai/dotenv가 이미 설치돼 있음)를 그대로 재사용하고, `OPENAI_API_KEY`/`OPENAI_MODEL`도
`backend/.env`의 값을 그대로 읽는다(별도 키 보관 없음).

설계 배경, 각 단계의 이유(왜 배치가 아닌 임베딩으로 클러스터링하는지, 9단계 impact 등급을 왜
도입했는지, Batch API 파일 크기 제한을 어떻게 겪고 해결했는지 등)는 **`DESIGN.md`**를 참고한다.
이 문서는 사용법 위주로 짧게 정리한다.

## 파이프라인 개요

1. **기사 단위 AI 라벨링** (`scoring.py`): 뉴스 1건마다 AI(`gpt-5.6-luna`, 백엔드와 동일 모델)가
   `depth1`(상위분류)/`depth2`(긍정·중립·부정)/`depth3`(세부 이벤트 유형)/`scope_type`(종목직접·
   업종전반·시장전체)/`related_tickers`/`related_industries`/`impact_grade`(1~9, 예시 앵커
   포함 — DESIGN.md §2.1)/`time_horizon`/`confidence`/`reasoning`을 고정 스키마 JSON으로 추출.
   `sentiment`/`magnitude`는 `depth2`/`impact_grade`로부터 파생 계산(추가 AI 호출 없음).
2. **이벤트 클러스터링** (`clustering.py`): 뉴스 임베딩(`text-embedding-3-small`)의 코사인
   유사도로, 기존 클러스터 대표(centroid)와 임계값(기본 0.62) 이상 유사하면 같은 이벤트로 편입.
3. **strength(영향도)**: `strength = sentiment * magnitude`.
4. **decay**: `decay(d) = 1 / (d + 1)` (d = 이벤트 최초 보도일로부터 경과일).
5. **뉴스개수 가중**: `count_factor = 1 + 0.3 * log(source_count)`.
6. **최종 종목 점수** (`aggregate.py`): `event_score = strength * decay(d) * count_factor`. 특정
   종목에 관련된 모든 이벤트의 `event_score`를 합산 -> 평균 -> `tanh`로 [-1, 1] 정규화.

## AI 풀(캐시) — JSON / SQLite 둘 다 지원

- `cache_store.py`: `JSONCacheStore`(`data/news_ai_cache.json`) / `SQLiteCacheStore`
  (`data/news_ai_cache.db`) 두 구현이 동일 인터페이스(`CacheStore`)를 제공. `--store json sqlite`로
  하나 또는 둘 다 선택.
- `build_pool.py`: OpenAI Batch API(50% 비용 절감)로 대량 처리해 캐시를 미리 채워두는 빌더.
  최근 N건만 빠르게 채우거나(`--limit`), 92,229건 전체를 청크로 나눠 처리(`--all`) 가능.
- `extract_variables.py`: 캐시에 없는 뉴스가 필요할 때(cache miss)만 그 자리에서 동기 호출로
  즉시 채점해 캐시를 채우는 온디맨드 경로 — 92,229건 전체를 매번 AI로 훑지 않도록, 종목/회사명
  문자열이 실제로 포함된 뉴스만 후보로 추려 AI를 호출한다.

## 사용법

```bash
cd back-news-analysis

# 1) 파이프라인 검증 — 소량(20건) 동기 처리, 비용 적음, 즉시 완료
../backend/.venv/bin/python build_pool.py --sync --limit 20

# 2) 최근 N건만 빠르게 채워두고 싶을 때 — Batch API로 제출(완료까지 수분~수시간)
../backend/.venv/bin/python build_pool.py --submit --limit 1000
../backend/.venv/bin/python build_pool.py --poll        # 완료 확인 및 캐시 반영(완료 전이면 잠시 후 재실행)

# 3) 92,229건 전체를 AI로 처리 — Batch API 1건당 최대 200MB 제한이 있어 청크(기본 25,000건)로 제출
../backend/.venv/bin/python build_pool.py --submit --all
../backend/.venv/bin/python build_pool.py --poll --all  # 청크별로 끝난 만큼 캐시에 반영, 안 끝난 청크는 다시 실행 시 이어서 처리

# 4) 특정 종목의 특정 기준일 뉴스 점수 확인 (캐시 미스는 즉시 AI로 채워짐)
../backend/.venv/bin/python score_stock.py --company "SK하이닉스" --as-of 2026-07-18 --store sqlite
../backend/.venv/bin/python score_stock.py --symbol 005930 --as-of 2026-07-10 --store json
```

## 디렉터리 구조

```
back-news-analysis/
  DESIGN.md               설계 배경·근거 상세 문서 (왜 이렇게 만들었는지)
  README.md               이 파일 (사용법 위주)
  config.py               환경설정 (backend/.env에서 OPENAI_API_KEY/OPENAI_MODEL 로드)
  schemas.py               NewsRecord / NewsVariables(10필드 + 파생값) / ClusterInfo
  news_loader.py           naver_economy_news.json 로더 (전체/최근 N건)
  cache_store.py           JSON/SQLite 이중 캐시 (CacheStore 인터페이스)
  embeddings.py            클러스터링용 임베딩 (Batch API + 동기 1건)
  clustering.py            임베딩 코사인 유사도 기반 이벤트 클러스터링 (기존 클러스터 누적)
  scoring.py               AI 라벨링 10필드 추출 — 9단계 impact_grade 앵커 포함 (Batch API + 동기)
  aggregate.py             decay/count_factor/최종 종목 점수 계산
  build_pool.py            AI 풀(캐시) 빌더 CLI (--limit 또는 --all, --submit/--poll)
  extract_variables.py     캐시미스 온디맨드 보강 (종목명 사전 필터 + 동기 AI 호출)
  score_stock.py           데모 CLI (종목·기준일 점수 조회)
  data/                    캐시 산출물 (news_ai_cache.json / .db, 배치 상태 파일) — gitignore 대상
```

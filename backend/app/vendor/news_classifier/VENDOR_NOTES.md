# vendored from koscom-mini-project-4/newsstock-lib

이 디렉터리는 `koscom-mini-project-4/newsstock-lib`의 `news_classifier` 패키지를 그대로
가져온 것이다(2026-07-28, `8b5cae8` 기준).

## nemo-stock 통합 시 수정한 부분

- `classifier.py::call_ai`: OpenAI 호출의 `temperature=0` 하드코딩이 nemo-stock 메인 모델
  `gpt-5.6-luna`(reasoning 계열, 기본값 외 temperature 거부)와 충돌해, `app/ai/openai_client.py`
  와 동일한 "BadRequestError(param=temperature) 시 temperature 없이 1회 재시도" 로직을 추가했다.
- `crawler.py`: 기사 본문 fetch가 건마다 순차로(지연 포함) 돌아 기본 설정 기준 실측 5분 이상
  걸려서, `crawl(workers=N)`으로 페이지 안의 기사들을 스레드풀로 동시에 가져올 수 있게 했다
  (기본 `CRAWL_WORKERS=4`, `workers=1`이면 원본과 동일한 순차 동작). 스레드마다 별도
  `requests.Session`(=별도 connection pool)을 쓴다(`_thread_session`). 목록 페이지 조회와
  분류(`pipeline.classify_many`, 오래된 뉴스부터 순서대로 처리해야 클러스터가 올바르게 쌓이는
  순차 의존성이 있음)는 병렬화하지 않았다 — 자세한 이유는 `crawler.py` 상단 docstring 참조.
- `classifier.py::call_ai`: 성공 응답의 `resp.usage`(prompt/completion/total tokens)를
  `set_usage_sink(callback)`으로 주입된 모듈 레벨 콜백에 넘기도록 했다(관리자 페이지 AI 사용량
  집계용, `app/dependencies.py::build_container()`가 1회 주입, `app/admin/metrics.py`가 집계).
  콜백이 없으면 아무 일도 안 하므로 라이브러리 단독 사용 시에도 하위호환.
- `db.py::cluster_stats`: 클러스터별로 연결된 종목/섹터/거시지표 키 목록(`cluster_tags`, 신규
  추가 함수)을 함께 반환하도록 확장했다 — 관리자 페이지에서 "이 주제가 어떤 종목/섹터/거시와
  연결됐는지" 바로 보여주기 위함(응답 필드 추가뿐이라 기존 소비자와 하위호환).
- `api.py::NewsTrader`: `clusters_for_key(group, key, start, end)`(기존 `db.group_cluster_rows`를
  얇게 감쌈)와 `keys_in_range(group, start, end)`(기존 `db.group_keys`를 감쌈)를 추가했다 —
  관리자 페이지에서 "종목/섹터/거시로부터 관련 클러스터 탐색"(반대 방향)을 위한 조회 전용
  메서드, 원본 로직은 건드리지 않고 새 진입점만 얹었다.
- `embeddings.py`(2026-07-29, 신규 파일, upstream에 없음): `classifier.call_ai()`가 매 분류
  호출마다 "보관기간(기본 7일) 내 클러스터 후보 전부"를 텍스트로 프롬프트에 넣던 문제 —
  실측 기준 후보 968개일 때 약 9만 자(4~5만 토큰)가 뉴스 한 건 분류할 때마다 반복 전송되고
  있었다(뉴스 유입량에 비례해 무한정 커지는 구조). 새 기사 제목을 `text-embedding-3-small`로
  임베딩해 기존 클러스터 대표제목 임베딩과 코사인 유사도 top-K(`CLUSTER_CANDIDATE_TOP_K`,
  기본 20)만 `call_ai()`에 넘기도록 `pipeline.py::classify_news`를 수정했다. 클러스터 판정
  로직(`classifier.SYSTEM_PROMPT`) 자체는 그대로이고, LLM이 보는 후보 범위만 좁혔다.
  - `db.py`: `clusters` 테이블에 `embedding TEXT`(JSON 배열) 컬럼 추가 + `_migrate()`에 기존
    DB용 `ALTER TABLE` 가드 추가(기존 `title` 컬럼 마이그레이션과 동일 패턴). `create_cluster()`
    가 `embedding` 키워드 인자(기본 None, 하위호환)를 받고, `recent_clusters()`가 각 후보의
    임베딩을 파싱해 함께 돌려준다.
  - `config.py`: `CLUSTER_CANDIDATE_TOP_K`(환경변수로 조정 가능, 기본 20) 추가.
  - 사용량 계측은 `classifier._usage_sink`(기존 훅)를 그대로 재사용해 `purpose=
    "newsstock_embed"`로 기록(관리자 페이지 AI 사용량 통계에 자동으로 잡힘, `app/admin/
    pricing.py`에 `text-embedding-3-small` 단가 추가).
  - 회귀 테스트: `backend/tests/unit/test_vendor_news_classifier_embeddings.py`(cosine_similarity/
    top_k_similar 단위 테스트 + `classify_news`가 실제로 top-K만 `call_ai`에 넘기는지 검증).
    실 DB 복사본(968개 클러스터)에 대한 마이그레이션 + 실제 OpenAI 호출 스모크 테스트도
    별도로 수행해 확인(스크립트는 커밋하지 않음).

그 외 파일은 원본 그대로다. 사용 방법은 `README.md`/`docs/API.md`(원본 문서, 그대로 유지) 참고.
nemo-stock 쪽 배선(Container.news_trader_factory, ai.news_signal 노드, /data/news/update
엔드포인트)은 `DESIGN.md` §0-5, 관리자 페이지 클러스터 상호 탐색은 §0-7 참조.

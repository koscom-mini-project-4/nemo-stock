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

그 외 파일은 원본 그대로다. 사용 방법은 `README.md`/`docs/API.md`(원본 문서, 그대로 유지) 참고.
nemo-stock 쪽 배선(Container.news_trader_factory, ai.news_signal 노드, /data/news/update
엔드포인트)은 `DESIGN.md` §0-5 참조.

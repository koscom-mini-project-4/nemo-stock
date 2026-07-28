"""app/vendor/news_classifier(koscom-mini-project-4/newsstock-lib)에 nemo-stock 통합 시
추가한 수정(classifier.py::call_ai의 temperature 재시도, crawler.py의 병렬 fetch)에 대한
회귀 테스트. temperature 재시도는 app/ai/openai_client.py의 test_openai_client.py와 동일한
시나리오다.
"""

from __future__ import annotations

import threading
from time import sleep as real_sleep  # crawler.time.sleep을 monkeypatch해도 영향받지 않는다
from unittest.mock import MagicMock

import httpx
import pytest
from openai import BadRequestError

from app.vendor.news_classifier import classifier, crawler, db


def _temperature_error() -> BadRequestError:
    response = httpx.Response(status_code=400, request=httpx.Request("POST", "https://api.openai.com/v1/x"))
    return BadRequestError(
        "temperature unsupported",
        response=response,
        body={
            "message": "Unsupported value: 'temperature' does not support 0 with this model.",
            "type": "invalid_request_error",
            "param": "temperature",
            "code": "unsupported_value",
        },
    )


def _fake_response(content: str, usage: MagicMock | None = None) -> MagicMock:
    resp = MagicMock()
    resp.choices = [MagicMock(message=MagicMock(content=content))]
    resp.usage = usage
    return resp


def test_call_ai_retries_without_temperature_on_unsupported_value(monkeypatch):
    create_mock = MagicMock(side_effect=[_temperature_error(), _fake_response('{"cluster_id": null}')])
    fake_client = MagicMock()
    fake_client.chat.completions.create = create_mock
    monkeypatch.setattr(classifier, "_client_once", lambda api_key=None: fake_client)

    result = classifier.call_ai({"title": "t", "content": "c"}, [], model="gpt-5.6-luna", api_key="sk-test")

    assert result == {"cluster_id": None}
    assert create_mock.call_count == 2
    assert "temperature" in create_mock.call_args_list[0].kwargs
    assert "temperature" not in create_mock.call_args_list[1].kwargs


def test_call_ai_reports_usage_via_sink(monkeypatch):
    usage = MagicMock(prompt_tokens=50, completion_tokens=10, total_tokens=60)
    create_mock = MagicMock(side_effect=[_fake_response('{"cluster_id": null}', usage=usage)])
    fake_client = MagicMock()
    fake_client.chat.completions.create = create_mock
    monkeypatch.setattr(classifier, "_client_once", lambda api_key=None: fake_client)
    monkeypatch.setattr(classifier, "_usage_sink", None)  # 다른 테스트에서 새는 것 방지

    calls: list[tuple] = []
    classifier.set_usage_sink(lambda *args: calls.append(args))
    try:
        classifier.call_ai({"title": "t", "content": "c"}, [], model="gpt-5.6-luna", api_key="sk-test")
    finally:
        classifier.set_usage_sink(None)

    assert calls == [("newsstock_classify", "gpt-5.6-luna", 50, 10, 60)]


def test_call_ai_without_usage_sink_does_not_error(monkeypatch):
    create_mock = MagicMock(side_effect=[_fake_response('{"cluster_id": null}')])
    fake_client = MagicMock()
    fake_client.chat.completions.create = create_mock
    monkeypatch.setattr(classifier, "_client_once", lambda api_key=None: fake_client)
    monkeypatch.setattr(classifier, "_usage_sink", None)

    result = classifier.call_ai({"title": "t", "content": "c"}, [], model="gpt-5.6-luna", api_key="sk-test")

    assert result == {"cluster_id": None}


def test_call_ai_reraises_unrelated_bad_request_error(monkeypatch):
    response = httpx.Response(status_code=400, request=httpx.Request("POST", "https://api.openai.com/v1/x"))
    other_error = BadRequestError(
        "bad model",
        response=response,
        body={"message": "unknown model", "type": "invalid_request_error", "param": "model", "code": "invalid"},
    )
    create_mock = MagicMock(side_effect=other_error)
    fake_client = MagicMock()
    fake_client.chat.completions.create = create_mock
    monkeypatch.setattr(classifier, "_client_once", lambda api_key=None: fake_client)

    with pytest.raises(BadRequestError):
        classifier.call_ai({"title": "t", "content": "c"}, [], model="gpt-5.6-luna", api_key="sk-test")

    assert create_mock.call_count == 1


def _stub_session():
    return object()  # _list_page/_article를 스텁하므로 실제로 쓰이지 않는다


def _fake_article(url: str) -> dict:
    return {
        "url": url,
        "url_hash": crawler.url_hash(url),
        "title": f"제목 {url[-3:]}",
        "content": "본문",
        "summary": "본문",
        "published_at": "2026-07-28 09:00:00",
    }


def test_crawl_with_workers_collects_same_items_as_sequential(monkeypatch):
    """crawl(workers=N)이 순차(workers=1)와 동일한 결과 집합을 모으면서, 실제로 여러 스레드에서
    fetch되는지 확인한다(nemo-stock 통합 시 추가한 병렬 fetch에 대한 회귀 테스트).

    crawler.time.sleep(지연)을 무력화하면 각 fetch가 사실상 즉시 끝나버려 ThreadPoolExecutor가
    스레드를 재사용해 우연히 1개 스레드만 쓸 수도 있다(그 자체로는 버그가 아님 — 크롤러
    코드는 여전히 병렬 실행 가능한 구조임). 스레드 관여를 확실히 관찰하려면 fake_article
    안에서 실제로 아주 짧게(진짜 time.sleep) 블로킹해 여러 fetch가 실제로 겹치게 만든다.
    """
    monkeypatch.setattr(crawler, "_session", _stub_session)
    monkeypatch.setattr(crawler.time, "sleep", lambda *_: None)  # CRAWL_DELAY만 무력화

    urls = [f"https://n.news.naver.com/article/000/{i:03d}" for i in range(6)]
    seen_threads: set[int] = set()

    def fake_list_page(session, date_str, page):
        return urls if page == 1 else []

    def fake_article(session, url):
        seen_threads.add(threading.get_ident())
        real_sleep(0.02)  # fetch가 겹치도록 의도적으로 블로킹(네트워크 지연 흉내)
        return _fake_article(url)

    monkeypatch.setattr(crawler, "_list_page", fake_list_page)
    monkeypatch.setattr(crawler, "_article", fake_article)

    conn = db.connect(":memory:")
    collected = crawler.crawl(conn, days=1, max_pages=2, workers=4)

    assert {item["url"] for item in collected} == set(urls)
    assert len(seen_threads) > 1  # 실제로 여러 스레드가 fetch에 참여했는지 확인


def test_crawl_sequential_and_parallel_produce_identical_url_sets(monkeypatch):
    monkeypatch.setattr(crawler, "_session", _stub_session)
    monkeypatch.setattr(crawler.time, "sleep", lambda *_: None)

    urls = [f"https://n.news.naver.com/article/111/{i:03d}" for i in range(5)]

    def fake_list_page(session, date_str, page):
        return urls if page == 1 else []

    def fake_article(session, url):
        return _fake_article(url)

    monkeypatch.setattr(crawler, "_list_page", fake_list_page)
    monkeypatch.setattr(crawler, "_article", fake_article)

    sequential = crawler.crawl(db.connect(":memory:"), days=1, max_pages=2, workers=1)
    parallel = crawler.crawl(db.connect(":memory:"), days=1, max_pages=2, workers=4)

    assert {i["url"] for i in sequential} == {i["url"] for i in parallel} == set(urls)

"""네이버 경제뉴스 증분 크롤러.

원본 `naver_crawler.py` 를 모듈로 옮기면서 두 가지를 바꿨다.

1. **중복 판정 기준이 JSON 파일 -> DB `crawled` 테이블**
   원본은 결과 JSON 을 통째로 읽어서 url 집합을 만들었다. 파일이 커질수록 느려지고,
   파일을 지우면 전부 다시 받는다. 지금은 `crawled` 테이블의 url_hash 를 본다.

2. **`news` 가 아니라 `crawled` 를 기준으로 본다**
   `news` 는 클러스터 보관기간이 지나면 같이 삭제되므로, 그걸 기준으로 삼으면
   지워진 기사를 다시 받아 다시 AI 에 넣게 된다. `crawled` 는 따로 오래 남긴다.

한 페이지가 전부 이미 본 기사면 그 날짜는 더 볼 게 없다고 보고 다음 날짜로 넘어간다
(네이버가 마지막 페이지를 계속 반복해서 보여주기 때문에 원본에도 있던 처리다).

nemo-stock 통합 시 추가한 부분: 기사 본문 fetch가 건마다 지연(CRAWL_DELAY)을 두고 순차로
돌아 시간이 오래 걸려서(실측 5분+), crawl(workers=N)로 페이지 안의 기사들을 스레드풀로
동시에 가져올 수 있게 했다(기본 workers=1이면 기존과 동일한 순차 동작). 스레드마다 별도
requests.Session(=별도 connection pool)을 쓴다(_thread_session, threading.local). 지연은
스레드별로 각자 넣으므로 정중함(초당 요청 수 제한 의도)은 유지하되 처리량은 workers배로
늘어난다. 목록 페이지 조회(_list_page)는 페이지당 1회뿐이라 병렬화 대상이 아니다. 분류
단계(pipeline.classify_many)는 오래된 뉴스부터 순서대로 처리해야 클러스터가 올바르게
쌓이는 순차 의존성이 있어(파일 docstring 참조) 병렬화하지 않았다.
"""
import hashlib
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta

from . import db
from .config import (NAVER_LIST_URL, HTTP_HEADERS, CRAWL_DELAY, CRAWL_TIMEOUT,
                     CRAWL_DAYS, CRAWL_MAX_PAGES, CRAWL_WORKERS, DATE_FMT)

_thread_local = threading.local()

LIST_SELECTOR = ".type06_headline dt a, .type06 dt a, .list_body dt a"
TITLE_SELECTOR = "#title_area span, .media_end_head_title, h2#title_area"
BODY_SELECTOR = "#newsct_article, #articleBodyContents, article#newsct_article"
DATE_SELECTOR = ".media_end_head_info_datestamp_time"


def url_hash(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def _parse_date(raw: str) -> str:
    try:
        raw = raw.replace("오전", "AM").replace("오후", "PM").strip()
        return datetime.strptime(raw, DATE_FMT).strftime(DATE_FMT)
    except (ValueError, AttributeError):
        return raw or ""


def _normalize(href: str) -> str:
    """목록의 상대/축약 링크를 기사 정규 URL 로."""
    if href.startswith("//"):
        href = "https:" + href
    elif href.startswith("/"):
        href = "https://n.news.naver.com" + href
    href = href.split("?")[0]
    if "news.naver.com" in href and "n.news.naver.com" not in href:
        href = href.replace("news.naver.com", "n.news.naver.com")
    return href


def _session():
    import requests
    s = requests.Session()
    s.headers.update(HTTP_HEADERS)
    try:
        s.get("https://news.naver.com/", timeout=5)   # 쿠키 확보
    except Exception:
        pass
    return s


def _thread_session():
    """스레드마다 별도 Session(=별도 connection pool)을 만들어 재사용한다."""
    session = getattr(_thread_local, "session", None)
    if session is None:
        session = _session()
        _thread_local.session = session
    return session


def _list_page(session, date_str: str, page: int) -> list:
    """목록 페이지 하나에서 (기사 URL, 헤드라인 제목) 튜플들을 뽑는다.

    목록 HTML의 <a> 텍스트가 곧 헤드라인이라(nemo-stock 통합 시 추가) 키워드 필터링에
    필요한 제목을 별도 네트워크 호출 없이 여기서 바로 얻는다 — crawl(keywords=...)가
    본문을 가져오기 전에 이 제목으로 먼저 걸러낸다.
    """
    from bs4 import BeautifulSoup
    res = session.get(f"{NAVER_LIST_URL}&date={date_str}&page={page}",
                      timeout=CRAWL_TIMEOUT)
    if res.status_code != 200:
        return []
    soup = BeautifulSoup(res.text, "html.parser")
    # 목록 HTML은 기사 하나당 <a>가 두 개(썸네일 이미지용 + 헤드라인 텍스트용) 나오고 둘의
    # href가 같다. 썸네일 <a>가 텍스트 <a>보다 먼저 나오는 경우가 대부분이라 "첫 등장만
    # 기록"하면 대부분 빈 제목("")이 저장돼(a.text가 <img>만 감싸 비어있음)
    # crawl(keywords=...)의 키워드 매칭이 사실상 항상 실패하는 버그가 있었다 — 같은 URL이
    # 다시 나오면 기존 값이 비어있을 때만 새 텍스트로 덮어써 실제 헤드라인을 보존한다.
    items: list[list[str]] = []
    index_by_url: dict[str, int] = {}
    for a in soup.select(LIST_SELECTOR):
        href = a.get("href", "")
        if "article/" not in href:
            continue
        u = _normalize(href)
        text = a.text.strip()
        if u not in index_by_url:
            index_by_url[u] = len(items)
            items.append([u, text])
        elif text and not items[index_by_url[u]][1]:
            items[index_by_url[u]][1] = text
    return [(u, t) for u, t in items]


def _article(session, url: str, fallback_date_str: str | None = None) -> dict:
    """기사 상세. 제목이나 본문이 없으면 None.

    fallback_date_str: 페이지에서 발행일시를 못 읽어왔을 때 대신 쓸 날짜("YYYYMMDD",
    crawl()이 현재 훑고 있는 목록 날짜). **수집 시점(datetime.now())이 아니라 그 기사가
    속한 목록 날짜(등록 시점 근사치)로 채워야 한다** — 과거 날짜를 크롤링 중에 파싱이
    실패하면 "지금 막 크롤링했다"는 이유만으로 기사가 오늘 발행된 것처럼 잘못 찍혀,
    날짜 기준 필터링(예: 최근 N일 조회, 백테스트 시점 재현)이 전부 틀어진다.
    """
    from bs4 import BeautifulSoup
    res = session.get(url, timeout=CRAWL_TIMEOUT)
    if res.status_code != 200:
        return None
    soup = BeautifulSoup(res.text, "html.parser")

    t = soup.select_one(TITLE_SELECTOR)
    b = soup.select_one(BODY_SELECTOR)
    title = t.text.strip() if t else ""
    content = b.text.strip() if b else ""
    if not title or not content:
        return None

    d = soup.select_one(DATE_SELECTOR)
    published = _parse_date(d.get("data-date-time", "")) if d else ""

    if not published:
        if fallback_date_str:
            published = datetime.strptime(fallback_date_str, "%Y%m%d").strftime("%Y-%m-%d 12:00:00")
        else:
            published = datetime.now().strftime(DATE_FMT)

    return {
        "url": url,
        "url_hash": url_hash(url),
        "title": title,
        "content": content,
        "summary": content[:200] + "..." if len(content) > 200 else content,
        "published_at": published,
    }


def _fetch_one(url: str, date_str: str) -> tuple[str, dict | None, Exception | None]:
    """스레드풀 워커 하나가 기사 하나를 가져온다. 지연은 워커별로 각자 넣는다.

    date_str: 이 URL이 발견된 목록 페이지의 날짜("YYYYMMDD") — 발행일시 파싱 실패 시
    _article()의 fallback_date_str으로 전달된다.
    """
    time.sleep(random.uniform(*CRAWL_DELAY))
    try:
        return url, _article(_thread_session(), url, fallback_date_str=date_str), None
    except Exception as e:  # noqa: BLE001 - 개별 기사 실패는 나머지에 영향 없이 건너뛴다
        return url, None, e


def _fetch_page_articles(
    urls: list[str], workers: int, progress, collected_len: int, date_str: str
) -> list[tuple[str, dict | None, bool]]:
    """한 페이지의 새 기사 URL들을 가져온다. (url, item, error?) 튜플 리스트를 돌려준다.

    workers<=1이면 메인 스레드에서 순차로(원본과 동일한 동작), 그 이상이면 스레드풀로
    동시에 가져온다. 두 경우 모두 _fetch_one 하나를 공유해 로직이 갈라지지 않는다.
    """
    results: list[tuple[str, dict | None, bool]] = []

    def _record(u: str, item: dict | None, err: Exception | None) -> None:
        results.append((u, item, err is not None))
        if progress:
            if err is not None:
                progress(collected_len + len(results), f"기사 실패: {err}")
            elif item:
                progress(collected_len + len(results), item["title"][:30])

    if workers <= 1:
        for u in urls:
            _record(*_fetch_one(u, date_str))
        return results

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(_fetch_one, u, date_str) for u in urls]
        for future in as_completed(futures):
            _record(*future.result())
    return results


def _matches_keywords(title: str, keywords: list[str] | None) -> bool:
    """keywords가 없으면 항상 True. 있으면 제목에 하나라도 부분일치하면 True(한글은
    대소문자 구분이 없어 단순 부분일치로 충분 — 예: "하이닉스"가 "SK하이닉스"에 매칭)."""
    if not keywords:
        return True
    return any(kw in title for kw in keywords)


def crawl(conn, days: int = CRAWL_DAYS, max_pages: int = CRAWL_MAX_PAGES,
          workers: int = CRAWL_WORKERS, progress=None, keywords: list[str] | None = None) -> list:
    """새 기사만 수집해서 `crawled` 테이블에 넣고, 새로 받은 것만 돌려준다.

    days      : 오늘부터 며칠 전까지의 목록을 훑을지
    max_pages : 날짜당 최대 목록 페이지 수 (무한 루프 방지)
    workers   : 기사 본문 fetch 동시 처리 수(스레드별 별도 connection pool). 1이면 순차(원본 동작).
    progress  : progress(수집수, 메시지) 콜백
    keywords  : 주어지면 헤드라인에 이 중 하나라도 포함된 기사만 본문을 가져온다(nemo-stock
                통합 시 추가, §0-12). "이 페이지 전부 이미 봤음" 조기 중단 판단은 키워드와
                무관하게 전체 URL 기준으로 하므로(아래 unseen), 키워드에 안 걸리는 기사가
                많은 페이지가 있어도 다음 페이지를 계속 훑는다. 키워드에 안 걸린 기사는
                DB에 기록하지 않는다(다음 크롤링 때 제목만 다시 확인 — 이미 받아온 목록
                페이지 HTML 파싱뿐이라 비용 무시할 만함).
    """
    seen = db.seen_hashes(conn)
    session = _session()
    collected = []

    for offset in range(days):
        date_str = (datetime.now() - timedelta(days=offset)).strftime("%Y%m%d")

        for page in range(1, max_pages + 1):
            try:
                items = _list_page(session, date_str, page)
            except Exception as e:
                if progress:
                    progress(len(collected), f"{date_str} p{page} 목록 실패: {e}")
                break

            if not items:
                break

            unseen = [(u, t) for u, t in items if url_hash(u) not in seen]
            if not unseen:
                # 이 페이지가 전부 이미 본 기사 -> 이 날짜는 더 볼 게 없다(키워드와 무관)
                if progress:
                    progress(len(collected), f"{date_str} p{page} 전부 중복, 다음 날짜로")
                break

            fresh = [u for u, t in unseen if _matches_keywords(t, keywords)]
            if not fresh:
                if progress:
                    progress(len(collected), f"{date_str} p{page} 키워드 불일치, 다음 페이지로")
                continue

            mark = len(collected)     # 이번 페이지에서 새로 담기 시작한 위치
            for u, item, error in _fetch_page_articles(fresh, workers, progress, len(collected), date_str):
                if error:
                    continue
                if not item:
                    # 파싱 실패한 URL 도 seen 에 넣어야 다음 실행에서 또 시도하지 않는다
                    seen.add(url_hash(u))
                    continue
                seen.add(item["url_hash"])
                collected.append(item)

            # 페이지 단위로 커밋해야 중간에 죽어도 여기까지는 남는다
            db.mark_crawled(conn, collected[mark:])
            time.sleep(1.0)

    db.set_meta(conn, "last_crawl_at", datetime.now().strftime(DATE_FMT))
    return collected


def last_crawl_at(conn) -> str:
    return db.get_meta(conn, "last_crawl_at")


def minutes_since_last_crawl(conn) -> float:
    """마지막 크롤링 후 몇 분 지났는지. 한 번도 안 했으면 무한대."""
    ts = last_crawl_at(conn)
    if not ts:
        return float("inf")
    try:
        return (datetime.now() - datetime.strptime(ts, DATE_FMT)).total_seconds() / 60
    except ValueError:
        return float("inf")

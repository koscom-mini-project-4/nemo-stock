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
"""
import hashlib
import random
import time
from datetime import datetime, timedelta

from . import db
from .config import (NAVER_LIST_URL, HTTP_HEADERS, CRAWL_DELAY, CRAWL_TIMEOUT,
                     CRAWL_DAYS, CRAWL_MAX_PAGES, DATE_FMT)

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


def _list_page(session, date_str: str, page: int) -> list:
    """목록 페이지 하나에서 기사 URL 들을 뽑는다."""
    from bs4 import BeautifulSoup
    res = session.get(f"{NAVER_LIST_URL}&date={date_str}&page={page}",
                      timeout=CRAWL_TIMEOUT)
    if res.status_code != 200:
        return []
    soup = BeautifulSoup(res.text, "html.parser")
    urls, seen = [], set()
    for a in soup.select(LIST_SELECTOR):
        href = a.get("href", "")
        if "article/" not in href:
            continue
        u = _normalize(href)
        if u not in seen:
            seen.add(u)
            urls.append(u)
    return urls


def _article(session, url: str) -> dict:
    """기사 상세. 제목이나 본문이 없으면 None."""
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

    return {
        "url": url,
        "url_hash": url_hash(url),
        "title": title,
        "content": content,
        "summary": content[:200] + "..." if len(content) > 200 else content,
        "published_at": published or datetime.now().strftime(DATE_FMT),
    }


def crawl(conn, days: int = CRAWL_DAYS, max_pages: int = CRAWL_MAX_PAGES,
          progress=None) -> list:
    """새 기사만 수집해서 `crawled` 테이블에 넣고, 새로 받은 것만 돌려준다.

    days      : 오늘부터 며칠 전까지의 목록을 훑을지
    max_pages : 날짜당 최대 목록 페이지 수 (무한 루프 방지)
    progress  : progress(수집수, 메시지) 콜백
    """
    seen = db.seen_hashes(conn)
    session = _session()
    collected = []

    for offset in range(days):
        date_str = (datetime.now() - timedelta(days=offset)).strftime("%Y%m%d")

        for page in range(1, max_pages + 1):
            try:
                urls = _list_page(session, date_str, page)
            except Exception as e:
                if progress:
                    progress(len(collected), f"{date_str} p{page} 목록 실패: {e}")
                break

            if not urls:
                break

            fresh = [u for u in urls if url_hash(u) not in seen]
            if not fresh:
                # 이 페이지가 전부 이미 본 기사 -> 이 날짜는 더 볼 게 없다
                if progress:
                    progress(len(collected), f"{date_str} p{page} 전부 중복, 다음 날짜로")
                break

            mark = len(collected)     # 이번 페이지에서 새로 담기 시작한 위치
            for u in fresh:
                time.sleep(random.uniform(*CRAWL_DELAY))
                try:
                    item = _article(session, u)
                except Exception as e:
                    if progress:
                        progress(len(collected), f"기사 실패: {e}")
                    continue
                if not item:
                    # 파싱 실패한 URL 도 seen 에 넣어야 다음 실행에서 또 시도하지 않는다
                    seen.add(url_hash(u))
                    continue
                seen.add(item["url_hash"])
                collected.append(item)
                if progress:
                    progress(len(collected), item["title"][:30])

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

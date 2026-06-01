"""
TAB 3 — 특징주 뉴스
dashboard.py의 기존 탭 구조에 아래 코드를 붙여넣으면 됩니다.

추가 의존성 없음 (기존 requirements.txt 그대로 사용 가능)
"""

import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta

import requests
import streamlit as st

# ── 상수 ──────────────────────────────────────────────────────────────
RSS_URL = "https://news.google.com/rss/search?q=특징주&hl=ko&gl=KR&ceid=KR:ko"
MAX_ITEMS = 100
KST = timezone(timedelta(hours=9))

STOCK_PATTERN = re.compile(
    r"['\"]?([가-힣A-Za-z&]+(?:\s[가-힣A-Za-z]+)?)['\"]?\s*"
    r"(?:주가|급등|급락|상한가|하한가|강세|약세|매수|매도|상승|하락|신고가|신저가|이슈|테마|관련주|수혜|주목|선정)"
)

NOISE_WORDS = {
    "오늘", "내일", "시장", "증시", "코스피", "코스닥", "전망", "분석", "투자", "주식",
    "이슈", "테마", "관련", "수혜", "특징", "종목", "뉴스", "기업", "업종", "섹터",
    "글로벌", "미국", "중국", "일본", "외국인", "기관", "개인", "거래량", "시가총액",
}


# ── 데이터 수집 ──────────────────────────────────────────────────────
@st.cache_data(ttl=300)
def fetch_rss_news() -> list[dict]:
    try:
        resp = requests.get(RSS_URL, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
    except Exception as e:
        st.error(f"RSS 수집 실패: {e}")
        return []

    items = []
    for item in root.findall(".//item")[:MAX_ITEMS]:
        title = item.findtext("title", "").strip()
        link  = item.findtext("link", "").strip()
        pub_date_raw = item.findtext("pubDate", "").strip()
        source = item.findtext("source", "").strip()

        try:
            pub_dt = datetime.strptime(pub_date_raw, "%a, %d %b %Y %H:%M:%S %Z")
            pub_dt = pub_dt.replace(tzinfo=timezone.utc).astimezone(KST)
            pub_str = pub_dt.strftime("%Y-%m-%d %H:%M")
        except Exception:
            pub_str = pub_date_raw[:16] if pub_date_raw else "날짜 미상"

        original_link = extract_original_url(link)
        stocks = extract_stock_names(title)

        items.append({
            "title": title,
            "link": original_link,
            "pub_str": pub_str,
            "source": source,
            "stocks": stocks,
        })

    return items


def extract_original_url(google_url: str) -> str:
    match = re.search(r"url=([^&]+)", google_url)
    if match:
        from urllib.parse import unquote
        return unquote(match.group(1))
    return google_url


def extract_stock_names(title: str) -> list[str]:
    found = STOCK_PATTERN.findall(title)
    cleaned = []
    for name in found:
        name = name.strip()
        if len(name) >= 2 and name not in NOISE_WORDS:
            cleaned.append(name)
    return list(dict.fromkeys(cleaned))


def get_all_stock_tags(news_list: list[dict]) -> list[str]:
    from collections import Counter
    counter = Counter()
    for item in news_list:
        for s in item["stocks"]:
            counter[s] += 1
    return [name for name, cnt in counter.most_common(10) if cnt >= 2]


# ── Streamlit UI ─────────────────────────────────────────────────────
def render_tab3():
    st.subheader("📰 특징주 뉴스")

    with st.spinner("뉴스 수집 중..."):
        news_list = fetch_rss_news()

    if not news_list:
        st.warning("뉴스를 불러오지 못했습니다.")
        return

    last_updated = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S KST")
    st.caption(f"총 {len(news_list)}건 · 마지막 업데이트: {last_updated} · 5분 캐시")

    # ── 검색창 + 새로고침 ──
    col_search, col_refresh = st.columns([5, 1])
    with col_search:
        search_query = st.text_input(
            "종목명 검색",
            placeholder="예: 삼성전자, 카카오, 현대차",
            label_visibility="collapsed",
        )
    with col_refresh:
        if st.button("🔄 새로고침", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    # ── 종목 태그 ──
    stock_tags = get_all_stock_tags(news_list)
    selected_tag = st.session_state.get("selected_tag", "")

    if stock_tags:
        st.markdown("**📌 급등 종목 태그**")
        tag_cols = st.columns(len(stock_tags))
        for i, tag in enumerate(stock_tags):
            with tag_cols[i]:
                if st.button(tag, key=f"tag_{tag}", use_container_width=True):
                    st.session_state.selected_tag = tag
                    selected_tag = tag

    # ── 필터 적용 ──
    active_filter = (selected_tag or search_query).strip()

    filtered = news_list
    if active_filter:
        keyword = active_filter.lower()
        filtered = [
            item for item in news_list
            if keyword in item["title"].lower()
            or any(keyword in s.lower() for s in item["stocks"])
        ]
        col_info, col_clear = st.columns([5, 1])
        with col_info:
            st.info(f"🔍 '{active_filter}' 검색 결과: {len(filtered)}건")
        with col_clear:
            if st.button("✕ 초기화", use_container_width=True):
                st.session_state.selected_tag = ""
                st.rerun()

    if not filtered:
        st.warning("검색 결과가 없습니다.")
        return

    st.divider()

    # ── 뉴스 목록 ──
    for item in filtered:
        st.markdown(f"**[{item['title']}]({item['link']})**")
        meta_parts = [f"🕐 {item['pub_str']}"]
        if item["source"]:
            meta_parts.append(f"📰 {item['source']}")
        if item["stocks"]:
            tags_str = " ".join(f"`{s}`" for s in item["stocks"])
            meta_parts.append(f"🏷️ {tags_str}")
        st.caption(" · ".join(meta_parts))
        st.divider()


# ── 단독 실행 테스트 ──────────────────────────────────────────────────
if __name__ == "__main__":
    st.set_page_config(page_title="특징주 테스트", layout="wide")
    render_tab3()

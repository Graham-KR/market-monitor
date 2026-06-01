import os
import re
from datetime import datetime, timezone, timedelta

import streamlit as st

KST = timezone(timedelta(hours=9))

STOCK_PATTERN = re.compile(
    r"['\"]?([가-힣A-Za-z&]+(?:\s[가-힣A-Za-z]+)?)['\"]?\s*"
    r"(?:주가|급등|급락|상한가|하한가|강세|약세|매수|매도|상승|하락|신고가|신저가|이슈|테마|관련주|수혜|주목|선정)"
)
NOISE_WORDS = {
    "오늘","내일","시장","증시","코스피","코스닥","전망","분석","투자","주식",
    "이슈","테마","관련","수혜","특징","종목","뉴스","기업","업종","섹터",
    "글로벌","미국","중국","일본","외국인","기관","개인","거래량","시가총액",
}


@st.cache_data(ttl=300)
def fetch_news_from_db(date_str: str) -> list[dict]:
    from supabase import create_client
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_KEY"]
    supabase = create_client(url, key)
    start = f"{date_str}T00:00:00+09:00"
    end   = f"{date_str}T23:59:59+09:00"
    res = (
        supabase.table("featured_news")
        .select("pub_dt, title, link, source, stocks")
        .gte("pub_dt", start)
        .lte("pub_dt", end)
        .order("pub_dt", desc=True)
        .limit(500)
        .execute()
    )
    return res.data or []


@st.cache_data(ttl=3600)
def get_available_dates() -> list[str]:
    from supabase import create_client
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_KEY"]
    supabase = create_client(url, key)
    res = (
        supabase.table("featured_news")
        .select("pub_dt")
        .order("pub_dt", desc=True)
        .limit(1000)
        .execute()
    )
    dates = set()
    for row in res.data or []:
        try:
            dt = datetime.fromisoformat(row["pub_dt"]).astimezone(KST)
            dates.add(dt.strftime("%Y-%m-%d"))
        except Exception:
            pass
    return sorted(dates, reverse=True)


def get_all_stock_tags(news_list: list[dict]) -> list[str]:
    from collections import Counter
    counter = Counter()
    for item in news_list:
        for s in (item.get("stocks") or []):
            counter[s] += 1
    return [name for name, cnt in counter.most_common(10) if cnt >= 2]


def render_tab3():
    st.subheader("📰 특징주 뉴스")

    # ── 날짜 선택 ──
    with st.spinner("날짜 목록 조회 중..."):
        available_dates = get_available_dates()

    if not available_dates:
        st.warning("수집된 뉴스가 없습니다. 오늘 18:00 이후 자동 수집됩니다.")
        return

    min_date = datetime.strptime(available_dates[-1], "%Y-%m-%d").date()
    max_date = datetime.strptime(available_dates[0], "%Y-%m-%d").date()
    selected_date = st.date_input(
        "날짜 선택",
        value=max_date,
        min_value=min_date,
        max_value=max_date,
        label_visibility="collapsed",
    ).strftime("%Y-%m-%d")

    # ── 뉴스 로드 ──
    with st.spinner("뉴스 불러오는 중..."):
        news_list = fetch_news_from_db(selected_date)

    if not news_list:
        st.warning(f"{selected_date} 뉴스가 없습니다.")
        return

    last_updated = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S KST")
    st.caption(f"총 {len(news_list)}건 · {selected_date} · 마지막 업데이트: {last_updated}")

    # ── 검색창 + 검색 버튼 ──
    col_search, col_btn = st.columns([5, 1])
    with col_search:
        search_query = st.text_input(
            "종목명 검색",
            placeholder="예: 삼성전자, 카카오, 현대차",
            label_visibility="collapsed",
            on_change=lambda: None,
        )
    with col_btn:
        if st.button("🔍 검색", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    # ── active_filter 계산 ──
    selected_tag  = st.session_state.get("selected_tag", "")
    active_filter = (selected_tag or search_query).strip()

    # ── 필터 적용 ──
    if active_filter:
        keyword  = active_filter.lower()
        filtered = [
            item for item in news_list
            if keyword in item["title"].lower()
            or any(keyword in s.lower() for s in (item.get("stocks") or []))
        ]
        col_info, col_clear = st.columns([5, 1])
        with col_info:
            st.info(f"🔍 '{active_filter}' 검색 결과: {len(filtered)}건")
        with col_clear:
            if st.button("✕ 초기화", use_container_width=True):
                st.session_state.selected_tag = ""
                st.rerun()
    else:
        filtered = news_list

    # ── 종목 태그 (필터 적용된 결과 기준) ──
    tag_source = filtered if active_filter else news_list
    stock_tags = get_all_stock_tags(tag_source)

    if stock_tags:
        st.markdown("**📌 급등 종목 태그**")
        tag_cols = st.columns(len(stock_tags))
        for i, tag in enumerate(stock_tags):
            with tag_cols[i]:
                if st.button(tag, key=f"tag_{tag}", use_container_width=True):
                    st.session_state.selected_tag = tag
                    st.rerun()

    if not filtered:
        st.warning("검색 결과가 없습니다.")
        return

    st.divider()

    # ── 뉴스 목록 ──
    for item in filtered:
        try:
            dt = datetime.fromisoformat(item["pub_dt"]).astimezone(KST)
            pub_str = dt.strftime("%Y-%m-%d %H:%M")
        except Exception:
            pub_str = item.get("pub_dt", "")[:16]

        st.markdown(f"**[{item['title']}]({item['link']})**")
        meta_parts = [f"🕐 {pub_str}"]
        if item.get("source"):
            meta_parts.append(f"📰 {item['source']}")
        if item.get("stocks"):
            tags_str = " ".join(f"`{s}`" for s in item["stocks"])
            meta_parts.append(f"🏷️ {tags_str}")
        st.caption(" · ".join(meta_parts))
        st.divider()


if __name__ == "__main__":
    st.set_page_config(page_title="특징주 테스트", layout="wide")
    render_tab3()

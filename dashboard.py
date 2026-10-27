import os

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots
from supabase import create_client

from tab3_featured_stocks import render_tab3

# ══════════════════════════════════════════
# 기본 설정
# ══════════════════════════════════════════
st.set_page_config(page_title="시장 모니터", layout="wide")

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# 금투협 API 전환 기준일 (이 날짜부터 백만원 단위)
KOFIA_START = pd.Timestamp("2026-06-10")

# 색상
COLOR_BLUE  = "#378ADD"
COLOR_RED   = "#D85A30"
COLOR_SKY   = "#85B7EB"
COLOR_GREEN = "#1D9E75"
BAR_COLORS  = ["#FF0000", "#A32D2D", "#888888", "#0C447C", "#0000FF"]
BAR_LABELS  = ["상한", "상승", "보합", "하락", "하한"]


# ══════════════════════════════════════════
# 데이터 로드
# ══════════════════════════════════════════
@st.cache_data(ttl=600)  # 10분마다 자동으로 새 데이터 확인
def load_table(name: str, limit: int) -> pd.DataFrame:
    # Supabase는 한 번에 최대 1,000행까지만 돌려주므로 1,000행씩 나눠서 모두 가져옴
    page_size = 1000
    rows = []
    while len(rows) < limit:
        start = len(rows)
        end = min(start + page_size, limit) - 1
        res = (
            supabase.table(name)
            .select("*")
            .order("base_date", desc=True)
            .range(start, end)
            .execute()
        )
        rows.extend(res.data)
        if len(res.data) < end - start + 1:  # 마지막 페이지
            break
    return pd.DataFrame(rows)


df_credit = load_table("credit_loan", 5000)
df_fund   = load_table("mkt_fund", 5000)
df_adr    = load_table("adr", 500)


# ══════════════════════════════════════════
# 공통 함수
# ══════════════════════════════════════════
def to_uk(x):
    """원 단위 → 억원"""
    return x / 100_000_000


def to_uk_mn(x):
    """백만원 단위 → 억원"""
    return x / 100


def convert_units(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """KOFIA_START 이후는 백만원, 이전은 원 단위 → 모두 억원으로 통일"""
    is_new = df["base_date"] >= KOFIA_START
    for c in cols:
        df[c] = df[c].where(~is_new, to_uk_mn(df[c])).where(is_new, to_uk(df[c]))
    return df


def prepare(df: pd.DataFrame) -> pd.DataFrame:
    """날짜 변환 + 오름차순 정렬"""
    df["base_date"] = pd.to_datetime(df["base_date"])
    return df.sort_values("base_date").reset_index(drop=True)


def add_change(df: pd.DataFrame, col: str, prefix: str) -> pd.DataFrame:
    """전일 대비 증감 / 증감률 컬럼 추가"""
    df[f"{prefix}_chg"] = df[col].diff()
    df[f"{prefix}_pct"] = (df[f"{prefix}_chg"] / df[col].shift(1) * 100).round(2)
    return df


def fmt_num(x):
    return f"{x:,.0f}"


def fmt_chg(x):
    return f"{x:+,.0f}" if pd.notna(x) else "-"


def fmt_pct(x):
    return f"{x:+.2f}%" if pd.notna(x) else "-"


def make_html_table(df: pd.DataFrame, cols: list[str], chg_cols: list[str]) -> str:
    th = "".join(
        f'<th style="padding:7px 10px;text-align:{"left" if c == "날짜" else "right"};'
        f'background:#f5f5f5;font-size:12px;font-weight:600;color:#444;'
        f'border-bottom:2px solid #ddd;white-space:nowrap;">{c}</th>'
        for c in cols
    )

    rows_html = ""
    for _, row in df[cols].iterrows():
        tds = ""
        for c in cols:
            val   = row[c]
            align = "left" if c == "날짜" else "right"
            style = f"padding:6px 10px;text-align:{align};border-bottom:1px solid #eee;font-size:13px;"

            if c in chg_cols:
                try:
                    v = float(str(val).replace(",", "").replace("%", "").replace("+", ""))
                    if v > 0:
                        style += "background:#FCEBEB;color:#A32D2D;font-weight:500;"
                    elif v < 0:
                        style += "background:#E6F1FB;color:#0C447C;font-weight:500;"
                except ValueError:
                    pass
            elif c == "날짜":
                style += "color:#666;"

            tds += f'<td style="{style}">{val}</td>'
        rows_html += f"<tr>{tds}</tr>"

    return (
        '<div style="overflow-x:auto;border:1px solid #ddd;border-radius:8px;">'
        '<table style="width:100%;border-collapse:collapse;">'
        f"<thead><tr>{th}</tr></thead>"
        f"<tbody>{rows_html}</tbody>"
        "</table></div>"
    )


def line_trace(df, y, name, color, width=1.5):
    return go.Scatter(x=df["base_date"], y=df[y], name=name, line=dict(color=color, width=width))


def bar_chart(values: list[int]) -> go.Figure:
    fig = go.Figure(go.Bar(
        x=BAR_LABELS, y=values,
        marker_color=BAR_COLORS,
        text=values, textposition="outside",
    ))
    fig.update_layout(
        margin=dict(l=0, r=0, t=20, b=0), height=300,
        plot_bgcolor="white", paper_bgcolor="white",
        yaxis=dict(showgrid=False, showticklabels=False),
        xaxis=dict(showgrid=False),
    )
    return fig


def adr_comment(adr: float) -> str:
    if adr >= 150:
        return "🔥 과열 구간"
    if adr >= 100:
        return "✅ 강세 구간"
    if adr >= 70:
        return "🟡 중립 구간"
    if adr >= 40:
        return "🔵 약세 구간"
    return "❄️ 침체 구간"


# ══════════════════════════════════════════
# 탭 구성
# ══════════════════════════════════════════
# 새로고침 버튼: 저장해 둔 데이터를 지우고 Supabase에서 다시 불러옴
_, refresh_col = st.columns([6, 1])
if refresh_col.button("🔄 새로고침", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

tab1, tab2, tab3 = st.tabs(["📊 신용거래융자 & 증시자금", "📈 ADR", "📰 특징주"])


# ── TAB 1: 신용거래융자 & 증시자금 ─────────────
with tab1:

    # ── 신용거래융자 ──
    if df_credit.empty:
        st.warning("아직 수집된 데이터가 없습니다.")
    else:
        df_credit = prepare(df_credit)
        df_credit = convert_units(df_credit, ["total", "kospi", "kosdaq"])

        latest = df_credit.iloc[-1]
        prev   = df_credit.iloc[-2] if len(df_credit) > 1 else latest
        latest_date = latest["base_date"].strftime("%Y-%m-%d")

        st.markdown(
            '<div style="display:flex;align-items:flex-end;justify-content:space-between;margin-bottom:1rem;">'
            '<h1 style="font-size:2rem;font-weight:600;margin:0;">신용거래융자 &amp; 증시자금 모니터</h1>'
            '<span style="font-size:15px;color:gray;padding-bottom:4px;white-space:nowrap;">'
            f'최신 데이터 기준일: <strong style="color:#222;">{latest_date}</strong></span>'
            "</div>",
            unsafe_allow_html=True,
        )

        col1, col2, col3 = st.columns(3)
        col1.metric("전체 융자잔고", f"{latest['total']:,.0f}억",  f"{latest['total']  - prev['total']:+,.0f}억")
        col2.metric("코스피",        f"{latest['kospi']:,.0f}억",  f"{latest['kospi']  - prev['kospi']:+,.0f}억")
        col3.metric("코스닥",        f"{latest['kosdaq']:,.0f}억", f"{latest['kosdaq'] - prev['kosdaq']:+,.0f}억")

        fig = go.Figure()
        fig.add_trace(line_trace(df_credit, "total",  "전체",   COLOR_BLUE))
        fig.add_trace(line_trace(df_credit, "kospi",  "코스피", COLOR_RED))
        fig.add_trace(line_trace(df_credit, "kosdaq", "코스닥", COLOR_SKY))
        fig.update_layout(
            title=dict(text="융자잔고 추이 (억원)", font=dict(size=16), x=0),
            legend=dict(orientation="h", x=0.25, y=1.12, xanchor="left"),
            margin=dict(l=0, r=0, t=60, b=0), height=340,
            xaxis=dict(showgrid=False),
            yaxis=dict(tickformat=",", gridcolor="#f0f0f0"),
            plot_bgcolor="white", paper_bgcolor="white", hovermode="x unified",
        )
        with st.expander("📈 융자잔고 추이 그래프 보기", expanded=False):
            st.plotly_chart(fig, use_container_width=True, key="credit_line")

        max_days = len(df_credit)  # 저장된 전체 영업일 수
        input_col, _ = st.columns([1, 3])
        days = int(input_col.number_input(
            f"표시 기간 (영업일, 최대 {max_days:,}일)",
            min_value=1, max_value=max_days, value=min(20, max_days), step=1,
        ))
        st.subheader(f"최근 {days}일 기록")

        tbl = df_credit.copy()
        for col in ["total", "kospi", "kosdaq"]:
            tbl = add_change(tbl, col, col)

        show = tbl.sort_values("base_date", ascending=False).head(days).copy()
        show["날짜"]          = show["base_date"].dt.strftime("%Y-%m-%d")
        show["전체(억)"]      = show["total"].map(fmt_num)
        show["전체 증감"]     = show["total_chg"].map(fmt_chg)
        show["전체 증감률"]   = show["total_pct"].map(fmt_pct)
        show["코스피(억)"]    = show["kospi"].map(fmt_num)
        show["코스피 증감"]   = show["kospi_chg"].map(fmt_chg)
        show["코스피 증감률"] = show["kospi_pct"].map(fmt_pct)
        show["코스닥(억)"]    = show["kosdaq"].map(fmt_num)
        show["코스닥 증감"]   = show["kosdaq_chg"].map(fmt_chg)
        show["코스닥 증감률"] = show["kosdaq_pct"].map(fmt_pct)

        chg_cols = ["전체 증감", "전체 증감률", "코스피 증감", "코스피 증감률", "코스닥 증감", "코스닥 증감률"]
        cols = ["날짜", "전체(억)", "전체 증감", "전체 증감률",
                "코스피(억)", "코스피 증감", "코스피 증감률",
                "코스닥(억)", "코스닥 증감", "코스닥 증감률"]
        st.markdown(make_html_table(show, cols, chg_cols), unsafe_allow_html=True)

    # ── 증시자금 ──
    st.divider()
    st.subheader("증시자금 현황")

    if df_fund.empty:
        st.info("증시자금 데이터 수집 대기 중입니다.")
    else:
        df_fund = prepare(df_fund)
        # 참고: DB 칸 이름은 cma_bal 이지만 실제 값은 금투협 "위탁매매 미수금" (TMPV5)
        df_fund = convert_units(df_fund, ["inv_deposit", "cma_bal"])

        latest_fund = df_fund.iloc[-1]
        prev_fund   = df_fund.iloc[-2] if len(df_fund) > 1 else latest_fund

        c1, c2 = st.columns(2)
        c1.metric("투자자예탁금", f"{latest_fund['inv_deposit']:,.0f}억",
                  f"{latest_fund['inv_deposit'] - prev_fund['inv_deposit']:+,.0f}억")
        c2.metric("위탁매매 미수금", f"{latest_fund['cma_bal']:,.0f}억",
                  f"{latest_fund['cma_bal'] - prev_fund['cma_bal']:+,.0f}억")

        fig2 = make_subplots(specs=[[{"secondary_y": True}]])
        fig2.add_trace(line_trace(df_fund, "inv_deposit", "투자자예탁금", COLOR_BLUE),  secondary_y=False)
        fig2.add_trace(line_trace(df_fund, "cma_bal",     "위탁매매 미수금", COLOR_GREEN), secondary_y=True)
        fig2.update_layout(
            legend=dict(orientation="h", x=0, y=1.12),
            margin=dict(l=0, r=0, t=40, b=0), height=280,
            xaxis=dict(showgrid=False),
            plot_bgcolor="white", paper_bgcolor="white", hovermode="x unified",
        )
        fig2.update_yaxes(tickformat=",", gridcolor="#f0f0f0", secondary_y=False)
        fig2.update_yaxes(tickformat=",", showgrid=False,      secondary_y=True)
        with st.expander("📈 예탁금 · 미수금 추이 그래프 보기", expanded=False):
            st.plotly_chart(fig2, use_container_width=True, key="fund_line")

        tbl_fund = df_fund.copy()
        tbl_fund = add_change(tbl_fund, "inv_deposit", "inv")
        tbl_fund = add_change(tbl_fund, "cma_bal",     "cma")

        show_fund = tbl_fund.sort_values("base_date", ascending=False).head(20).copy()
        show_fund["날짜"]          = show_fund["base_date"].dt.strftime("%Y-%m-%d")
        show_fund["예탁금(억)"]    = show_fund["inv_deposit"].map(fmt_num)
        show_fund["예탁금 증감"]   = show_fund["inv_chg"].map(fmt_chg)
        show_fund["예탁금 증감률"] = show_fund["inv_pct"].map(fmt_pct)
        show_fund["미수금(억)"]     = show_fund["cma_bal"].map(fmt_num)
        show_fund["미수금 증감"]    = show_fund["cma_chg"].map(fmt_chg)
        show_fund["미수금 증감률"]  = show_fund["cma_pct"].map(fmt_pct)

        fund_chg_cols = ["예탁금 증감", "예탁금 증감률", "미수금 증감", "미수금 증감률"]
        fund_cols = ["날짜", "예탁금(억)", "예탁금 증감", "예탁금 증감률",
                     "미수금(억)", "미수금 증감", "미수금 증감률"]
        st.markdown(make_html_table(show_fund, fund_cols, fund_chg_cols), unsafe_allow_html=True)

    st.caption("데이터 출처: 금융투자협회 | 매일 15:03 · 18:03 자동 수집 (월~토)")


# ── TAB 2: ADR ────────────────────────────
with tab2:
    st.subheader("ADR (등락비율)")
    st.caption("ADR = 상승종목수 / 하락종목수 × 100 | 100 이상: 강세, 100 미만: 약세")

    if df_adr.empty:
        st.info("ADR 데이터 수집 대기 중입니다.")
    else:
        df_adr = prepare(df_adr)
        latest_adr = df_adr.iloc[-1]
        adr_date   = latest_adr["base_date"].strftime("%Y-%m-%d")

        st.markdown(
            f'<p style="text-align:right;color:gray;font-size:14px;">기준일: <strong>{adr_date}</strong></p>',
            unsafe_allow_html=True,
        )

        # 화살표 없이 표시
        c1, c2 = st.columns(2)
        c1.metric("KOSPI ADR", f"{latest_adr['kospi_adr']:.2f}",
                  f"상승 {int(latest_adr['kospi_up'])} / 하락 {int(latest_adr['kospi_down'])}",
                  delta_color="off")
        c2.metric("KOSDAQ ADR", f"{latest_adr['kosdaq_adr']:.2f}",
                  f"상승 {int(latest_adr['kosdaq_up'])} / 하락 {int(latest_adr['kosdaq_down'])}",
                  delta_color="off")

        st.divider()

        with st.expander("📊 종목 현황 그래프 보기 (상한·상승·보합·하락·하한)", expanded=False):
            col1, col2 = st.columns(2)
            for column, market, title in [(col1, "kospi", "KOSPI"), (col2, "kosdaq", "KOSDAQ")]:
                with column:
                    st.markdown(f"#### {title} 종목 현황")
                    values = [
                        int(latest_adr[f"{market}_upper_limit"]),
                        int(latest_adr[f"{market}_up"]),
                        int(latest_adr[f"{market}_flat"]),
                        int(latest_adr[f"{market}_down"]),
                        int(latest_adr[f"{market}_lower_limit"]),
                    ]
                    st.plotly_chart(bar_chart(values), use_container_width=True, key=f"adr_bar_{market}")

        st.divider()

        kospi_adr  = float(latest_adr["kospi_adr"])
        kosdaq_adr = float(latest_adr["kosdaq_adr"])

        c1, c2 = st.columns(2)
        c1.info(f"KOSPI: {adr_comment(kospi_adr)} ({kospi_adr:.2f})")
        c2.info(f"KOSDAQ: {adr_comment(kosdaq_adr)} ({kosdaq_adr:.2f})")

        # ADR 구간 해설
        st.divider()
        st.markdown("#### ADR 구간 해설")
        st.markdown("""
| 구간 | ADR 범위 | 의미 |
|------|----------|------|
| 🔥 과열 | 150 이상 | 단기 급등 과열 — 조정 가능성 높음 |
| ✅ 강세 | 100 ~ 150 | 상승 종목이 하락 종목보다 많은 건강한 상승장 |
| 🟡 중립 | 70 ~ 100 | 상승/하락 균형 — 방향성 탐색 구간 |
| 🔵 약세 | 40 ~ 70 | 하락 종목 우세 — 하락 추세 진행 중 |
| ❄️ 침체 | 40 미만 | 극단적 약세 — 단기 반등 가능성 있음 |
""")

        # 이동평균 ADR (10일)
        if len(df_adr) >= 10:
            st.divider()
            df_adr["kospi_adr_ma10"]  = df_adr["kospi_adr"].rolling(10).mean()
            df_adr["kosdaq_adr_ma10"] = df_adr["kosdaq_adr"].rolling(10).mean()

            fig_ma = go.Figure()
            fig_ma.add_trace(line_trace(df_adr, "kospi_adr_ma10",  "KOSPI ADR(10일)",  COLOR_RED,  width=2))
            fig_ma.add_trace(line_trace(df_adr, "kosdaq_adr_ma10", "KOSDAQ ADR(10일)", COLOR_BLUE, width=2))
            fig_ma.add_hline(y=100, line_dash="dash", line_color="gray", annotation_text="기준선(100)")
            fig_ma.update_layout(
                legend=dict(orientation="h", x=0, y=1.12),
                margin=dict(l=0, r=0, t=40, b=0), height=300,
                xaxis=dict(showgrid=False, type="date"),
                yaxis=dict(gridcolor="#f0f0f0"),
                plot_bgcolor="white", paper_bgcolor="white",
                hovermode="x unified",
            )
            with st.expander("📈 이동평균 ADR 추이 (10일) 그래프 보기", expanded=False):
                st.plotly_chart(fig_ma, use_container_width=True, key="adr_ma10")

        st.caption("데이터 출처: 네이버금융 | 매일 15:03 · 18:03 자동 수집 (월~토)")


# ── TAB 3: 특징주 ─────────────────────────
with tab3:
    render_tab3()

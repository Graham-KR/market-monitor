import os
import streamlit as st
import pandas as pd
from supabase import create_client

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

st.set_page_config(page_title="신용거래융자 모니터", layout="wide")
st.title("신용거래융자 & 증시자금 모니터")

@st.cache_data(ttl=3600)
def load_credit():
    res = supabase.table("credit_loan").select("*").order("base_date", desc=True).limit(120).execute()
    return pd.DataFrame(res.data)

@st.cache_data(ttl=3600)
def load_fund():
    res = supabase.table("mkt_fund").select("*").order("base_date", desc=True).limit(60).execute()
    return pd.DataFrame(res.data)

df_credit = load_credit()
df_fund   = load_fund()

if df_credit.empty:
    st.warning("아직 수집된 데이터가 없습니다. 첫 수집은 평일 오후 6시에 자동 실행됩니다.")
else:
    df_credit["base_date"] = pd.to_datetime(df_credit["base_date"])
    df_credit = df_credit.sort_values("base_date").reset_index(drop=True)

    latest = df_credit.iloc[-1]
    prev   = df_credit.iloc[-2] if len(df_credit) > 1 else latest

    # ── 요약 카드 (단위: 억원) ──
    col1, col2, col3 = st.columns(3)
    col1.metric("전체 융자잔고",
                f"{latest['total']:,.0f}억",
                f"{latest['total']-prev['total']:+,.0f}억")
    col2.metric("코스피",
                f"{latest['kospi']:,.0f}억",
                f"{latest['kospi']-prev['kospi']:+,.0f}억")
    col3.metric("코스닥",
                f"{latest['kosdaq']:,.0f}억",
                f"{latest['kosdaq']-prev['kosdaq']:+,.0f}억")

    # ── 추이 차트 (억원) ──
    st.subheader("융자잔고 추이 (억원)")
    chart_df = df_credit.set_index("base_date")[["total","kospi","kosdaq"]]
    chart_df.columns = ["전체","코스피","코스닥"]
    st.line_chart(chart_df)

    # ── 최근 20일 표 (증감액/증감률 포함) ──
    st.subheader("최근 20일 기록")
    tbl = df_credit.copy()
    for col in ["total","kospi","kosdaq"]:
        tbl[f"{col}_chg"] = tbl[col].diff()
        tbl[f"{col}_pct"] = (tbl[f"{col}_chg"] / tbl[col].shift(1) * 100).round(2)

    show = tbl.sort_values("base_date", ascending=False).head(20).copy()
    show["날짜"]          = show["base_date"].dt.strftime("%Y-%m-%d")
    show["전체(억)"]      = show["total"].map("{:,.0f}".format)
    show["전체 증감"]     = show["total_chg"].map(lambda x: f"{x:+,.0f}" if pd.notna(x) else "-")
    show["전체 증감률"]   = show["total_pct"].map(lambda x: f"{x:+.2f}%" if pd.notna(x) else "-")
    show["코스피(억)"]    = show["kospi"].map("{:,.0f}".format)
    show["코스피 증감"]   = show["kospi_chg"].map(lambda x: f"{x:+,.0f}" if pd.notna(x) else "-")
    show["코스피 증감률"] = show["kospi_pct"].map(lambda x: f"{x:+.2f}%" if pd.notna(x) else "-")
    show["코스닥(억)"]    = show["kosdaq"].map("{:,.0f}".format)
    show["코스닥 증감"]   = show["kosdaq_chg"].map(lambda x: f"{x:+,.0f}" if pd.notna(x) else "-")
    show["코스닥 증감률"] = show["kosdaq_pct"].map(lambda x: f"{x:+.2f}%" if pd.notna(x) else "-")

    st.dataframe(
        show[["날짜","전체(억)","전체 증감","전체 증감률",
              "코스피(억)","코스피 증감","코스피 증감률",
              "코스닥(억)","코스닥 증감","코스닥 증감률"]],
        use_container_width=True
    )

st.divider()
st.subheader("증시자금 현황")

if df_fund.empty:
    st.info("증시자금 데이터 수집 대기 중입니다.")
else:
    df_fund["base_date"] = pd.to_datetime(df_fund["base_date"])
    df_fund = df_fund.sort_values("base_date")
    latest_fund = df_fund.iloc[-1]
    c1, c2 = st.columns(2)
    c1.metric("투자자예탁금", f"{latest_fund['inv_deposit']:,.0f}억")
    c2.metric("CMA 잔고",    f"{latest_fund['cma_bal']:,.0f}억")
    fund_chart = df_fund.set_index("base_date")[["inv_deposit","cma_bal"]]
    fund_chart.columns = ["투자자예탁금","CMA잔고"]
    st.line_chart(fund_chart)

st.caption("데이터 출처: 공공데이터포털 금융투자협회종합통계정보 | 매일 18:00 자동 수집")

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
    df_credit = df_credit.sort_values("base_date")

    latest = df_credit.iloc[-1]
    prev   = df_credit.iloc[-2] if len(df_credit) > 1 else latest

    col1, col2, col3 = st.columns(3)
    col1.metric("전체 융자잔고",
                f"{latest['total']/1e4:.2f}조",
                f"{(latest['total']-prev['total'])/1e4:+.3f}조")
    col2.metric("코스피",
                f"{latest['kospi']/1e4:.2f}조",
                f"{(latest['kospi']-prev['kospi'])/1e4:+.3f}조")
    col3.metric("코스닥",
                f"{latest['kosdaq']/1e4:.2f}조",
                f"{(latest['kosdaq']-prev['kosdaq'])/1e4:+.3f}조")

    st.subheader("융자잔고 추이")
    chart_df = df_credit.set_index("base_date")[["total","kospi","kosdaq"]] / 1e4
    chart_df.columns = ["전체","코스피","코스닥"]
    st.line_chart(chart_df)

    st.subheader("최근 20일 기록")
    show = df_credit.sort_values("base_date", ascending=False).head(20)[
        ["base_date","total","kospi","kosdaq"]
    ].copy()
    show["total"]  = (show["total"]  / 1e4).round(3)
    show["kospi"]  = (show["kospi"]  / 1e4).round(3)
    show["kosdaq"] = (show["kosdaq"] / 1e4).round(3)
    show.columns   = ["날짜","전체(조)","코스피(조)","코스닥(조)"]
    st.dataframe(show, use_container_width=True)

st.divider()
st.subheader("증시자금 현황")

if df_fund.empty:
    st.info("증시자금 데이터 수집 대기 중입니다.")
else:
    df_fund["base_date"] = pd.to_datetime(df_fund["base_date"])
    df_fund = df_fund.sort_values("base_date")
    latest_fund = df_fund.iloc[-1]
    c1, c2 = st.columns(2)
    c1.metric("투자자예탁금", f"{latest_fund['inv_deposit']/1e4:.1f}조")
    c2.metric("CMA 잔고",    f"{latest_fund['cma_bal']/1e4:.1f}조")
    st.line_chart(df_fund.set_index("base_date")[["inv_deposit","cma_bal"]] / 1e4)

st.caption("데이터 출처: 공공데이터포털 금융투자협회종합통계정보 | 매일 18:00 자동 수집")

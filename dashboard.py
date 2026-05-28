import os
import streamlit as st
import pandas as pd
from supabase import create_client

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

st.set_page_config(page_title="신용거래융자 모니터", layout="wide")

@st.cache_data(ttl=3600)
def load_credit():
    res = supabase.table("credit_loan").select("*").order("base_date", desc=True).limit(5000).execute()
    return pd.DataFrame(res.data)

@st.cache_data(ttl=3600)
def load_fund():
    res = supabase.table("mkt_fund").select("*").order("base_date", desc=True).limit(5000).execute()
    return pd.DataFrame(res.data)

df_credit = load_credit()
df_fund   = load_fund()

def to_uk(x):
    return x / 100000000

if df_credit.empty:
    st.title("신용거래융자 & 증시자금 모니터")
    st.warning("아직 수집된 데이터가 없습니다. 첫 수집은 평일 오후 6시에 자동 실행됩니다.")
else:
    df_credit["base_date"] = pd.to_datetime(df_credit["base_date"])
    df_credit = df_credit.sort_values("base_date").reset_index(drop=True)

    for col in ["total", "kospi", "kosdaq"]:
        df_credit[col] = df_credit[col].apply(to_uk)

    latest = df_credit.iloc[-1]
    prev   = df_credit.iloc[-2] if len(df_credit) > 1 else latest
    latest_date = latest["base_date"].strftime("%Y-%m-%d")

    col_title, col_date = st.columns([3, 1])
    with col_title:
        st.title("신용거래융자 & 증시자금 모니터")
    with col_date:
        st.markdown(
            f'<div style="display:flex;align-items:center;height:100%;padding-top:16px;'
            f'justify-content:flex-end;gap:5px;font-size:13px;color:var(--text-color);">'
            f'<span style="opacity:0.6;">최신 데이터 기준일:</span>'
            f'<strong>{latest_date}</strong></div>',
            unsafe_allow_html=True
        )

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

    st.subheader("융자잔고 추이 (억원)")
    chart_df = df_credit.set_index("base_date")[["total","kospi","kosdaq"]]
    chart_df.columns = ["전체","코스피","코스닥"]
    st.line_chart(chart_df)

    max_days = min(len(df_credit), 250)
    days = st.slider("표시 기간 (영업일)", min_value=5, max_value=max_days, value=20, step=5)
    st.subheader(f"최근 {days}일 기록")

    tbl = df_credit.copy()
    for col in ["total","kospi","kosdaq"]:
        tbl[f"{col}_chg"] = tbl[col].diff()
        tbl[f"{col}_pct"] = (tbl[f"{col}_chg"] / tbl[col].shift(1) * 100).round(2)

    show = tbl.sort_values("base_date", ascending=False).head(days).copy()
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

    chg_cols = ["전체 증감","전체 증감률",
                "코스피 증감","코스피 증감률",
                "코스닥 증감","코스닥 증감률"]
    cols = ["날짜","전체(억)","전체 증감","전체 증감률",
            "코스피(억)","코스피 증감","코스피 증감률",
            "코스닥(억)","코스닥 증감","코스닥 증감률"]

    def make_html_table(df):
        th = "".join([
            f'<th style="padding:7px 10px;text-align:{"left" if c=="날짜" else "right"};'
            f'background:#f5f5f5;font-size:12px;font-weight:600;color:#444;'
            f'border-bottom:2px solid #ddd;white-space:nowrap;">{c}</th>'
            for c in cols
        ])
        rows_html = ""
        for _, row in df[cols].iterrows():
            tds = ""
            for c in cols:
                val = row[c]
                align = "left" if c == "날짜" else "right"
                base_style = f"padding:6px 10px;text-align:{align};border-bottom:1px solid #eee;font-size:13px;"
                if c in chg_cols:
                    try:
                        v = float(str(val).replace(",","").replace("%","").replace("+",""))
                        if v > 0:
                            style = base_style + "background:#FCEBEB;color:#A32D2D;font-weight:500;"
                        elif v < 0:
                            style = base_style + "background:#E6F1FB;color:#0C447C;font-weight:500;"
                        else:
                            style = base_style
                    except:
                        style = base_style
                elif c == "날짜":
                    style = base_style + "color:#666;"
                else:
                    style = base_style
                tds += f'<td style="{style}">{val}</td>'
            rows_html += f"<tr>{tds}</tr>"

        return (
            f'<div style="overflow-x:auto;border:1px solid #ddd;border-radius:8px;">'
            f'<table style="width:100%;border-collapse:collapse;">'
            f'<thead><tr>{th}</tr></thead>'
            f'<tbody>{rows_html}</tbody>'
            f'</table></div>'
        )

    st.markdown(make_html_table(show), unsafe_allow_html=True)

st.divider()
st.subheader("증시자금 현황")

if df_fund.empty:
    st.info("증시자금 데이터 수집 대기 중입니다.")
else:
    df_fund["base_date"] = pd.to_datetime(df_fund["base_date"])
    df_fund = df_fund.sort_values("base_date")
    df_fund["inv_deposit"] = df_fund["inv_deposit"]

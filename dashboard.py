import os
import re
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from supabase import create_client
from tab3_featured_stocks import render_tab3

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

st.set_page_config(page_title="시장 모니터", layout="wide")

@st.cache_data(ttl=3600)
def load_credit():
    res = supabase.table("credit_loan").select("*").order("base_date", desc=True).limit(5000).execute()
    return pd.DataFrame(res.data)

@st.cache_data(ttl=3600)
def load_fund():
    res = supabase.table("mkt_fund").select("*").order("base_date", desc=True).limit(5000).execute()
    return pd.DataFrame(res.data)

@st.cache_data(ttl=3600)
def load_adr():
    res = supabase.table("adr").select("*").order("base_date", desc=True).limit(500).execute()
    return pd.DataFrame(res.data)

def to_uk(x):
    return x / 100000000

df_credit = load_credit()
df_fund   = load_fund()
df_adr    = load_adr()

def make_html_table(df, cols, chg_cols):
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

tab1, tab2, tab3 = st.tabs(["신용거래융자 & 증시자금", "ADR", "특징주"])

# ── TAB 1 ──────────────────────────────────
with tab1:
    if df_credit.empty:
        st.warning("아직 수집된 데이터가 없습니다.")
    else:
        df_credit["base_date"] = pd.to_datetime(df_credit["base_date"])
        df_credit = df_credit.sort_values("base_date").reset_index(drop=True)
        for col in ["total", "kospi", "kosdaq"]:
            df_credit[col] = df_credit[col].apply(to_uk)

        latest = df_credit.iloc[-1]
        prev   = df_credit.iloc[-2] if len(df_credit) > 1 else latest
        latest_date = latest["base_date"].strftime("%Y-%m-%d")

        st.markdown(
            f'<div style="display:flex;align-items:flex-end;justify-content:space-between;margin-bottom:1rem;">'
            f'<h1 style="font-size:2rem;font-weight:600;margin:0;">신용거래융자 &amp; 증시자금 모니터</h1>'
            f'<span style="font-size:15px;color:gray;padding-bottom:4px;white-space:nowrap;">'
            f'최신 데이터 기준일: <strong style="color:#222;">{latest_date}</strong></span>'
            f'</div>',
            unsafe_allow_html=True
        )

        col1, col2, col3 = st.columns(3)
        col1.metric("전체 융자잔고", f"{latest['total']:,.0f}억", f"{latest['total']-prev['total']:+,.0f}억")
        col2.metric("코스피", f"{latest['kospi']:,.0f}억", f"{latest['kospi']-prev['kospi']:+,.0f}억")
        col3.metric("코스닥", f"{latest['kosdaq']:,.0f}억", f"{latest['kosdaq']-prev['kosdaq']:+,.0f}억")

        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df_credit["base_date"], y=df_credit["total"], name="전체", line=dict(color="#378ADD", width=1.5)))
        fig.add_trace(go.Scatter(x=df_credit["base_date"], y=df_credit["kospi"], name="코스피", line=dict(color="#D85A30", width=1.5)))
        fig.add_trace(go.Scatter(x=df_credit["base_date"], y=df_credit["kosdaq"], name="코스닥", line=dict(color="#85B7EB", width=1.5)))
        fig.update_layout(
            title=dict(text="융자잔고 추이 (억원)", font=dict(size=16), x=0),
            legend=dict(orientation="h", x=0.25, y=1.12, xanchor="left"),
            margin=dict(l=0, r=0, t=60, b=0), height=340,
            xaxis=dict(showgrid=False),
            yaxis=dict(tickformat=",", gridcolor="#f0f0f0"),
            plot_bgcolor="white", paper_bgcolor="white", hovermode="x unified"
        )
        st.plotly_chart(fig, use_container_width=True)

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

        chg_cols = ["전체 증감","전체 증감률","코스피 증감","코스피 증감률","코스닥 증감","코스닥 증감률"]
        cols = ["날짜","전체(억)","전체 증감","전체 증감률","코스피(억)","코스피 증감","코스피 증감률","코스닥(억)","코스닥 증감","코스닥 증감률"]
        st.markdown(make_html_table(show, cols, chg_cols), unsafe_allow_html=True)

    st.divider()
    st.subheader("증시자금 현황")

    if df_fund.empty:
        st.info("증시자금 데이터 수집 대기 중입니다.")
    else:
        df_fund["base_date"] = pd.to_datetime(df_fund["base_date"])
        df_fund = df_fund.sort_values("base_date")
        df_fund["inv_deposit"] = df_fund["inv_deposit"].apply(to_uk)
        df_fund["cma_bal"]     = df_fund["cma_bal"].apply(to_uk)
        latest_fund = df_fund.iloc[-1]
        prev_fund   = df_fund.iloc[-2] if len(df_fund) > 1 else latest_fund
        c1, c2 = st.columns(2)
        c1.metric("투자자예탁금", f"{latest_fund['inv_deposit']:,.0f}억", f"{latest_fund['inv_deposit']-prev_fund['inv_deposit']:+,.0f}억")
        c2.metric("CMA 잔고", f"{latest_fund['cma_bal']:,.0f}억", f"{latest_fund['cma_bal']-prev_fund['cma_bal']:+,.0f}억")

        fig2 = make_subplots(specs=[[{"secondary_y": True}]])
        fig2.add_trace(go.Scatter(x=df_fund["base_date"], y=df_fund["inv_deposit"], name="투자자예탁금", line=dict(color="#378ADD", width=1.5)), secondary_y=False)
        fig2.add_trace(go.Scatter(x=df_fund["base_date"], y=df_fund["cma_bal"], name="CMA잔고", line=dict(color="#1D9E75", width=1.5)), secondary_y=True)
        fig2.update_layout(
            legend=dict(orientation="h", x=0, y=1.12),
            margin=dict(l=0, r=0, t=40, b=0), height=280,
            xaxis=dict(showgrid=False),
            plot_bgcolor="white", paper_bgcolor="white", hovermode="x unified"
        )
        fig2.update_yaxes(tickformat=",", gridcolor="#f0f0f0", secondary_y=False)
        fig2.update_yaxes(tickformat=",", showgrid=False, secondary_y=True)
        st.plotly_chart(fig2, use_container_width=True)

        tbl_fund = df_fund.copy()
        tbl_fund["inv_chg"] = tbl_fund["inv_deposit"].diff()
        tbl_fund["inv_pct"] = (tbl_fund["inv_chg"] / tbl_fund["inv_deposit"].shift(1) * 100).round(2)
        tbl_fund["cma_chg"] = tbl_fund["cma_bal"].diff()
        tbl_fund["cma_pct"] = (tbl_fund["cma_chg"] / tbl_fund["cma_bal"].shift(1) * 100).round(2)

        show_fund = tbl_fund.sort_values("base_date", ascending=False).head(20).copy()
        show_fund["날짜"]          = show_fund["base_date"].dt.strftime("%Y-%m-%d")
        show_fund["예탁금(억)"]    = show_fund["inv_deposit"].map("{:,.0f}".format)
        show_fund["예탁금 증감"]   = show_fund["inv_chg"].map(lambda x: f"{x:+,.0f}" if pd.notna(x) else "-")
        show_fund["예탁금 증감률"] = show_fund["inv_pct"].map(lambda x: f"{x:+.2f}%" if pd.notna(x) else "-")
        show_fund["CMA잔고(억)"]   = show_fund["cma_bal"].map("{:,.0f}".format)
        show_fund["CMA 증감"]      = show_fund["cma_chg"].map(lambda x: f"{x:+,.0f}" if pd.notna(x) else "-")
        show_fund["CMA 증감률"]    = show_fund["cma_pct"].map(lambda x: f"{x:+.2f}%" if pd.notna(x) else "-")

        fund_chg_cols = ["예탁금 증감","예탁금 증감률","CMA 증감","CMA 증감률"]
        fund_cols = ["날짜","예탁금(억)","예탁금 증감","예탁금 증감률","CMA잔고(억)","CMA 증감","CMA 증감률"]
        st.markdown(make_html_table(show_fund, fund_cols, fund_chg_cols), unsafe_allow_html=True)

    st.caption("데이터 출처: 공공데이터포털 금융투자협회종합통계정보 | 매일 18:00 자동 수집")

# ── TAB 2 ──────────────────────────────────
with tab2:
    st.subheader("ADR (등락비율)")
    st.caption("ADR = 상승종목수 / 하락종목수 × 100 | 100 이상: 강세, 100 미만: 약세")

    if df_adr.empty:
        st.info("ADR 데이터 수집 대기 중입니다.")
    else:
        df_adr["base_date"] = pd.to_datetime(df_adr["base_date"])
        df_adr = df_adr.sort_values("base_date").reset_index(drop=True)
        latest_adr = df_adr.iloc[-1]
        adr_date   = latest_adr["base_date"].strftime("%Y-%m-%d")

        st.markdown(f'<p style="text-align:right;color:gray;font-size:14px;">기준일: <strong>{adr_date}</strong></p>', unsafe_allow_html=True)

        c1, c2 = st.columns(2)
        c1.metric("KOSPI ADR", f"{latest_adr['kospi_adr']:.2f}", f"상승 {int(latest_adr['kospi_up'])} / 하락 {int(latest_adr['kospi_down'])}")
        c2.metric("KOSDAQ ADR", f"{latest_adr['kosdaq_adr']:.2f}", f"상승 {int(latest_adr['kosdaq_up'])} / 하락 {int(latest_adr['kosdaq_down'])}")

        st.divider()

        col1, col2 = st.columns(2)

        with col1:
            st.markdown("#### KOSPI 종목 현황")
            kospi_values = [
                int(latest_adr['kospi_upper_limit']),
                int(latest_adr['kospi_up']),
                int(latest_adr['kospi_flat']),
                int(latest_adr['kospi_down']),
                int(latest_adr['kospi_lower_limit']),
            ]
            kospi_labels = ["상한", "상승", "보합", "하락", "하한"]
            kospi_colors = ["#FF0000", "#A32D2D", "#888888", "#0C447C", "#0000FF"]
            fig_k = go.Figure(go.Bar(
                x=kospi_labels,
                y=kospi_values,
                marker_color=kospi_colors,
                text=kospi_values,
                textposition="outside"
            ))
            fig_k.update_layout(
                margin=dict(l=0, r=0, t=20, b=0), height=300,
                plot_bgcolor="white", paper_bgcolor="white",
                yaxis=dict(showgrid=False, showticklabels=False),
                xaxis=dict(showgrid=False)
            )
            st.plotly_chart(fig_k, use_container_width=True)

        with col2:
            st.markdown("#### KOSDAQ 종목 현황")
            kosdaq_values = [
                int(latest_adr['kosdaq_upper_limit']),
                int(latest_adr['kosdaq_up']),
                int(latest_adr['kosdaq_flat']),
                int(latest_adr['kosdaq_down']),
                int(latest_adr['kosdaq_lower_limit']),
            ]
            kosdaq_labels = ["상한", "상승", "보합", "하락", "하한"]
            kosdaq_colors = ["#FF0000", "#A32D2D", "#888888", "#0C447C", "#0000FF"]
            fig_d = go.Figure(go.Bar(
                x=kosdaq_labels,
                y=kosdaq_values,
                marker_color=kosdaq_colors,
                text=kosdaq_values,
                textposition="outside"
            ))
            fig_d.update_layout(
                margin=dict(l=0, r=0, t=20, b=0), height=300,
                plot_bgcolor="white", paper_bgcolor="white",
                yaxis=dict(showgrid=False, showticklabels=False),
                xaxis=dict(showgrid=False)
            )
            st.plotly_chart(fig_d, use_container_width=True)

        st.divider()

        kospi_adr  = float(latest_adr['kospi_adr'])
        kosdaq_adr = float(latest_adr['kosdaq_adr'])

        def adr_comment(adr):
            if adr >= 150:   return "🔥 과열 구간"
            elif adr >= 100: return "✅ 강세 구간"
            elif adr >= 70:  return "🟡 중립 구간"
            elif adr >= 40:  return "🔵 약세 구간"
            else:            return "❄️ 침체 구간"

        c1, c2 = st.columns(2)
        c1.info(f"KOSPI: {adr_comment(kospi_adr)} ({kospi_adr:.2f})")
        c2.info(f"KOSDAQ: {adr_comment(kosdaq_adr)} ({kosdaq_adr:.2f})")

        # 이동평균 ADR (데이터 10일 이상일 때만 표시)
        if len(df_adr) >= 10:
            st.divider()
            st.markdown("#### 이동평균 ADR 추이 (10일)")
            df_adr["kospi_adr_ma10"]  = df_adr["kospi_adr"].rolling(10).mean()
            df_adr["kosdaq_adr_ma10"] = df_adr["kosdaq_adr"].rolling(10).mean()

            fig_ma = go.Figure()
            fig_ma.add_trace(go.Scatter(
                x=df_adr["base_date"], y=df_adr["kospi_adr_ma10"],
                name="KOSPI ADR(10일)", line=dict(color="#D85A30", width=2)
            ))
            fig_ma.add_trace(go.Scatter(
                x=df_adr["base_date"], y=df_adr["kosdaq_adr_ma10"],
                name="KOSDAQ ADR(10일)", line=dict(color="#378ADD", width=2)
            ))
            fig_ma.add_hline(y=100, line_dash="dash", line_color="gray", annotation_text="기준선(100)")
            fig_ma.update_layout(
                legend=dict(orientation="h", x=0, y=1.12),
                margin=dict(l=0, r=0, t=40, b=0), height=300,
                xaxis=dict(showgrid=False, type="date"),
                yaxis=dict(gridcolor="#f0f0f0"),
                plot_bgcolor="white", paper_bgcolor="white",
                hovermode="x unified"
            )
            st.plotly_chart(fig_ma, use_container_width=True)

        st.caption("데이터 출처: 네이버금융 | 매일 18:00 자동 수집")

# ── TAB 3 ──────────────────────────────────
with tab3:
    render_tab3()

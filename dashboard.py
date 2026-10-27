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
#

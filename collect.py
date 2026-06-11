import os
import re
import json
import xml.etree.ElementTree as ET
import requests
import pandas as pd
from bs4 import BeautifulSoup
from supabase import create_client
from datetime import datetime, timezone, timedelta, date
from urllib.parse import unquote

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

KST = timezone(timedelta(hours=9))

KOFIA_URL  = "https://freesis.kofia.or.kr/meta/getMetaDataList.do"
KOFIA_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer":    "https://freesis.kofia.or.kr/stat/FreeSIS.do?parentDivId=MSIS10000000000000&serviceId=STATSCU0100000070",
    "Content-Type": "application/json; charset=UTF-8",
    "X-Requested-With": "XMLHttpRequest",
    "Origin": "https://freesis.kofia.or.kr",
}

def get_last_date(table):
    res = supabase.table(table).select("base_date").order("base_date", desc=True).limit(1).execute()
    if res.data:
        return res.data[0]["base_date"].replace("-", "")
    return "20220101"

def kofia_fetch(obj_nm, start_dt, end_dt):
    """금융투자협회 getMetaDataList API 호출"""
    payload = {
        "dmSearch": {
            "OBJ_NM":  obj_nm,
            "tmpV1":   "D",
            "tmpV40":  "1000000",
            "tmpV41":  "1",
            "tmpV45":  start_dt,
            "tmpV46":  end_dt,
        }
    }
    r = requests.post(KOFIA_URL, json=payload, headers=KOFIA_HEADERS, timeout=30)
    r.raise_for_status()
    data = r.json()
    return data.get("ds1", [])

def collect_credit():
    """신용거래융자 — 금투협 직접 크롤링 (T+1)"""
    start = get_last_date("credit_loan")
    end   = datetime.now(KST).strftime("%Y%m%d")
    print(f"신용공여 수집: {start} ~ {end}")

    rows = kofia_fetch("STATSCU0100000070B0", start, end)
    if not rows:
        print("신용공여 신규 데이터 없음")
        return

    saved = 0
    for row in rows:
        dt_str = str(row.get("TMPY1", ""))
        if len(dt_str) != 8:
            continue
        base_date = f"{dt_str[:4]}-{dt_str[4:6]}-{dt_str[6:8]}"
        # TMPY2=전체, TMPY3=코스피, TMPY4=코스닥 (단위: 백만원)
        # DB 저장단위: 백만원 그대로 (dashboard에서 /100 해서 억원으로 표시)
        record = {
            "base_date": base_date,
            "total":     float(row.get("TMPY2", 0) or 0),
            "kospi":     float(row.get("TMPY3", 0) or 0),
            "kosdaq":    float(row.get("TMPY4", 0) or 0),
            "created_at": datetime.now(KST).isoformat(),
        }
        supabase.table("credit_loan").upsert(record, on_conflict="base_date").execute()
        saved += 1

    print(f"신용공여 {saved}건 저장 완료")

def collect_mkt_fund():
    """증시자금(투자자예탁금) — 금투협 직접 크롤링 (T+1)"""
    start = get_last_date("mkt_fund")
    end   = datetime.now(KST).strftime("%Y%m%d")
    print(f"증시자금 수집: {start} ~ {end}")

    rows = kofia_fetch("STATSCU0100000060B0", start, end)
    if not rows:
        print("증시자금 신규 데이터 없음")
        return
    print(f"증시자금 API 응답 첫 번째 행: {rows[0]}")

    saved = 0
    for row in rows:
        dt_str = str(row.get("TMPY1", ""))
        if len(dt_str) != 8:
            continue
        base_date = f"{dt_str[:4]}-{dt_str[4:6]}-{dt_str[6:8]}"
        record = {
            "base_date":   base_date,
            "inv_deposit": float(row.get("TMPY2", 0) or 0),
            "cma_bal":     float(row.get("TMPY5", 0) or 0),
            "created_at":  datetime.now(KST).isoformat(),
        }
        supabase.table("mkt_fund").upsert(record, on_conflict="base_date").execute()
        saved += 1

    print(f"증시자금 {saved}건 저장 완료")

def collect_adr():
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://finance.naver.com"
    }
    result = {"base_date": datetime.now(KST).strftime("%Y-%m-%d")}

    for market, code in [("kospi", "KOSPI"), ("kosdaq", "KOSDAQ")]:
        url = f"https://finance.naver.com/sise/sise_index.naver?code={code}"
        r = requests.get(url, headers=headers)
        soup = BeautifulSoup(r.text, "html.parser")

        text = ""
        for tag in soup.find_all("td"):
            t = tag.get_text(strip=True)
            if "상승종목수" in t and "하락종목수" in t:
                text = t
                break

        def extract(key, t):
            m = re.search(key + r"(\d+)", t)
            return int(m.group(1)) if m else 0

        up   = extract("상승종목수", text)
        down = extract("하락종목수", text)
        adr  = round(up / down * 100, 2) if down > 0 else 0

        result[f"{market}_up"]          = up
        result[f"{market}_flat"]        = extract("보합종목수", text)
        result[f"{market}_down"]        = down
        result[f"{market}_upper_limit"] = extract("상한종목수", text)
        result[f"{market}_lower_limit"] = extract("하한종목수", text)
        result[f"{market}_adr"]         = adr
        print(f"{code} ADR: {adr} (상승:{up} 하락:{down})")

    supabase.table("adr").upsert(result, on_conflict="base_date").execute()
    print(f"ADR 저장 완료 ({result['base_date']})")

def collect_featured_news():
    RSS_URL = "https://news.google.com/rss/search?q=특징주&hl=ko&gl=KR&ceid=KR:ko"

    STOCK_PATTERN = re.compile(
        r"['\"]?([가-힣A-Za-z&]+(?:\s[가-힣A-Za-z]+)?)['\"]?\s*"
        r"(?:주가|급등|급락|상한가|하한가|강세|약세|매수|매도|상승|하락|신고가|신저가|이슈|테마|관련주|수혜|주목|선정)"
    )
    NOISE_WORDS = {
        "오늘","내일","시장","증시","코스피","코스닥","전망","분석","투자","주식",
        "이슈","테마","관련","수혜","특징","종목","뉴스","기업","업종","섹터",
        "글로벌","미국","중국","일본","외국인","기관","개인","거래량","시가총액",
    }

    try:
        resp = requests.get(RSS_URL, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
    except Exception as e:
        print(f"특징주 RSS 수집 실패: {e}")
        return

    saved = 0
    for item in root.findall(".//item")[:100]:
        title        = item.findtext("title", "").strip()
        link         = item.findtext("link", "").strip()
        pub_date_raw = item.findtext("pubDate", "").strip()
        source       = item.findtext("source", "").strip()

        try:
            pub_dt = datetime.strptime(pub_date_raw, "%a, %d %b %Y %H:%M:%S %Z")
            pub_dt = pub_dt.replace(tzinfo=timezone.utc).astimezone(KST)
            pub_str = pub_dt.isoformat()
        except Exception:
            pub_str = datetime.now(KST).isoformat()

        m = re.search(r"url=([^&]+)", link)
        if m:
            link = unquote(m.group(1))

        found = STOCK_PATTERN.findall(title)
        stocks = list(dict.fromkeys(
            n.strip() for n in found
            if len(n.strip()) >= 2 and n.strip() not in NOISE_WORDS
        ))

        try:
            supabase.table("featured_news").upsert(
                {"pub_dt": pub_str, "title": title, "link": link, "source": source, "stocks": stocks},
                on_conflict="link"
            ).execute()
            saved += 1
        except Exception as e:
            print(f"저장 실패: {e}")

    print(f"특징주 뉴스 {saved}건 저장 완료")

if __name__ == "__main__":
    print(f"[{datetime.now(KST).strftime('%Y-%m-%d %H:%M')}] 수집 시작")
    collect_credit()
    collect_mkt_fund()
    collect_adr()
    collect_featured_news()
    print("완료")

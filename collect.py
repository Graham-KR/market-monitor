import os
import re
import sys
import json
import traceback
import xml.etree.ElementTree as ET
import requests
import pandas as pd
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
        last = res.data[0]["base_date"].replace("-", "")
        # 마지막 저장일 다음날부터 수집 (중복 방지 + 누락 방지)
        last_dt = datetime.strptime(last, "%Y%m%d") + timedelta(days=1)
        return last_dt.strftime("%Y%m%d")
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

    keys = list(rows[0].keys()) if rows else []
    print(f"신용공여 키: {keys}")
    date_key  = keys[0] if len(keys) > 0 else "TMPY1"
    total_key = keys[1] if len(keys) > 1 else "TMPY2"
    kospi_key = keys[2] if len(keys) > 2 else "TMPY3"
    kosdaq_key= keys[3] if len(keys) > 3 else "TMPY4"

    saved = 0
    for row in rows:
        dt_str = str(row.get(date_key, "")).strip()
        if len(dt_str) != 8 or not dt_str.isdigit():
            continue
        base_date = f"{dt_str[:4]}-{dt_str[4:6]}-{dt_str[6:8]}"
        record = {
            "base_date": base_date,
            "total":     float(row.get(total_key, 0) or 0),
            "kospi":     float(row.get(kospi_key, 0) or 0),
            "kosdaq":    float(row.get(kosdaq_key, 0) or 0),
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
    keys = list(rows[0].keys()) if rows else []
    print(f"증시자금 키: {keys}")
    date_key    = keys[0] if len(keys) > 0 else "TMPY1"
    deposit_key = keys[1] if len(keys) > 1 else "TMPY2"
    cma_key     = keys[4] if len(keys) > 4 else "TMPY5"

    saved = 0
    for row in rows:
        dt_str = str(row.get(date_key, "")).strip()
        if len(dt_str) != 8 or not dt_str.isdigit():
            continue
        base_date = f"{dt_str[:4]}-{dt_str[4:6]}-{dt_str[6:8]}"
        record = {
            "base_date":   base_date,
            "inv_deposit": float(row.get(deposit_key, 0) or 0),
            "cma_bal":     float(row.get(cma_key, 0) or 0),
            "created_at":  datetime.now(KST).isoformat(),
        }
        supabase.table("mkt_fund").upsert(record, on_conflict="base_date").execute()
        saved += 1

    print(f"증시자금 {saved}건 저장 완료")

NAVER_API_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://m.stock.naver.com",
}

def _to_int(v):
    """'1,234' 같은 문자열 숫자 → 정수"""
    return int(str(v).replace(",", "").strip() or 0)

def collect_adr():
    """ADR(등락비율) — 네이버 증권 모바일 API (2026-10 네이버 금융 페이지 개편 대응)"""
    result = {}
    trade_dates = []

    for market, code in [("kospi", "KOSPI"), ("kosdaq", "KOSDAQ")]:
        # 1) 거래일: 마지막 거래 시각에서 날짜를 가져옴
        #    → 주말·공휴일에 실행돼도 직전 거래일 날짜로 저장되어 엉뚱한 날짜가 생기지 않음
        basic = requests.get(f"https://m.stock.naver.com/api/index/{code}/basic",
                             headers=NAVER_API_HEADERS, timeout=15)
        basic.raise_for_status()
        traded_at = basic.json().get("localTradedAt", "")
        if len(traded_at) < 10:
            raise ValueError(f"{code} 거래일(localTradedAt)을 찾지 못함: {traded_at!r}")
        trade_dates.append(traded_at[:10])

        # 2) 상승/하락/보합/상한/하한 종목수
        integ = requests.get(f"https://m.stock.naver.com/api/index/{code}/integration",
                             headers=NAVER_API_HEADERS, timeout=15)
        integ.raise_for_status()
        info = integ.json().get("upDownStockInfo")
        if not info:
            raise ValueError(f"{code} upDownStockInfo 없음 (네이버 API 구조 변경 가능성)")

        up    = _to_int(info.get("riseCount", 0))
        down  = _to_int(info.get("fallCount", 0))
        flat  = _to_int(info.get("steadyCount", 0))
        upper = _to_int(info.get("upperCount", 0))
        lower = _to_int(info.get("lowerCount", 0))

        # 숫자를 못 읽었으면 0으로 저장하지 말고 실패 처리
        if up == 0 and down == 0:
            raise ValueError(f"{code} 상승/하락 종목수가 모두 0 (데이터 이상)")

        adr = round(up / down * 100, 2) if down > 0 else 0

        result[f"{market}_up"]          = up
        result[f"{market}_flat"]        = flat
        result[f"{market}_down"]        = down
        result[f"{market}_upper_limit"] = upper
        result[f"{market}_lower_limit"] = lower
        result[f"{market}_adr"]         = adr
        print(f"{code} ADR: {adr} (상한:{upper} 상승:{up} 보합:{flat} 하락:{down} 하한:{lower})")

    if trade_dates[0] != trade_dates[1]:
        print(f"⚠️ 코스피/코스닥 거래일 불일치: {trade_dates} → 코스피 기준 사용")
    result["base_date"] = trade_dates[0]

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

def run_step(name, func, failed):
    """수집 항목 하나를 실행. 실패해도 다음 항목은 계속 진행."""
    print(f"\n── {name} ──")
    try:
        func()
    except Exception as e:
        print(f"❌ {name} 실패: {type(e).__name__}: {e}")
        traceback.print_exc()
        failed.append(name)


if __name__ == "__main__":
    print(f"[{datetime.now(KST).strftime('%Y-%m-%d %H:%M')}] 수집 시작")

    failed = []
    run_step("신용거래융자", collect_credit,        failed)
    run_step("증시자금",     collect_mkt_fund,      failed)
    run_step("ADR",          collect_adr,           failed)
    run_step("특징주 뉴스",  collect_featured_news, failed)

    if failed:
        print(f"\n⚠️ 실패 항목: {', '.join(failed)}")
        # GitHub Actions에서 빨간 X로 표시되도록 실패 코드로 종료
        # (나머지 항목은 이미 저장된 상태)
        sys.exit(1)

    print("\n✅ 전체 완료")

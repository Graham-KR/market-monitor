import os
import re
import xml.etree.ElementTree as ET
import requests
import pandas as pd
from bs4 import BeautifulSoup
from supabase import create_client
from datetime import datetime, timezone, timedelta
from urllib.parse import unquote

API_KEY      = os.environ["DATA_GO_KR_KEY"]
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

BASE_URL = "https://apis.data.go.kr/1160100/service/GetKofiaStatisticsInfoService"
END_DATE = datetime.today().strftime("%Y%m%d")

def get_last_date(table):
    res = supabase.table(table).select("base_date").order("base_date", desc=True).limit(1).execute()
    if res.data:
        return res.data[0]["base_date"].replace("-", "")
    return "20100104"

def fetch(endpoint, extra_params):
    params = {
        "serviceKey": API_KEY,
        "pageNo": 1,
        "numOfRows": 1,
        "resultType": "json",
    }
    params.update(extra_params)
    r = requests.get(endpoint, params=params, timeout=15)
    r.raise_for_status()
    total = int(r.json()["response"]["body"]["totalCount"])
    if total == 0:
        return []
    params["numOfRows"] = total
    r2 = requests.get(endpoint, params=params, timeout=30)
    r2.raise_for_status()
    items = r2.json()["response"]["body"]["items"]["item"]
    return items if isinstance(items, list) else [items]

def collect_credit():
    start = get_last_date("credit_loan")
    print(f"신용공여 수집 시작: {start} ~ {END_DATE}")
    rows = fetch(f"{BASE_URL}/getGrantingOfCreditBalanceInfo", {
        "beginBasDt": start,
        "endBasDt":   END_DATE,
    })
    if not rows:
        print("신용공여 신규 데이터 없음")
        return
    df = pd.DataFrame(rows)
    for _, row in df.iterrows():
        record = {
            "base_date":  str(row.get("basDt", "")),
            "total":      float(row.get("crdTrFingWhl", 0) or 0),
            "kospi":      float(row.get("crdTrFingScrs", 0) or 0),
            "kosdaq":     float(row.get("crdTrFingKosdaq", 0) or 0),
            "created_at": datetime.now().isoformat(),
        }
        supabase.table("credit_loan").upsert(record, on_conflict="base_date").execute()
    print(f"신용공여 {len(df)}건 저장 완료 (최신: {df['basDt'].max()})")

def collect_mkt_fund():
    start = get_last_date("mkt_fund")
    print(f"증시자금 수집 시작: {start} ~ {END_DATE}")
    rows = fetch(f"{BASE_URL}/getSecuritiesMarketTotalCapitalInfo", {
        "beginBasDt": start,
        "endBasDt":   END_DATE,
    })
    if not rows:
        print("증시자금 신규 데이터 없음")
        return
    df = pd.DataFrame(rows)
    for _, row in df.iterrows():
        record = {
            "base_date":   str(row.get("basDt", "")),
            "inv_deposit": float(row.get("invrDpsgAmt", 0) or 0),
            "cma_bal":     float(row.get("brkTrdUcolMny", 0) or 0),
            "created_at":  datetime.now().isoformat(),
        }
        supabase.table("mkt_fund").upsert(record, on_conflict="base_date").execute()
    print(f"증시자금 {len(df)}건 저장 완료 (최신: {df['basDt'].max()})")

def collect_adr():
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://finance.naver.com"
    }
    result = {"base_date": datetime.today().strftime("%Y-%m-%d")}

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
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] 수집 시작")
    collect_credit()
    collect_mkt_fund()
    collect_adr()
    collect_featured_news()
    print("완료")

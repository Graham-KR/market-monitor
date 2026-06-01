import os
import requests
import pandas as pd
from supabase import create_client
from datetime import datetime
from bs4 import BeautifulSoup

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
        supabase.table("credit_loan").upsert(
            record, on_conflict="base_date"
        ).execute()
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
        supabase.table("mkt_fund").upsert(
            record, on_conflict="base_date"
        ).execute()
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
        data = {}
        for tag in soup.find_all("td"):
            text = tag.get_text(strip=True)
            for key in ["상한종목수", "상승종목수", "보합종목수", "하락종목수", "하한종목수"]:
                if key in text:
                    try:
                        val = int(''.join(filter(str.isdigit, text)))
                        data[key] = val
                    except:
                        pass
        up   = data.get("상승종목수", 0)
        down = data.get("하락종목수", 0)
        adr  = round(up / down * 100, 2) if down > 0 else 0
        result[f"{market}_up"]          = up
        result[f"{market}_flat"]        = data.get("보합종목수", 0)
        result[f"{market}_down"]        = down
        result[f"{market}_upper_limit"] = data.get("상한종목수", 0)
        result[f"{market}_lower_limit"] = data.get("하한종목수", 0)
        result[f"{market}_adr"]         = adr
        print(f"{code} ADR: {adr} (상승:{up} 하락:{down})")

    supabase.table("adr").upsert(result, on_conflict="base_date").execute()
    print(f"ADR 저장 완료 ({result['base_date']})")

if __name__ == "__main__":
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] 수집 시작")
    collect_credit()
    collect_mkt_fund()
    collect_adr()
    print("완료")

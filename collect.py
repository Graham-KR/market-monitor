import os
import requests
import pandas as pd
from supabase import create_client
from datetime import datetime

API_KEY      = os.environ["DATA_GO_KR_KEY"]
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

BASE_URL   = "https://apis.data.go.kr/1160100/service/GetKofiaStatisticsInfoService"
START_DATE = "20260102"
END_DATE   = datetime.today().strftime("%Y%m%d")

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
    rows = fetch(f"{BASE_URL}/getGrantingOfCreditBalanceInfo", {
        "beginBasDt": START_DATE,
        "endBasDt":   END_DATE,
    })
    if not rows:
        print("신용공여 데이터 없음")
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
    print(f"신용공여 {len(df)}건 저장 완료")

def collect_mkt_fund():
    rows = fetch(f"{BASE_URL}/getSecuritiesMarketTotalCapitalInfo", {
        "beginBasDt": START_DATE,
        "endBasDt":   END_DATE,
    })
    if not rows:
        print("증시자금 데이터 없음")
        return
    df = pd.DataFrame(rows)
    print("증시자금 컬럼:", df.columns.tolist())
    for _, row in df.iterrows():
        record = {
            "base_date":   str(row.get("basDt", "")),
            "inv_deposit": float(row.get("invstDpst", 0) or 0),
            "cma_bal":     float(row.get("cmaBlnc", 0) or 0),
            "created_at":  datetime.now().isoformat(),
        }
        supabase.table("mkt_fund").upsert(
            record, on_conflict="base_date"
        ).execute()
    print(f"증시자금 {len(df)}건 저장 완료")

if __name__ == "__main__":
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] 수집 시작")
    collect_credit()
    collect_mkt_fund()
    print("완료")

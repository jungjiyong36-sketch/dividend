import json
import os
import re
from datetime import datetime, timedelta, timezone
import numpy as np
import pandas as pd
import yfinance as yf

# 국내 상장 미국배당다우존스 3대장 티커 정의
KR_ETF_LIST = [
    {"key": "TIGER", "ticker": "458730.KS", "code": "458730", "name": "TIGER 미국배당다우존스", "default_price": 13800},
    {"key": "ACE",   "ticker": "402970.KS", "code": "402970", "name": "ACE 미국배당다우존스",   "default_price": 13600},
    {"key": "SOL",   "ticker": "446720.KS", "code": "446720", "name": "SOL 미국배당다우존스",   "default_price": 11300},
]

def fetch_fed_rates_safe(start_date: str) -> pd.Series:
    try:
        irx = yf.Ticker("^IRX").history(start=start_date, auto_adjust=False)
        if not irx.empty:
            s = irx["Close"].dropna() / 4.0
            s.index = pd.to_datetime(s.index).tz_localize(None)
            return s
    except Exception as e:
        print(f"[Warning] 기준금리 대체 수집 경고: {e}")
    return pd.Series(dtype=float)

def fetch_usdkrw_series(start_date: str) -> pd.Series:
    try:
        krw = yf.Ticker("KRW=X").history(start=start_date, auto_adjust=False)
        if not krw.empty:
            s = krw["Close"].dropna().astype(float)
            s.index = pd.to_datetime(s.index).tz_localize(None)
            s = s[(s >= 900) & (s <= 2000)]
            return s
    except Exception as e:
        print(f"[Warning] 원/달러 환율 시계열 수집 경고: {e}")
    return pd.Series(dtype=float)

def fetch_kr_etfs(schd_current_yield: float) -> dict:
    result = {}
    fallback_yield = max(2.8, min(5.0, schd_current_yield))

    for item in KR_ETF_LIST:
        key = item["key"]
        ticker = item["ticker"]
        cur_price = item["default_price"]
        ttm_div = int(round(cur_price * (fallback_yield / 100.0)))
        etf_yield = round(fallback_yield, 2)

        try:
            hist = yf.Ticker(ticker).history(period="1y", auto_adjust=False)
            if not hist.empty:
                closes = hist["Close"].dropna()
                if not closes.empty:
                    cur_price = int(round(float(closes.iloc[-1])))
                divs = hist["Dividends"].dropna()
                divs_pos = divs[divs > 0]
                if len(divs_pos) >= 4:
                    raw_div_sum = float(divs_pos.sum())
                    calc_yield = (raw_div_sum / cur_price) * 100.0
                    if 2.0 <= calc_yield <= 6.5:
                        ttm_div = int(round(raw_div_sum))
                        etf_yield = round(calc_yield, 2)
        except Exception as e:
            print(f"[Warning] {key} 데이터 수집 경고: {e}")

        result[key] = {
            "code": item["code"],
            "name": item["name"],
            "price": cur_price,
            "ttm_div": ttm_div,
            "yield": etf_yield
        }
    return result

def update_index_html_seo_summary(html_path: str, summary_data: dict):
    if not os.path.exists(html_path):
        return
    try:
        with open(html_path, "r", encoding="utf-8") as f:
            content = f.read()

        new_block = (
            "<!-- SEO_LIVE_SUMMARY_START -->\n"
            '                <div id="seo-live-summary" style="font-size:0.78rem; color:#94a3b8; margin-top:10px; line-height:1.5;">\n'
            f'                    📌 <b>실시간 퀀트 요약 ({summary_data["date"]} 기준):</b> 현재 SCHD 주가는 <b>${summary_data["price"]:.2f}</b>, '
            f'직전 4분기 확정 연 배당금은 <b>${summary_data["ttm_div"]:.4f}</b>(시가배당률 <b>${summary_data["yield"]:.2f}%</b>)이며, '
            f'최근 5년 대비 매수 매력 점수는 <b>{summary_data["score_5y"]}점</b>(5년 중앙 적정주가 <b>${summary_data["fair_5y"]:.2f}</b>, '
            f'상위 10% 꿀통 매수선 <b>${summary_data["honey_5y"]:.2f}</b>, 원/달러 환율 <b>{summary_data["usdkrw"]:.1f}원</b>, '
            f'TIGER 현재가 <b>{summary_data["tiger_price"]:,}원</b>)입니다.\n'
            "                </div>\n"
            "                <!-- SEO_LIVE_SUMMARY_END -->"
        )

        pattern = re.compile(r"<!-- SEO_LIVE_SUMMARY_START -->.*?<!-- SEO_LIVE_SUMMARY_END -->", re.DOTALL)
        if pattern.search(content):
            updated_content = pattern.sub(new_block, content)
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(updated_content)
        else:
            print("[Info] index.html 내 SEO_LIVE_SUMMARY 주석 마커를 찾지 못해 갱신을 생략합니다.")
    except Exception as e:
        print(f"[Warning] SEO 요약 갱신 경고 (무시됨): {e}")

def generate_schd_data(output_path: str = "schd_data.json"):
    print("1. SCHD 상장 이후 전체 데이터 수집 중...")
    schd = yf.Ticker("SCHD")
    hist = schd.history(period="max", auto_adjust=False)
    if hist.empty:
        raise RuntimeError("yfinance에서 SCHD 데이터를 가져오지 못했습니다.")

    hist.index = pd.to_datetime(hist.index).tz_localize(None)
    hist = hist.sort_index()

    df = pd.DataFrame(index=hist.index)
    df["price"] = hist["Close"].astype(float)
    df["dividend"] = hist["Dividends"].fillna(0.0).astype(float)

    print("2. 직전 4개 분기 확정 배당금 합산 계산 중...")
    div_events = df[df["dividend"] > 0]["dividend"].copy()
    rolling_4q = div_events.rolling(4).sum()
    df["ttm_dividend"] = rolling_4q.reindex(df.index).ffill()

    df = df[df.index >= pd.Timestamp("2012-10-01")].copy()
    df = df.dropna(subset=["price", "ttm_dividend"])
    df["yield"] = np.where(df["price"] > 0, (df["ttm_dividend"] / df["price"]) * 100.0, 0.0)

    recent_divs = div_events.tail(8)
    div_ledger = [
        {"date": idx.strftime("%Y-%m-%d"), "amount": round(float(val), 4)}
        for idx, val in recent_divs.items()
    ]

    latest_q_div = float(div_events.iloc[-1]) if not div_events.empty else 0.75
    latest_price = float(df["price"].iloc[-1]) if not df["price"].empty else 70.0
    forward_yield = round(((latest_q_div * 4.0) / latest_price) * 100.0, 2)

    if len(rolling_4q) >= 21:
        div_now = float(rolling_4q.iloc[-1])
        div_5y_ago = float(rolling_4q.iloc[-21])
        cagr_5y = round(((div_now / div_5y_ago) ** (1.0 / 5.0) - 1.0) * 100.0, 1) if div_5y_ago > 0 else 11.0
    else:
        cagr_5y = 11.0

    print("3. 기준금리 및 원/달러 환율 시계열 병합 중...")
    start_str = df.index.min().strftime("%Y-%m-%d")

    fed_series = fetch_fed_rates_safe(start_str)
    if not fed_series.empty:
        full_idx = df.index.union(fed_series.index).sort_values()
        df["fed_rate"] = fed_series.reindex(full_idx).ffill().bfill().reindex(df.index).fillna(4.5)
    else:
        df["fed_rate"] = 4.5

    fx_series = fetch_usdkrw_series(start_str)
    if not fx_series.empty:
        full_fx_idx = df.index.union(fx_series.index).sort_values()
        df["fx_rate"] = fx_series.reindex(full_fx_idx).ffill().bfill().reindex(df.index).fillna(1380.0)
    else:
        df["fx_rate"] = 1380.0

    print("4. 국내 3대장 실시간 데이터 수집 중...")
    cur_yield_val = round(float(df["yield"].iloc[-1]), 2) if not df["yield"].empty else 3.2
    kr_etfs_data = fetch_kr_etfs(cur_yield_val)

    dates_list = df.index.strftime("%Y-%m-%d").tolist()
    prices_list = [round(float(x), 2) for x in df["price"].tolist()]
    ttm_divs_list = [round(float(x), 4) for x in df["ttm_dividend"].tolist()]
    yields_list = [round(float(x), 2) for x in df["yield"].tolist()]
    fed_rates_list = [round(float(x), 2) for x in df["fed_rate"].tolist()]
    fx_rates_list = [round(float(x), 1) for x in df["fx_rate"].tolist()]

    usdkrw_latest = fx_rates_list[-1] if fx_rates_list else 1380.0
    usdkrw_1y_avg = round(float(np.mean(fx_rates_list[-252:])), 1) if len(fx_rates_list) >= 252 else usdkrw_latest

    y_5y = yields_list[-1260:] if len(yields_list) >= 1260 else yields_list
    cheaper_5y = sum(1 for y in y_5y if y > yields_list[-1])
    score_5y = int(round(100.0 - (cheaper_5y / len(y_5y)) * 100.0))
    p50_5y = float(np.percentile(y_5y, 50))
    p90_5y = float(np.percentile(y_5y, 90))
    fair_5y = round(ttm_divs_list[-1] / (p50_5y / 100.0), 2)
    honey_5y = round(ttm_divs_list[-1] / (p90_5y / 100.0), 2)

    kst = timezone(timedelta(hours=9))
    updated_at_str = datetime.now(kst).strftime("%Y년 %m월 %d일 %H시 %M분 (한국시간)")

    output_data = {
        "updated_at": updated_at_str,
        "cagr_5y": cagr_5y,
        "latest": {
            "price": prices_list[-1],
            "yield": yields_list[-1],
            "forward_yield": forward_yield,
            "ttm_dividend": ttm_divs_list[-1],
            "fed_rate": fed_rates_list[-1],
            "date": dates_list[-1],
            "usdkrw": usdkrw_latest,
            "usdkrw_1y_avg": usdkrw_1y_avg
        },
        "kr_etfs": kr_etfs_data,
        "div_ledger": div_ledger,
        "dates": dates_list,
        "prices": prices_list,
        "ttm_dividends": ttm_divs_list,
        "yields": yields_list,
        "fed_rates": fed_rates_list,
        "fx_rates": fx_rates_list
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, separators=(",", ":"))

    try:
        update_index_html_seo_summary("index.html", {
            "date": dates_list[-1],
            "price": prices_list[-1],
            "ttm_div": ttm_divs_list[-1],
            "yield": yields_list[-1],
            "score_5y": score_5y,
            "fair_5y": fair_5y,
            "honey_5y": honey_5y,
            "usdkrw": usdkrw_latest,
            "tiger_price": kr_etfs_data["TIGER"]["price"]
        })
    except Exception as e:
        print(f"[Info] SEO 요약 업데이트 스킵: {e}")

    print(f"✅ 생성 완료: {output_path}")

if __name__ == "__main__":
    generate_schd_data()

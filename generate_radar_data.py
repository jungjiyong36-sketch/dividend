import json
from datetime import datetime, timedelta, timezone
import numpy as np
import pandas as pd
import yfinance as yf
import pandas_datareader.data as web

def fetch_fed_rates(start_date: str, end_date: str) -> pd.Series:
    """
    FRED에서 미국 실효 연방기금금리(DFF) 데이터를 가져옵니다.
    네트워크 오류 시에도 파이프라인이 멈추지 않도록 폴백(Fallback) 처리를 포함합니다.
    """
    try:
        df_fed = web.DataReader("DFF", "fred", start_date, end_date)
        return df_fed["DFF"]
    except Exception as e:
        print(f"[Warning] FRED DFF 데이터 수집 실패, 대체 로직 실행: {e}")
        # 폴백: 13주 국채 수익률(^IRX)로 근사치 대체
        irx = yf.Ticker("^IRX").history(start=start_date, end=end_date)
        if not irx.empty:
            s = irx["Close"]
            s.index = s.index.tz_localize(None)
            return s
        return pd.Series(dtype=float)

def fetch_usdkrw() -> tuple[float, float]:
    """
    최근 원/달러 환율(KRW=X)과 1년(252영업일) 이동평균 환율을 반환합니다.
    """
    try:
        krw = yf.Ticker("KRW=X").history(period="2y")
        if not krw.empty:
            closes = krw["Close"].dropna()
            latest_krw = round(float(closes.iloc[-1]), 2)
            avg_1y_krw = round(float(closes.tail(252).mean()), 2)
            return latest_krw, avg_1y_krw
    except Exception as e:
        print(f"[Warning] 원/달러 환율 수집 실패: {e}")
    return 1380.0, 1350.0

def generate_schd_data(output_path: str = "schd_data.json"):
    print("1. SCHD 상장 이후 전체(period='max') 데이터 수집 중...")
    schd = yf.Ticker("SCHD")
    
    # 중요: auto_adjust=False를 사용해야 배당 재투자 할인이 제외된 '실제 거래 종가(액면분할만 보정)'와
    # 액면분할 보정 배당금이 매칭되어 정확한 역사적 시가배당률(Yield)이 계산됨
    hist = schd.history(period="max", auto_adjust=False)
    if hist.empty:
        raise RuntimeError("yfinance에서 SCHD 데이터를 가져오지 못했습니다.")

    # 타임존 제거 (날짜 매칭 용이성)
    hist.index = pd.to_datetime(hist.index).tz_localize(None)
    hist = hist.sort_index()

    # 필요한 컬럼만 추출
    df = pd.DataFrame(index=hist.index)
    df["price"] = hist["Close"].astype(float)
    df["dividend"] = hist["Dividends"].fillna(0.0).astype(float)

    print("2. 직전 365일(4분기) 합산 TTM 배당금 및 시가배당률 계산 중...")
    # 캘린더 데이 기준 직전 365일 동안 지급된 배당금 합산 (분기 배당 밀림 현상 방지을 위해 370D 윈도우 후 보정 가능하나 표준 365D 적용)
    df["ttm_dividend"] = df["dividend"].rolling("365D").sum()
    df["yield"] = np.where(df["price"] > 0, (df["ttm_dividend"] / df["price"]) * 100.0, 0.0)

    # 상장 직후 첫 1년(2011.10 ~ 2012.09)은 4분기 배당이 모두 쌓이지 않아 배당률이 왜곡되므로
    # 첫 4분기 배당이 온전히 반영된 2012-10-01 이후 데이터부터 필터링
    df = df[df.index >= pd.Timestamp("2012-10-01")].copy()
    df = df.dropna(subset=["price", "ttm_dividend", "yield"])

    print("3. FRED 미국 실효 기준금리(DFF) 데이터 병합 중...")
    start_str = df.index.min().strftime("%Y-%m-%d")
    end_str = (df.index.max() + timedelta(days=5)).strftime("%Y-%m-%d")
    fed_series = fetch_fed_rates(start_str, end_str)

    if not fed_series.empty:
        fed_series.index = pd.to_datetime(fed_series.index).tz_localize(None)
        # 전체 날짜 리인덱싱 후 주말/공휴일 결측치 앞방향 채우기(ffill)
        full_idx = df.index.union(fed_series.index).sort_values()
        fed_aligned = fed_series.reindex(full_idx).ffill().bfill()
        df["fed_rate"] = fed_aligned.reindex(df.index).fillna(0.0)
    else:
        df["fed_rate"] = 0.0

    print("4. 원/달러 환율(KRW=X) 수집 중...")
    usdkrw_latest, usdkrw_1y_avg = fetch_usdkrw()

    # 반올림 처리 (JSON 파일 용량 최적화 및 가독성 향상)
    dates_list = df.index.strftime("%Y-%m-%d").tolist()
    prices_list = [round(float(x), 4) for x in df["price"].tolist()]
    ttm_divs_list = [round(float(x), 4) for x in df["ttm_dividend"].tolist()]
    yields_list = [round(float(x), 4) for x in df["yield"].tolist()]
    fed_rates_list = [round(float(x), 2) for x in df["fed_rate"].tolist()]

    # 한국 시간(KST, UTC+9) 기준 업데이트 시각 생성
    kst = timezone(timedelta(hours=9))
    now_kst = datetime.now(kst)
    updated_at_str = now_kst.strftime("%Y년 %m월 %d일 %H시 %M분 (한국시간)")

    output_data = {
        "updated_at": updated_at_str,
        "latest": {
            "price": round(prices_list[-1], 2),
            "yield": round(yields_list[-1], 2),
            "ttm_dividend": round(ttm_divs_list[-1], 4),
            "fed_rate": round(fed_rates_list[-1], 2),
            "date": dates_list[-1],
            "usdkrw": usdkrw_latest,
            "usdkrw_1y_avg": usdkrw_1y_avg
        },
        "dates": dates_list,
        "prices": prices_list,
        "ttm_dividends": ttm_divs_list,
        "yields": yields_list,
        "fed_rates": fed_rates_list
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, separators=(",", ":"))

    print(f"✅ 데이터 생성 완료: {output_path} (총 {len(dates_list)}영업일, 최신일: {dates_list[-1]})")

if __name__ == "__main__":
    generate_schd_data()

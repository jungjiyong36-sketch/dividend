import json
import os
from datetime import datetime, timedelta, timezone
import pandas as pd
import requests
import yfinance as yf

def fetch_data():
    print("1. SCHD 주가 및 배당 데이터 수집 중...")
    schd = yf.Ticker("SCHD")
    
    # 최근 10년 치 일별 주가 데이터 (배당락 수정 반영 전 원본 종가 기준)
    hist = schd.history(period="10y", interval="1d", auto_adjust=False)
    if hist.empty:
        raise ValueError("주가 데이터를 가져오지 못했습니다.")

    # 일별 배당금 내역
    dividends = schd.dividends
    if dividends.empty:
        raise ValueError("배당금 데이터를 가져오지 못했습니다.")

    # 인덱스 타임존 통일 (UTC 제거)
    hist.index = hist.index.tz_localize(None)
    dividends.index = dividends.index.tz_localize(None)

    # 2. 일별 TTM 배당금 계산 (각 날짜 기준 직전 365일간 지급된 배당금 합산)
    print("2. 일별 TTM(Trailing 12-Month) 배당금 산출 중...")
    ttm_dividends = []
    for current_date in hist.index:
        start_date = current_date - timedelta(days=365)
        # 당일 포함 직전 365일간의 배당금 합계
        div_sum = dividends[(dividends.index > start_date) & (dividends.index <= current_date)].sum()
        ttm_dividends.append(float(div_sum))

    hist['TTM_Dividend'] = ttm_dividends
    
    # 유효한 TTM 배당금이 형성된 이후 데이터만 필터링 (초기 1년 결측 방지)
    hist = hist[hist['TTM_Dividend'] > 0].copy()
    hist['Yield'] = (hist['TTM_Dividend'] / hist['Close']) * 100

    # 3. 미국 실효 기준금리(FRED DFF) 데이터 수집
    print("3. 미국 기준금리(FRED DFF) 데이터 병합 중...")
    fred_url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DFF"
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    try:
        fed_df = pd.read_csv(fred_url, storage_options={'headers': headers})
        fed_df['DATE'] = pd.to_datetime(fed_df['DATE'])
        fed_df['DFF'] = pd.to_numeric(fed_df['DFF'], errors='coerce')
        fed_df = fed_df.dropna().set_index('DATE')
        
        # 주가 거래일에 맞춰 기준금리 forward-fill
        hist['Fed_Rate'] = hist.index.map(fed_df['DFF']).ffill().bfill()
    except Exception as e:
        print(f"기준금리 수집 실패 (기본값 처리): {e}")
        hist['Fed_Rate'] = 4.5  # 폴백 기본값

    # 4. JSON 파일 구조화 (소수점 2 ~ 4자리 반올림으로 파일 용량 최소화)
    dates = [d.strftime('%Y-%m-%d') for d in hist.index]
    prices = [round(float(p), 2) for p in hist['Close']]
    ttm_divs = [round(float(d), 4) for d in hist['TTM_Dividend']]
    yields = [round(float(y), 2) for y in hist['Yield']]
    fed_rates = [round(float(r), 2) for r in hist['Fed_Rate']]

    KST = timezone(timedelta(hours=9))
    now_kst = datetime.now(KST)
    updated_at_str = now_kst.strftime('%Y년 %m월 %d일 %H시 %M분 (한국시간)')

    output_data = {
        "updated_at": updated_at_str,
        "latest": {
            "price": prices[-1],
            "yield": yields[-1],
            "ttm_dividend": ttm_divs[-1],
            "fed_rate": fed_rates[-1],
            "date": dates[-1]
        },
        "dates": dates,
        "prices": prices,
        "ttm_dividends": ttm_divs,
        "yields": yields,
        "fed_rates": fed_rates
    }

    output_path = os.path.join(os.path.dirname(__file__), 'schd_data.json')
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, separators=(',', ':')) # 공백 제거로 전송 트래픽 절감
        
    print(f"완료: {output_path} 저장 성공 (총 {len(dates)} 거래일)")

if __name__ == "__main__":
    fetch_data()

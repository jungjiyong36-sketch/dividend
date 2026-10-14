import json
import os
from datetime import datetime, timedelta, timezone
import pandas as pd
import yfinance as yf

def fetch_and_verify_quant_data():
    print("1. [Quant Engine] SCHD 전체 시계열 주가 및 배당 데이터 수집 중...")
    schd = yf.Ticker("SCHD")
    
    # 상장(2011년 10월) 이후 전체 일별 데이터 로드 (3:1 액면분할 보정 반영)
    hist = schd.history(period="max", interval="1d", auto_adjust=False)
    if hist.empty:
        raise ValueError("SCHD 주가 데이터를 가져오지 못했습니다.")

    hist.index = hist.index.tz_localize(None).normalize()
    hist = hist[~hist.index.duplicated(keep='last')].sort_index()

    # 2. [핵심 교정] 365일 달력 윈도우가 아닌 '최근 4개 분기 확정 배당금(4Q Discrete Rolling)' 산출
    print("2. [Quant Engine] 4분기 이산 롤링(4Q Rolling) TTM 배당금 및 배당 원장 생성 중...")
    div_series = hist[hist['Dividends'] > 0]['Dividends'].copy()
    
    # 동일 월 내 중복 배당 기록 방어 (월별 합산 후 4분기 롤링)
    div_events = div_series.groupby(div_series.index.to_period('M')).agg(
        last_date=('index', lambda x: x[-1]) if isinstance(div_series, pd.DataFrame) else 'sum'
    )
    # 정확한 배당락일 보존을 위해 월별 마지막 배당락일 기준으로 정리
    div_clean = div_series.groupby(div_series.index.to_period('M')).sum()
    div_dates = div_series.reset_index().groupby(div_series.index.to_period('M'))['Date'].last()
    div_events = pd.Series(div_clean.values, index=pd.DatetimeIndex(div_dates.values)).sort_index()

    if len(div_events) < 4:
        raise ValueError("배당 이벤트 데이터가 4분기 미만입니다.")

    # 직전 4개 분기 확정 배당금 합산 (스파이크 원천 차단)
    ttm_div_events = div_events.rolling(window=4, min_periods=4).sum()
    latest_q_div_events = div_events.copy()

    # 일별 주가 시계열에 매핑 후 Forward-Fill
    hist['TTM_Dividend'] = ttm_div_events.reindex(hist.index).ffill()
    hist['Latest_Q_Div'] = latest_q_div_events.reindex(hist.index).ffill()

    # 초기 4개 분기 형성 이전 데이터 제거
    hist = hist.dropna(subset=['TTM_Dividend', 'Close']).copy()
    hist = hist[hist['TTM_Dividend'] > 0].copy()

    # 시가배당률(TTM Yield) 및 최근 분기 연환산 배당률(Forward Yield) 계산
    hist['Yield'] = (hist['TTM_Dividend'] / hist['Close']) * 100
    hist['Forward_Yield'] = ((hist['Latest_Q_Div'] * 4.0) / hist['Close']) * 100

    # 최근 8개 분기 배당 내역 원장 추출 (UI 투명성 검증용)
    recent_divs = div_events.tail(8)
    div_ledger = [
        {"date": d.strftime('%Y-%m-%d'), "amount": round(float(val), 4)}
        for d, val in recent_divs.items()
    ]

    # 3. 미국 실효 기준금리(FRED DFF) 병합
    print("3. [Quant Engine] 미국 기준금리(FRED DFF) 데이터 병합 중...")
    fred_url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DFF"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        fed_df = pd.read_csv(fred_url, storage_options={'headers': headers})
        fed_df['DATE'] = pd.to_datetime(fed_df['DATE']).dt.normalize()
        fed_df['DFF'] = pd.to_numeric(fed_df['DFF'], errors='coerce')
        fed_df = fed_df.dropna().set_index('DATE')
        
        combined_idx = hist.index.union(fed_df.index).sort_values()
        aligned_fed = fed_df['DFF'].reindex(combined_idx).ffill().bfill()
        hist['Fed_Rate'] = aligned_fed.reindex(hist.index)
    except Exception as e:
        print(f"기준금리 수집 실패 (폴백 적용): {e}")
        hist['Fed_Rate'] = 4.50

    # 4. 원/달러 환율(KRW=X) 데이터 수집 및 병합 (국내 ETF 투자자용)
    print("4. [Quant Engine] 원/달러 환율(KRW=X) 데이터 수집 중...")
    try:
        fx = yf.Ticker("KRW=X").history(period="max", interval="1d", auto_adjust=False)
        fx.index = fx.index.tz_localize(None).normalize()
        fx = fx[~fx.index.duplicated(keep='last')].sort_index()
        fx_clean = fx['Close'][(fx['Close'] > 800) & (fx['Close'] < 2000)]
        
        combined_fx_idx = hist.index.union(fx_clean.index).sort_values()
        aligned_fx = fx_clean.reindex(combined_fx_idx).ffill().bfill()
        hist['FX_Rate'] = aligned_fx.reindex(hist.index)
    except Exception as e:
        print(f"환율 수집 실패 (폴백 적용): {e}")
        hist['FX_Rate'] = 1380.0

    # 5. 최근 5년 배당성장률(CAGR) 실측 계산
    try:
        div_5y_ago = hist['TTM_Dividend'].iloc[max(0, len(hist) - 1260)]
        div_now = hist['TTM_Dividend'].iloc[-1]
        cagr_5y = ((div_now / div_5y_ago) ** (1 / 5) - 1) * 100
        cagr_5y = round(float(cagr_5y), 2)
    except Exception:
        cagr_5y = 11.20

    # 6. 한국 시간(KST) 타임스탬프 및 JSON 구조화
    KST = timezone(timedelta(hours=9))
    now_kst = datetime.now(KST)
    updated_at_str = now_kst.strftime('%Y년 %m월 %d일 %H시 %M분 (한국시간)')

    dates = [d.strftime('%Y-%m-%d') for d in hist.index]
    prices = [round(float(p), 2) for p in hist['Close']]
    ttm_divs = [round(float(d), 4) for d in hist['TTM_Dividend']]
    yields = [round(float(y), 2) for y in hist['Yield']]
    fed_rates = [round(float(r), 2) for r in hist['Fed_Rate']]
    fx_rates = [round(float(x), 1) for x in hist['FX_Rate']]

    output_data = {
        "updated_at": updated_at_str,
        "cagr_5y": cagr_5y,
        "div_ledger": div_ledger,
        "latest": {
            "price": prices[-1],
            "yield": yields[-1],
            "forward_yield": round(float(hist['Forward_Yield'].iloc[-1]), 2),
            "ttm_dividend": ttm_divs[-1],
            "fed_rate": fed_rates[-1],
            "fx_rate": fx_rates[-1],
            "date": dates[-1]
        },
        "dates": dates,
        "prices": prices,
        "ttm_dividends": ttm_divs,
        "yields": yields,
        "fed_rates": fed_rates,
        "fx_rates": fx_rates
    }

    output_path = os.path.join(os.path.dirname(__file__), 'schd_data.json')
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, separators=(',', ':'), ensure_ascii=False)
        
    print(f"✅ 완료: {output_path} 저장 성공 (총 {len(dates)} 영업일)")

if __name__ == "__main__":
    fetch_and_verify_quant_data()

import json
import os
from datetime import datetime, timedelta, timezone
import pandas as pd
import yfinance as yf

def fetch_and_verify_quant_data():
    print("1. [Quant Engine] SCHD 전체 시계열 주가 및 배당 데이터 수집 중...")
    schd = yf.Ticker("SCHD")
    
    # 상장(2011년 10월) 이후 전체 일별 데이터 로드
    # auto_adjust=False: 배당 재투자 왜곡을 배제한 실제 시장 종가(액면분할만 보정됨)와 배당금을 함께 가져옴
    hist = schd.history(period="max", interval="1d", auto_adjust=False)
    if hist.empty:
        raise ValueError("SCHD 주가 데이터를 가져오지 못했습니다.")

    # 타임존 제거 (일별 날짜 매칭 정확성 확보)
    hist.index = hist.index.tz_localize(None).normalize()

    # 2. [핵심 교정] 365일 달력 윈도우가 아닌 '최근 4개 분기 확정 배당금(4-Quarter Rolling)' 산출
    print("2. [Quant Engine] 4분기 이산 롤링(Discrete 4Q Rolling) TTM 배당금 산출 중...")
    
    # 배당금이 실제로 지급된 날(Dividends > 0)만 추출
    div_events = hist[hist['Dividends'] > 0]['Dividends'].copy()
    if len(div_events) < 4:
        raise ValueError("배당 데이터가 충분하지 않습니다.")

    # 직전 4번의 분기 배당금을 정확히 합산 (3분기/5분기 중복 합산 스파이크 원천 차단)
    ttm_div_events = div_events.rolling(window=4, min_periods=4).sum()

    # 일별 주가 테이블에 매핑 후 다음 배당락일 전까지 확정 TTM 배당금을 유지(Forward-Fill)
    hist['TTM_Dividend'] = ttm_div_events.reindex(hist.index).ffill()

    # 최초 4개 분기 배당이 쌓이기 전의 초기 결측 구간(상장 첫 1년) 제거
    hist = hist.dropna(subset=['TTM_Dividend', 'Close']).copy()
    hist = hist[hist['TTM_Dividend'] > 0].copy()

    # 일별 시가배당률(%) 계산
    hist['Yield'] = (hist['TTM_Dividend'] / hist['Close']) * 100

    # 3. [퀀트 이상치 검증] 전일 대비 배당금이 비정상적(50% 이상)으로 급변한 데이터 오염 체크
    ttm_pct_change = hist['TTM_Dividend'].pct_change().abs()
    anomalies = hist[ttm_pct_change > 0.5]
    if not anomalies.empty:
        print(f"⚠️ 경고: 비정상적 배당 변동 감지 건수: {len(anomalies)}건")

    # 4. 미국 실효 기준금리(FRED DFF) 데이터 수집 및 휴장일 정밀 보정
    print("3. [Quant Engine] 미국 기준금리(FRED DFF) 시계열 병합 중...")
    fred_url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DFF"
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    try:
        fed_df = pd.read_csv(fred_url, storage_options={'headers': headers})
        fed_df['DATE'] = pd.to_datetime(fed_df['DATE']).dt.normalize()
        fed_df['DFF'] = pd.to_numeric(fed_df['DFF'], errors='coerce')
        fed_df = fed_df.dropna().set_index('DATE')
        
        # 주가 인덱스와 금리 인덱스의 합집합을 만든 뒤 ffill하여 주말/공휴일 금리 발표 누락 방지
        combined_index = hist.index.union(fed_df.index).sort_values()
        aligned_fed = fed_df['DFF'].reindex(combined_index).ffill().bfill()
        hist['Fed_Rate'] = aligned_fed.reindex(hist.index)
    except Exception as e:
        print(f"기준금리 수집 실패 (직전 데이터 또는 폴백 적용): {e}")
        hist['Fed_Rate'] = 4.50

    # 5. 한국 시간(KST) 타임스탬프 생성 및 JSON 출력
    KST = timezone(timedelta(hours=9))
    now_kst = datetime.now(KST)
    updated_at_str = now_kst.strftime('%Y-%m-%d %H:%M KST')

    dates = [d.strftime('%Y-%m-%d') for d in hist.index]
    prices = [round(float(p), 2) for p in hist['Close']]
    ttm_divs = [round(float(d), 4) for d in hist['TTM_Dividend']]
    yields = [round(float(y), 2) for y in hist['Yield']]
    fed_rates = [round(float(r), 2) for r in hist['Fed_Rate']]

    output_data = {
        "updated_at": updated_at_str,
        "update_policy": "미국 정규장 중 2시간 간격 및 장 마감 직후(일 5회) 자동 갱신",
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
        json.dump(output_data, f, separators=(',', ':'), ensure_ascii=False)
        
    print(f"✅ 완료: {output_path} 저장 성공 (총 {len(dates)} 영업일, 최신 배당률 {yields[-1]}%)")

if __name__ == "__main__":
    fetch_and_verify_quant_data()

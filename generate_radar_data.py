import json
import os
import re
from datetime import datetime, timedelta, timezone, date
import numpy as np
import pandas as pd
import yfinance as yf

# 1. 국내 상장 미국배당다우존스 4대장 티커 정의 (KRX 표준코드 기준)
KR_ETF_LIST = [
    {"key": "TIGER", "ticker": "458730.KS", "code": "458730", "name": "TIGER 미국배당다우존스", "default_price": 14410},
    {"key": "SOL",   "ticker": "446720.KS", "code": "446720", "name": "SOL 미국배당다우존스",   "default_price": 11800},
    {"key": "KODEX", "ticker": "489250.KS", "code": "489250", "name": "KODEX 미국배당다우존스", "default_price": 10800},
    {"key": "ACE",   "ticker": "402970.KS", "code": "402970", "name": "ACE 미국배당다우존스",   "default_price": 14100},
]

# 2. SCHD 주요 편입 배당주 한국어 기업명 · 섹터 · 사업영역 마스터 사전 (리밸런싱 시 자동 매칭용)
STOCK_METADATA_KR = {
    "TXN":  {"name_kr": "텍사스 인스트루먼트", "sector": "기술(반도체)", "biz": "글로벌 아날로그 및 임베디드 반도체 시장 점유율 1위 기업"},
    "PG":   {"name_kr": "프록터 앤 갬블(P&G)", "sector": "필수소비재", "biz": "질레트·다우니·페브리즈 등 보유, 68년 연속 배당 인상 배당왕"},
    "QCOM": {"name_kr": "퀄컴", "sector": "기술(반도체·통신)", "biz": "스마트폰 AP(스냅드래곤) 및 5G 무선통신 모뎀 특허 글로벌 1위"},
    "KO":   {"name_kr": "코카콜라", "sector": "필수소비재", "biz": "200개국 이상 유통망을 보유한 글로벌 비알코올 음료 브랜드 1위"},
    "CVX":  {"name_kr": "셰브론", "sector": "에너지", "biz": "석유·천연가스 탐사부터 정유·화학까지 수직계열화된 미국 에너지 메이저"},
    "COP":  {"name_kr": "코노코필립스", "sector": "에너지", "biz": "미국 최대 규모의 독립 석유·천연가스 탐사 및 생산(E&P) 전문 기업"},
    "UNH":  {"name_kr": "유나이티드헬스 그룹", "sector": "헬스케어", "biz": "미국 1위 민영 건강보험(UnitedHealthcare) 및 헬스케어 데이터(Optum) 기업"},
    "AMGN": {"name_kr": "암젠", "sector": "헬스케어(바이오)", "biz": "골다공증·항암·심혈관 질환 중심의 글로벌 대표 바이오 의약품 기업"},
    "MRK":  {"name_kr": "머크(Merck)", "sector": "헬스케어(제약)", "biz": "글로벌 매출 1위 면역항암제 '키트루다(Keytruda)' 및 백신 보유 빅파마"},
    "HD":   {"name_kr": "홈디포", "sector": "경기소비재", "biz": "북미 시장 점유율 1위 주택 개보수(Home Improvement) 및 건축자재 유통망"},
    "VZ":   {"name_kr": "버라이즌", "sector": "통신서비스", "biz": "미국 최대 무선통신 가입자 기반의 5G·광대역 통신 인프라 사업자"},
    "ABT":  {"name_kr": "애보트 래보라토리즈", "sector": "헬스케어(의료기기)", "biz": "연속혈당측정기(프리스타일 리브레)·진단키트·심혈관 의료기기 글로벌 리더"},
    "PEP":  {"name_kr": "펩시코", "sector": "필수소비재", "biz": "펩시 음료 및 프리토레이(레이즈·도리토스)·퀘이커 스낵 보유 글로벌 식음료 기업"},
    "LMT":  {"name_kr": "록히드 마틴", "sector": "산업재(방산)", "biz": "F-35 스텔스 전투기·미사일 방어체계를 생산하는 세계 최대 방위산업체"},
    "BLK":  {"name_kr": "블랙록", "sector": "금융(자산운용)", "biz": "iShares ETF 브랜드와 알라딘 시스템을 보유한 세계 최대 자산운용사"},
    "ACN":  {"name_kr": "액센츄어", "sector": "기술(IT서비스)", "biz": "포춘 500대 기업의 디지털 전환 및 AI 도입을 설계하는 글로벌 1위 IT 컨설팅사"},
    "ADP":  {"name_kr": "오토매틱 데이터 프로세싱", "sector": "기술(클라우드)", "biz": "미국 직장인 6명 중 1명의 급여를 처리하는 글로벌 1위 HR·급여 클라우드 기업"},
    "BMY":  {"name_kr": "브리스톨 마이어스 스큅", "sector": "헬스케어(제약)", "biz": "항응고제(엘리퀴스) 및 면역항암제(옵디보) 중심의 글로벌 제약사"},
    "UPS":  {"name_kr": "유나이티드 파슬 서비스", "sector": "산업재(물류)", "biz": "전 세계 220개국 항공·육상 화물 네트워크를 운영하는 글로벌 최대 특송 물류사"},
    "FAST": {"name_kr": "패스널", "sector": "산업재", "biz": "산업용 볼트·너트 및 공장 안전용품을 공급하는 북미 최대 B2B 산업재 유통사"},
    "TGT":  {"name_kr": "타겟(Target)", "sector": "필수소비재(유통)", "biz": "미국 전역 약 2,000개 대형 매장과 이커머스를 결합한 대표 종합 소매 유통망"},
    "USB":  {"name_kr": "US 뱅코프", "sector": "금융(은행)", "biz": "미국 중서부·서부 기반 자산규모 5위권의 대형 상업은행"},
    "TROW": {"name_kr": "티로우 프라이스", "sector": "금융(자산운용)", "biz": "무차입 경영과 은퇴 타겟데이트펀드(TDF)에 강점을 가진 미국의 대표 자산운용사"},
    "ONEOK":{"name_kr": "원오크(OKE)", "sector": "에너지(미드스트림)", "biz": "북미 핵심 천연가스 및 천연가스액(NGL) 파이프라인 운송 인프라 사업자"},
    "OKE":  {"name_kr": "원오크(ONEOK)", "sector": "에너지(미드스트림)", "biz": "북미 핵심 천연가스 및 천연가스액(NGL) 파이프라인 운송 인프라 사업자"},
    "MO":   {"name_kr": "알트리아 그룹", "sector": "필수소비재(담배)", "biz": "말보로(Marlboro) 미국 판권 및 무연담배 브랜드를 보유한 초고배당 기업"},
    "ITW":  {"name_kr": "일리노이 툴 웍스", "sector": "산업재", "biz": "자동차·식음료 장비·용접기 등 고마진 특수 산업용 부품을 제조하는 배당왕"},
    "GD":   {"name_kr": "제너럴 다이내믹스", "sector": "산업재(방산)", "biz": "핵잠수함·에이브람스 전차·걸프스트림 비즈니스 제트기를 생산하는 방산 대기업"},
    "PAYX": {"name_kr": "페이첵스", "sector": "기술(B2B솔루션)", "biz": "중소·중견기업 특화 급여 정산 및 인사관리(HR) 아웃소싱 플랫폼"},
    "GIS":  {"name_kr": "제너럴 밀스", "sector": "필수소비재(식품)", "biz": "하겐다즈·치리오스·네이처밸리 등 100년 이상 배당을 지급해온 북미 종합식품사"}
}

# yfinance funds_data 섹터 영문 키 → 한국어 표준 섹터명 매핑
SECTOR_KR_MAP = {
    "consumer_defensive": "필수소비재",
    "healthcare": "헬스케어",
    "technology": "기술(IT·반도체)",
    "energy": "에너지",
    "financial_services": "금융서비스",
    "industrials": "산업재·방산",
    "consumer_cyclical": "경기소비재",
    "communication_services": "통신서비스",
    "basic_materials": "소재·화학",
    "utilities": "유틸리티",
    "real_estate": "리츠·부동산"
}

# 2026년 10월 공시 기준 검증된 폴백(Fallback) 포트폴리오 데이터 (API 일시 장애 대비용)
DEFAULT_TOP10 = [
    {"ticker": "TXN",  "weight": 4.52},
    {"ticker": "PG",   "weight": 4.31},
    {"ticker": "QCOM", "weight": 4.28},
    {"ticker": "KO",   "weight": 4.19},
    {"ticker": "CVX",  "weight": 4.15},
    {"ticker": "COP",  "weight": 4.02},
    {"ticker": "UNH",  "weight": 3.98},
    {"ticker": "AMGN", "weight": 3.96},
    {"ticker": "MRK",  "weight": 3.92},
    {"ticker": "HD",   "weight": 3.88}
]

DEFAULT_SECTORS = [
    {"sector": "필수소비재", "weight": 20.16},
    {"sector": "헬스케어", "weight": 18.98},
    {"sector": "기술(IT·반도체)", "weight": 16.34},
    {"sector": "에너지", "weight": 13.10},
    {"sector": "금융서비스", "weight": 12.85},
    {"sector": "산업재·방산", "weight": 9.80},
    {"sector": "경기소비재", "weight": 5.12},
    {"sector": "통신서비스", "weight": 3.65}
]

# 2026년 3월 23일 발효 정기 리밸런싱(Reconstitution) 주요 편입(IN) / 퇴출(OUT) 팩트 데이터
REBALANCE_2026_HISTORY = {
    "effective_date": "2026-03-23",
    "summary": "2026년 3월 정기 변경에서 총 25개 종목이 신규 편입(IN)되고 22개 종목이 퇴출(OUT)되어 총 103개 종목으로 재편되었습니다. 에너지 섹터 비중이 약 8%p 축소되고 재무건전성이 우수한 헬스케어·기술주·필수소비재 비중이 확대되었습니다.",
    "added_count": 25,
    "removed_count": 22,
    "key_in": [
        {"ticker": "UNH", "name_kr": "유나이티드헬스 그룹", "sector": "헬스케어", "biz": "미국 1위 민영 건강보험 및 Optum 헬스케어 데이터 기업", "reason": "주가 조정으로 시가배당률이 지수 상위 50% 커트라인을 통과하며 높은 ROE·배당성장률 점수로 Top 10 직행"},
        {"ticker": "PG",  "name_kr": "프록터 앤 갬블(P&G)", "sector": "필수소비재", "biz": "다우니·질레트·페브리즈 보유 글로벌 생활용품 1위 배당왕", "reason": "우수한 부채 대비 현금흐름(FCF/Debt)과 68년 연속 배당 인상 기록으로 4대 팩터 종합 점수 상위권 진입"},
        {"ticker": "QCOM","name_kr": "퀄컴", "sector": "기술(반도체)", "biz": "스마트폰 스냅드래곤 칩셋 및 무선통신 특허 글로벌 1위", "reason": "높은 자기자본이익률(ROE)과 5년 배당성장률 점수를 바탕으로 기술 섹터 핵심 종목으로 편입"},
        {"ticker": "ABT", "name_kr": "애보트 래보라토리즈", "sector": "헬스케어", "biz": "연속혈당측정기 및 글로벌 진단·의료기기 리더", "reason": "안정적인 잉여현금흐름 창출력과 50년 이상 연속 배당성장 이력으로 신규 편입"},
        {"ticker": "ACN", "name_kr": "액센츄어", "sector": "기술(IT컨설팅)", "biz": "글로벌 1위 기업용 AI·디지털 전환 컨설팅 기업", "reason": "사실상 무차입에 가까운 재무 구조(FCF/Debt 최상위)와 높은 ROE로 신규 편입"},
        {"ticker": "ADP", "name_kr": "ADP", "sector": "기술(클라우드)", "biz": "북미 1위 클라우드 급여 및 인사관리(HR) 플랫폼", "reason": "고금리 환경에서도 흔들리지 않는 현금흐름과 49년 연속 배당 인상 기록으로 편입"}
    ],
    "key_out": [
        {"ticker": "ABBV", "name_kr": "애브비", "sector": "헬스케어(제약)", "biz": "휴미라·스카이리지·린버크 보유 글로벌 바이오 빅파마", "reason": "대규모 인수합병에 따른 총부채 부담으로 '현금흐름 대 총부채(FCF/Debt)' 팩터 점수가 하락하며 100위권 밖으로 밀려남"},
        {"ticker": "CSCO", "name_kr": "시스코 시스템즈", "sector": "기술(네트워크)", "biz": "글로벌 기업용 라우터·스위치·보안 네트워크 장비 1위", "reason": "스플렁크(Splunk) 인수 이후 총부채 증가 및 주가 상승에 따른 시가배당률 매력 감소로 종합 점수 미달 편출"},
        {"ticker": "VLO",  "name_kr": "발레로 에너지", "sector": "에너지(정유)", "biz": "북미 최대 규모의 독립 석유 정제 및 바이오연료 기업", "reason": "정제마진 둔화에 따른 잉여현금흐름 감소로 에너지 섹터 비중 축소(-8%p)와 함께 편출"},
        {"ticker": "HAL",  "name_kr": "할리버튼", "sector": "에너지(유전서비스)", "biz": "글로벌 시추 및 유전 개발 엔지니어링 서비스 기업", "reason": "과거 배당 삭감 이력으로 인한 5년 배당성장률 점수 열위 및 시가배당률 하락으로 편출"}
    ]
}

def get_third_friday(year: int, month: int) -> date:
    """특정 연도·월의 세 번째 금요일 날짜를 정확히 계산합니다 (S&P DJI 리밸런싱 기준일)."""
    first_day = date(year, month, 1)
    # weekday(): 월요일=0 ... 금요일=4
    days_until_first_friday = (4 - first_day.weekday()) % 7
    first_friday = first_day + timedelta(days=days_until_first_friday)
    third_friday = first_friday + timedelta(days=14)
    return third_friday

def calc_rebalance_schedule(today_date: date) -> dict:
    """
    다가오는 다음 연간 종목 전면 교체일(3월 세 번째 금요일 장 마감 후)과
    다음 분기 비중 리밸런싱일(3·6·9·12월 세 번째 금요일) 및 D-Day를 자동 계산합니다.
    """
    yr = today_date.year
    # 1) 다음 연간 전면 교체(Reconstitution): 3월 세 번째 금요일
    march_3rd_fri = get_third_friday(yr, 3)
    if march_3rd_fri < today_date:
        march_3rd_fri = get_third_friday(yr + 1, 3)
    effective_monday = march_3rd_fri + timedelta(days=3)
    annual_dday = (march_3rd_fri - today_date).days

    # 2) 다음 분기 비중 리밸런싱(Quarterly Weight Cap): 3, 6, 9, 12월 세 번째 금요일
    q_candidates = []
    for y in [yr, yr + 1]:
        for m in [3, 6, 9, 12]:
            d = get_third_friday(y, m)
            if d >= today_date:
                q_candidates.append(d)
    next_q_date = min(q_candidates)
    q_dday = (next_q_date - today_date).days

    return {
        "next_annual_reconstitution_date": march_3rd_fri.strftime("%Y-%m-%d"),
        "next_annual_effective_date": effective_monday.strftime("%Y-%m-%d"),
        "annual_dday": annual_dday,
        "next_quarterly_rebalance_date": next_q_date.strftime("%Y-%m-%d"),
        "quarterly_dday": q_dday
    }

def fetch_schd_portfolio(schd_ticker_obj: yf.Ticker, kst_date_str: str) -> dict:
    """
    yfinance funds_data 모듈을 통해 SCHD의 최신 Top 10 구성 종목과 섹터 비중을 자동 수집하고,
    Top 10 개별 기업의 실시간 주가 및 일간 등락률(%)을 함께 조회합니다.
    """
    holdings_raw = []
    sectors_list = []
    source_status = "Yahoo Finance (Morningstar / Charles Schwab 공식 ETF 공시 피드 자동 연동)"

    try:
        fdata = schd_ticker_obj.funds_data
        # 1) Top 10 보유 종목 및 비중 추출
        top_df = getattr(fdata, "top_holdings", None)
        if top_df is not None and not top_df.empty:
            for symbol, row in top_df.head(10).iterrows():
                sym_str = str(symbol).strip().upper()
                w_val = 0.0
                for col in top_df.columns:
                    if "pct" in col.lower() or "weight" in col.lower() or "holding" in col.lower():
                        w_val = float(row[col])
                        break
                if w_val == 0.0 and len(row) > 0:
                    for val in row.values:
                        if isinstance(val, (int, float, np.floating)) and 0 < float(val) < 1.0:
                            w_val = float(val)
                            break
                weight_pct = round(w_val * 100.0 if w_val <= 1.0 else w_val, 2)
                if weight_pct > 0:
                    holdings_raw.append({"ticker": sym_str, "weight": weight_pct})

        # 2) 섹터 비중 추출
        sec_data = getattr(fdata, "sector_weightings", None)
        if sec_data:
            sec_dict = {}
            if isinstance(sec_data, dict):
                sec_dict = sec_data
            elif isinstance(sec_data, list):
                for item in sec_data:
                    if isinstance(item, dict):
                        sec_dict.update(item)
            for k, v in sec_dict.items():
                try:
                    vf = float(v)
                    wp = round(vf * 100.0 if vf <= 1.0 else vf, 2)
                    if wp > 0.1:
                        kr_sec = SECTOR_KR_MAP.get(str(k).lower(), str(k))
                        sectors_list.append({"sector": kr_sec, "weight": wp})
                except Exception:
                    pass
            sectors_list.sort(key=lambda x: x["weight"], reverse=True)
    except Exception as e:
        print(f"[Info] funds_data 자동 조회 경고, 검증된 공시 스냅샷 폴백 사용: {e}")

    if len(holdings_raw) < 5:
        holdings_raw = DEFAULT_TOP10
        source_status = "Charles Schwab 2026 공시 기준 스냅샷 + 개별 종목 일별 주가 실시간 연동"
    if len(sectors_list) < 4:
        sectors_list = DEFAULT_SECTORS

    # 3) Top 10 개별 종목의 최근 주가 및 일간 등락률(%) 일괄 수집
    tickers_to_fetch = [h["ticker"] for h in holdings_raw]
    live_prices_map = {}
    try:
        batch_df = yf.download(tickers_to_fetch, period="5d", auto_adjust=False, progress=False)
        if not batch_df.empty and "Close" in batch_df:
            close_df = batch_df["Close"]
            for tk in tickers_to_fetch:
                if tk in close_df:
                    s = close_df[tk].dropna()
                    if len(s) >= 2:
                        p_cur = round(float(s.iloc[-1]), 2)
                        p_prev = float(s.iloc[-2])
                        chg = round(((p_cur - p_prev) / p_prev) * 100.0, 2) if p_prev > 0 else 0.0
                        live_prices_map[tk] = {"price": p_cur, "change_pct": chg}
                    elif len(s) == 1:
                        live_prices_map[tk] = {"price": round(float(s.iloc[-1]), 2), "change_pct": 0.0}
    except Exception as e:
        print(f"[Warning] Top 10 개별 주가 조회 경고: {e}")

    enriched_holdings = []
    for idx, item in enumerate(holdings_raw, start=1):
        tk = item["ticker"]
        meta = STOCK_METADATA_KR.get(tk, {
            "name_kr": tk,
            "sector": "배당우량주",
            "biz": "Dow Jones U.S. Dividend 100 지수 편입 10년 연속 배당 우량 기업"
        })
        p_info = live_prices_map.get(tk, {"price": 0.0, "change_pct": 0.0})
        enriched_holdings.append({
            "rank": idx,
            "ticker": tk,
            "name_kr": meta["name_kr"],
            "sector": meta["sector"],
            "biz": meta["biz"],
            "weight": item["weight"],
            "price": p_info["price"],
            "change_pct": p_info["change_pct"]
        })

    top10_weight_sum = round(sum(x["weight"] for x in enriched_holdings), 2)
    today_dt = datetime.strptime(kst_date_str, "%Y-%m-%d").date()
    schedule_info = calc_rebalance_schedule(today_dt)

    return {
        "as_of_date": kst_date_str,
        "total_holdings_count": 103,
        "top10_weight_sum": top10_weight_sum,
        "top_holdings": enriched_holdings,
        "sector_weights": sectors_list,
        "schedule": schedule_info,
        "rebalance_2026": REBALANCE_2026_HISTORY,
        "sources": {
            "holdings_source": source_status,
            "index_methodology": "S&P Dow Jones Indices — Dow Jones U.S. Dividend 100 Index Methodology",
            "official_url": "https://www.schwabassetmanagement.com/products/schd"
        }
    }

def fetch_fed_rates_official(start_date: str) -> pd.Series:
    try:
        fred_csv_url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DFF"
        df_fed = pd.read_csv(fred_csv_url)
        date_col = df_fed.columns[0]
        val_col = df_fed.columns[1]
        df_fed[date_col] = pd.to_datetime(df_fed[date_col], errors="coerce")
        df_fed[val_col] = pd.to_numeric(df_fed[val_col], errors="coerce")
        df_fed = df_fed.dropna(subset=[date_col, val_col])
        df_fed = df_fed[df_fed[date_col] >= pd.Timestamp(start_date)]
        s = pd.Series(df_fed[val_col].values, index=df_fed[date_col])
        return s.sort_index()
    except Exception as e:
        print(f"[Warning] FRED 공식 CSV 로드 실패, 13주 단기국채(^IRX) 폴백 실행: {e}")
        try:
            irx = yf.Ticker("^IRX").history(start=start_date, auto_adjust=False)
            if not irx.empty:
                s = irx["Close"].dropna().astype(float)
                s.index = pd.to_datetime(s.index).tz_localize(None)
                return s
        except Exception:
            pass
    return pd.Series(dtype=float)

def fetch_usdkrw_series(start_date: str) -> pd.Series:
    try:
        krw = yf.Ticker("KRW=X").history(start=start_date, auto_adjust=False)
        if not krw.empty:
            s = krw["Close"].dropna().astype(float)
            s.index = pd.to_datetime(s.index).tz_localize(None)
            s = s[(s >= 900.0) & (s <= 2000.0)]
            return s.sort_index()
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
        prev_price = cur_price
        close_date_str = "--"
        ttm_div = int(round(cur_price * (fallback_yield / 100.0)))
        etf_yield = round(fallback_yield, 2)
        is_est_div = True

        try:
            hist = yf.Ticker(ticker).history(period="1y", auto_adjust=False)
            if not hist.empty:
                hist.index = pd.to_datetime(hist.index).tz_localize(None)
                closes = hist["Close"].dropna()
                if not closes.empty:
                    cur_price = int(round(float(closes.iloc[-1])))
                    prev_price = int(round(float(closes.iloc[-2]))) if len(closes) >= 2 else cur_price
                    close_date_str = closes.index[-1].strftime("%Y-%m-%d")

                divs = hist["Dividends"].dropna()
                divs_pos = divs[divs > 0]
                if len(divs_pos) >= 6:
                    raw_div_sum = float(divs_pos.sum())
                    calc_yield = (raw_div_sum / cur_price) * 100.0
                    if 2.0 <= calc_yield <= 6.5:
                        ttm_div = int(round(raw_div_sum))
                        etf_yield = round(calc_yield, 2)
                        is_est_div = False
                    else:
                        ttm_div = int(round(cur_price * (fallback_yield / 100.0)))
                        etf_yield = round(fallback_yield, 2)
                else:
                    ttm_div = int(round(cur_price * (fallback_yield / 100.0)))
                    etf_yield = round(fallback_yield, 2)
        except Exception as e:
            print(f"[Warning] {key} ({ticker}) 데이터 수집 경고: {e}")

        result[key] = {
            "code": item["code"],
            "name": item["name"],
            "price": cur_price,
            "prev_price": prev_price,
            "close_date": close_date_str,
            "ttm_div": ttm_div,
            "yield": etf_yield,
            "is_est_div": is_est_div
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
            f'                    📌 <b>실시간 퀀트 요약 ({summary_data["date"]} 기준):</b> 현재 SCHD 주가는 <b>${summary_data["price"]:.2f}</b>'
            f'(일간 <b>{summary_data["change_pct"]:+.2f}%</b>), 직전 4분기 확정 연 배당금은 <b>${summary_data["ttm_div"]:.4f}</b>'
            f'(시가배당률 <b>{summary_data["yield"]:.2f}%</b>)이며, 최근 5년 대비 매수 매력 점수는 <b>{summary_data["score_5y"]}점</b>'
            f'(5년 중앙 적정주가 <b>${summary_data["fair_5y"]:.2f}</b>, 상위 10% 꿀통 매수선 <b>${summary_data["honey_5y"]:.2f}</b>, '
            f'최근 환율 <b>{summary_data["usdkrw"]:.1f}원</b>, TIGER 종가 <b>{summary_data["tiger_price"]:,}원</b>)입니다.\n'
            "                </div>\n"
            "                <!-- SEO_LIVE_SUMMARY_END -->"
        )

        pattern = re.compile(r"<!-- SEO_LIVE_SUMMARY_START -->.*?<!-- SEO_LIVE_SUMMARY_END -->", re.DOTALL)
        if pattern.search(content):
            updated_content = pattern.sub(new_block, content)
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(updated_content)
    except Exception as e:
        print(f"[Warning] SEO 요약 갱신 경고 (무시됨): {e}")

def generate_schd_data(output_path: str = "schd_data.json"):
    print("1. SCHD 상장 이후 전체(period='max', auto_adjust=False) 실제 데이터 수집 중...")
    schd = yf.Ticker("SCHD")
    hist = schd.history(period="max", auto_adjust=False)
    if hist.empty:
        raise RuntimeError("yfinance에서 SCHD 데이터를 가져오지 못했습니다.")

    hist.index = pd.to_datetime(hist.index).tz_localize(None)
    hist = hist.sort_index()

    df = pd.DataFrame(index=hist.index)
    df["price"] = hist["Close"].astype(float)
    df["dividend"] = hist["Dividends"].fillna(0.0).astype(float)

    print("2. 직전 4개 분기 확정 배당금 합산(4Q Discrete Rolling TTM) 계산 중...")
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

    latest_q_div = float(div_events.iloc[-1]) if not div_events.empty else 0.26
    latest_price = float(df["price"].iloc[-1])
    prev_schd_price = float(df["price"].iloc[-2]) if len(df["price"]) >= 2 else latest_price
    schd_change_pct = round(((latest_price - prev_schd_price) / prev_schd_price) * 100.0, 2) if prev_schd_price > 0 else 0.0
    forward_yield = round(((latest_q_div * 4.0) / latest_price) * 100.0, 2)

    if len(rolling_4q) >= 21:
        div_now = float(rolling_4q.iloc[-1])
        div_5y_ago = float(rolling_4q.iloc[-21])
        cagr_5y = round(((div_now / div_5y_ago) ** (1.0 / 5.0) - 1.0) * 100.0, 1) if div_5y_ago > 0 else 11.0
    else:
        cagr_5y = 11.0

    print("3. 미국 실효 기준금리(FRED DFF) 및 원/달러 환율(KRW=X) 실제 시계열 병합 중...")
    start_str = df.index.min().strftime("%Y-%m-%d")

    fed_series = fetch_fed_rates_official(start_str)
    if not fed_series.empty:
        full_idx = df.index.union(fed_series.index).sort_values()
        df["fed_rate"] = fed_series.reindex(full_idx).ffill().bfill().reindex(df.index).fillna(4.5)
    else:
        df["fed_rate"] = 4.5

    fx_series = fetch_usdkrw_series(start_str)
    if not fx_series.empty:
        full_fx_idx = df.index.union(fx_series.index).sort_values()
        df["fx_rate"] = fx_series.reindex(full_fx_idx).ffill().bfill().reindex(df.index).fillna(1340.0)
    else:
        df["fx_rate"] = 1340.0

    print("4. 국내 4대장(TIGER, SOL, KODEX, ACE) 확정 종가 수집 중...")
    cur_yield_val = round(float(df["yield"].iloc[-1]), 2)
    kr_etfs_data = fetch_kr_etfs(cur_yield_val)

    kst = timezone(timedelta(hours=9))
    now_kst = datetime.now(kst)
    updated_at_str = now_kst.strftime("%Y년 %m월 %d일 %H시 %M분 (한국시간)")
    kst_date_str = now_kst.strftime("%Y-%m-%d")

    print("5. SCHD 포트폴리오 Top 10 구성 종목 및 섹터 비중 자동 수집 중...")
    portfolio_data = fetch_schd_portfolio(schd, kst_date_str)

    dates_list = df.index.strftime("%Y-%m-%d").tolist()
    prices_list = [round(float(x), 2) for x in df["price"].tolist()]
    ttm_divs_list = [round(float(x), 4) for x in df["ttm_dividend"].tolist()]
    yields_list = [round(float(x), 2) for x in df["yield"].tolist()]
    fed_rates_list = [round(float(x), 2) for x in df["fed_rate"].tolist()]
    fx_rates_list = [round(float(x), 1) for x in df["fx_rate"].tolist()]

    usdkrw_latest = fx_rates_list[-1]
    usdkrw_prev = fx_rates_list[-2] if len(fx_rates_list) >= 2 else usdkrw_latest
    usdkrw_1y_avg = round(float(np.mean(fx_rates_list[-252:])), 1) if len(fx_rates_list) >= 252 else usdkrw_latest

    y_5y = yields_list[-1260:] if len(yields_list) >= 1260 else yields_list
    cheaper_5y = sum(1 for y in y_5y if y > yields_list[-1])
    score_5y = int(round(100.0 - (cheaper_5y / len(y_5y)) * 100.0))
    p50_5y = float(np.percentile(y_5y, 50))
    p90_5y = float(np.percentile(y_5y, 90))
    fair_5y = round(ttm_divs_list[-1] / (p50_5y / 100.0), 2)
    honey_5y = round(ttm_divs_list[-1] / (p90_5y / 100.0), 2)

    output_data = {
        "updated_at": updated_at_str,
        "cagr_5y": cagr_5y,
        "latest": {
            "price": prices_list[-1],
            "prev_price": round(prev_schd_price, 2),
            "change_pct": schd_change_pct,
            "yield": yields_list[-1],
            "forward_yield": forward_yield,
            "ttm_dividend": ttm_divs_list[-1],
            "fed_rate": fed_rates_list[-1],
            "date": dates_list[-1],
            "prev_date": dates_list[-2] if len(dates_list) >= 2 else dates_list[-1],
            "usdkrw": usdkrw_latest,
            "prev_usdkrw": usdkrw_prev,
            "usdkrw_1y_avg": usdkrw_1y_avg
        },
        "kr_etfs": kr_etfs_data,
        "portfolio": portfolio_data,
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

    update_index_html_seo_summary("index.html", {
        "date": dates_list[-1],
        "price": prices_list[-1],
        "change_pct": schd_change_pct,
        "ttm_div": ttm_divs_list[-1],
        "yield": yields_list[-1],
        "score_5y": score_5y,
        "fair_5y": fair_5y,
        "honey_5y": honey_5y,
        "usdkrw": usdkrw_latest,
        "tiger_price": kr_etfs_data["TIGER"]["price"]
    })

    print(f"✅ 데이터 생성 완료: {output_path} (Top 1 종목: {portfolio_data['top_holdings'][0]['ticker']} {portfolio_data['top_holdings'][0]['weight']}%)")

if __name__ == "__main__":
    generate_schd_data()

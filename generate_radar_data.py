import json
import os
import re
from datetime import datetime, timedelta, timezone
import pandas as pd
import yfinance as yf

def fetch_and_verify_quant_data():
    print("1. [Quant Engine] SCHD 전체 시계열 주가 및 배당 데이터 수집 중...")
    schd = yf.Ticker("SCHD")
    
    hist = schd.history(period="max", interval="1d", auto_adjust=False)
    if hist.empty:
        raise ValueError("SCHD 주가 데이터를 가져오지 못했습니다.")

    hist.index = hist.index.tz_localize(None).normalize()
    hist = hist[~hist.index.duplicated(keep='last')].sort_index()

    print("2. [Quant Engine] 4분기 이산 롤링(4Q Rolling) TTM 배당금 및 배당 원장 생성 중...")
    div_series = hist[hist['Dividends'] > 0]['Dividends'].copy()
    
    div_clean = div_series.groupby(div_series.index.to_period('M')).sum()
    div_dates = div_series.reset_index().groupby(div_series.index.to_period('M'))['Date'].last()
    div_events = pd.Series(div_clean.values, index=pd.DatetimeIndex(div_dates.values)).sort_index()

    if len(div_events) < 4:
        raise ValueError("배당 이벤트 데이터가 4분기 미만입니다.")

    ttm_div_events = div_events.rolling(window=4, min_periods=4).sum()
    latest_q_div_events = div_events.copy()

    hist['TTM_Dividend'] = ttm_div_events.reindex(hist.index).ffill()
    hist['Latest_Q_Div'] = latest_q_div_events.reindex(hist.index).ffill()

    hist = hist.dropna(subset=['TTM_Dividend', 'Close']).copy()
    hist = hist[hist['TTM_Dividend'] > 0].copy()

    hist['Yield'] = (hist['TTM_Dividend'] / hist['Close']) * 100
    hist['Forward_Yield'] = ((hist['Latest_Q_Div'] * 4.0) / hist['Close']) * 100

    recent_divs = div_events.tail(8)
    div_ledger = [
        {"date": d.strftime('%Y-%m-%d'), "amount": round(float(val), 4)}
        for d, val in recent_divs.items()
    ]

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

    try:
        div_5y_ago = hist['TTM_Dividend'].iloc[max(0, len(hist) - 1260)]
        div_now = hist['TTM_Dividend'].iloc[-1]
        cagr_5y = ((div_now / div_5y_ago) ** (1 / 5) - 1) * 100
        cagr_5y = round(float(cagr_5y), 2)
    except Exception:
        cagr_5y = 11.20

    KST = timezone(timedelta(hours=9))
    now_kst = datetime.now(KST)
    updated_at_str = now_kst.strftime('%Y년 %m월 %d일 %H시 %M분 (한국시간)')
    iso_date_str = now_kst.strftime('%Y-%m-%d')

    dates = [d.strftime('%Y-%m-%d') for d in hist.index]
    prices = [round(float(p), 2) for p in hist['Close']]
    ttm_divs = [round(float(d), 4) for d in hist['TTM_Dividend']]
    yields = [round(float(y), 2) for y in hist['Yield']]
    fed_rates = [round(float(r), 2) for r in hist['Fed_Rate']]
    fx_rates = [round(float(x), 1) for x in hist['FX_Rate']]

    # 최근 5년(1260일) 기준 매수 매력 점수 및 분위수 미리 계산 (정적 HTML 주입용)
    yields_5y = yields[-1260:] if len(yields) >= 1260 else yields
    curr_p = prices[-1]
    curr_y = yields[-1]
    curr_div = ttm_divs[-1]
    curr_fed = fed_rates[-1]
    curr_fx = fx_rates[-1]

    cheaper_days_5y = len([y for y in yields_5y if y > curr_y])
    cheaper_pct_5y = (cheaper_days_5y / len(yields_5y)) * 100
    buy_score_5y = round(100 - cheaper_pct_5y)

    sorted_y5 = sorted(yields_5y)
    y_p50 = sorted_y5[int(len(sorted_y5) * 0.50)]
    y_p90 = sorted_y5[int(len(sorted_y5) * 0.90)]
    fair_price_5y = round(curr_div / (y_p50 / 100), 2)
    honey_price_5y = round(curr_div / (y_p90 / 100), 2)

    output_data = {
        "updated_at": updated_at_str,
        "cagr_5y": cagr_5y,
        "div_ledger": div_ledger,
        "latest": {
            "price": curr_p,
            "yield": curr_y,
            "forward_yield": round(float(hist['Forward_Yield'].iloc[-1]), 2),
            "ttm_dividend": curr_div,
            "fed_rate": curr_fed,
            "fx_rate": curr_fx,
            "date": dates[-1],
            "buy_score_5y": buy_score_5y,
            "fair_price_5y": fair_price_5y,
            "honey_price_5y": honey_price_5y
        },
        "dates": dates,
        "prices": prices,
        "ttm_dividends": ttm_divs,
        "yields": yields,
        "fed_rates": fed_rates,
        "fx_rates": fx_rates
    }

    base_dir = os.path.dirname(__file__)
    output_path = os.path.join(base_dir, 'schd_data.json')
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, separators=(',', ':'), ensure_ascii=False)
    print(f"✅ 1. JSON 저장 완료: {output_path}")

    # [SEO 핵심 1] sitemap.xml 자동 갱신 (검색엔진에 매일 최신화된 문서임을 알림)
    sitemap_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>https://dividend.besmelt.com/</loc>
    <lastmod>{iso_date_str}</lastmod>
    <changefreq>daily</changefreq>
    <priority>1.0</priority>
  </url>
</urlset>"""
    sitemap_path = os.path.join(base_dir, 'sitemap.xml')
    with open(sitemap_path, 'w', encoding='utf-8') as f:
        f.write(sitemap_content)
    print(f"✅ 2. Sitemap.xml 최신화 완료 (<lastmod>{iso_date_str}</lastmod>)")

    # [SEO 핵심 2] index.html 내부에 최신 수치 정적 베이킹 (네이버 Yeti & 구글봇 크롤링 최적화)
    index_path = os.path.join(base_dir, 'index.html')
    if os.path.exists(index_path):
        with open(index_path, 'r', encoding='utf-8') as f:
            html_str = f.read()

        seo_summary_block = (
            f"<!-- SEO_LIVE_SUMMARY_START -->\n"
            f"                <div id=\"seo-live-summary\" style=\"font-size:0.78rem; color:#94a3b8; margin-top:10px; line-height:1.5;\">\n"
            f"                    📌 <b>실시간 퀀트 요약 ({dates[-1]} 기준):</b> 현재 SCHD 주가는 <b>${curr_p:.2f}</b>, 직전 4분기 확정 연 배당금은 <b>${curr_div:.4f}</b>(시가배당률 <b>{curr_y:.2f}%</b>)이며, "
            f"최근 5년 대비 매수 매력 점수는 <b>{buy_score_5y}점</b>(5년 중앙 적정주가 <b>${fair_price_5y:.2f}</b>, 상위 10% 꿀통 매수선 <b>${honey_price_5y:.2f}</b>, 원/달러 환율 <b>{curr_fx:.1f}원</b>)입니다.\n"
            f"                </div>\n"
            f"                <!-- SEO_LIVE_SUMMARY_END -->"
        )

        pattern = r"<!-- SEO_LIVE_SUMMARY_START -->.*?<!-- SEO_LIVE_SUMMARY_END -->"
        if re.search(pattern, html_str, flags=re.DOTALL):
            html_str = re.sub(pattern, seo_summary_block, html_str, flags=re.DOTALL)
            with open(index_path, 'w', encoding='utf-8') as f:
                f.write(html_str)
            print("✅ 3. index.html 정적 SEO 브리핑 텍스트 베이킹 완료")

if __name__ == "__main__":
    fetch_and_verify_quant_data()

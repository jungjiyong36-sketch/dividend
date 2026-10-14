/**
 * dividend.besmelt.com 공통 설정 및 퀀트 계산 코어 엔진
 */
const SITE_CONFIG = {
  dataUrl: "schd_data.json",
  cacheKey: "SCHD_RADAR_CACHE_V2",
  cacheTTL: 1000 * 60 * 30, // 30분 세션 캐시 유지
  adsenseClient: "ca-pub-2894031755177844",
  primarySlotId: "3305729383",
  secondarySlotId: "3305729383", // 추가 슬롯 생성 시 이곳 번호만 변경하면 전 페이지 자동 반영
  threadsUrl: "https://www.threads.net/@dividend_besmelt",
  defaultTimeframeKey: "5Y",
  fedBandTolerance: 0.5 // 기준금리 유사 시기 필터링 범위 (±0.5%p)
};

// 7단계 멀티 타임프레임 정의 (영업일 기준)
const TIMEFRAMES = [
  { key: "1M", label: "1달", days: 21, group: "short" },
  { key: "3M", label: "3달", days: 63, group: "short" },
  { key: "1Y", label: "1년", days: 252, group: "mid" },
  { key: "3Y", label: "3년", days: 756, group: "mid" },
  { key: "5Y", label: "5년", days: 1260, group: "mid" },
  { key: "10Y", label: "10년", days: 2520, group: "long" },
  { key: "MAX", label: "전체", days: Infinity, group: "long" }
];

/**
 * 1. 테마 관리 (다크/라이트 모드)
 */
function initTheme() {
  const saved = localStorage.getItem("SCHD_THEME") || "dark";
  document.documentElement.setAttribute("data-theme", saved);
  updateThemeButtonLabel(saved);
}

function toggleTheme() {
  const current = document.documentElement.getAttribute("data-theme") || "dark";
  const next = current === "dark" ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", next);
  localStorage.setItem("SCHD_THEME", next);
  updateThemeButtonLabel(next);
  window.dispatchEvent(new CustomEvent("themeChanged", { detail: { theme: next } }));
}

function updateThemeButtonLabel(theme) {
  const btn = document.getElementById("themeToggleBtn");
  if (btn) {
    btn.innerHTML = theme === "dark" ? "☀️ 라이트" : "🌙 다크";
  }
}

/**
 * 2. 상단 헤더 & 하단 고정 네비게이션 바 렌더링 (MPA 페이지 이동 유도)
 */
function renderAppShell(activePage) {
  initTheme();

  const headerEl = document.getElementById("appHeader");
  if (headerEl) {
    headerEl.innerHTML = `
      <div class="header-inner">
        <a href="index.html" class="brand-logo">
          <span>📈 SCHD 퀀트 레이더</span>
          <span class="brand-badge">PRO</span>
        </a>
        <div class="header-actions">
          <a href="${SITE_CONFIG.threadsUrl}" target="_blank" rel="noopener" class="icon-btn">Threads @dividend_besmelt</a>
          <button id="themeToggleBtn" class="icon-btn" onclick="toggleTheme()">☀️ 라이트</button>
        </div>
      </div>
    `;
    updateThemeButtonLabel(document.documentElement.getAttribute("data-theme") || "dark");
  }

  const navEl = document.getElementById("bottomNav");
  if (navEl) {
    const tabs = [
      { id: "home", href: "index.html", icon: "📊", label: "레이더 홈" },
      { id: "diagnosis", href: "diagnosis.html", icon: "🎯", label: "내 평단 진단" },
      { id: "kschd", href: "kschd.html", icon: "🇰🇷", label: "국내ETF·환율" },
      { id: "simulator", href: "simulator.html", icon: "🚀", label: "은퇴 타임머신" }
    ];
    navEl.innerHTML = `
      <div class="bottom-nav-inner">
        ${tabs.map(t => `
          <a href="${t.href}" class="nav-item ${t.id === activePage ? "active" : ""}">
            <span class="nav-icon">${t.icon}</span>
            <span>${t.label}</span>
          </a>
        `).join("")}
      </div>
    `;
  }
}

/**
 * 3. 데이터 Fetch 및 sessionStorage 캐싱 로더
 */
async function loadSchdData() {
  try {
    const rawCache = sessionStorage.getItem(SITE_CONFIG.cacheKey);
    if (rawCache) {
      const parsed = JSON.parse(rawCache);
      if (Date.now() - parsed.timestamp < SITE_CONFIG.cacheTTL && parsed.data) {
        return parsed.data;
      }
    }
  } catch (e) {
    console.warn("세션 캐시 읽기 실패, 네트워크에서 새로 불러옵니다.", e);
  }

  const res = await fetch(`${SITE_CONFIG.dataUrl}?t=${Date.now()}`);
  if (!res.ok) throw new Error("schd_data.json 데이터를 불러올 수 없습니다.");
  const data = await res.json();

  try {
    sessionStorage.setItem(SITE_CONFIG.cacheKey, JSON.stringify({
      timestamp: Date.now(),
      data: data
    }));
  } catch (e) {
    console.warn("sessionStorage 용량 초과 등으로 캐시 저장 생략", e);
  }

  return data;
}

/**
 * 4. 핵심 퀀트 알고리즘: 특정 배당수익률(targetYield)의 기간 내 백분위 매력 점수 계산
 * - 정의: 선택 기간 내 'targetYield보다 배당수익률이 높았던(더 저평가였던) 과거 영업일 비율(%)'을 구한 뒤 100 - 비율로 역산
 */
function calcAttractivenessScore(yieldsArray, targetYield) {
  if (!yieldsArray || yieldsArray.length === 0) return 50;
  let higherCount = 0;
  const total = yieldsArray.length;
  for (let i = 0; i < total; i++) {
    if (yieldsArray[i] > targetYield) higherCount++;
  }
  const higherRatio = (higherCount / total) * 100;
  return Math.max(0, Math.min(100, Math.round(100 - higherRatio)));
}

/**
 * 분위기/점수별 시맨틱 컬러 및 등급 텍스트 반환
 */
function getScoreMeta(score) {
  if (score >= 80) {
    return {
      color: "var(--score-diamond)",
      hex: "#10b981",
      bg: "rgba(16, 185, 129, 0.14)",
      tier: "역사적 꿀통 구간",
      shortTag: "강력매수",
      action: "역사적 상위 20% 이내 저평가! 적극적 비중 확대 유효"
    };
  }
  if (score >= 60) {
    return {
      color: "var(--score-good)",
      hex: "#3b82f6",
      bg: "rgba(59, 130, 246, 0.14)",
      tier: "매수 매력 우위",
      shortTag: "분할매수",
      action: "평년 대비 배당 매력 높음, 정기 적립 + 추가 매수 유리"
    };
  }
  if (score >= 40) {
    return {
      color: "var(--score-neutral)",
      hex: "#f59e0b",
      bg: "rgba(245, 158, 11, 0.14)",
      tier: "중립 · 적정 주가",
      shortTag: "정기적립",
      action: "역사적 중간값 수준, 감정 배제하고 기계적 적립 유지"
    };
  }
  return {
    color: "var(--score-hot)",
    hex: "#ef4444",
    bg: "rgba(239, 68, 68, 0.14)",
    tier: "단기 주가 과열",
    shortTag: "관망·보류",
    action: "주가 상승으로 시가배당률 낮아진 상태, 무리한 추격매수 자제"
  };
}

/**
 * 배열 분위수(Quantile) 계산 함수 (0.0 ~ 1.0)
 */
function getQuantile(arr, q) {
  if (!arr || arr.length === 0) return 0;
  const sorted = [...arr].sort((a, b) => a - b);
  const pos = (sorted.length - 1) * q;
  const base = Math.floor(pos);
  const rest = pos - base;
  if (sorted[base + 1] !== undefined) {
    return sorted[base] + rest * (sorted[base + 1] - sorted[base]);
  }
  return sorted[base];
}

/**
 * 선택된 타임프레임 키(1M ~ MAX)에 맞춰 데이터 슬라이스 및 종합 통계 산출
 */
function analyzeTimeframe(data, tfKey) {
  const tfObj = TIMEFRAMES.find(t => t.key === tfKey) || TIMEFRAMES[4];
  const totalLen = data.dates.length;
  const sliceCount = tfObj.days === Infinity ? totalLen : Math.min(totalLen, tfObj.days);
  const startIndex = totalLen - sliceCount;

  const dates = data.dates.slice(startIndex);
  const prices = data.prices.slice(startIndex);
  const yields = data.yields.slice(startIndex);
  const divs = data.ttm_dividends.slice(startIndex);
  const fedRates = data.fed_rates.slice(startIndex);

  const currentYield = data.latest.yield;
  const currentFed = data.latest.fed_rate;
  const currentDiv = data.latest.ttm_dividend;

  // 1) 기본 배당 매력 점수
  const rawScore = calcAttractivenessScore(yields, currentYield);

  // 2) 미국 기준금리(±0.5%p) 유사 시기 필터링 보정 점수
  const similarFedYields = [];
  for (let i = 0; i < yields.length; i++) {
    if (Math.abs(fedRates[i] - currentFed) <= SITE_CONFIG.fedBandTolerance) {
      similarFedYields.push(yields[i]);
    }
  }
  const fedAdjustedScore = similarFedYields.length >= 10
    ? calcAttractivenessScore(similarFedYields, currentYield)
    : rawScore;

  // 3) 기간 내 상위 10%(90분위 배당률 = 꿀통선), 중앙값(50분위 = 적정선), 하위 10%(10분위 = 고평가선)
  const yieldP90 = getQuantile(yields, 0.90); // 배당률 상위 10% (저평가 주가 하단)
  const yieldP50 = getQuantile(yields, 0.50); // 배당률 중앙값 (적정 주가)
  const yieldP10 = getQuantile(yields, 0.10); // 배당률 하위 10% (고평가 주가 상단)

  // 현재 TTM 배당금 기준 역산 주가
  const bargainPrice = yieldP90 > 0 ? (currentDiv / (yieldP90 / 100)) : 0;
  const fairPrice = yieldP50 > 0 ? (currentDiv / (yieldP50 / 100)) : 0;
  const expensivePrice = yieldP10 > 0 ? (currentDiv / (yieldP10 / 100)) : 0;

  return {
    tf: tfObj,
    sliceCount,
    dates,
    prices,
    yields,
    divs,
    fedRates,
    rawScore,
    fedAdjustedScore,
    similarFedDays: similarFedYields.length,
    yieldP90,
    yieldP50,
    yieldP10,
    bargainPrice,
    fairPrice,
    expensivePrice
  };
}

/**
 * 애드센스 광고 슬롯 안전 초기화
 */
function triggerAdSense() {
  try {
    const ads = document.querySelectorAll(".adsbygoogle");
    ads.forEach(ad => {
      if (!ad.getAttribute("data-adsbygoogle-status")) {
        (window.adsbygoogle = window.adsbygoogle || []).push({});
      }
    });
  } catch (e) {
    // 광고 차단기 사용 시 조용히 무시
  }
}

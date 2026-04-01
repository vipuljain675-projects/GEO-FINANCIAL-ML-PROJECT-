/**
 * Market Intelligence JS Module
 */

let marketChartInstance = null;
let strategicForecastChartInstance = null;
let _liveTicker = null;         // currently selected ticker
let _livePoller = null;         // setInterval handle
let _marketSnapshot = null;

function formatMoneyCompact(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—';
  return `₹${Math.round(Number(value)).toLocaleString('en-IN')}`;
}

function formatDeltaPct(current, target) {
  if (!current || !target) return '—';
  const pct = ((target - current) / current) * 100;
  const sign = pct > 0 ? '+' : '';
  return `${sign}${pct.toFixed(1)}% vs current`;
}

// ─── Populate company dropdown from globalData ───────────────────────────────
function populateMarketSelect() {
  const sel = document.getElementById('market-company-select');
  const forecastSel = document.getElementById('forecast-company-select');
  if (!globalData.companies || (!sel && !forecastSel)) return;

  const sorted = [...globalData.companies].sort((a, b) => a.name.localeCompare(b.name));
  [sel, forecastSel].filter(Boolean).forEach((selectEl) => {
    selectEl.innerHTML = '<option value="">— Select a company —</option>';
    sorted.forEach(c => {
      const opt = document.createElement('option');
      opt.value = c.ticker;
      opt.dataset.name = c.name;
      opt.dataset.sector = c.sector;
      opt.textContent = `${c.name} (${c.ticker})`;
      selectEl.appendChild(opt);
    });
  });

  if (sel && !sel.dataset.bound) {
    sel.dataset.bound = 'true';
    sel.addEventListener('change', () => {
      const opt = sel.selectedOptions[0];
      if (!opt.value) return;
      if (forecastSel) forecastSel.value = opt.value;
      loadMarketData(opt.value, opt.dataset.name || '', opt.dataset.sector || '');
    });
  }
  if (forecastSel && !forecastSel.dataset.bound) {
    forecastSel.dataset.bound = 'true';
    forecastSel.addEventListener('change', () => {
      const opt = forecastSel.selectedOptions[0];
      if (!opt.value) return;
      if (sel) sel.value = opt.value;
      loadMarketData(opt.value, opt.dataset.name || '', opt.dataset.sector || '');
    });
  }
}

// ─── Main loader ─────────────────────────────────────────────────────────────
async function loadMarketData(ticker, companyName, sector) {
  _marketSnapshot = null;
  const sel = document.getElementById('market-company-select');
  const forecastSel = document.getElementById('forecast-company-select');
  if (sel && ticker) sel.value = ticker;
  if (forecastSel && ticker) forecastSel.value = ticker;
  // Show loading state
  document.getElementById('chart-title').textContent = `Loading ${companyName}…`;
  document.getElementById('market-loading').style.display = 'flex';
  document.getElementById('marketChart').style.display = 'none';
  document.getElementById('event-pills').innerHTML = '';

  // Reset KPIs
  ['kpi-price', 'kpi-ath', 'kpi-atl', 'kpi-growth'].forEach(id => {
    document.getElementById(id).textContent = '…';
  });
  ['twitter-panel', 'gdelt-panel', 'events-panel'].forEach(id => {
    document.getElementById(id).innerHTML = '<div class="loading">Fetching…</div>';
  });

  try {
    const res = await fetch(`/api/market?ticker=${encodeURIComponent(ticker)}&company=${encodeURIComponent(companyName)}&sector=${encodeURIComponent(sector)}`);
    const raw = await res.text();
    let data;
    try {
      data = JSON.parse(raw);
    } catch (_e) {
      throw new Error(raw || 'Market data endpoint returned invalid JSON');
    }
    if (!res.ok) {
      throw new Error(data?.detail || data?.error || raw || `HTTP ${res.status}`);
    }

    if (data.error) throw new Error(data.error);
    _marketSnapshot = data;

    renderStockChart(data);
    renderForecastCards(data);
    renderStrategicForecast(data);
    renderStrategicForecastChart(data);
    renderForecastInputs(data);
    renderNewsPanel(data.news_sentiment);
    renderGDELTPanel(data.gdelt_signal, sector);
    renderEventsPanel(data.events);
    initializeDateInspector(data);
    renderKPIs(data);

    // Start live price polling for this ticker
    startLivePolling(ticker);

  } catch (e) {
    console.error('Market load error:', e);
    document.getElementById('chart-title').textContent = `Error: ${e.message}`;
    document.getElementById('market-loading').innerHTML = `<div class="loading" style="color:var(--critical)">Failed to load data: ${e.message}</div>`;
  }
}

// ─── Render KPI strip ─────────────────────────────────────────────────────────
function renderKPIs(data, liveSnap) {
  const h = data ? data.history : null;
  const current = liveSnap ? liveSnap.live_price : (h ? h.current_price : null);
  const base = h ? h.price_2010 : null;
  const change = base && current ? (((current - base) / base) * 100).toFixed(0) : '—';
  const changeColor = parseFloat(change) >= 0 ? 'var(--low)' : 'var(--critical)';
  const changeSign = parseFloat(change) >= 0 ? '+' : '';

  document.getElementById('kpi-price').textContent = current ? `₹${current.toLocaleString('en-IN')}` : '—';
  if (h) {
    document.getElementById('kpi-ath').textContent = `₹${h.all_time_high.toLocaleString('en-IN')}`;
    document.getElementById('kpi-atl').textContent = `₹${h.all_time_low.toLocaleString('en-IN')}`;
    const growthEl = document.getElementById('kpi-growth');
    growthEl.textContent = `${changeSign}${change}%`;
    growthEl.style.color = changeColor;
  }

  // Live status badge
  updateLiveBadge(liveSnap);
}

function updateHoverReadout(dateLabel, value, seriesLabel) {
  const box = document.getElementById('market-hover-readout');
  const dateNode = document.getElementById('market-hover-date');
  const priceNode = document.getElementById('market-hover-price');
  const metaNode = document.getElementById('market-hover-meta');
  if (!box || !dateNode || !priceNode || !metaNode) return;
  box.classList.remove('hidden');
  dateNode.textContent = dateLabel || 'Hover over the chart';
  priceNode.textContent = formatMoneyCompact(value);
  metaNode.textContent = seriesLabel ? `${seriesLabel} point on the chart.` : 'Precise date and price view.';
}

function getNearestHistoricalPoint(targetDate) {
  if (!_marketSnapshot?.history?.dates?.length) return null;
  const dates = _marketSnapshot.history.dates;
  const prices = _marketSnapshot.history.prices;
  const target = new Date(targetDate);
  let bestIndex = 0;
  let bestDistance = Infinity;
  dates.forEach((date, index) => {
    const distance = Math.abs(new Date(date) - target);
    if (distance < bestDistance) {
      bestDistance = distance;
      bestIndex = index;
    }
  });
  return { date: dates[bestIndex], price: prices[bestIndex] };
}

function getNearestForecastPoint(targetDate) {
  if (!_marketSnapshot?.forecast?.dates?.length) return null;
  const dates = _marketSnapshot.forecast.dates;
  const prices = _marketSnapshot.forecast.predicted || [];
  const target = new Date(targetDate);
  let bestIndex = 0;
  let bestDistance = Infinity;
  dates.forEach((date, index) => {
    const distance = Math.abs(new Date(date) - target);
    if (distance < bestDistance) {
      bestDistance = distance;
      bestIndex = index;
    }
  });
  return { date: dates[bestIndex], price: prices[bestIndex] };
}

function inspectMarketDate() {
  const input = document.getElementById('market-date-input');
  const output = document.getElementById('market-date-output');
  if (!input || !output || !_marketSnapshot?.history) return;
  if (!input.value) {
    output.textContent = 'Pick a date to inspect the nearest historical close or the nearest forecast point.';
    return;
  }
  const historyDates = _marketSnapshot.history.dates || [];
  const forecastDates = _marketSnapshot.forecast?.dates || [];
  const target = new Date(input.value);
  const lastHistorical = historyDates.length ? new Date(historyDates[historyDates.length - 1]) : null;
  const lastForecast = forecastDates.length ? new Date(forecastDates[forecastDates.length - 1]) : null;

  let point = null;
  let seriesLabel = 'Historical';
  let note = '';

  if (lastHistorical && target <= lastHistorical) {
    point = getNearestHistoricalPoint(input.value);
  } else if (lastForecast) {
    point = getNearestForecastPoint(input.value);
    seriesLabel = 'Forecast';
    if (target > lastForecast) {
      note = ` Requested date is beyond the 45-day horizon, so the last available forecast point is shown.`;
    }
  }

  if (!point) {
    output.textContent = 'No price point found near that date.';
    return;
  }
  const current = Number(_marketSnapshot.history.current_price || 0);
  const delta = current && point.price ? ((current - point.price) / point.price) * 100 : null;
  output.innerHTML = `
    <strong>${point.date}</strong> ${seriesLabel === 'Historical' ? 'close was' : 'forecast is'} <strong>${formatMoneyCompact(point.price)}</strong>.
    ${delta === null ? '' : `Current price is <strong>${delta >= 0 ? '+' : ''}${delta.toFixed(1)}%</strong> versus that date.`}
    ${note}
  `;
  updateHoverReadout(point.date, point.price, seriesLabel);
}

function initializeDateInspector(data) {
  const input = document.getElementById('market-date-input');
  const button = document.getElementById('market-date-jump');
  const historyDates = data?.history?.dates || [];
  const forecastDates = data?.forecast?.dates || [];
  if (!input || !button || !historyDates.length) return;
  input.min = historyDates[0];
  input.max = forecastDates[forecastDates.length - 1] || historyDates[historyDates.length - 1];
  input.value = historyDates[Math.max(0, historyDates.length - 30)] || historyDates[historyDates.length - 1];
  button.onclick = inspectMarketDate;
  input.onchange = inspectMarketDate;
  inspectMarketDate();
}

// ─── Live status badge (LIVE / CLOSED + day change) ──────────────────────────
function updateLiveBadge(snap) {
  let badge = document.getElementById('market-status-badge');
  if (!badge) {
    // Create badge next to the current price KPI
    const priceKpi = document.querySelector('.kpi-item');
    if (!priceKpi) return;
    badge = document.createElement('div');
    badge.id = 'market-status-badge';
    badge.style.cssText = 'font-size:11px;font-weight:700;letter-spacing:0.5px;margin-top:4px;display:flex;align-items:center;gap:6px';
    priceKpi.appendChild(badge);
  }

  if (!snap) {
    badge.innerHTML = '';
    return;
  }

  const isOpen = snap.market_open;
  const dotColor = isOpen ? '#10b981' : '#6b7280';
  const statusText = isOpen ? 'NSE LIVE' : 'MARKET CLOSED';
  const pct = snap.pct_change;
  const pctColor = pct > 0 ? '#10b981' : (pct < 0 ? '#ef4444' : '#9ca3af');
  const pctText = pct != null ? `${pct > 0 ? '+' : ''}${pct.toFixed(2)}% today` : '';

  badge.innerHTML = `
    <span style="display:inline-flex;align-items:center;gap:4px;background:rgba(16,185,129,0.1);border:1px solid ${dotColor}40;padding:2px 7px;border-radius:12px;color:${dotColor}">
      <span style="width:6px;height:6px;border-radius:50%;background:${dotColor};display:inline-block${isOpen ? ';animation:pulse 1.5s infinite' : ''};"></span>
      ${statusText}
    </span>
    ${pctText ? `<span style="color:${pctColor};font-size:12px">${pctText}</span>` : ''}
    <span style="color:#4b5563;font-size:10px">${snap.as_of}</span>
  `;
}

// ─── Live price polling ───────────────────────────────────────────────────────
function startLivePolling(ticker) {
  // Clear any previous poller
  if (_livePoller) clearInterval(_livePoller);
  _liveTicker = ticker;

  // Immediate first fetch
  fetchLivePrice(ticker);

  // Then every 60 seconds
  _livePoller = setInterval(() => {
    if (_liveTicker === ticker) fetchLivePrice(ticker);
    else clearInterval(_livePoller);
  }, 60000);
}

async function fetchLivePrice(ticker) {
  try {
    const res = await fetch(`/api/live-price?ticker=${encodeURIComponent(ticker)}`);
    const snap = await res.json();
    if (snap.live_price) {
      document.getElementById('kpi-price').textContent = `₹${snap.live_price.toLocaleString('en-IN')}`;
    }
    updateLiveBadge(snap);
  } catch (e) {
    // silent fail — don't break the UI
  }
}


// ─── Render stock chart (historical + forecast + events) ──────────────────────
function renderStockChart(data) {
  const { history, events, ticker, company } = data;

  document.getElementById('chart-title').textContent =
    `${company} (${ticker}) — NSE Price History 2010 → Today`;

  document.getElementById('market-loading').style.display = 'none';
  const canvas = document.getElementById('marketChart');
  canvas.style.display = 'block';

  // Destroy previous chart instance
  if (marketChartInstance) {
    marketChartInstance.destroy();
    marketChartInstance = null;
  }

  // Historical dataset
  const historicalDataset = {
    label: 'Price (₹)',
    data: history.prices,
    borderColor: '#6366f1',
    backgroundColor: 'rgba(99, 102, 241, 0.08)',
    borderWidth: 1.5,
    fill: true,
    tension: 0.3,
    pointRadius: 0,
    pointHoverRadius: 4,
  };
  const fullLabels = [...history.dates];

  const ctx = canvas.getContext('2d');

  // Build annotation config from events
  const annotations = {};
  if (events && events.length) {
    events.forEach((e, i) => {
      // Find the closest date index in the combined labels array
      const idx = fullLabels.findIndex(d => d >= e.date);
      if (idx === -1) return;
      annotations[`event_${i}`] = {
        type: 'line',
        xMin: idx,
        xMax: idx,
        borderColor: e.color,
        borderWidth: 1.5,
        borderDash: [4, 4],
        label: {
          display: true,
          content: e.label,
          position: 'start',
          backgroundColor: e.color + 'cc',
          color: '#fff',
          font: { size: 9, weight: 'bold' },
          padding: { x: 4, y: 2 },
          rotation: -90,
        }
      };
    });
  }

  // Today line
  const todayIdx = history.dates.length - 1;
  annotations['today'] = {
    type: 'line',
    xMin: todayIdx,
    xMax: todayIdx,
    borderColor: 'rgba(255,255,255,0.2)',
    borderWidth: 1,
    borderDash: [6, 3],
    label: {
      display: true,
      content: 'Today',
      position: 'end',
      backgroundColor: 'rgba(255,255,255,0.1)',
      color: '#9ca3af',
      font: { size: 9 },
    }
  };

  marketChartInstance = new Chart(ctx, {
    type: 'line',
    data: { labels: fullLabels, datasets: [historicalDataset] },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { labels: { color: '#9ca3af' } },
        annotation: { annotations },
        tooltip: {
          backgroundColor: 'rgba(11,15,25,0.95)',
          borderColor: '#374151',
          borderWidth: 1,
          titleColor: '#e5e7eb',
          bodyColor: '#9ca3af',
          callbacks: {
            label: (ctx) => {
              if (ctx.raw === null) return null;
              return ` ₹${Math.round(ctx.raw).toLocaleString('en-IN')}`;
            },
            afterBody: (items) => {
              const point = items.find((item) => item.raw !== null) || items[0];
              if (point && point.raw !== null) {
                setTimeout(() => updateHoverReadout(point.label, point.raw, point.dataset.label), 0);
              }
              return '';
            }
          }
        },
      },
      onHover: (_event, activeElements) => {
        if (!activeElements.length) return;
        const point = activeElements[0];
        const label = fullLabels[point.index];
        const dataset = marketChartInstance.data.datasets[point.datasetIndex];
        const value = dataset.data[point.index];
        if (value !== null && value !== undefined) {
          updateHoverReadout(label, value, dataset.label);
        }
      },
      scales: {
        x: {
          grid: { color: '#1f2937' },
          ticks: {
            color: '#9ca3af',
            maxTicksLimit: 14,
            font: { size: 10 },
            maxRotation: 0,
          }
        },
        y: {
          grid: { color: '#1f2937' },
          ticks: {
            color: '#9ca3af',
            callback: (v) => `₹${Math.round(v).toLocaleString('en-IN')}`,
          }
        }
      }
    }
  });


  // Render event pills below the header
  renderEventPills(events, history.dates);
}

function renderStrategicForecastChart(data) {
  const canvas = document.getElementById('forecastChartCanvas');
  const loading = document.getElementById('forecast-chart-loading');
  if (!canvas || !loading || !data?.history || !data?.forecast) return;

  const historyDates = data.history.dates || [];
  const historyPrices = data.history.prices || [];
  const lookback = 90;
  const recentHistoryDates = historyDates.slice(-lookback);
  const recentHistoryPrices = historyPrices.slice(-lookback);
  const forecastDates = data.forecast.dates || [];
  const rawForecastPredicted = data.forecast.predicted || [];
  const rawForecastUpper = data.forecast.upper || [];
  const rawForecastLower = data.forecast.lower || [];
  const currentPrice = Number(data.history.current_price || recentHistoryPrices[recentHistoryPrices.length - 1] || 0);
  const lastHistoricalPrice = Number(recentHistoryPrices[recentHistoryPrices.length - 1] || currentPrice);
  const anchorDelta = currentPrice - lastHistoricalPrice;
  const forecastPredicted = rawForecastPredicted.map((value) => value + anchorDelta);
  const forecastUpper = rawForecastUpper.map((value) => value + anchorDelta);
  const forecastLower = rawForecastLower.map((value) => value + anchorDelta);

  const combinedLabels = [...recentHistoryDates, ...forecastDates];
  const historyDataset = {
    label: 'Recent History (₹)',
    data: [...recentHistoryPrices, ...new Array(forecastDates.length).fill(null)],
    borderColor: '#6366f1',
    backgroundColor: 'rgba(99, 102, 241, 0.08)',
    borderWidth: 2,
    fill: true,
    tension: 0.28,
    pointRadius: 0,
    pointHoverRadius: 4,
    spanGaps: true,
  };
  const forecastDataset = {
    label: 'Strategic Forecast (₹)',
    data: [...new Array(recentHistoryDates.length).fill(null), ...forecastPredicted],
    borderColor: '#f59e0b',
    borderWidth: 2,
    borderDash: [6, 4],
    fill: false,
    tension: 0.28,
    pointRadius: 0,
    pointHoverRadius: 4,
    spanGaps: true,
  };
  const upperDataset = {
    label: 'Risk Corridor',
    data: [...new Array(recentHistoryDates.length).fill(null), ...forecastUpper],
    borderColor: 'rgba(0,0,0,0)',
    backgroundColor: 'rgba(245, 158, 11, 0.10)',
    borderWidth: 0,
    fill: '+1',
    tension: 0.28,
    pointRadius: 0,
    pointHitRadius: 0,
    spanGaps: true,
  };
  const lowerDataset = {
    label: 'Lower Bound',
    data: [...new Array(recentHistoryDates.length).fill(null), ...forecastLower],
    borderColor: 'rgba(0,0,0,0)',
    borderWidth: 0,
    fill: false,
    tension: 0.28,
    pointRadius: 0,
    pointHitRadius: 0,
    spanGaps: true,
  };

  if (strategicForecastChartInstance) {
    strategicForecastChartInstance.destroy();
    strategicForecastChartInstance = null;
  }

  loading.style.display = 'none';
  canvas.style.display = 'block';

  strategicForecastChartInstance = new Chart(canvas.getContext('2d'), {
    type: 'line',
    data: { labels: combinedLabels, datasets: [historyDataset, forecastDataset, upperDataset, lowerDataset] },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: {
          labels: {
            color: '#9ca3af',
            filter: (item) => !['Risk Corridor', 'Lower Bound'].includes(item.text),
          }
        },
        tooltip: {
          backgroundColor: 'rgba(11,15,25,0.95)',
          borderColor: '#374151',
          borderWidth: 1,
          titleColor: '#e5e7eb',
          bodyColor: '#9ca3af',
          filter: (ctx) => !['Risk Corridor', 'Lower Bound'].includes(ctx.dataset.label),
          callbacks: {
            label: (ctx) => ctx.raw == null ? null : ` ${ctx.dataset.label}: ${formatMoneyCompact(ctx.raw)}`
          }
        }
      },
      scales: {
        x: {
          grid: { color: '#1f2937' },
          ticks: { color: '#9ca3af', maxTicksLimit: 10, font: { size: 10 }, maxRotation: 0 }
        },
        y: {
          grid: { color: '#1f2937' },
          ticks: {
            color: '#9ca3af',
            callback: (v) => `₹${Math.round(v).toLocaleString('en-IN')}`,
          }
        }
      }
    }
  });
}

function renderForecastCards(data) {
  const current = Number(data?.history?.current_price || 0);
  const predicted = data?.forecast?.predicted || [];
  const upper = data?.forecast?.upper || [];
  const lower = data?.forecast?.lower || [];
  const contextBias = Number(data?.forecast?.context_bias || 0);
  const basis = data?.forecast_basis;

  const shortTerm = predicted.length ? predicted[Math.min(6, predicted.length - 1)] : null;
  const baseCase = predicted.length ? predicted[Math.min(29, predicted.length - 1)] : null;
  const bullCase = upper.length ? upper[Math.min(29, upper.length - 1)] : null;
  const riskCase = lower.length ? lower[Math.min(29, lower.length - 1)] : null;

  let biasLabel = 'Balanced setup';
  let biasSub = 'Price trend, company news, and macro signals are aligned neutrally.';
  if (contextBias > 0.18) {
    biasLabel = 'Constructive setup';
    biasSub = 'Company headlines are supportive enough to tilt the forecast upward.';
  } else if (contextBias < -0.18) {
    biasLabel = 'Pressure building';
    biasSub = 'Macro stress and negative headlines are leaning against the trend.';
  }
  if (basis?.drivers?.length) {
    biasSub = `Built from ${basis.window_points} recent points, structural importance ${basis.structural_support ?? '—'}, resilience ${basis.resilience_score ?? '—'}, and current news/macro pressure.`;
  }

  const pageBias = document.getElementById('forecast-page-bias');
  if (pageBias) {
    pageBias.textContent = biasLabel;
    document.getElementById('forecast-page-bias-sub').textContent = biasSub;
    document.getElementById('forecast-page-7d').textContent = formatMoneyCompact(shortTerm);
    document.getElementById('forecast-page-7d-sub').textContent = formatDeltaPct(current, shortTerm);
    document.getElementById('forecast-page-30d').textContent = formatMoneyCompact(baseCase);
    document.getElementById('forecast-page-30d-sub').textContent = formatDeltaPct(current, baseCase);
    document.getElementById('forecast-page-risk').textContent = formatMoneyCompact(riskCase);
    document.getElementById('forecast-page-risk-sub').textContent = bullCase
      ? `Bull case ${formatMoneyCompact(bullCase)} · 30-day lower band`
      : '30-day lower band';
  }
}

function renderStrategicForecast(data) {
  const strategic = data?.strategic_forecast || {};
  const pageHeadline = document.getElementById('forecast-page-headline');
  const pageMethod = document.getElementById('forecast-page-method');
  const pageFactors = document.getElementById('forecast-page-factors');
  const pageAnalogue = document.getElementById('forecast-page-analogue');
  if (!pageHeadline || !pageMethod || !pageFactors || !pageAnalogue) return;

  pageHeadline.textContent = strategic.headline || 'Select a company to see the strategic drivers behind the future price path.';
  pageMethod.textContent = strategic.method || 'Future price is built from price trend, significance, news, and historical event behavior.';

  const factors = strategic.factors || [];
  pageFactors.innerHTML = factors.map((factor) => {
    const color = factor.effect === 'supportive' ? 'var(--low)' : (factor.effect === 'negative' ? 'var(--critical)' : 'var(--energy)');
    const numeric = Number(factor.score || 0);
    const signed = factor.effect === 'negative' ? `-${numeric.toFixed(2)}` : `+${numeric.toFixed(2)}`;
    return `
      <div class="strategic-factor">
        <div class="strategic-factor-head">
          <div class="strategic-factor-label">${factor.label}</div>
          <div class="strategic-factor-score" style="color:${color}">${signed}</div>
        </div>
        <div class="strategic-factor-why">${factor.why || ''}</div>
      </div>
    `;
  }).join('');

  const analogue = strategic.historical_analogue;
  pageAnalogue.innerHTML = analogue
    ? `<strong>Historical analogue:</strong> ${analogue.label} (${analogue.date}) moved the stock from ${formatMoneyCompact(analogue.event_price)} to ${formatMoneyCompact(analogue.after_30d_price)} over the next 30 sessions (${analogue.after_30d_return >= 0 ? '+' : ''}${analogue.after_30d_return}%).`
    : '<strong>Historical analogue:</strong> No strong comparable shock-response pattern was found for this company yet.';
}

function renderForecastInputs(data) {
  const inputsEl = document.getElementById('forecast-page-inputs');
  const basisEl = document.getElementById('forecast-page-basis');
  if (!inputsEl || !basisEl) return;

  const sentiment = data?.news_sentiment || {};
  const gdelt = data?.gdelt_signal || {};
  const events = data?.events || [];
  const basis = data?.forecast_basis || {};
  const headlines = sentiment.headlines || [];
  const topEvent = events[events.length - 1];

  const liveItems = [];
  liveItems.push({
    kicker: 'Feed strength',
    title: sentiment.count
      ? `${sentiment.count} recent headline${sentiment.count > 1 ? 's' : ''} influenced the current company-news score of ${sentiment.score >= 0 ? '+' : ''}${Number(sentiment.score || 0).toFixed(2)}.`
      : 'No strong direct company headline was available, so the model leaned more on strategic fallback events and market structure.',
    meta: sentiment.reason || 'Live news + fallback event memory'
  });
  if (headlines.length) {
    liveItems.push(...headlines.slice(0, 3).map((h) => ({
      kicker: 'Company / sector news',
      title: h.title,
      meta: `${h.source || 'Unknown source'}${h.date ? ` · ${h.date}` : ''}`
    })));
  }
  if (gdelt?.top_headline) {
    liveItems.push({
      kicker: 'Macro / geopolitical signal',
      title: gdelt.top_headline,
      meta: `${gdelt.signal || 'neutral'} · ${gdelt.event_count || 0} events over 3 days`
    });
  }
  if (topEvent) {
    liveItems.push({
      kicker: 'Historical analogue in model',
      title: `${topEvent.label} remains part of the event memory for this company.`,
      meta: topEvent.date || ''
    });
  }
  if (!liveItems.length) {
    liveItems.push({
      kicker: 'Live inputs',
      title: 'No strong live headlines were available at this moment, so the model is leaning more on price behavior, company significance, and historical analogue.',
      meta: 'Feed quiet / rate-limited fallback mode'
    });
  }

  inputsEl.innerHTML = `<div class="forecast-input-list">${liveItems.map((item) => `
    <div class="forecast-input-item">
      <div class="forecast-input-kicker">${item.kicker}</div>
      <div class="forecast-input-title">${item.title}</div>
      <div class="forecast-input-meta">${item.meta}</div>
    </div>
  `).join('')}</div>`;

  const basisItems = [
    basis.window_points ? `<strong>Price memory:</strong> built from the last ${basis.window_points} market points, not just today's move.` : null,
    basis.structural_support !== undefined ? `<strong>Company significance:</strong> structural support score is ${basis.structural_support}, reflecting national importance and replacement difficulty.` : null,
    basis.resilience_score !== undefined ? `<strong>Shock recovery:</strong> resilience score is ${basis.resilience_score}, so the model checks whether this stock historically bounces back after stress.` : null,
    typeof data?.forecast?.context_bias === 'number' ? `<strong>Live adjustment:</strong> current news + macro bias is ${data.forecast.context_bias >= 0 ? '+' : ''}${data.forecast.context_bias.toFixed(2)}, which nudges the base path up or down.` : null,
    `<strong>Risk band:</strong> the lower and upper bands are bounded scenarios, not wild crash / moonshot guesses.`
  ].filter(Boolean);

  basisEl.innerHTML = `<div class="forecast-basis-list">${basisItems.map((item) => `
    <div class="forecast-basis-item">${item}</div>
  `).join('')}</div>`;
}

// ─── Event Pills (coloured badges above chart) ────────────────────────────────
function renderEventPills(events, historicalDates) {
  const container = document.getElementById('event-pills');
  if (!events || !events.length) { container.innerHTML = ''; return; }

  container.innerHTML = events.map(e => `
    <span class="event-pill" style="border-color:${e.color}; color:${e.color}">
      <span style="display:inline-block;width:6px;height:6px;border-radius:50%;background:${e.color};margin-right:5px;"></span>
      ${e.label} · ${e.date}
    </span>
  `).join('');
}

// ─── Render News Sentiment panel ─────────────────────────────────────────────
function renderNewsPanel(sentiment) {
  const el = document.getElementById('twitter-panel');
  if (!sentiment) { el.innerHTML = '<div class="loading">No data</div>'; return; }

  const score = sentiment.score || 0;
  const scorePercent = Math.round((score + 1) * 50);
  const barColor = score > 0.1 ? 'var(--low)' : (score < -0.1 ? 'var(--critical)' : 'var(--energy)');
  const textColor = barColor;

  let html = `
    <div class="sentiment-score" style="color:${textColor}">${score >= 0 ? '+' : ''}${score.toFixed(2)}</div>
    <div class="sentiment-label" style="color:${textColor}">${sentiment.label || 'Neutral'}</div>
    <div class="sentiment-bar-bg">
      <div class="sentiment-bar" style="width:${scorePercent}%; background:${barColor}"></div>
    </div>
    <div style="font-size:11px; color: var(--text-muted); margin-bottom:10px">Forecast context is using ${sentiment.count || 0} recent company articles.</div>
  `;

  if (sentiment.reason) {
    html += `<div class="tweet-sample" style="border-color:var(--energy); color:var(--energy)">⚙ ${sentiment.reason}</div>`;
  }

  const headlines = sentiment.headlines || [];
  if (headlines.length > 0) {
    html += headlines.map(h => {
      const sentColor = h.sentiment === 'bullish' ? 'var(--low)' : (h.sentiment === 'bearish' ? 'var(--critical)' : 'var(--text-muted)');
      const sentIcon = h.sentiment === 'bullish' ? '▲' : (h.sentiment === 'bearish' ? '▼' : '—');
      return `
        <div class="news-headline">
          <span class="news-sentiment-dot" style="color:${sentColor}">${sentIcon}</span>
          <div>
            <a href="${h.url}" target="_blank" class="news-title">${h.title}</a>
            <div class="news-source">${h.source}</div>
            <div class="news-date">${h.date || ''}</div>
          </div>
        </div>
      `;
    }).join('');
  }
  if (headlines.length === 0) {
    html += `<div class="tweet-sample">No recent company-specific headlines were found. Try another stock or check if the feed is temporarily quiet.</div>`;
  }

  el.innerHTML = html;
}


// ─── Render GDELT panel ───────────────────────────────────────────────────────
function renderGDELTPanel(gdelt, sector) {
  const el = document.getElementById('gdelt-panel');
  if (!gdelt) { el.innerHTML = '<div class="loading">No signal</div>'; return; }

  const signalColors = { elevated: '#ef4444', moderate: '#f59e0b', low: '#10b981', neutral: '#6b7280' };
  const color = signalColors[gdelt.signal] || '#6b7280';

  let html = `
    <div class="gdelt-signal-row">
      <span class="gdelt-signal-dot" style="background:${color}"></span>
      <span style="color:${color}; text-transform: uppercase; font-weight:700; font-size:13px">${gdelt.signal || 'Neutral'}</span>
      <span style="color:var(--text-muted); font-size:11px; margin-left:8px">${gdelt.event_count} events (3d)</span>
    </div>
    <div style="font-size:11px;color:var(--text-muted);margin-bottom:8px">Sector: <span style="text-transform:capitalize;color:var(--text-dim)">${sector}</span></div>
  `;

  if (gdelt.top_headline) {
    html += `<div class="gdelt-headline">📰 ${gdelt.top_headline}</div>`;
  }

  el.innerHTML = html;
}

// ─── Render Events panel ──────────────────────────────────────────────────────
function renderEventsPanel(events) {
  const el = document.getElementById('events-panel');
  if (!events || !events.length) {
    el.innerHTML = '<div class="loading">No major events annotated</div>';
    return;
  }

  el.innerHTML = events.map(e => `
    <div class="event-row">
      <div class="event-dot" style="background:${e.color}"></div>
      <div class="event-date">${e.date}</div>
      <div class="event-label">${e.label}</div>
    </div>
  `).join('');
}

// ─── Initialize on view switch ────────────────────────────────────────────────
window.initMarketIntelligence = function () {
  populateMarketSelect();
};

window.initStrategicForecast = function () {
  populateMarketSelect();
};

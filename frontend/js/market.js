/**
 * Market Intelligence JS Module
 */

let marketChartInstance = null;
let _liveTicker = null;         // currently selected ticker
let _livePoller = null;         // setInterval handle

// ─── Populate company dropdown from globalData ───────────────────────────────
function populateMarketSelect() {
  const sel = document.getElementById('market-company-select');
  if (!globalData.companies || !sel) return;

  const sorted = [...globalData.companies].sort((a, b) => a.name.localeCompare(b.name));
  sel.innerHTML = '<option value="">— Select a company —</option>';
  sorted.forEach(c => {
    const opt = document.createElement('option');
    opt.value = c.ticker;
    opt.dataset.name = c.name;
    opt.dataset.sector = c.sector;
    opt.textContent = `${c.name} (${c.ticker})`;
    sel.appendChild(opt);
  });

  sel.addEventListener('change', () => {
    const opt = sel.selectedOptions[0];
    if (!opt.value) return;
    loadMarketData(opt.value, opt.dataset.name || '', opt.dataset.sector || '');
  });
}

// ─── Main loader ─────────────────────────────────────────────────────────────
async function loadMarketData(ticker, companyName, sector) {
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
    const data = await res.json();

    if (data.error) throw new Error(data.error);

    renderStockChart(data);
    renderKPIs(data);
    renderNewsPanel(data.news_sentiment);
    renderGDELTPanel(data.gdelt_signal, sector);
    renderEventsPanel(data.events);

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
  const { history, forecast, events, ticker, company } = data;

  document.getElementById('chart-title').textContent =
    `${company} (${ticker}) — NSE Price History 2010 → Today + 45-Day ML Forecast`;

  document.getElementById('market-loading').style.display = 'none';
  const canvas = document.getElementById('marketChart');
  canvas.style.display = 'block';

  // Destroy previous chart instance
  if (marketChartInstance) {
    marketChartInstance.destroy();
    marketChartInstance = null;
  }

  // Build labels (all historical + forecast)
  const allLabels = [...history.dates];
  const forecastDates = forecast.dates || [];
  const allForecastLabels = forecastDates;

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

  // Forecast dataset
  const forecastDataset = {
    label: 'ML Forecast (₹)',
    data: new Array(history.prices.length).fill(null).concat(forecast.predicted || []),
    borderColor: '#f59e0b',
    borderWidth: 2,
    borderDash: [6, 4],
    fill: false,
    tension: 0.3,
    pointRadius: 0,
    pointHoverRadius: 4,
    spanGaps: true,
  };

  // Upper confidence band
  const upperDataset = {
    label: 'Confidence High',
    data: new Array(history.prices.length).fill(null).concat(forecast.upper || []),
    borderColor: 'rgba(245, 158, 11, 0.3)',
    backgroundColor: 'rgba(245, 158, 11, 0.08)',
    borderWidth: 1,
    borderDash: [2, 3],
    fill: '+1',
    tension: 0.3,
    pointRadius: 0,
    spanGaps: true,
  };

  // Lower confidence band
  const lowerDataset = {
    label: 'Confidence Low',
    data: new Array(history.prices.length).fill(null).concat(forecast.lower || []),
    borderColor: 'rgba(245, 158, 11, 0.3)',
    fill: false,
    tension: 0.3,
    pointRadius: 0,
    spanGaps: true,
    borderWidth: 1,
    borderDash: [2, 3],
  };

  const fullLabels = [...history.dates, ...forecastDates];

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
    data: { labels: fullLabels, datasets: [historicalDataset, upperDataset, lowerDataset, forecastDataset] },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: {
          labels: {
            color: '#9ca3af',
            filter: (item) => !['Confidence High', 'Confidence Low'].includes(item.text),
          }
        },
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
            }
          }
        },
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
    <div style="font-size:11px; color: var(--text-muted); margin-bottom:10px">Based on ${sentiment.count || 0} recent articles</div>
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
          </div>
        </div>
      `;
    }).join('');
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

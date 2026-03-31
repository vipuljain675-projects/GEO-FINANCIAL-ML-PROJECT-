// State
let globalData = {};
let riskData = [];
let portfolioChatHistory = [];

// DOM Elements
const views = document.querySelectorAll('.view');
const navItems = document.querySelectorAll('.nav-item');
const viewTitle = document.getElementById('view-title');
const viewSub = document.getElementById('view-sub');

// View configurations
const viewConfigs = {
  'overview': { title: 'Strategic Overview', sub: 'National Critical Infrastructure Analysis' },
  'network': { title: 'Dependency Network', sub: 'Inter-company Critical Links' },
  'threat-sim': { title: 'Scenario Engine', sub: 'AI Gen. Actionable Scenarios' },
  'risk': { title: 'Market Intelligence', sub: 'NSE Stock History · ML Forecast · Twitter + GDELT Signals' },
  'analyst': { title: 'Sentinel AI Analyst', sub: 'Encrypted Strategic Intelligence' },
  'portfolio': { title: 'Personal Advisor', sub: 'Individualized Wealth Risk & Strategic Advisory' }
};

// --- AUTH HELPERS ---
function getAuthHeaders() {
  const token = localStorage.getItem('sentinel_token');
  if (token) return { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' };
  return { 'Content-Type': 'application/json' };
}

function isGuest() {
  return localStorage.getItem('sentinel_guest') === 'true' && !localStorage.getItem('sentinel_token');
}

function updatePortfolioAccess() {
  const portfolioNav = document.querySelector('.nav-item[data-view="portfolio"]');
  if (portfolioNav) {
    portfolioNav.classList.toggle('hidden', isGuest());
  }
}

function populatePortfolioTickerSelect() {
  const sel = document.getElementById('port-ticker');
  if (!sel || !globalData.companies) return;
  const currentValue = sel.value;
  const sorted = [...globalData.companies].sort((a, b) => a.name.localeCompare(b.name));
  sel.innerHTML = '<option value="">— Select tracked company —</option>';
  sorted.forEach(company => {
    const opt = document.createElement('option');
    opt.value = company.ticker;
    opt.textContent = `${company.name} (${company.ticker})`;
    sel.appendChild(opt);
  });
  if (currentValue) sel.value = currentValue;
}

// Initialize
async function init() {
  updateTime();
  setInterval(updateTime, 1000);
  updatePortfolioAccess();
  
  // Navigation
  navItems.forEach(item => {
    item.addEventListener('click', () => {
      sentinelAudio.playTactical(400, 0.05);
      switchView(item.dataset.view);
      
      if (item.dataset.view === 'risk' && typeof initMarketIntelligence === 'function') {
        setTimeout(initMarketIntelligence, 100);
      }
      if (item.dataset.view === 'portfolio') {
        initPortfolio();
      }
    });
  });

  // Export init for splash screen finish
  window.SENTINEL_INIT = () => {
    switchView('overview');
    initPortfolio(); // Pre-fetch if logged in
  };

  try {
    document.getElementById('status-text').innerText = 'Fetching Intelligence...';
    
    const [compRes, topRes, secRes] = await Promise.all([
      fetch('/api/companies'),
      fetch('/api/top-critical?n=5'),
      fetch('/api/sector-summary')
    ]);

    globalData.companies = (await compRes.json()).companies;
    globalData.topCritical = (await topRes.json()).nodes;
    globalData.sectorSummary = (await secRes.json()).sectors;

    document.getElementById('status-text').innerText = 'Secure Link Established';
    document.querySelector('.status-dot').style.background = 'var(--low)';

    populateOverview();
    populateSimSelect();
    populatePortfolioTickerSelect();

  } catch (err) {
    console.error(err);
    document.getElementById('status-text').innerText = 'Connection Failed';
    document.querySelector('.status-dot').style.background = 'var(--critical)';
  }
}

// --- PORTFOLIO LOGIC ---
async function initPortfolio() {
  const container = document.getElementById('view-portfolio');
  const authStatus = document.getElementById('portfolio-auth-status');
  const portfolioUserName = document.getElementById('portfolio-user-name');
  if (!container || !authStatus) return;
  if (portfolioUserName) {
    portfolioUserName.textContent = localStorage.getItem('sentinel_user_name') || 'Guest';
  }
  
  if (isGuest()) {
    authStatus.innerHTML = '<span class="pulse-dot" style="background:#f59e0b; box-shadow:0 0 10px #f59e0b"></span> GUEST ACCESS (ADVISORY RESTRICTED)';
    authStatus.style.borderColor = 'rgba(245, 158, 11, 0.3)';
    authStatus.style.color = '#f59e0b';
    document.getElementById('holdings-body').innerHTML = '<tr><td colspan="5" style="text-align:center; padding:40px; color:rgba(255,255,255,0.3)">Identity Verification Required for Personal Advisor Features</td></tr>';
    document.getElementById('btn-add-to-port').disabled = true;
    document.getElementById('btn-run-advisor').disabled = true;
    return;
  }

  authStatus.innerHTML = '<span class="pulse-dot"></span> SECURE UPLINK ACTIVE';
  authStatus.style.borderColor = 'rgba(16, 185, 129, 0.3)';
  authStatus.style.color = '#10b981';
  document.getElementById('btn-add-to-port').disabled = false;
  document.getElementById('btn-run-advisor').disabled = false;
  fetchHoldings();
}

async function fetchHoldings() {
  try {
    const res = await fetch('/api/portfolio', { headers: getAuthHeaders() });
    if (!res.ok) throw new Error('Auth failed');
    const items = await res.json();
    renderHoldings(items);
    renderPortfolioSummaryFromItems(items);
    return items;
  } catch (e) {
    console.error(e);
    return [];
  }
}

async function renderHoldings(items) {
  const body = document.getElementById('holdings-body');
  if (!items || items.length === 0) {
    body.innerHTML = '<tr><td colspan="5" style="text-align:center; padding:40px; color:rgba(255,255,255,0.2)">No strategic assets registered.</td></tr>';
    return;
  }

  let html = '';
  for (const item of items) {
    // Fetch live price for valuation
    let price = '---';
    let val = '---';
    try {
      const pRes = await fetch(`/api/live-price?ticker=${item.ticker}`);
      const pData = await pRes.json();
      if (pData.live_price) {
        price = '₹' + pData.live_price;
        val = '₹' + (pData.live_price * item.quantity).toLocaleString();
      }
    } catch(e) {}

    html += `
      <tr>
        <td><strong>${item.ticker}</strong></td>
        <td>${item.quantity}</td>
        <td>₹${item.purchase_price || '---'}</td>
        <td>${item.purchase_date || '---'}</td>
        <td>${price}</td>
        <td class="valuation-cell">${val}</td>
        <td><button class="delete-btn" onclick="removeFromPortfolio('${item.ticker}')">🗑</button></td>
      </tr>
    `;
  }
  body.innerHTML = html;
}

function formatMoney(value) {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  return '₹' + Number(value).toLocaleString('en-IN', { maximumFractionDigits: 2 });
}

function formatPct(value) {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  const sign = value > 0 ? '+' : '';
  return `${sign}${value.toFixed(2)}%`;
}

function renderPortfolioSummaryFromItems(items) {
  document.getElementById('summary-invested').textContent = '—';
  document.getElementById('summary-current').textContent = items && items.length ? 'Live sync via scan' : '—';
  document.getElementById('summary-pnl').textContent = items && items.length ? 'Run scan' : '—';
  document.getElementById('summary-risk').textContent = items && items.length ? 'Run scan' : '—';
}

function renderPortfolioSummary(summary) {
  document.getElementById('summary-invested').textContent = formatMoney(summary.total_invested);
  document.getElementById('summary-current').textContent = formatMoney(summary.current_value);
  document.getElementById('summary-pnl').textContent = summary.total_pnl === null || summary.total_pnl === undefined
    ? '—'
    : `${formatMoney(summary.total_pnl)} (${formatPct(summary.total_pnl_pct)})`;
  document.getElementById('summary-risk').textContent = summary.highest_risk || '—';
}

function renderDecisionCards(holdings) {
  const container = document.getElementById('portfolio-decision-cards');
  if (!container) return;
  if (!holdings || holdings.length === 0) {
    container.innerHTML = '<div class="loading">Add holdings and run the scan to generate action cards.</div>';
    return;
  }
  container.innerHTML = holdings.map(holding => `
    <article class="decision-card">
      <div class="decision-card-head">
        <div>
          <div class="decision-card-title">${holding.company_name}</div>
          <div class="decision-card-meta">${holding.ticker} · ${holding.sector.toUpperCase()} · ${holding.role}</div>
        </div>
        <span class="decision-badge ${holding.action.replace(' ', '_')}">${holding.action.replace('_', ' ')}</span>
      </div>
      <div class="decision-metrics">
        <div class="decision-metric">
          <span class="decision-metric-label">Buy</span>
          <span class="decision-metric-value">${formatMoney(holding.purchase_price)} on ${holding.purchase_date || '—'}</span>
        </div>
        <div class="decision-metric">
          <span class="decision-metric-label">Current</span>
          <span class="decision-metric-value">${formatMoney(holding.live_price)}</span>
        </div>
        <div class="decision-metric">
          <span class="decision-metric-label">P/L</span>
          <span class="decision-metric-value">${formatMoney(holding.pnl_value)} / ${formatPct(holding.pnl_pct)}</span>
        </div>
        <div class="decision-metric">
          <span class="decision-metric-label">Portfolio Weight</span>
          <span class="decision-metric-value">${formatPct(holding.concentration_pct)}</span>
        </div>
      </div>
      <div class="decision-rationale">${holding.rationale}</div>
      <div class="decision-thesis">${holding.thesis}</div>
    </article>
  `).join('');
}

function appendPortfolioChatMessage(role, text) {
  const container = document.getElementById('portfolio-chat-messages');
  if (!container) return;
  const node = document.createElement('div');
  node.className = `portfolio-chat-msg ${role}`;
  node.innerHTML = `
    <div class="portfolio-chat-role">${role === 'user' ? 'YOU' : 'SENTINEL'}</div>
    <div class="portfolio-chat-bubble">${marked.parse(text)}</div>
  `;
  container.appendChild(node);
  container.scrollTop = container.scrollHeight;
}

async function sendPortfolioChatMessage(prefillText) {
  const input = document.getElementById('portfolio-chat-input');
  const sendBtn = document.getElementById('portfolio-chat-send');
  const text = (prefillText || input?.value || '').trim();
  if (!text) return;

  appendPortfolioChatMessage('user', text);
  if (input) input.value = '';
  if (sendBtn) sendBtn.disabled = true;

  try {
    const res = await fetch('/api/personal/chat', {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify({ message: text, history: portfolioChatHistory })
    });
    const data = await res.json();
    const reply = data.response || 'No response from portfolio advisor.';
    appendPortfolioChatMessage('assistant', reply);
    portfolioChatHistory.push({ role: 'user', content: text });
    portfolioChatHistory.push({ role: 'assistant', content: reply });
    if (portfolioChatHistory.length > 20) portfolioChatHistory = portfolioChatHistory.slice(-20);
  } catch (e) {
    appendPortfolioChatMessage('assistant', `Comm-link failure: ${e.message}`);
  } finally {
    if (sendBtn) sendBtn.disabled = false;
    if (input) input.focus();
  }
}

window.removeFromPortfolio = async (ticker) => {
  if (!confirm(`Confirm de-registration of ${ticker}?`)) return;
  try {
    await fetch(`/api/portfolio/${ticker}`, { method: 'DELETE', headers: getAuthHeaders() });
    fetchHoldings();
  } catch (e) { alert(e); }
};

document.getElementById('btn-add-to-port')?.addEventListener('click', async () => {
  const ticker = document.getElementById('port-ticker').value;
  const qty = parseFloat(document.getElementById('port-qty').value);
  const buyPrice = parseFloat(document.getElementById('port-buy-price').value);
  const buyDate = document.getElementById('port-buy-date').value;
  if (!ticker || isNaN(qty)) { alert('Invalid asset markers'); return; }

  try {
    const res = await fetch('/api/portfolio', {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify({
        ticker: ticker,
        quantity: qty,
        purchase_price: Number.isNaN(buyPrice) ? null : buyPrice,
        purchase_date: buyDate || null
      })
    });
    if (res.ok) {
      document.getElementById('port-ticker').value = '';
      document.getElementById('port-qty').value = '';
      document.getElementById('port-buy-price').value = '';
      document.getElementById('port-buy-date').value = '';
      fetchHoldings();
    }
  } catch (e) { alert(e); }
});

document.getElementById('btn-refresh-port')?.addEventListener('click', fetchHoldings);

document.getElementById('btn-run-advisor')?.addEventListener('click', async () => {
  const container = document.getElementById('advisor-result-container');
  const text = document.getElementById('advisor-text');
  const btn = document.getElementById('btn-run-advisor');

  container.classList.remove('hidden');
  document.querySelector('.advisor-loading').style.display = 'flex';
  text.innerHTML = '';
  btn.disabled = true;

  try {
    const res = await fetch('/api/personal/analyze', { method: 'POST', headers: getAuthHeaders() });
    const data = await res.json();
    document.querySelector('.advisor-loading').style.display = 'none';
    renderPortfolioSummary(data.summary || {});
    renderDecisionCards(data.holdings || []);
    
    // Typewriter effect for advisor
    let i = 0;
    const fullText = data.response || 'No advisor response available.';
    function tick() {
      if (i < fullText.length) {
        text.innerHTML = marked.parse(fullText.substring(0, i + 3));
        i += 3;
        setTimeout(tick, 5);
      } else {
        btn.disabled = false;
      }
    }
    tick();

  } catch (e) {
    alert(e);
    btn.disabled = false;
  }
});

document.getElementById('portfolio-chat-send')?.addEventListener('click', () => sendPortfolioChatMessage());
document.getElementById('portfolio-chat-input')?.addEventListener('keydown', (e) => {
  if (e.key === 'Enter') sendPortfolioChatMessage();
});
document.querySelectorAll('.portfolio-chat-prompt').forEach(btn => {
  btn.addEventListener('click', () => sendPortfolioChatMessage(btn.dataset.prompt || ''));
});

function switchView(viewId) {
  if (viewId === 'portfolio' && isGuest()) {
    return;
  }
  navItems.forEach(n => n.classList.remove('active'));
  const navItem = document.querySelector(`.nav-item[data-view="${viewId}"]`);
  if (navItem) navItem.classList.add('active');
  
  views.forEach(v => v.classList.remove('active'));
  const targetView = document.getElementById(`view-${viewId}`);
  if (targetView) targetView.classList.add('active');
  
  const config = viewConfigs[viewId];
  if (config) {
    viewTitle.innerText = config.title;
    viewSub.innerText = config.sub;
  }

  if (viewId === 'network' && window.initGraph) {
    window.initGraph();
  }
  if (viewId === 'risk') {
    loadMLIntelligence();
  }
}

function updateTime() {
  const now = new Date();
  const ts = document.getElementById('timestamp');
  if (ts) ts.innerText = now.toISOString().replace('T', ' ').substring(0, 19) + ' IST';
}

function getSectorColor(sector) {
  const colors = {
    defense: 'var(--defense)',
    energy: 'var(--energy)',
    finance: 'var(--finance)',
    logistics: 'var(--logistics)'
  };
  return colors[sector] || '#fff';
}

function populateOverview() {
  const statTotal = document.getElementById('stat-total');
  if (statTotal) statTotal.innerText = globalData.companies.length;
  
  const statCritical = document.getElementById('stat-critical');
  if (statCritical) statCritical.innerText = globalData.topCritical.length;
  
  let totalEdges = 0;
  globalData.companies.forEach(c => totalEdges += (c.dependencies ? c.dependencies.length : 0));
  const statEdges = document.getElementById('stat-edges');
  if (statEdges) statEdges.innerText = totalEdges;

  let gdpLoss = 0;
  globalData.topCritical.forEach(n => {
    n.threats.forEach(t => gdpLoss += (t.loss_estimate_bn || 0));
  });
  const statGdp = document.getElementById('stat-gdp');
  if (statGdp) statGdp.innerText = '$' + gdpLoss.toFixed(1) + 'B';

  const tcList = document.getElementById('top-critical-list');
  if (tcList) {
    const tcHtml = globalData.topCritical.map((n, i) => `
      <div class="node-row">
        <div class="node-rank">0${i+1}</div>
        <div class="node-dot" style="background:${getSectorColor(n.sector)}"></div>
        <div class="node-info">
          <div class="node-name">${n.name} <span style="font-size:10px; color:var(--text-muted)">${n.ticker}</span></div>
          <div class="node-sub">${n.role}</div>
        </div>
        <div class="vuln-bar-wrap">
          <div class="vuln-bar-bg">
            <div class="vuln-bar" style="width:${n.vulnerability_score}%; background:var(--critical)"></div>
          </div>
          <div class="vuln-score">${n.vulnerability_score}/100</div>
        </div>
      </div>
    `).join('');
    tcList.innerHTML = tcHtml;
  }

  const sbList = document.getElementById('sector-breakdown');
  if (sbList) {
    const maxVuln = Math.max(...globalData.sectorSummary.map(s => s.total_potential_loss_bn));
    const sbHtml = globalData.sectorSummary.map(s => {
      const width = (s.total_potential_loss_bn / maxVuln) * 100;
      return `
        <div class="sector-row">
          <div class="sector-top">
            <div class="sector-name" style="color:${getSectorColor(s.sector)}">${s.sector.toUpperCase()}</div>
            <div class="sector-meta">$${s.total_potential_loss_bn.toFixed(1)}B exposure • ${s.company_count} assets</div>
          </div>
          <div class="sector-bar-bg">
            <div class="sector-bar" style="width:${width}%; background:${getSectorColor(s.sector)}"></div>
          </div>
        </div>
      `;
    }).join('');
    sbList.innerHTML = sbHtml;
  }

  loadThreatActors();
}

async function loadThreatActors() {
  const talist = document.getElementById('threat-actors-list');
  if (!talist) return;
  try {
    const res = await fetch('/api/companies');
    const data = await res.json();
    const actors = data.threat_actors || [];
    
    if (actors.length === 0) {
      talist.innerHTML = '<div class="loading">No actor data</div>';
      return;
    }

    const html = actors.map(a => `
      <div class="actor-card">
        <div class="actor-badge" style="background:var(--bg3)">${a.type}</div>
        <div class="actor-info">
          <div class="actor-name">${a.name}</div>
          <div class="actor-methods">Vectors: ${a.methods.join(', ')}</div>
          <div class="actor-targets">
            ${a.primary_targets.map(t => `<span class="tag ${t}">${t}</span>`).join('')}
          </div>
        </div>
      </div>
    `).join('');
    talist.innerHTML = html;
  } catch(e) { console.error(e); }
}

// --- ML INTELLIGENCE ---
let mlForecastLoaded = false;
async function loadMLIntelligence() {
  if (mlForecastLoaded) return;
  mlForecastLoaded = true;

  try {
    const [forecastRes, clustersRes] = await Promise.all([
      fetch('/api/ml/forecast'),
      fetch('/api/ml/clusters')
    ]);
    const forecastData = await forecastRes.json();
    const clusterData = await clustersRes.json();
    
    renderForecastChart(forecastData);
    renderClusterMap(clusterData.clusters);
  } catch(e) { console.error("ML Error:", e); }
}

function renderForecastChart(data) {
  const el = document.getElementById('forecastChart');
  if (!el) return;
  const ctx = el.getContext('2d');
  
  const datasets = [
    { label: 'Defense', data: data.series.defense, borderColor: '#ef4444', backgroundColor: 'rgba(239, 68, 68, 0.1)', tension: 0.4, fill: true },
    { label: 'Energy', data: data.series.energy, borderColor: '#eab308', backgroundColor: 'rgba(234, 179, 8, 0.1)', tension: 0.4, fill: true },
    { label: 'Finance', data: data.series.finance, borderColor: '#3b82f6', backgroundColor: 'rgba(59, 130, 246, 0.1)', tension: 0.4, fill: true },
    { label: 'Logistics', data: data.series.logistics, borderColor: '#10b981', backgroundColor: 'rgba(16, 185, 129, 0.1)', tension: 0.4, fill: true }
  ];

  new Chart(ctx, {
    type: 'line',
    data: { labels: data.dates, datasets: datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { labels: { color: '#9ca3af' } }
      },
      scales: {
        y: { beginAtZero: true, max: 100, title: { display: true, text: 'Threat Probability %', color: '#9ca3af' }, grid: { color: '#1f2937' }, ticks: { color: '#9ca3af'} },
        x: { grid: { color: '#1f2937' }, ticks: { color: '#9ca3af', maxTicksLimit: 10 } }
      }
    }
  });
}

function renderClusterMap(nodes) {
  const container = document.getElementById('cluster-map');
  if (!container) return;
  container.innerHTML = ''; 
  
  if (!nodes || nodes.length === 0) return;

  const w = container.clientWidth;
  const h = container.clientHeight;
  const svg = d3.select('#cluster-map').append('svg').attr('width', '100%').attr('height', '100%');
  const xExtent = d3.extent(nodes, d => d.plot_x || 0);
  const yExtent = d3.extent(nodes, d => d.plot_y || 0);
  const padding = 40;
  const xScale = d3.scaleLinear().domain([xExtent[0]-1, xExtent[1]+1]).range([padding, w-padding]);
  const yScale = d3.scaleLinear().domain([yExtent[0]-1, yExtent[1]+1]).range([h-padding, padding]);
  
  svg.append('g').attr('class', 'grid')
     .selectAll('line').data(xScale.ticks(10)).enter().append('line')
     .attr('x1', d=>xScale(d)).attr('x2', d=>xScale(d)).attr('y1', padding).attr('y2', h-padding)
     .attr('stroke', '#1f2937').attr('stroke-width', 1).attr('stroke-dasharray', '2,2');
     
  svg.append('g').attr('class', 'grid')
     .selectAll('line').data(yScale.ticks(10)).enter().append('line')
     .attr('y1', d=>yScale(d)).attr('y2', d=>yScale(d)).attr('x1', padding).attr('x2', w-padding)
     .attr('stroke', '#1f2937').attr('stroke-width', 1).attr('stroke-dasharray', '2,2');

  let tooltip = d3.select('body').select('.cluster-tooltip');
  if (tooltip.empty()) {
      tooltip = d3.select('body').append('div').attr('class', 'cluster-tooltip');
  }

  const nodeGroups = svg.selectAll('.cnode').data(nodes).enter().append('g')
     .attr('transform', d => `translate(${xScale(d.plot_x || 0)}, ${yScale(d.plot_y || 0)})`)
     .attr('class', 'cnode');
     
  nodeGroups.append('circle')
     .attr('r', 6)
     .attr('fill', d => getSectorColor(d.sector))
     .attr('stroke', '#0b0f19').attr('stroke-width', 1.5)
     .on('mouseover', function(event, d) {
        d3.select(this).attr('stroke', '#fff').attr('stroke-width', 2).attr('r', 8);
        tooltip.style('opacity', 1)
               .html(`<strong>${d.name} (${d.ticker})</strong><br><span style="color:${getSectorColor(d.sector)};text-transform:capitalize">${d.sector}</span><br>Vuln Score: ${d.vulnerability_score}<br>Cluster: ${d.cluster_name}`);
     })
     .on('mousemove', function(event) {
        tooltip.style('left', (event.pageX + 15) + 'px')
               .style('top', (event.pageY - 15) + 'px');
     })
     .on('mouseout', function(event, d) {
        d3.select(this).attr('stroke', '#0b0f19').attr('stroke-width', 1.5).attr('r', 6);
        tooltip.style('opacity', 0);
     });
     
  const clusterNames = [...new Set(nodes.map(n => n.cluster_name))].filter(Boolean);
  const legend = svg.append('g').attr('transform', 'translate(10, 10)');
  clusterNames.forEach((name, i) => {
     legend.append('text').text(`Cluster ${i+1}: ${name}`).attr('y', i*16).attr('font-size', '11px').attr('fill', 'var(--accent)');
  });
}

// --- SCENARIO ENGINE ---
function populateSimSelect() {
  const select = document.getElementById('sim-target');
  if (!select) return;
  let opts = '<option value="">— Select company —</option>';
  if(globalData.companies) {
    const sorted = [...globalData.companies].sort((a,b) => a.name.localeCompare(b.name));
    sorted.forEach(c => {
      opts += `<option value="${c.ticker}">${c.name} (${c.ticker})</option>`;
    });
  }
  select.innerHTML = opts;
}

document.getElementById('run-sim-btn')?.addEventListener('click', async () => {
  const ticker = document.getElementById('sim-target').value;
  const vector = document.getElementById('sim-vector').value || "Hostile Kinetic and Cyber Degradation";
  if (!ticker) { alert('Select a company first.'); return; }

  const btn = document.getElementById('run-sim-btn');
  btn.disabled = true;
  btn.innerText = 'GENERATING SCENARIO...';
  document.getElementById('sim-results').classList.add('hidden');

  try {
    const res = await fetch('/api/ml/scenario', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ticker: ticker, vector: vector })
    });
    const data = await res.json();
    if (data.error) throw new Error(data.error);
    renderScenarioResults(data);
  } catch (err) { alert('Scenario failed: ' + err.message); } finally {
    btn.disabled = false;
    btn.innerText = 'GENERATE SCENARIO';
  }
});

function renderScenarioResults(data) {
  document.getElementById('sim-results').classList.remove('hidden');
  document.getElementById('sim-summary-cards').innerHTML = `
    <div class="stat-card critical">
      <div class="stat-label">Primary Target</div>
      <div class="stat-value" style="font-size:1.2rem">${data.target}</div>
      <div class="stat-sub">${data.vector}</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Downstream Impact</div>
      <div class="stat-value">${data.downstream_impact_count}</div>
      <div class="stat-sub">Crippled assets</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Simulated Chain Loss</div>
      <div class="stat-value">$${data.simulated_loss_bn}B</div>
      <div class="stat-sub">Total Estimated Exposure</div>
    </div>
  `;
  document.getElementById('sim-intelligence').innerHTML = marked.parse(data.intelligence_report);
}

window.triggerSimulation = (ticker) => {
  switchView('threat-sim');
  const target = document.getElementById('sim-target');
  if (target) target.value = ticker;
};

init();

// State
let globalData = {};
let riskData = [];

// DOM Elements
const views = document.querySelectorAll('.view');
const navItems = document.querySelectorAll('.nav-item');
const viewTitle = document.getElementById('view-title');
const viewSub = document.getElementById('view-sub');

// View configurations
const viewConfigs = {
  'overview': { title: 'Strategic Overview', sub: 'National Critical Infrastructure Analysis' },
  'network': { title: 'Dependency Network', sub: 'Inter-company Critical Links' },
  'threat-sim': { title: 'Threat Simulator', sub: 'Cascade Failure Projections' },
  'risk': { title: 'Risk Matrix', sub: 'ML-driven Vulnerability Scoring' },
  'analyst': { title: 'Sentinel AI Analyst', sub: 'Encrypted Strategic Intelligence' }
};

// Initialize
async function init() {
  updateTime();
  setInterval(updateTime, 1000);
  
  // Navigation
  navItems.forEach(item => {
    item.addEventListener('click', () => switchView(item.dataset.view));
  });

  try {
    document.getElementById('status-text').innerText = 'Fetching Intelligence...';
    
    // Fetch data in parallel
    const [compRes, riskRes, topRes, secRes] = await Promise.all([
      fetch('/api/companies'),
      fetch('/api/risk-scores'),
      fetch('/api/top-critical?n=5'),
      fetch('/api/sector-summary')
    ]);

    globalData.companies = (await compRes.json()).companies;
    riskData = (await riskRes.json()).risk_scores;
    globalData.topCritical = (await topRes.json()).nodes;
    globalData.sectorSummary = (await secRes.json()).sectors;

    document.getElementById('status-text').innerText = 'Secure Link Established';
    document.querySelector('.status-dot').style.background = 'var(--low)';

    // Populate Overview
    populateOverview();
    
    // Populate Risk Table
    renderRiskTable(riskData);
    
    // Populate Threat Sim Select
    populateSimSelect();
    
    // Risk Filter
    document.querySelectorAll('.filter-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
        e.target.classList.add('active');
        const tier = e.target.dataset.tier;
        renderRiskTable(tier === 'all' ? riskData : riskData.filter(r => r.risk_tier === tier));
      });
    });

  } catch (err) {
    console.error(err);
    document.getElementById('status-text').innerText = 'Connection Failed';
    document.querySelector('.status-dot').style.background = 'var(--critical)';
  }
}

function switchView(viewId) {
  navItems.forEach(n => n.classList.remove('active'));
  document.querySelector(`.nav-item[data-view="${viewId}"]`).classList.add('active');
  
  views.forEach(v => v.classList.remove('active'));
  document.getElementById(`view-${viewId}`).classList.add('active');
  
  const config = viewConfigs[viewId];
  viewTitle.innerText = config.title;
  viewSub.innerText = config.sub;

  // Trigger resize or specific initializers
  if (viewId === 'network' && window.initGraph) {
    window.initGraph();
  }
}

function updateTime() {
  const now = new Date();
  document.getElementById('timestamp').innerText = now.toISOString().replace('T', ' ').substring(0, 19) + ' IST';
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
  document.getElementById('stat-total').innerText = globalData.companies.length;
  
  const criticalCount = riskData.filter(r => r.risk_tier === 'CRITICAL').length;
  document.getElementById('stat-critical').innerText = criticalCount;
  
  let totalEdges = 0;
  globalData.companies.forEach(c => totalEdges += (c.dependencies ? c.dependencies.length : 0));
  document.getElementById('stat-edges').innerText = totalEdges;

  let gdpLoss = 0;
  globalData.topCritical.forEach(n => {
    n.threats.forEach(t => gdpLoss += (t.loss_estimate_bn || 0));
  });
  document.getElementById('stat-gdp').innerText = '$' + gdpLoss.toFixed(1) + 'B';

  // Top Critical List
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
  document.getElementById('top-critical-list').innerHTML = tcHtml;

  // Sector Breakdown
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
  document.getElementById('sector-breakdown').innerHTML = sbHtml;

  // Actors list (mocked from db structure)
  loadThreatActors();
}

async function loadThreatActors() {
  try {
    const res = await fetch('/api/companies');
    const data = await res.json();
    const actors = data.threat_actors || [];
    
    if (actors.length === 0) {
      document.getElementById('threat-actors-list').innerHTML = '<div class="loading">No actor data</div>';
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
    document.getElementById('threat-actors-list').innerHTML = html;
  } catch(e) { console.error(e); }
}

function renderRiskTable(data) {
  const tbody = document.getElementById('risk-table-body');
  if (data.length === 0) {
    tbody.innerHTML = '<tr><td colspan="8" class="loading">No records found.</td></tr>';
    return;
  }

  tbody.innerHTML = data.map(r => `
    <tr>
      <td><strong>${r.name}</strong> <br><span style="font-size:10px;color:var(--text-muted)">${r.ticker}</span></td>
      <td style="color:${getSectorColor(r.sector)};text-transform:capitalize">${r.sector}</td>
      <td class="risk-score-cell">${r.risk_score.toFixed(1)}</td>
      <td><span class="risk-badge ${r.risk_tier}">${r.risk_tier}</span></td>
      <td>${r.criticality}/10</td>
      <td>${r.betweenness.toFixed(3)}</td>
      <td>$${r.revenue_bn}B</td>
      <td>${r.employees.toLocaleString()}</td>
    </tr>
  `).join('');
}

// SIMULATOR
function populateSimSelect() {
  const select = document.getElementById('sim-target');
  let opts = '<option value="">— Select company —</option>';
  
  if(globalData.companies) {
    // Sort alpha
    const sorted = [...globalData.companies].sort((a,b) => a.name.localeCompare(b.name));
    sorted.forEach(c => {
      opts += `<option value="${c.ticker}">${c.name} (${c.ticker})</option>`;
    });
  }
  select.innerHTML = opts;
}

document.getElementById('run-sim-btn').addEventListener('click', async () => {
  const ticker = document.getElementById('sim-target').value;
  const depth = document.getElementById('sim-depth').value;
  if (!ticker) return;

  const btn = document.getElementById('run-sim-btn');
  btn.disabled = true;
  btn.innerText = 'SIMULATING...';
  document.getElementById('sim-results').classList.add('hidden');

  try {
    const res = await fetch(`/api/threat-sim/${ticker}?depth=${depth}`);
    const data = await res.json();
    
    if (data.error) throw new Error(data.error);
    renderSimResults(data);
    
  } catch (err) {
    console.error(err);
    alert('Simulation failed: ' + err.message);
  } finally {
    btn.disabled = false;
    btn.innerText = 'RUN ATTACK SIMULATION';
  }
});

function renderSimResults(data) {
  document.getElementById('sim-results').classList.remove('hidden');
  
  // Summary Cards
  document.getElementById('sim-summary-cards').innerHTML = `
    <div class="stat-card critical">
      <div class="stat-label">Companies Affected</div>
      <div class="stat-value">${data.affected_count}</div>
      <div class="stat-sub">Across cascade depth</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Est. Financial Loss</div>
      <div class="stat-value">$${data.total_estimated_loss_bn}B</div>
      <div class="stat-sub">Direct + Indirect</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">GDP Impact</div>
      <div class="stat-value">${data.gdp_impact_percent}%</div>
      <div class="stat-sub">Of national GDP</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Recovery Time</div>
      <div class="stat-value">${data.estimated_recovery_days}d</div>
      <div class="stat-sub">Estimated</div>
    </div>
  `;

  // Target Info
  const t = data.target;
  let tHtml = `
    <div class="detail-name">${t.name}</div>
    <div class="detail-ticker" style="margin-bottom:12px">${t.ticker} • Sector: <span style="color:${getSectorColor(t.sector)}">${t.sector.toUpperCase()}</span></div>
    
    <div class="detail-section-title">Direct Threats</div>
  `;
  
  if (t.threats) {
    t.threats.forEach(th => {
      tHtml += `
        <div class="threat-item">
          <div class="threat-actor">${th.actor}</div>
          <div class="threat-method">${th.method}</div>
          <div class="threat-loss">Est. Loss: $${th.loss_estimate_bn}B</div>
        </div>
      `;
    });
  }
  document.getElementById('sim-target-info').innerHTML = tHtml;

  // Cascade
  let cHtml = '';
  if (data.cascade && data.cascade.length > 0) {
    data.cascade.forEach(c => {
      cHtml += `
        <div class="cascade-item">
          <div class="cascade-level">Lvl ${c.level}</div>
          <div class="node-dot" style="background:${getSectorColor(c.sector)}; width:6px;height:6px;"></div>
          <div style="flex:1; font-weight:600">${c.name}</div>
          <div class="cascade-impact">Impact: ${(c.impact_factor*100).toFixed(0)}%</div>
          <div class="cascade-loss">-$${c.estimated_loss_bn}B</div>
        </div>
      `;
    });
  } else {
    cHtml = '<div class="loading">No cascading dependencies at this depth.</div>';
  }
  document.getElementById('sim-cascade-list').innerHTML = cHtml;

  // Threat Actors
  let aHtml = '';
  if (data.threat_actors && data.threat_actors.length > 0) {
    data.threat_actors.forEach(a => {
      aHtml += `
        <div class="actor-card">
          <div class="actor-info">
            <div class="actor-name">${a.name}</div>
            <div class="actor-methods" style="margin-top:4px">Known Methods: ${a.methods.join(', ')}</div>
          </div>
        </div>
      `;
    });
  }
  document.getElementById('sim-threat-actors').innerHTML = aHtml;
}

// Global functions for graph to call
window.triggerSimulation = (ticker) => {
  switchView('threat-sim');
  document.getElementById('sim-target').value = ticker;
  document.getElementById('run-sim-btn').click();
};

init();

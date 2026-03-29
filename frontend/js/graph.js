let graphData = null;
let svg, g, link, node, simulation;
let width, height;
let isGraphInit = false;

async function initGraph() {
  if (isGraphInit) return;
  
  const container = document.querySelector('.graph-container');
  width = container.clientWidth;
  height = container.clientHeight;

  svg = d3.select("#network-graph");
  g = svg.append("g");

  // Zoom
  const zoom = d3.zoom()
    .scaleExtent([0.1, 4])
    .on("zoom", (event) => g.attr("transform", event.transform));
  svg.call(zoom);

  try {
    const res = await fetch('/api/graph');
    graphData = await res.json();
    renderGraph();
    isGraphInit = true;
  } catch (err) {
    console.error("Failed to load graph data", err);
  }

  // Filters
  document.getElementById('sector-filter').addEventListener('change', renderGraph);
  document.getElementById('node-size-by').addEventListener('change', renderGraph);

  // Close panel
  document.getElementById('close-detail').addEventListener('click', () => {
    document.getElementById('node-detail-panel').classList.add('hidden');
    resetHighlight();
  });
}

function getSectorColor(sector) {
  const colors = {
    defense: '#ef4444',
    energy: '#f59e0b',
    finance: '#3b82f6',
    logistics: '#22c55e'
  };
  return colors[sector] || '#999';
}

function renderGraph() {
  if (!graphData) return;

  const sectorFilter = document.getElementById('sector-filter').value;
  const sizeAttr = document.getElementById('node-size-by').value;

  // Filter nodes
  let nodes = graphData.nodes.filter(n => sectorFilter === 'all' || n.sector === sectorFilter);
  const nodeIds = new Set(nodes.map(n => n.id || n.ticker));
  
  // Filter links
  let links = graphData.edges.filter(l => {
    const s = l.source.id || l.source;
    const t = l.target.id || l.target;
    return nodeIds.has(s) && nodeIds.has(t);
  });

  // Deep copy for D3
  nodes = nodes.map(d => Object.create(d));
  links = links.map(d => Object.create(d));

  g.selectAll("*").remove();

  // Scales
  const sizeExt = d3.extent(nodes, d => d[sizeAttr]);
  const sizeScale = d3.scaleLinear().domain(sizeExt).range([8, 24]);

  simulation = d3.forceSimulation(nodes)
    .force("link", d3.forceLink(links).id(d => d.ticker).distance(80))
    .force("charge", d3.forceManyBody().strength(-300))
    .force("center", d3.forceCenter(width / 2, height / 2))
    .force("collide", d3.forceCollide().radius(d => sizeScale(d[sizeAttr]) + 10));

  // Edges
  link = g.append("g")
    .selectAll("line")
    .data(links)
    .join("line")
    .attr("class", "link");

  // Nodes
  node = g.append("g")
    .selectAll("g")
    .data(nodes)
    .join("g")
    .attr("class", "node")
    .call(drag(simulation))
    .on("click", (event, d) => showNodeDetail(d));

  node.append("circle")
    .attr("r", d => sizeScale(d[sizeAttr]))
    .attr("fill", d => getSectorColor(d.sector))
    .attr("stroke", "#13161e")
    .attr("stroke-width", 2);

  node.append("text")
    .attr("x", d => sizeScale(d[sizeAttr]) + 4)
    .attr("y", 3)
    .text(d => d.short || d.ticker);

  simulation.on("tick", () => {
    link
      .attr("x1", d => d.source.x)
      .attr("y1", d => d.source.y)
      .attr("x2", d => d.target.x)
      .attr("y2", d => d.target.y);

    node
      .attr("transform", d => `translate(${d.x},${d.y})`);
  });
}

function showNodeDetail(d) {
  // Highlight
  node.classed("dimmed", n => n !== d);
  link.classed("dimmed", true);
  
  const connectedIds = new Set();
  link.filter(l => {
    if (l.source.ticker === d.ticker) connectedIds.add(l.target.ticker);
    if (l.target.ticker === d.ticker) connectedIds.add(l.source.ticker);
    return l.source.ticker === d.ticker || l.target.ticker === d.ticker;
  }).classed("dimmed", false).classed("highlighted", true);

  node.filter(n => connectedIds.has(n.ticker) || n === d).classed("dimmed", false);
  d3.select(event.currentTarget).classed("highlighted", true);

  // Panel
  const panel = document.getElementById('node-detail-panel');
  const content = document.getElementById('detail-content');
  
  let html = `
    <div class="detail-ticker">${d.ticker}</div>
    <div class="detail-name">${d.name}</div>
    <div class="detail-role">${d.role}</div>
    
    <div class="detail-section">
      <div class="detail-section-title">Overview</div>
      <div class="detail-desc">${d.description}</div>
    </div>

    <div class="detail-section">
      <div class="detail-section-title">Metrics</div>
      <div class="metric-row"><span class="metric-label">Sector</span><span class="metric-value" style="color:${getSectorColor(d.sector)};text-transform:capitalize">${d.sector}</span></div>
      <div class="metric-row"><span class="metric-label">Leader</span><span class="metric-value">${d.leader || 'N/A'}</span></div>
      <div class="metric-row"><span class="metric-label">Valuation</span><span class="metric-value">${d.valuation_t ? '₹'+d.valuation_t+'T' : '$'+d.revenue_bn+'B'}</span></div>
      <div class="metric-row"><span class="metric-label">Criticality</span><span class="metric-value">${d.criticality}/10</span></div>
      <div class="metric-row"><span class="metric-label">Vulnerability</span><span class="metric-value">${d.vulnerability_score.toFixed(1)}</span></div>
      <div class="metric-row"><span class="metric-label">Betweenness</span><span class="metric-value">${d.betweenness.toFixed(3)}</span></div>
      <div class="metric-row"><span class="metric-label">Dependencies</span><span class="metric-value">${d.out_degree} out / ${d.in_degree} in</span></div>
    </div>
  `;

  if (d.threats && d.threats.length > 0) {
    html += `<div class="detail-section"><div class="detail-section-title">Known Threats</div>`;
    d.threats.forEach(t => {
      html += `
        <div class="threat-item">
          <div class="threat-actor">${t.actor}</div>
          <div class="threat-method">${t.method}</div>
          <div class="threat-impact">Impact: ${t.impact}</div>
        </div>
      `;
    });
    html += `</div>`;
  }

  if (d.protections && d.protections.length > 0) {
    html += `<div class="detail-section"><div class="detail-section-title">Defensive Posture</div>`;
    d.protections.forEach(p => {
      html += `<div class="protection-item">${p}</div>`;
    });
    html += `</div>`;
  }

  html += `<button class="sim-btn" onclick="window.triggerSimulation('${d.ticker}')">LAUNCH ATTACK SIMULATION</button>`;

  content.innerHTML = html;
  panel.classList.remove('hidden');
}

function resetHighlight() {
  node.classed("dimmed", false).classed("highlighted", false);
  link.classed("dimmed", false).classed("highlighted", false);
}

function drag(simulation) {
  function dragstarted(event, d) {
    if (!event.active) simulation.alphaTarget(0.3).restart();
    d.fx = d.x;
    d.fy = d.y;
  }
  function dragged(event, d) {
    d.fx = event.x;
    d.fy = event.y;
  }
  function dragended(event, d) {
    if (!event.active) simulation.alphaTarget(0);
    d.fx = null;
    d.fy = null;
  }
  return d3.drag()
    .on("start", dragstarted)
    .on("drag", dragged)
    .on("end", dragended);
}

// Expose to window for external calls
window.initGraph = initGraph;
window.addEventListener('resize', () => {
  if(isGraphInit && document.getElementById('view-network').classList.contains('active')) {
    const container = document.querySelector('.graph-container');
    width = container.clientWidth;
    height = container.clientHeight;
    svg.attr("width", width).attr("height", height);
    if(simulation) {
      simulation.force("center", d3.forceCenter(width / 2, height / 2));
      simulation.alpha(0.3).restart();
    }
  }
});

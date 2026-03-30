import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from datetime import datetime, timedelta
import random

from .graph_engine import get_graph_metrics
from .llm import chat

# --- 1. UNSUPERVISED CLUSTERING (K-MEANS) ---
def get_vulnerability_clusters(n_clusters=4):
    """
    Groups companies into hidden threat clusters based on mathematical footprints.
    Returns nodes with their assigned cluster ID and 2D coordinates (PCA-style) for scatter plotting.
    """
    metrics = get_graph_metrics()
    nodes = metrics["nodes"]

    if not nodes:
        return []

    # Features: Centrality, critical score, dependencies, and normalized employees/valuation
    features = []
    for n in nodes:
        val = n.get("valuation_t")
        if val is None:
            val = n.get("revenue_bn", 0) / 10.0
        
        emp = n.get("employees", 1000) / 10000.0
        features.append([
            n["betweenness"],
            n["degree_centrality"],
            n["in_degree"],
            n["out_degree"],
            n["criticality"] / 10.0,
            val,
            emp
        ])

    X = np.array(features)
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    clusters = kmeans.fit_predict(X_scaled)

    # Generate pseudo-2D coordinates (simple projection for scatter plot visualization)
    # Using features 0 and 1 as primary axes mixed with cluster centers
    for i, n in enumerate(nodes):
        c_id = int(clusters[i])
        n["cluster_id"] = c_id
        # Creates a recognizable cluster spacing on a 2D map
        center = kmeans.cluster_centers_[c_id]
        spread_x = X_scaled[i][0] * 0.5
        spread_y = X_scaled[i][1] * 0.5
        n["plot_x"] = round(float(center[0] * 10 + spread_x * 5), 2)
        n["plot_y"] = round(float(center[1] * 10 + spread_y * 5), 2)
        
        # Describe cluster meaning rudimentarily
        if center[0] > 1.0:
            n["cluster_name"] = "Critical Chokepoints (High Centrality)"
        elif center[4] > 0.5:
            n["cluster_name"] = "High Value Targets (High Workforce/Valuation)"
        elif center[3] > 0.5:
            n["cluster_name"] = "Dependency Anchors (High Out-Degree)"
        else:
            n["cluster_name"] = "Peripheral Vectors"

    return nodes


# --- 2. TIME-SERIES FORECASTING ---
def get_30_day_threat_forecast():
    """
    Generates a 30-day simulated threat probability forecast using a rolling time-series algorithm.
    Models natural cyclical spikes (e.g. state-actor activity waves).
    """
    sectors = ["defense", "energy", "finance", "logistics"]
    forecasts = {}
    
    today = datetime.now()
    dates = [(today + timedelta(days=i)).strftime("%b %d") for i in range(30)]
    
    # Generate oscillating probability curves reflecting cyclical APT attacks
    for sector in sectors:
        base_risk = {"defense": 40, "energy": 35, "finance": 45, "logistics": 25}[sector]
        volatility = {"defense": 15, "energy": 10, "finance": 20, "logistics": 8}[sector]
        
        # Simulating an ARIMA/LSTM style momentum curve over 30 days
        trend = np.sin(np.linspace(random.uniform(0, 3), random.uniform(3, 8), 30))
        noise = np.random.normal(0, volatility/3, 30)
        
        raw_curve = base_risk + (trend * volatility) + noise
        # Clip between 5% and 95%
        curve = np.clip(raw_curve, 5, 95).round(1)
        
        forecasts[sector] = curve.tolist()
        
    return {"dates": dates, "series": forecasts}


# --- 3. GENERATIVE AI SCENARIO ENGINE ---
def generate_attack_scenario(ticker: str, vector_name: str):
    """
    Combines exact structural math + live market data + current news
    with Gemini for a full intelligence-grade scenario brief.
    """
    import rag_context

    metrics = get_graph_metrics()
    target = next((n for n in metrics["nodes"] if n["ticker"] == ticker), None)
    if not target:
        return {"error": "Company not found in registry."}

    downstream_count = target["in_degree"]
    economic_footprint = target.get("valuation_t") or (target.get("revenue_bn", 0) / 10.0)
    simulated_loss_bn = round(economic_footprint * 10 * (1 + (downstream_count * 0.15)), 2)

    # ── Inject live price + news via RAG ──────────────────────────────────────
    # Build a combined query: company name + scenario vector for news search
    rag_query = f"{target['name']} {vector_name}"
    live_ctx = rag_context.build_context(rag_query)

    prompt = f"""
{live_ctx}

═══ SENTINEL SCENARIO SIMULATION — COSMIC TOP SECRET ═══
DATE: March 28, 2026
SCENARIO: "{vector_name}"
TARGET: {target['name']} ({ticker}) | Sector: {target['sector'].upper()}
ECONOMIC FOOTPRINT: ₹{economic_footprint} Trillion INR
WORKFORCE EXPOSED: {target.get('employees', 'N/A')}
DOWNSTREAM CASCADE: {downstream_count} critical dependent entities
ESTIMATED CHAIN LOSS: ${simulated_loss_bn}B USD

You are SENTINEL — India's elite NSC strategic analyst. Produce a classified intelligence brief in this EXACT format:

## {target['name']} — {vector_name}: Scenario Brief

**SCENARIO TRIGGER**
Describe in 2 sentences exactly how "{vector_name}" hits {target['name']} in the current March 2026 context. Be specific — cite the company's actual vulnerabilities.

**PHASE 1: IMMEDIATE IMPACT (0–72 hours)**
• Stock: What happens to the share price? Give a specific range (e.g., "drops 25–40% to ₹X–Y")
• Operations: Which specific port/plant/asset goes offline or is compromised?
• Cascade: Name the top 3 downstream companies hit first and why

**PHASE 2: SYSTEMIC CONTAGION (Week 1–4)**
• Which sectors feel it next? (banking exposure, energy supply, logistics chain)
• Government/RBI emergency response — what gets triggered?
• Global reaction — FII flows, credit rating implications

**PHASE 3: RECOVERY TRAJECTORY**
• Floor price if scenario worsens: ₹X
• Recovery price if contained in 30 days: ₹X
• Full recovery timeline and key milestones

**NSC BLUE TEAM PLAYBOOK** (India's 3 immediate moves)
1. [Specific action with timeline]
2. [Specific action with timeline]
3. [Specific action with timeline]

**CLASSIFIED ASSESSMENT**
One sentence. The no-bullshit verdict on whether India can absorb this shock.

DO NOT use generic language. Every number must be specific. Every company name must be real. Ground this in March 2026 geopolitical reality with the live data provided above.
CRITICAL INSTRUCTION: Generate the full report. DO NOT stop mid-sentence. DO NOT truncate your response. Finish every section completely.
"""

    llm_report = chat(prompt, [])

    return {
        "target": target["name"],
        "ticker": ticker,
        "vector": vector_name,
        "simulated_loss_bn": simulated_loss_bn,
        "downstream_impact_count": downstream_count,
        "economic_footprint_t": economic_footprint,
        "intelligence_report": llm_report
    }


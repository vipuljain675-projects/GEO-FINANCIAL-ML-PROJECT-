import numpy as np
from sklearn.ensemble import IsolationForest
from graph_engine import get_graph_metrics

RISK_TIERS = [
    (80, "CRITICAL"),
    (60, "HIGH"),
    (40, "MEDIUM"),
    (0,  "LOW")
]

def get_risk_tier(score):
    for threshold, label in RISK_TIERS:
        if score >= threshold:
            return label
    return "LOW"

def compute_risk_scores():
    metrics = get_graph_metrics()
    nodes = metrics["nodes"]

    features = np.array([
        [
            n["betweenness"],
            n["degree_centrality"],
            n["in_degree"],
            n["out_degree"],
            n["criticality"] / 10.0,
            len(n["threats"]) / 5.0,
        ]
        for n in nodes
    ])

    clf = IsolationForest(contamination=0.2, random_state=42)
    clf.fit(features)
    scores = clf.score_samples(features)
    # Normalize anomaly scores to 0-100 (more negative = more anomalous = higher risk)
    norm_scores = ((scores - scores.min()) / (scores.max() - scores.min() + 1e-9))
    iso_risk = 1 - norm_scores  # invert: high anomaly = high risk

    results = []
    for i, n in enumerate(nodes):
        vuln = n["vulnerability_score"] / 100.0
        iso = iso_risk[i]
        final_score = round((vuln * 0.7 + iso * 0.3) * 100, 1)
        results.append({
            "ticker": n["ticker"],
            "name": n["name"],
            "sector": n["sector"],
            "risk_score": final_score,
            "risk_tier": get_risk_tier(final_score),
            "vulnerability_score": n["vulnerability_score"],
            "betweenness": n["betweenness"],
            "criticality": n["criticality"],
            "employees": n["employees"],
            "revenue_bn": n["revenue_bn"],
        })

    return sorted(results, key=lambda x: x["risk_score"], reverse=True)

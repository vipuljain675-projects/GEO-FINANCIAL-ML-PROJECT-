import json
from pathlib import Path
from graph_engine import load_data, build_graph

GDP_INDIA_BN = 3500  # approximate India GDP in $bn

SECTOR_GDP_WEIGHT = {
    "defense": 0.08,
    "energy": 0.12,
    "finance": 0.20,
    "logistics": 0.10
}

def simulate_attack_cascade(target_ticker: str, depth: int = 3):
    data = load_data()
    G, companies = build_graph(data)

    if target_ticker not in companies:
        return {"error": f"Company {target_ticker} not found"}

    target = companies[target_ticker]
    cascade = []
    visited = {target_ticker}
    queue = [(target_ticker, 0, 1.0)]
    total_loss = sum(t["loss_estimate_bn"] for t in target["threats"]) if target["threats"] else 0.5

    # BFS cascade through reverse dependencies
    reverse_G = G.reverse()
    while queue:
        ticker, level, impact_factor = queue.pop(0)
        if level >= depth:
            continue
        c = companies.get(ticker)
        if not c:
            continue
        for dep_ticker in reverse_G.successors(ticker):
            if dep_ticker in visited:
                continue
            visited.add(dep_ticker)
            dep = companies[dep_ticker]
            new_impact = round(impact_factor * 0.6, 3)
            dep_loss = sum(t["loss_estimate_bn"] for t in dep["threats"]) * new_impact if dep["threats"] else 0.2
            cascade.append({
                "ticker": dep_ticker,
                "name": dep["name"],
                "sector": dep["sector"],
                "level": level + 1,
                "impact_factor": new_impact,
                "estimated_loss_bn": round(dep_loss, 2)
            })
            total_loss += dep_loss
            queue.append((dep_ticker, level + 1, new_impact))

    gdp_impact_pct = round((total_loss / GDP_INDIA_BN) * 100, 2)
    recovery_days = int(target["criticality"] * 12 + len(cascade) * 5)

    return {
        "target": {
            "ticker": target_ticker,
            "name": target["name"],
            "sector": target["sector"],
            "criticality": target["criticality"],
            "threats": target["threats"],
            "protections": target["protections"]
        },
        "cascade": sorted(cascade, key=lambda x: x["level"]),
        "affected_count": len(cascade) + 1,
        "total_estimated_loss_bn": round(total_loss, 2),
        "gdp_impact_percent": gdp_impact_pct,
        "estimated_recovery_days": recovery_days,
        "threat_actors": get_applicable_threat_actors(target["sector"])
    }

def get_applicable_threat_actors(sector: str):
    data = load_data()
    actors = []
    for actor in data.get("threat_actors", []):
        if sector in actor.get("primary_targets", []):
            actors.append(actor)
    return actors

def get_sector_risk_summary():
    data = load_data()
    sectors = {}
    for c in data["companies"]:
        s = c["sector"]
        if s not in sectors:
            sectors[s] = {"count": 0, "total_criticality": 0, "total_threats": 0, "total_loss_bn": 0}
        sectors[s]["count"] += 1
        sectors[s]["total_criticality"] += c["criticality"]
        sectors[s]["total_threats"] += len(c["threats"])
        sectors[s]["total_loss_bn"] += sum(t["loss_estimate_bn"] for t in c["threats"])

    result = []
    for s, v in sectors.items():
        result.append({
            "sector": s,
            "company_count": v["count"],
            "avg_criticality": round(v["total_criticality"] / v["count"], 2),
            "total_threat_vectors": v["total_threats"],
            "total_potential_loss_bn": round(v["total_loss_bn"], 2),
        })
    return result

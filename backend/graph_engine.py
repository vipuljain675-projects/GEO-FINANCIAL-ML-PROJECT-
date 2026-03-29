import json
import networkx as nx
from pathlib import Path

DATA_PATH = Path(__file__).parent / "data" / "companies.json"

def load_data():
    with open(DATA_PATH) as f:
        return json.load(f)

def build_graph(data):
    G = nx.DiGraph()
    companies = {c["ticker"]: c for c in data["companies"]}
    for c in data["companies"]:
        G.add_node(c["ticker"], **{k: v for k, v in c.items() if k not in ["threats", "protections", "dependencies"]})
    for c in data["companies"]:
        for dep in c.get("dependencies", []):
            if dep in companies:
                G.add_edge(c["ticker"], dep)
    return G, companies

def get_graph_metrics():
    data = load_data()
    G, companies = build_graph(data)
    bc = nx.betweenness_centrality(G, normalized=True)
    dc = nx.degree_centrality(G)
    in_deg = dict(G.in_degree())
    out_deg = dict(G.out_degree())

    nodes = []
    for ticker, attrs in G.nodes(data=True):
        c = companies[ticker]
        vuln_score = round(
            (bc.get(ticker, 0) * 40) +
            (dc.get(ticker, 0) * 20) +
            (c.get("criticality", 5) / 10 * 40), 2
        )
        nodes.append({
            "ticker": ticker,
            "name": c["name"],
            "short": c["short"],
            "sector": c["sector"],
            "role": c["role"],
            "criticality": c["criticality"],
            "description": c["description"],
            "threats": c["threats"],
            "protections": c["protections"],
            "dependencies": c["dependencies"],
            "betweenness": round(bc.get(ticker, 0), 4),
            "degree_centrality": round(dc.get(ticker, 0), 4),
            "in_degree": in_deg.get(ticker, 0),
            "out_degree": out_deg.get(ticker, 0),
            "vulnerability_score": vuln_score,
            "revenue_bn": c.get("revenue_bn", 0),
            "employees": c.get("employees", 0),
        })

    edges = [{"source": u, "target": v} for u, v in G.edges()]
    return {"nodes": nodes, "edges": edges}

def get_top_critical(n=10):
    metrics = get_graph_metrics()
    return sorted(metrics["nodes"], key=lambda x: x["vulnerability_score"], reverse=True)[:n]

def get_shortest_path(source, target):
    data = load_data()
    G, _ = build_graph(data)
    try:
        path = nx.shortest_path(G, source, target)
        return {"path": path, "length": len(path) - 1}
    except nx.NetworkXNoPath:
        return {"path": [], "length": -1}
    except nx.NodeNotFound as e:
        return {"error": str(e)}

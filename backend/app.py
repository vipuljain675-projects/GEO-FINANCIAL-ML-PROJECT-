import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Optional
import json

from graph_engine import get_graph_metrics, get_top_critical, get_shortest_path, load_data
from threat_engine import simulate_attack_cascade, get_sector_risk_summary
from ml_engine import compute_risk_scores
import llm

app = FastAPI(title="Strategic Shield API", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve frontend
frontend_path = os.path.join(os.path.dirname(__file__), "..", "frontend")
app.mount("/static", StaticFiles(directory=frontend_path), name="static")

@app.get("/")
def root():
    return FileResponse(os.path.join(frontend_path, "index.html"))

@app.get("/api/companies")
def get_companies():
    data = load_data()
    return {"companies": data["companies"], "threat_actors": data.get("threat_actors", [])}

@app.get("/api/graph")
def get_graph():
    return get_graph_metrics()

@app.get("/api/risk-scores")
def get_risk_scores():
    scores = compute_risk_scores()
    return {"risk_scores": scores}

@app.get("/api/threat-sim/{ticker}")
def threat_simulation(ticker: str, depth: int = 3):
    result = simulate_attack_cascade(ticker.upper(), depth=min(depth, 5))
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result

@app.get("/api/sector-summary")
def sector_summary():
    return {"sectors": get_sector_risk_summary()}

@app.get("/api/top-critical")
def top_critical(n: int = 10):
    return {"nodes": get_top_critical(n)}

@app.get("/api/path")
def shortest_path(source: str, target: str):
    return get_shortest_path(source.upper(), target.upper())

class ChatMessage(BaseModel):
    message: str
    history: Optional[List[dict]] = []

@app.post("/api/chat")
def chat_endpoint(body: ChatMessage):
    response = llm.chat(body.message, body.history)
    return {"response": response}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)

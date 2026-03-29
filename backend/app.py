from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr
from typing import List, Optional
from sqlalchemy.orm import Session
import json

# Database & Logic
from . import models, auth, database
from graph_engine import get_graph_metrics, get_top_critical, get_shortest_path, load_data
from threat_engine import get_sector_risk_summary
import ml_advanced
import market_intelligence
import rag_context
import llm

# Initialize DB
models.Base.metadata.create_all(bind=database.engine)

app = FastAPI(title="Strategic Shield API", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

# --- AUTH UTILS ---
def get_current_user(db: Session = Depends(database.get_db), token: str = Depends(oauth2_scheme)):
    payload = auth.decode_access_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    email: str = payload.get("sub")
    user = db.query(models.User).filter(models.User.email == email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

# --- AUTH ENDPOINTS ---
class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: str

class Token(BaseModel):
    access_token: str
    token_type: str

@app.post("/api/auth/signup", response_model=Token)
def signup(user: UserCreate, db: Session = Depends(database.get_db)):
    db_user = db.query(models.User).filter(models.User.email == user.email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    hashed_password = auth.get_password_hash(user.password)
    new_user = models.User(email=user.email, hashed_password=hashed_password, full_name=user.full_name)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    access_token = auth.create_access_token(data={"sub": new_user.email})
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/api/auth/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(database.get_db)):
    user = db.query(models.User).filter(models.User.email == form_data.username).first()
    if not user or not auth.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    
    access_token = auth.create_access_token(data={"sub": user.email})
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/api/auth/me")
def read_users_me(current_user: models.User = Depends(get_current_user)):
    return {"email": current_user.email, "full_name": current_user.full_name, "id": current_user.id}

# --- PORTFOLIO ENDPOINTS ---
class PortfolioItem(BaseModel):
    ticker: str
    quantity: float

@app.get("/api/portfolio")
def get_portfolio(current_user: models.User = Depends(get_current_user), db: Session = Depends(database.get_db)):
    items = db.query(models.Portfolio).filter(models.Portfolio.user_id == current_user.id).all()
    return items

@app.post("/api/portfolio")
def add_to_portfolio(item: PortfolioItem, current_user: models.User = Depends(get_current_user), db: Session = Depends(database.get_db)):
    # Check if exists
    existing = db.query(models.Portfolio).filter(
        models.Portfolio.user_id == current_user.id,
        models.Portfolio.ticker == item.ticker.upper()
    ).first()
    
    if existing:
        existing.quantity += item.quantity
    else:
        new_item = models.Portfolio(ticker=item.ticker.upper(), quantity=item.quantity, user_id=current_user.id)
        db.add(new_item)
    
    db.commit()
    return {"status": "success"}

@app.delete("/api/portfolio/{ticker}")
def remove_from_portfolio(ticker: str, current_user: models.User = Depends(get_current_user), db: Session = Depends(database.get_db)):
    db.query(models.Portfolio).filter(
        models.Portfolio.user_id == current_user.id,
        models.Portfolio.ticker == ticker.upper()
    ).delete()
    db.commit()
    return {"status": "deleted"}

# --- AI PERSONAL ADVISOR ---
@app.post("/api/personal/analyze")
def analyze_personal(current_user: models.User = Depends(get_current_user), db: Session = Depends(database.get_db)):
    items = db.query(models.Portfolio).filter(models.Portfolio.user_id == current_user.id).all()
    if not items:
        return {"response": "Your portfolio is empty. Add some assets to trigger a strategic analysis."}
    
    portfolio_str = ", ".join([f"{i.quantity} units of {i.ticker}" for i in items])
    prompt = f"Perform a HIGH-LEVEL STRATEGIC RISK ANALYSIS for {current_user.full_name}'s personal investment portfolio: {portfolio_str}. " \
             "Focus on how current West Asia tensions or logistics disruptions (Red Sea/Hormuz) specifically impact THESE stocks. " \
             "Provide a 'Portfolio Vulnerability Index' and clear 'Hold/Hedge' defensive recommendations."
    
    # Simple history bypass for advisor
    response = llm.chat(prompt, [])
    return {"response": response}

# --- CORE APP ENDPOINTS ---
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

@app.get("/api/ml/forecast")
def get_forecast():
    return ml_advanced.get_30_day_threat_forecast()

@app.get("/api/ml/clusters")
def get_clusters():
    return {"clusters": ml_advanced.get_vulnerability_clusters()}

class ScenarioRequest(BaseModel):
    ticker: str
    vector: str

@app.post("/api/ml/scenario")
def run_scenario(body: ScenarioRequest):
    result = ml_advanced.generate_attack_scenario(body.ticker.upper(), body.vector)
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

@app.get("/api/market")
def get_market_data(ticker: str, company: str = "", sector: str = ""):
    result = market_intelligence.get_market_intelligence(ticker, company, sector)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result

@app.get("/api/live-price")
def get_live_price(ticker: str):
    try:
        import yfinance as yf
        from datetime import datetime, timezone, timedelta
        import math

        if not ticker.endswith(".NS") and not ticker.endswith(".BO"):
            ticker = ticker + ".NS"

        stock = yf.Ticker(ticker)
        ist = timezone(timedelta(hours=5, minutes=30))
        now_ist = datetime.now(ist)
        weekday = now_ist.weekday()
        hour = now_ist.hour
        minute = now_ist.minute
        time_mins = hour * 60 + minute
        market_open = (weekday < 5) and (9 * 60 + 15 <= time_mins <= 15 * 60 + 30)

        try:
            live_price = round(float(stock.fast_info.last_price), 2)
        except Exception:
            live_price = None

        today_hist = stock.history(period="1d", interval="5m")
        open_price = None
        day_high = None
        day_low = None
        pct_change = None

        if not today_hist.empty:
            valid = [(float(v)) for v in today_hist["Close"]
                     if math.isfinite(float(v)) and float(v) > 0]
            if valid:
                open_price = round(valid[0], 2)
                day_high = round(max(valid), 2)
                day_low = round(min(valid), 2)
                if live_price and open_price:
                    pct_change = round(((live_price - open_price) / open_price) * 100, 2)

        return {
            "ticker": ticker,
            "live_price": live_price,
            "open": open_price,
            "day_high": day_high,
            "day_low": day_low,
            "pct_change": pct_change,
            "market_open": market_open,
            "as_of": now_ist.strftime("%d %b %Y %H:%M IST"),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class ChatMessage(BaseModel):
    message: str
    history: Optional[List[dict]] = []

@app.post("/api/chat")
def chat_endpoint(body: ChatMessage):
    context = rag_context.build_context(body.message)
    augmented_message = f"{context}{body.message}" if context else body.message
    response = llm.chat(augmented_message, body.history)
    return {"response": response}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)

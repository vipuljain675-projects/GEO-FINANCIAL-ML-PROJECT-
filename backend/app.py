from fastapi import FastAPI, HTTPException, Depends, status, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr
from typing import List, Optional
import json
import os
from starlette.config import Config
from authlib.integrations.starlette_client import OAuth
from urllib.parse import quote
from dotenv import load_dotenv
import threading
import time
from datetime import timedelta

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"), override=True)

# Database & Logic
from . import auth, database
from .graph_engine import get_graph_metrics, get_top_critical, get_shortest_path, load_data
from .threat_engine import get_sector_risk_summary
from . import ml_advanced
from . import market_intelligence
from . import rag_context
from . import llm

app = FastAPI(title="Strategic Shield API", version="1.0")
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SECRET_KEY", "strategic-secret-99"))

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")
LIVE_EVENT_REFRESH_MINUTES = max(5, int(os.getenv("LIVE_EVENT_REFRESH_MINUTES", "15")))
_live_event_worker_started = False


@app.on_event("startup")
def startup_initialize_database():
    database.initialize_database()
    _start_live_event_worker()


def _live_event_refresh_loop():
    while True:
        try:
            db = database.get_database()
            stats = rag_context.ingest_default_event_set(db=db)
            print(f"[LIVE EVENT WORKER] Refreshed events: {stats}")
        except Exception as exc:
            print(f"[LIVE EVENT WORKER] Refresh failed: {exc}")
        time.sleep(LIVE_EVENT_REFRESH_MINUTES * 60)


def _start_live_event_worker():
    global _live_event_worker_started
    if _live_event_worker_started:
        return
    worker = threading.Thread(target=_live_event_refresh_loop, daemon=True, name="live-event-worker")
    worker.start()
    _live_event_worker_started = True

def _serialize_user(user: dict) -> dict:
    return {
        "id": str(user["_id"]),
        "email": user["email"],
        "full_name": user.get("full_name") or user["email"].split("@")[0],
    }


def _serialize_portfolio_item(item: dict) -> dict:
    return {
        "id": str(item["_id"]),
        "ticker": item["ticker"],
        "quantity": float(item.get("quantity", 0)),
        "purchase_price": item.get("purchase_price"),
        "purchase_date": item.get("purchase_date"),
        "user_id": item["user_id"],
    }


def _resolve_user_from_auth_header(request: Request, db):
    auth_header = request.headers.get("authorization", "")
    if not auth_header.lower().startswith("bearer "):
        return None
    token = auth_header.split(" ", 1)[1].strip()
    if not token:
        return None
    payload = auth.decode_access_token(token)
    if not payload:
        return None
    email = payload.get("sub")
    if not email:
        return None
    user = db["users"].find_one({"email": email})
    return _serialize_user(user) if user else None


def _memory_scope(scope: str) -> str:
    return scope if scope in {"analyst", "portfolio"} else "analyst"


def _memory_doc(db, user_id: str, scope: str):
    return db["chat_memory"].find_one({"user_id": user_id, "scope": _memory_scope(scope)})


def get_persistent_history(db, user_id: str, scope: str, limit: int = 24) -> list:
    doc = _memory_doc(db, user_id, scope)
    if not doc:
        return []
    messages = doc.get("messages", [])
    return messages[-limit:]


def save_persistent_history(db, user_id: str, scope: str, history: list):
    trimmed = (history or [])[-24:]
    db["chat_memory"].update_one(
        {"user_id": user_id, "scope": _memory_scope(scope)},
        {
            "$set": {
                "user_id": user_id,
                "scope": _memory_scope(scope),
                "messages": trimmed,
                "updated_at": time.time(),
            }
        },
        upsert=True,
    )


# --- AUTH UTILS ---
def get_current_user(db=Depends(database.get_db), token: str = Depends(oauth2_scheme)):
    payload = auth.decode_access_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    email: str = payload.get("sub")
    user = db["users"].find_one({"email": email})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return _serialize_user(user)

# --- AUTH ENDPOINTS ---
class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: str

class Token(BaseModel):
    access_token: str
    token_type: str

class UserProfile(BaseModel):
    email: EmailStr
    full_name: str


class InvestorPreferences(BaseModel):
    risk_mode: str = "balanced"
    conviction_style: str = "medium"
    time_horizon: str = "medium_term"
    reply_style: str = "full_context"

@app.post("/api/auth/signup", response_model=Token)
def signup(user: UserCreate, db=Depends(database.get_db)):
    db_user = db["users"].find_one({"email": user.email})
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    hashed_password = auth.get_password_hash(user.password)
    db["users"].insert_one(
        {
            "email": user.email,
            "hashed_password": hashed_password,
            "full_name": user.full_name,
        }
    )

    access_token = auth.create_access_token(
        data={"sub": user.email},
        expires_delta=timedelta(minutes=auth.ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/api/auth/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db=Depends(database.get_db)):
    user = db["users"].find_one({"email": form_data.username})
    if not user or not auth.verify_password(form_data.password, user["hashed_password"]):
        raise HTTPException(status_code=401, detail="Incorrect email or password")

    access_token = auth.create_access_token(
        data={"sub": user["email"]},
        expires_delta=timedelta(minutes=auth.ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/api/auth/me", response_model=UserProfile)
def me(current_user=Depends(get_current_user)):
    return {"email": current_user["email"], "full_name": current_user["full_name"]}

# --- GOOGLE AUTH CONFIG ---
config = Config('.env')
oauth = OAuth(config)

oauth.register(
    name='google',
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_id=os.getenv("GOOGLE_CLIENT_ID"),
    client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
    client_kwargs={
        'scope': 'openid email profile'
    }
)

def google_auth_enabled() -> bool:
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    return bool(client_id and client_secret)

@app.get("/api/auth/google/status")
def google_status():
    return {"enabled": google_auth_enabled()}

@app.get("/api/auth/google/debug")
def google_debug():
    client_id = os.getenv("GOOGLE_CLIENT_ID", "")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "")
    return {
        "enabled": google_auth_enabled(),
        "client_id_prefix": client_id[:20],
        "client_id_suffix": client_id[-20:] if client_id else "",
        "client_secret_prefix": client_secret[:10],
        "client_secret_length": len(client_secret),
    }

@app.get("/api/auth/google/login")
async def google_login(request: Request):
    if not google_auth_enabled():
        raise HTTPException(status_code=503, detail="Google sign-in is not configured on this system")
    redirect_uri = request.url_for('auth_google_callback')
    return await oauth.google.authorize_redirect(request, redirect_uri)

@app.get("/api/auth/google/callback")
async def auth_google_callback(request: Request, db=Depends(database.get_db)):
    if not google_auth_enabled():
        raise HTTPException(status_code=503, detail="Google sign-in is not configured on this system")
    token = await oauth.google.authorize_access_token(request)
    user_info = token.get('userinfo')
    if not user_info:
        raise HTTPException(status_code=400, detail="Google authentication failed")
    
    email = user_info.email
    full_name = user_info.name

    user = db["users"].find_one({"email": email})
    if not user:
        db["users"].insert_one(
            {
                "email": email,
                "full_name": full_name,
                "hashed_password": "GOOGLE_AUTH_EXTERNAL",
            }
        )

    access_token = auth.create_access_token(data={"sub": email})
    redirect_url = request.url_for('root')
    return RedirectResponse(
        url=f"{redirect_url}?auth_token={quote(access_token)}&auth_name={quote(full_name)}",
        status_code=302
    )

# --- PORTFOLIO ENDPOINTS ---
class PortfolioItem(BaseModel):
    ticker: str
    quantity: float
    purchase_price: Optional[float] = None
    purchase_date: Optional[str] = None

class PortfolioChatRequest(BaseModel):
    message: str
    history: Optional[List[dict]] = []


def _default_investor_preferences() -> dict:
    return {
        "risk_mode": "balanced",
        "conviction_style": "medium",
        "time_horizon": "medium_term",
        "reply_style": "full_context",
    }


def _get_user_preferences(db, user_id: str) -> dict:
    prefs = _default_investor_preferences()
    stored = db["user_preferences"].find_one({"user_id": user_id}) or {}
    for key in prefs:
        if stored.get(key):
            prefs[key] = stored[key]
    return prefs

def _format_currency(value: Optional[float]) -> str:
    if value is None:
        return "Unknown"
    return f"₹{value:,.2f}"

def _portfolio_action_label(pnl_pct: Optional[float], sector: str, concentration_pct: float) -> tuple[str, str]:
    sector = (sector or "").lower()
    elevated_sector = sector in {"defense", "energy", "logistics"}
    if concentration_pct >= 45:
        return "REDUCE", "Portfolio concentration is too high in a single position."
    if pnl_pct is None:
        return "HOLD", "Need more live data before changing the position."
    if pnl_pct <= -20 and elevated_sector:
        return "HOLD", "Loss is deep but the sector still carries strategic upside if the thesis remains intact."
    if pnl_pct <= -18:
        return "REDUCE", "Loss is turning structural and needs tighter risk control."
    if pnl_pct >= 30 and elevated_sector:
        return "HOLD", "Strong gains with continuing strategic tailwinds support patience."
    if pnl_pct >= 25:
        return "REDUCE", "You are sitting on strong gains; partial profit-taking lowers future drawdown risk."
    if -8 <= pnl_pct <= 8:
        return "BUY MORE", "Position is near cost basis, so disciplined accumulation can improve the average if conviction is intact."
    return "HOLD", "Current move still looks tactical rather than thesis-breaking."


def _entry_quality(pnl_pct: Optional[float]) -> str:
    if pnl_pct is None:
        return "unknown"
    if pnl_pct >= 35:
        return "excellent_entry"
    if pnl_pct >= 12:
        return "good_entry"
    if pnl_pct >= -8:
        return "fair_entry"
    if pnl_pct >= -18:
        return "weak_entry"
    return "stressed_entry"


def _position_state(pnl_pct: Optional[float]) -> str:
    if pnl_pct is None:
        return "unclear"
    if pnl_pct >= 40:
        return "big_winner"
    if pnl_pct >= 12:
        return "winner"
    if pnl_pct >= -8:
        return "flat_zone"
    if pnl_pct >= -20:
        return "in_loss"
    return "deep_in_loss"


def _thesis_status(sector: str, pnl_pct: Optional[float], criticality: float, ticker: str = "", role: str = "") -> str:
    sector = (sector or "").lower()
    ticker = (ticker or "").upper()
    role_text = (role or "").lower()
    if pnl_pct is None:
        return "intact"
    if pnl_pct <= -22 and criticality < 7 and sector not in {"defense", "energy", "logistics"}:
        return "broken"
    if sector == "logistics":
        return "pressured"
    if sector == "energy":
        if ticker == "ONGC.NS" or "crude oil production" in role_text:
            return "pressured" if pnl_pct <= -12 else "intact"
        return "pressured"
    if pnl_pct <= -10:
        return "pressured"
    return "intact"


def _holding_cases(holding: dict) -> tuple[list[str], list[str]]:
    sector = (holding.get("sector") or "").lower()
    ticker = (holding.get("ticker") or "").upper()
    role = holding.get("role") or ""

    if ticker == "ADANIPORTS.NS":
        return (
            [
                "India's trade and export flows structurally support major logistics gateways over time.",
                "Trade deals and cargo expansion can help once shipping routes normalize.",
                "The company remains strategically important to India's cargo network."
            ],
            [
                "West Asia, Red Sea, and Hormuz disruptions still pressure near-term margins and sentiment.",
                "Fresh buying at a weak entry can trap more capital while routes remain stressed."
            ],
        )

    if ticker == "ONGC.NS" or "crude oil production" in role.lower():
        return (
            [
                "ONGC is an upstream producer, so firmer crude prices can directly support realizations and earnings.",
                "Energy security keeps strategic support high for India's main domestic producer.",
                "Supply shocks can strengthen ONGC faster than they help downstream fuel distributors."
            ],
            [
                "Crude volatility can reverse quickly, so chasing short-term spikes can still create bad entries.",
                "Government intervention or windfall-style pressure can cap how much upside reaches shareholders."
            ],
        )

    if ticker in {"IOC.NS", "BPCL.NS"} or "fuel distribution" in role.lower() or "strategic petroleum reserves" in role.lower():
        return (
            [
                "Energy security keeps these names strategically relevant in India's fuel system."
            ],
            [
                "Refiners and distributors can be squeezed when crude spikes faster than retail price pass-through.",
                "Geopolitical oil shocks raise working-capital and margin risk for downstream energy names."
            ],
        )

    if sector == "logistics":
        return (
            [
                "India's trade and export flows structurally support major logistics gateways over time.",
                "Trade deals and cargo expansion can help once shipping routes normalize."
            ],
            [
                "West Asia, Red Sea, and Hormuz disruptions still pressure near-term margins and sentiment.",
                "Fresh buying at a weak entry can trap more capital while routes remain stressed."
            ],
        )

    if sector == "defense":
        return (
            [
                "Defense procurement and strategic autonomy still support the long-term thesis.",
                "Government alignment is stronger for mission-critical defense names."
            ],
            [
                "Supply-chain or import dependencies can still delay execution and near-term upside."
            ],
        )

    if sector == "energy":
        return (
            [
                "Energy security keeps strategic support high for critical producers and utilities."
            ],
            [
                "Oil and commodity volatility can sharply change margins and headline risk."
            ],
        )

    return (
        [
            "The company still sits in India's strategic backbone, which supports the long-duration thesis."
        ],
        [
            "Macro pressure and valuation risk can still dominate the near term."
        ],
    )


def _position_advice_context(
    pnl_pct: Optional[float],
    concentration_pct: float,
    thesis_status: str,
    sector: str,
    ticker: str,
    role: str,
    criticality: float,
    preferences: dict,
) -> tuple[str, str]:
    risk_mode = preferences.get("risk_mode", "balanced")
    conviction_style = preferences.get("conviction_style", "medium")
    sector = (sector or "").lower()
    ticker = (ticker or "").upper()
    role_text = (role or "").lower()

    if pnl_pct is None:
        return "hold_pending_data", "Live context is incomplete, so the safest move is to hold until better confirmation arrives."
    if thesis_status == "broken":
        return "exit_if_thesis_broken", "The thesis looks broken, so protecting capital matters more than patience."
    if concentration_pct >= 35 and pnl_pct >= 15:
        return "trim_on_strength", "This is already a large profitable position, so trimming on strength lowers future drawdown risk."
    if (
        thesis_status == "intact"
        and concentration_pct < 25
        and pnl_pct is not None
        and -15 <= pnl_pct <= 3
        and criticality >= 8
    ):
        if ticker == "ONGC.NS" or "crude oil production" in role_text:
            if risk_mode == "aggressive" or conviction_style == "high":
                return "buy_on_weakness", "Current weakness looks more event-driven than thesis-breaking, so staggered buying into a strategic upstream producer can be justified."
            return "hold_or_small_add", "The thesis is intact and the weakness looks temporary, so holding is fine and small staggered additions can be considered."
    if pnl_pct <= -8 and thesis_status == "pressured":
        if risk_mode == "aggressive" and conviction_style == "high":
            return "hold_not_add", "Conviction can justify holding, but the entry is weak enough that averaging blindly would be reckless."
        return "hold_not_add", "The thesis may still be alive, but the entry is weak enough that holding is safer than adding fresh money."
    if -6 <= pnl_pct <= 8 and thesis_status == "intact" and risk_mode == "aggressive" and conviction_style == "high":
        return "can_add_on_dip", "The position is near cost basis and conviction is high, so staggered buying on dips can be justified."
    if pnl_pct >= 25:
        return "hold_or_trim", "You already have a strong profit cushion, so the question is profit management, not panic."
    return "hold", "This setup still looks like a hold while the thesis and macro picture evolve."

def build_portfolio_intelligence(current_user: dict, db):
    preferences = _get_user_preferences(db, current_user["id"])
    items = list(db["portfolios"].find({"user_id": current_user["id"]}))
    if not items:
        return {
            "summary": {
                "total_invested": None,
                "current_value": None,
                "total_pnl": None,
                "total_pnl_pct": None,
                "biggest_position": None,
                "highest_risk": None,
                "concentration_warning": "No holdings uploaded yet."
            },
            "holdings": [],
            "narrative_prompt": "The portfolio is empty.",
            "preferences": preferences,
        }

    company_index = {c["ticker"]: c for c in load_data().get("companies", [])}
    enriched = []
    total_current_value = 0.0
    total_invested_value = 0.0
    known_invested = False

    for item in items:
        ticker = (item.get("ticker") or "").upper()
        company = company_index.get(ticker, {})
        company_name = company.get("name", ticker)
        sector = company.get("sector", "unknown")
        role = company.get("role", "Unknown strategic role")
        threat_score = company.get("criticality", 5)

        live_price = None
        try:
            market_data = market_intelligence.get_market_intelligence(ticker, company_name, sector)
            live_price = market_data.get("history", {}).get("current_price")
            if live_price is None:
                live_price = market_data.get("price")
            if live_price is not None:
                live_price = float(live_price)
        except Exception:
            live_price = None

        invested = None
        if item.get("purchase_price") is not None:
            invested = float(item["purchase_price"]) * float(item.get("quantity", 0))
            total_invested_value += invested
            known_invested = True
        current_value = live_price * float(item.get("quantity", 0)) if live_price is not None else None
        if current_value is not None:
            total_current_value += current_value
        pnl_value = current_value - invested if invested is not None and current_value is not None else None
        pnl_pct = ((pnl_value / invested) * 100) if invested not in (None, 0) and pnl_value is not None else None

        enriched.append({
            "ticker": ticker,
            "company_name": company_name,
            "sector": sector,
            "role": role,
            "quantity": float(item.get("quantity", 0)),
            "purchase_price": item.get("purchase_price"),
            "purchase_date": item.get("purchase_date"),
            "live_price": live_price,
            "invested": invested,
            "current_value": current_value,
            "pnl_value": pnl_value,
            "pnl_pct": pnl_pct,
            "criticality": threat_score,
        })

    for holding in enriched:
        current_value = holding["current_value"] or 0
        concentration_pct = (current_value / total_current_value * 100) if total_current_value > 0 else 0
        action, rationale = _portfolio_action_label(holding["pnl_pct"], holding["sector"], concentration_pct)
        entry_quality = _entry_quality(holding["pnl_pct"])
        position_state = _position_state(holding["pnl_pct"])
        thesis_status = _thesis_status(
            holding["sector"],
            holding["pnl_pct"],
            holding["criticality"],
            holding["ticker"],
            holding["role"],
        )
        action_context, action_context_reason = _position_advice_context(
            holding["pnl_pct"],
            concentration_pct,
            thesis_status,
            holding["sector"],
            holding["ticker"],
            holding["role"],
            holding["criticality"],
            preferences,
        )
        positive_case, negative_case = _holding_cases(holding)
        holding["concentration_pct"] = concentration_pct
        holding["action"] = action
        holding["rationale"] = rationale
        holding["entry_quality"] = entry_quality
        holding["position_state"] = position_state
        holding["thesis_status"] = thesis_status
        holding["action_context"] = action_context
        holding["action_context_reason"] = action_context_reason
        holding["positive_case"] = positive_case
        holding["negative_case"] = negative_case
        holding["thesis"] = (
            f"{holding['company_name']} sits in the {holding['sector']} bucket with role '{holding['role']}'. "
            f"Entered on {holding['purchase_date'] or 'an unknown date'} at {_format_currency(holding['purchase_price'])}, "
            f"it now trades at {_format_currency(holding['live_price'])}."
        )

    biggest_position = max(enriched, key=lambda x: x["current_value"] or 0)
    highest_risk = max(enriched, key=lambda x: ((x["criticality"] * 100) + ((x["concentration_pct"] or 0))))
    total_pnl = (total_current_value - total_invested_value) if known_invested and total_current_value else None
    total_pnl_pct = ((total_pnl / total_invested_value) * 100) if known_invested and total_invested_value else None

    narrative_lines = []
    for holding in enriched:
        pnl_pct_text = f"{holding['pnl_pct']:.2f}%" if holding["pnl_pct"] is not None else "unknown"
        narrative_lines.append(
            f"- {holding['company_name']} ({holding['ticker']}), sector={holding['sector']}, role={holding['role']}, "
            f"buy_date={holding['purchase_date'] or 'unknown'}, buy_price={_format_currency(holding['purchase_price'])}, "
            f"current_price={_format_currency(holding['live_price'])}, quantity={holding['quantity']}, "
            f"pnl={_format_currency(holding['pnl_value'])}, pnl_pct={pnl_pct_text}, "
            f"action={holding['action']}, entry_quality={holding['entry_quality']}, position_state={holding['position_state']}, "
            f"thesis_status={holding['thesis_status']}, action_context={holding['action_context']}, "
            f"positive_case={' | '.join(holding['positive_case'])}, negative_case={' | '.join(holding['negative_case'])}"
        )

    concentration_warning = (
        f"{biggest_position['company_name']} is your biggest live position at {biggest_position['concentration_pct']:.1f}% of portfolio value."
        if total_current_value > 0 else
        "Live valuation is incomplete, so concentration is estimated."
    )

    return {
        "summary": {
            "total_invested": total_invested_value if known_invested else None,
            "current_value": total_current_value if total_current_value else None,
            "total_pnl": total_pnl,
            "total_pnl_pct": total_pnl_pct,
            "biggest_position": biggest_position["company_name"],
            "highest_risk": highest_risk["company_name"],
            "concentration_warning": concentration_warning,
            "preferences": preferences,
        },
        "holdings": enriched,
        "narrative_prompt": "\n".join(narrative_lines),
        "preferences": preferences,
    }

@app.get("/api/portfolio")
def get_portfolio(current_user=Depends(get_current_user), db=Depends(database.get_db)):
    items = db["portfolios"].find({"user_id": current_user["id"]}).sort("ticker", 1)
    return [_serialize_portfolio_item(item) for item in items]

@app.post("/api/portfolio/bulk")
def add_bulk_portfolio(items: List[PortfolioItem], current_user=Depends(get_current_user), db=Depends(database.get_db)):
    for item in items:
        db["portfolios"].update_one(
            {"user_id": current_user["id"], "ticker": item.ticker.upper()},
            {
                "$set": {
                    "user_id": current_user["id"],
                    "ticker": item.ticker.upper(),
                    "quantity": item.quantity,
                    "purchase_price": item.purchase_price,
                    "purchase_date": item.purchase_date,
                }
            },
            upsert=True,
        )

    return {"status": "success", "count": len(items)}

@app.post("/api/portfolio")
def add_to_portfolio(item: PortfolioItem, current_user=Depends(get_current_user), db=Depends(database.get_db)):
    existing = db["portfolios"].find_one({"user_id": current_user["id"], "ticker": item.ticker.upper()})

    if existing:
        update_fields = {
            "quantity": float(existing.get("quantity", 0)) + item.quantity,
        }
        if item.purchase_price is not None:
            update_fields["purchase_price"] = item.purchase_price
        if item.purchase_date:
            update_fields["purchase_date"] = item.purchase_date
        db["portfolios"].update_one({"_id": existing["_id"]}, {"$set": update_fields})
    else:
        db["portfolios"].insert_one(
            {
                "ticker": item.ticker.upper(),
                "quantity": item.quantity,
                "purchase_price": item.purchase_price,
                "purchase_date": item.purchase_date,
                "user_id": current_user["id"],
            }
        )

    return {"status": "success"}

@app.delete("/api/portfolio/{ticker}")
def remove_from_portfolio(ticker: str, current_user=Depends(get_current_user), db=Depends(database.get_db)):
    db["portfolios"].delete_one({"user_id": current_user["id"], "ticker": ticker.upper()})
    return {"status": "deleted"}


@app.get("/api/personal/preferences")
def get_personal_preferences(current_user=Depends(get_current_user), db=Depends(database.get_db)):
    return _get_user_preferences(db, current_user["id"])


@app.put("/api/personal/preferences")
def update_personal_preferences(
    prefs: InvestorPreferences,
    current_user=Depends(get_current_user),
    db=Depends(database.get_db),
):
    payload = prefs.model_dump()
    db["user_preferences"].update_one(
        {"user_id": current_user["id"]},
        {"$set": {"user_id": current_user["id"], **payload}},
        upsert=True,
    )
    return payload

# --- AI PERSONAL ADVISOR ---
@app.post("/api/personal/analyze")
def analyze_personal(current_user=Depends(get_current_user), db=Depends(database.get_db)):
    intelligence = build_portfolio_intelligence(current_user, db)
    if not intelligence["holdings"]:
        return {
            "summary": intelligence["summary"],
            "holdings": [],
            "response": "Your portfolio is empty. Add assets during onboarding or in the dashboard to trigger analysis."
        }

    live_context = rag_context.build_context(
        "latest developments affecting this portfolio",
        db=db,
        portfolio_holdings=intelligence["holdings"],
    )
    prompt = (
        f"You are the Strategic Shield personal portfolio advisor. Analyze {current_user['full_name']}'s holdings.\n\n"
        f"{live_context}\n\n"
        f"Investor preferences: {json.dumps(intelligence['preferences'])}\n\n"
        f"Portfolio Snapshot:\n{intelligence['narrative_prompt']}\n\n"
        "Write a concise portfolio verdict with exactly these sections:\n"
        "1. PORTFOLIO VERDICT\n"
        "2. TOP RISKS\n"
        "3. NEXT 3 MOVES\n"
        "Use the investor preferences and do not treat HOLD, BUY MORE, and HOLD, DO NOT ADD as the same thing.\n"
        "Make it crisp, readable, and practical. No markdown tables. No fluff."
    )

    response = llm.chat(prompt, [], live_query="latest developments affecting this portfolio", force_live_search=True)
    return {
        "summary": intelligence["summary"],
        "holdings": intelligence["holdings"],
        "response": response
    }

@app.post("/api/personal/chat")
def chat_personal(body: PortfolioChatRequest, current_user=Depends(get_current_user), db=Depends(database.get_db)):
    intelligence = build_portfolio_intelligence(current_user, db)
    if not intelligence["holdings"]:
        return {"response": "Your portfolio is empty. Add holdings first, then ask me portfolio questions."}

    live_context = rag_context.build_context(body.message, db=db, portfolio_holdings=intelligence["holdings"])
    tracked_companies = load_data().get("companies", [])
    tracked_universe = "\n".join(
        f"- {company['ticker']}: {company['name']} | sector={company.get('sector', 'unknown')} | role={company.get('role', 'unknown')}"
        for company in tracked_companies
    )
    held_tickers = ", ".join(holding["ticker"] for holding in intelligence["holdings"])

    prompt = (
        f"You are the personal portfolio copilot for {current_user['full_name']}.\n"
        f"{live_context}\n\n"
        f"Investor preferences: {json.dumps(intelligence['preferences'])}\n\n"
        f"Use this live portfolio context:\n{intelligence['narrative_prompt']}\n\n"
        f"Current holdings tickers: {held_tickers}\n\n"
        f"Tracked universe available for recommendations:\n{tracked_universe}\n\n"
        f"User question: {body.message}\n\n"
        "Rules:\n"
        "1. Answer the user's exact question in the first line.\n"
        "2. If the user asks what to buy/add now, give a ranked shortlist from the tracked universe, not a lecture.\n"
        "3. If the question is about an existing holding, explicitly separate: POSITION STATUS, BULL CASE, BEAR CASE, ACTION NOW.\n"
        "4. If entry quality is weak or the user is already in loss, distinguish HOLD from BUY MORE. Use HOLD, DO NOT ADD when the thesis is alive but fresh buying is unattractive.\n"
        "5. Use sections exactly as needed: BUY NOW, WATCHLIST, AVOID / NO BUY, PORTFOLIO FIT.\n"
        "6. Adjust the final action to the investor preferences, but never let 'aggressive' mean blindly averaging into a bad entry.\n"
        "7. If a company has strategic significance or supportive trade/government developments, mention them before the final action.\n"
        "8. If live price is missing, say 'Price check: use Market Intelligence tab for live NSE data.'\n"
        "9. Keep the answer crisp, specific, and data-oriented.\n"
        "10. Avoid over-concentrating into the user's existing largest position or sector unless conviction is very strong.\n"
        "11. Prefer ideas that diversify the user's current holdings and are strategically strong in the present environment.\n"
        "12. Be blunt and decisive. Do not refuse. Do not say you cannot give buy/sell recommendations.\n"
        "13. Distinguish upstream producers from downstream refiners/distributors. Higher crude can support ONGC-style upstream names, while it can squeeze IOC/BPCL-style downstream names.\n"
        "14. Do not give one-sided energy answers. Always show both the earnings upside from higher crude and the volatility/policy risk before the final action.\n"
        "15. If the user argues that current weakness may be temporary and the thesis is still intact, evaluate a BUY ON WEAKNESS path explicitly instead of defaulting to avoid/add-no-fresh-capital."
    )
    effective_history = body.history or get_persistent_history(db, current_user["id"], "portfolio")
    response = llm.chat(prompt, effective_history, live_query=body.message)
    updated_history = (effective_history + [
        {"role": "user", "content": body.message},
        {"role": "assistant", "content": response},
    ])[-24:]
    save_persistent_history(db, current_user["id"], "portfolio", updated_history)
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

@app.get("/api/chat/history")
def chat_history(request: Request, scope: str = "analyst", db=Depends(database.get_db)):
    user = _resolve_user_from_auth_header(request, db)
    if not user:
        return {"messages": []}
    return {"messages": get_persistent_history(db, user["id"], scope)}

@app.get("/api/live-events/status")
def live_events_status(db=Depends(database.get_db)):
    latest = db["live_events"].find_one(sort=[("fetched_at", -1)])
    return {
        "event_count": db["live_events"].count_documents({}),
        "cache_count": db["live_event_cache"].count_documents({}),
        "latest_fetch": latest.get("fetched_at").isoformat() if latest and latest.get("fetched_at") else None,
        "latest_title": latest.get("title") if latest else None,
    }

@app.post("/api/live-events/refresh")
def live_events_refresh(db=Depends(database.get_db)):
    return rag_context.ingest_default_event_set(db=db)

@app.post("/api/chat")
def chat_endpoint(body: ChatMessage, request: Request, db=Depends(database.get_db)):
    user = _resolve_user_from_auth_header(request, db)
    context = rag_context.build_context(body.message, db=db)
    augmented_message = f"{context}\n\nUser question: {body.message}" if context else body.message
    effective_history = body.history or (get_persistent_history(db, user["id"], "analyst") if user else [])
    response = llm.chat(augmented_message, effective_history, live_query=body.message)
    if user:
        updated_history = (effective_history + [
            {"role": "user", "content": body.message},
            {"role": "assistant", "content": response},
        ])[-24:]
        save_persistent_history(db, user["id"], "analyst", updated_history)
    return {"response": response}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)

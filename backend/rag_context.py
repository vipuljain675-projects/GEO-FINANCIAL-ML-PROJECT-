"""
RAG Context Builder for SENTINEL Chat
- Detects company mentions → injects REAL live yfinance prices
- Searches NewsAPI for current headlines on ANY topic in query
SENTINEL is grounded in today's actual world, not just training data.
"""
import math
import os
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()
NEWSAPI_KEY = os.getenv("NEWSAPI_KEY", "")

# ─── Company Map ──────────────────────────────────────────────────────────────
COMPANY_MAP = {
    "adani port": ("Adani Ports", "ADANIPORTS.NS", "logistics"),
    "adaniports": ("Adani Ports", "ADANIPORTS.NS", "logistics"),
    "adani enterprise": ("Adani Enterprises", "ADANIENT.NS", "logistics"),
    "adanient": ("Adani Enterprises", "ADANIENT.NS", "logistics"),
    "adani green": ("Adani Green Energy", "ADANIGREEN.NS", "energy"),
    "adani power": ("Adani Power", "ADANIPOWER.NS", "energy"),
    "adani": ("Adani Enterprises", "ADANIENT.NS", "logistics"),
    "hal": ("HAL", "HAL.NS", "defense"),
    "hindustan aeronautics": ("HAL", "HAL.NS", "defense"),
    "bel": ("BEL", "BEL.NS", "defense"),
    "bharat electronics": ("BEL", "BEL.NS", "defense"),
    "bdl": ("BDL", "BDL.NS", "defense"),
    "mazagon": ("Mazagon Dock", "MAZDOCK.NS", "defense"),
    "mazdock": ("Mazagon Dock", "MAZDOCK.NS", "defense"),
    "grse": ("GRSE", "GRSE.NS", "defense"),
    "cochin ship": ("Cochin Shipyard", "COCHINSHIP.NS", "defense"),
    "larsen": ("L&T", "LT.NS", "defense"),
    "l&t": ("L&T", "LT.NS", "defense"),
    "bharat forge": ("Bharat Forge", "BHARATFORG.NS", "defense"),
    "solar industries": ("Solar Industries", "SOLARINDS.NS", "defense"),
    "reliance": ("Reliance Industries", "RELIANCE.NS", "energy"),
    "ongc": ("ONGC", "ONGC.NS", "energy"),
    "ioc": ("Indian Oil", "IOC.NS", "energy"),
    "indian oil": ("Indian Oil", "IOC.NS", "energy"),
    "bpcl": ("BPCL", "BPCL.NS", "energy"),
    "gail": ("GAIL", "GAIL.NS", "energy"),
    "ntpc": ("NTPC", "NTPC.NS", "energy"),
    "power grid": ("Power Grid", "POWERGRID.NS", "energy"),
    "coal india": ("Coal India", "COALINDIA.NS", "energy"),
    "tata steel": ("Tata Steel", "TATASTEEL.NS", "energy"),
    "jsw steel": ("JSW Steel", "JSWSTEEL.NS", "energy"),
    "hindalco": ("Hindalco", "HINDALCO.NS", "energy"),
    "sbi": ("State Bank of India", "SBIN.NS", "finance"),
    "state bank": ("State Bank of India", "SBIN.NS", "finance"),
    "hdfc": ("HDFC Bank", "HDFCBANK.NS", "finance"),
    "icici": ("ICICI Bank", "ICICIBANK.NS", "finance"),
    "axis bank": ("Axis Bank", "AXISBANK.NS", "finance"),
    "tcs": ("TCS", "TCS.NS", "finance"),
    "infosys": ("Infosys", "INFY.NS", "finance"),
    "hcltech": ("HCL Tech", "HCLTECH.NS", "finance"),
    "hcl tech": ("HCL Tech", "HCLTECH.NS", "finance"),
    "paytm": ("Paytm", "PAYTM.NS", "finance"),
    "airtel": ("Bharti Airtel", "BHARTIARTL.NS", "finance"),
    "concor": ("CONCOR", "CONCOR.NS", "logistics"),
    "rvnl": ("RVNL", "RVNL.NS", "logistics"),
    "tata motors": ("Tata Motors", "TATAMOTORS.NS", "logistics"),
    "siemens": ("Siemens India", "SIEMENS.NS", "logistics"),
    "abb": ("ABB India", "ABB.NS", "logistics"),
    "indigo": ("IndiGo", "INDIGO.NS", "logistics"),
    "sun pharma": ("Sun Pharma", "SUNPHARMA.NS", "logistics"),
    "dlf": ("DLF", "DLF.NS", "logistics"),
}

# Geopolitical / macro keywords → will trigger news search even without company
GEO_KEYWORDS = [
    "iran", "israel", "war", "ukraine", "russia", "china", "pakistan",
    "supply chain", "oil", "crude", "nse", "sensex", "rbi", "fed",
    "interest rate", "recession", "inflation", "budget", "modi", "sebi",
    "nifty", "stock market", "geopolit", "tariff", "sanction",
]


def detect_companies(message: str) -> list:
    msg = message.lower()
    found = {}
    for keyword, info in COMPANY_MAP.items():
        if keyword in msg:
            ticker = info[1]
            if ticker not in found:
                found[ticker] = info
    return list(found.values())


def build_search_query(message: str, companies: list) -> str:
    msg = message.lower()
    if companies:
        names = [c[0] for c in companies[:2]]
        query = " OR ".join(f'"{n}"' for n in names)
        for kw in GEO_KEYWORDS:
            if kw in msg:
                query += f" {kw}"
                break
        return query
    hits = [kw for kw in GEO_KEYWORDS if kw in msg]
    if hits:
        return " ".join(hits[:3]) + " India"
    return " ".join(message.split()[:8])


def fetch_live_news(query: str, days: int = 7) -> list:
    """Search NewsAPI for the latest headlines on the given query."""
    if not NEWSAPI_KEY:
        return []
    try:
        from_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        resp = requests.get(
            "https://newsapi.org/v2/everything",
            params={
                "q": query,
                "from": from_date,
                "sortBy": "publishedAt",
                "language": "en",
                "pageSize": 8,
                "apiKey": NEWSAPI_KEY,
            },
            timeout=5,
        )
        if resp.status_code != 200:
            return []
        articles = resp.json().get("articles", [])
        results = []
        for a in articles:
            title = (a.get("title") or "").strip()
            source = (a.get("source") or {}).get("name", "")
            pub = (a.get("publishedAt") or "")[:10]
            if title and "[Removed]" not in title:
                results.append({"title": title, "source": source, "date": pub})
        return results
    except Exception:
        return []


def fetch_live_snapshot(ticker: str) -> dict | None:
    """Fetches current price + 5-day trend from yfinance."""
    try:
        import yfinance as yf
        stock = yf.Ticker(ticker)
        end = datetime.now().strftime("%Y-%m-%d")
        start = (datetime.now() - timedelta(days=20)).strftime("%Y-%m-%d")
        hist = stock.history(start=start, end=end, interval="1d")
        if hist.empty:
            return None
        closes = [round(float(v), 2) for v in hist["Close"]
                  if math.isfinite(float(v)) and float(v) > 0]
        dates = [d.strftime("%b %d") for d in hist.index][-len(closes):]
        if not closes:
            return None
        try:
            live = round(float(stock.fast_info.last_price), 2)
        except Exception:
            live = closes[-1]
        try:
            hi52 = round(float(stock.fast_info.year_high), 2)
            lo52 = round(float(stock.fast_info.year_low), 2)
        except Exception:
            hi52 = max(closes)
            lo52 = min(closes)
        pct_5d = round(((live - closes[-5]) / closes[-5]) * 100, 2) if len(closes) >= 5 else None
        return {
            "live_price": live, "hi_52w": hi52, "lo_52w": lo52,
            "pct_5d": pct_5d, "recent_closes": list(zip(dates[-5:], closes[-5:])),
        }
    except Exception:
        return None


def build_context(message: str) -> str:
    """
    Builds the full RAG block injected into every SENTINEL chat:
    1. Live yfinance stock data (if company mentioned)
    2. Real NewsAPI headlines from last 7 days (always)
    """
    companies = detect_companies(message)
    now = datetime.now().strftime("%d %b %Y %H:%M IST")
    blocks = []

    # ── 1. Live stock prices ──────────────────────────────────────────────────
    if companies:
        blocks.append(f"╔══ LIVE MARKET DATA — {now} ══╗")
        for name, ticker, sector in companies[:3]:
            snap = fetch_live_snapshot(ticker)
            if not snap:
                blocks.append(f"  {name} ({ticker}): Data unavailable")
                continue
            arrow = "▼ BEARISH" if (snap["pct_5d"] or 0) < -0.5 else \
                    "▲ BULLISH" if (snap["pct_5d"] or 0) > 0.5 else "➡ SIDEWAYS"
            recent = " → ".join([f"₹{p}" for _, p in snap["recent_closes"]])
            pct = f"{snap['pct_5d']:+.2f}%" if snap["pct_5d"] is not None else "n/a"
            blocks.append(
                f"\n  📊 {name} ({ticker}) | {sector.upper()}\n"
                f"  Price: ₹{snap['live_price']} | 5D: {pct} {arrow}\n"
                f"  52W High: ₹{snap['hi_52w']} | 52W Low: ₹{snap['lo_52w']}\n"
                f"  Trend: {recent}"
            )
        blocks.append("\n╚══ USE THESE EXACT NUMBERS. DO NOT INVENT PRICES. ══╝\n")

    # ── 2. Live news feed ─────────────────────────────────────────────────────
    query = build_search_query(message, companies)
    news = fetch_live_news(query)

    if news:
        blocks.append(f'╔══ LIVE NEWS — Last 7 Days (query: "{query}") ══╗')
        for n in news:
            blocks.append(f"  [{n['date']}] {n['source']}: {n['title']}")
        blocks.append(
            "╚══ BASE YOUR ANALYSIS ON THESE REAL HEADLINES. "
            "Quote specific sources where relevant. ══╝\n"
        )

    return "\n".join(blocks) if blocks else ""

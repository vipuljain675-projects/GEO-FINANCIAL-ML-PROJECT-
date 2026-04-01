"""
Autonomous live context for SENTINEL.

- Pulls fresh market snapshots for mentioned or held companies
- Pulls fresh NewsAPI + GDELT events on-demand
- Caches fetched event payloads in Mongo so the assistant builds short-term memory
- Injects a structured "live event memory" block into prompts
"""
import hashlib
import json
import math
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()
NEWSAPI_KEY = os.getenv("NEWSAPI_KEY", "")

COMPANIES_PATH = Path(__file__).parent / "data" / "companies.json"
COMPANIES = json.loads(COMPANIES_PATH.read_text()).get("companies", [])

COMPANY_MAP = {}
for company in COMPANIES:
    ticker = company["ticker"].upper()
    names = {
        company["name"].lower(),
        company.get("short", "").lower(),
        ticker.lower(),
        ticker.replace(".ns", "").lower(),
        ticker.replace(".bo", "").lower(),
    }
    for name in names:
        if name:
            COMPANY_MAP[name] = (
                company["name"],
                ticker,
                company.get("sector", "unknown"),
                company.get("role", "unknown"),
            )

MACRO_KEYWORDS = [
    "iran", "israel", "war", "ceasefire", "ukraine", "russia", "china", "pakistan",
    "oil", "crude", "rbi", "fed", "inflation", "interest rate", "tariff", "sanction",
    "budget", "sebi", "regulation", "market", "nifty", "sensex", "shipping",
]

SECTOR_QUERIES = {
    "defense": "India defense procurement military border tensions",
    "energy": "India oil crude LNG energy sanctions RBI inflation",
    "finance": "India banks RBI rates liquidity regulation SEBI",
    "logistics": "India ports shipping Red Sea supply chain freight",
}

EVENT_POSITIVE = [
    "ceasefire", "truce", "approval", "cleared", "wins order", "order win",
    "expansion", "rate cut", "de-escalation", "profit jumps", "surge", "record",
]
EVENT_NEGATIVE = [
    "attack", "strike", "war", "sanction", "probe", "raid", "blockade", "tariff",
    "downgrade", "disruption", "crash", "slump", "selloff", "missile", "conflict",
]


def _now_utc():
    return datetime.now(timezone.utc)


def _cache_key(kind: str, query: str) -> str:
    raw = f"{kind}:{query.strip().lower()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _collection(db):
    return None if db is None else db["live_event_cache"]


def _get_cached_payload(db, kind: str, query: str, max_age_minutes: int = 20):
    coll = _collection(db)
    if coll is None:
        return None
    doc = coll.find_one({"cache_key": _cache_key(kind, query)})
    if not doc:
        return None
    fetched_at = doc.get("fetched_at")
    if not fetched_at or (_now_utc() - fetched_at) > timedelta(minutes=max_age_minutes):
        return None
    return doc.get("payload")


def _store_cache(db, kind: str, query: str, payload):
    coll = _collection(db)
    if coll is None:
        return
    coll.update_one(
        {"cache_key": _cache_key(kind, query)},
        {
            "$set": {
                "cache_key": _cache_key(kind, query),
                "kind": kind,
                "query": query,
                "payload": payload,
                "fetched_at": _now_utc(),
            }
        },
        upsert=True,
    )


def detect_companies(message: str, portfolio_holdings: list | None = None) -> list:
    msg = (message or "").lower()
    found = {}
    for keyword, info in COMPANY_MAP.items():
        if not keyword:
            continue
        if " " in keyword or "." in keyword:
            matched = keyword in msg
        else:
            matched = re.search(rf"\b{re.escape(keyword)}\b", msg) is not None
        if matched:
            found[info[1]] = info
    if portfolio_holdings:
        for holding in portfolio_holdings:
            ticker = (holding.get("ticker") or "").upper()
            for company in COMPANIES:
                if company["ticker"].upper() == ticker and ticker not in found:
                    found[ticker] = (
                        company["name"],
                        ticker,
                        company.get("sector", "unknown"),
                        company.get("role", "unknown"),
                    )
    return list(found.values())


def _extract_macro_hits(message: str) -> list:
    msg = (message or "").lower()
    return [kw for kw in MACRO_KEYWORDS if kw in msg]


def _build_queries(message: str, companies: list, portfolio_holdings: list | None = None) -> list:
    queries = []
    if companies:
        for name, ticker, sector, _role in companies[:3]:
            queries.append(f"\"{name}\" OR {ticker.replace('.NS', '').replace('.BO', '')} stock India")

    sectors = []
    if portfolio_holdings:
        sectors.extend((holding.get("sector") or "").lower() for holding in portfolio_holdings if holding.get("sector"))
    sectors.extend(company[2].lower() for company in companies if len(company) > 2)
    for sector in list(dict.fromkeys(sectors))[:2]:
        if sector in SECTOR_QUERIES:
            queries.append(SECTOR_QUERIES[sector])

    macro_hits = _extract_macro_hits(message)
    if macro_hits:
        queries.append(" ".join(macro_hits[:3]) + " India markets")
    else:
        queries.append("India markets RBI SEBI oil war ceasefire")

    deduped = []
    seen = set()
    for query in queries:
        key = query.lower().strip()
        if key and key not in seen:
            deduped.append(query)
            seen.add(key)
    return deduped[:4]


def fetch_live_news(query: str, days: int = 5, db=None) -> list:
    cached = _get_cached_payload(db, "newsapi", query)
    if cached is not None:
        return cached
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
                "pageSize": 6,
                "apiKey": NEWSAPI_KEY,
            },
            timeout=6,
        )
        if resp.status_code != 200:
            return []
        articles = []
        for article in resp.json().get("articles", []):
            title = (article.get("title") or "").strip()
            if not title or "[Removed]" in title:
                continue
            articles.append(
                {
                    "title": title,
                    "source": (article.get("source") or {}).get("name", ""),
                    "date": (article.get("publishedAt") or "")[:10],
                    "url": article.get("url", ""),
                }
            )
        _store_cache(db, "newsapi", query, articles)
        return articles
    except Exception:
        return []


def fetch_gdelt_events(query: str, db=None) -> list:
    cached = _get_cached_payload(db, "gdelt", query)
    if cached is not None:
        return cached
    try:
        resp = requests.get(
            "https://api.gdeltproject.org/api/v2/doc/doc",
            params={
                "query": query,
                "mode": "artlist",
                "maxrecords": 6,
                "format": "json",
                "timespan": "3d",
            },
            timeout=6,
        )
        if resp.status_code != 200:
            return []
        items = []
        for article in resp.json().get("articles", []):
            title = (article.get("title") or "").strip()
            if not title:
                continue
            items.append(
                {
                    "title": title,
                    "source": article.get("domain", "GDELT"),
                    "date": (article.get("seendate") or "")[:10],
                    "url": article.get("url", ""),
                }
            )
        _store_cache(db, "gdelt", query, items)
        return items
    except Exception:
        return []


def fetch_live_snapshot(ticker: str) -> dict | None:
    try:
        import yfinance as yf

        stock = yf.Ticker(ticker)
        end = datetime.now().strftime("%Y-%m-%d")
        start = (datetime.now() - timedelta(days=20)).strftime("%Y-%m-%d")
        hist = stock.history(start=start, end=end, interval="1d")
        if hist.empty:
            return None
        closes = [round(float(v), 2) for v in hist["Close"] if math.isfinite(float(v)) and float(v) > 0]
        if not closes:
            return None
        try:
            live = round(float(stock.fast_info.last_price), 2)
        except Exception:
            live = closes[-1]
        pct_5d = round(((live - closes[-5]) / closes[-5]) * 100, 2) if len(closes) >= 5 else None
        return {
            "live_price": live,
            "pct_5d": pct_5d,
            "recent_closes": closes[-5:],
            "hi_52w": round(float(stock.fast_info.year_high), 2) if getattr(stock, "fast_info", None) else max(closes),
            "lo_52w": round(float(stock.fast_info.year_low), 2) if getattr(stock, "fast_info", None) else min(closes),
        }
    except Exception:
        return None


def _classify_event(title: str) -> str:
    t = title.lower()
    pos = sum(1 for kw in EVENT_POSITIVE if kw in t)
    neg = sum(1 for kw in EVENT_NEGATIVE if kw in t)
    if pos > neg:
        return "positive"
    if neg > pos:
        return "negative"
    return "neutral"


def _extract_relevant_metadata(title: str, query: str) -> tuple[list, list]:
    text = f"{title} {query}".lower()
    tickers = []
    sectors = []
    for company in COMPANIES:
        ticker = company["ticker"].upper()
        name = company["name"].lower()
        short = company.get("short", "").lower()
        if (
            name in text
            or (short and re.search(rf"\b{re.escape(short)}\b", text))
            or ticker.lower() in text
            or ticker.replace(".NS", "").lower() in text
            or ticker.replace(".BO", "").lower() in text
        ):
            tickers.append(ticker)
            sector = company.get("sector", "").lower()
            if sector:
                sectors.append(sector)
    if not sectors:
        for sector, sector_query in SECTOR_QUERIES.items():
            if sector in text or sector_query.lower() in text:
                sectors.append(sector)
    return sorted(set(tickers)), sorted(set(sectors))


def _event_fingerprint(source: str, title: str, date: str) -> str:
    return hashlib.sha256(f"{source}|{title.strip().lower()}|{date}".encode("utf-8")).hexdigest()


def _to_event_docs(kind: str, query: str, articles: list) -> list:
    docs = []
    for article in articles:
        title = (article.get("title") or "").strip()
        if not title:
            continue
        event_date = article.get("date") or ""
        tickers, sectors = _extract_relevant_metadata(title, query)
        docs.append(
            {
                "fingerprint": _event_fingerprint(article.get("source", kind), title, event_date),
                "kind": kind,
                "query": query,
                "title": title,
                "source": article.get("source", kind),
                "event_date": event_date,
                "url": article.get("url", ""),
                "signal": _classify_event(title),
                "tickers": tickers,
                "sectors": sectors,
                "fetched_at": _now_utc(),
            }
        )
    return docs


def upsert_live_events(db, kind: str, query: str, articles: list) -> int:
    if db is None or not articles:
        return 0
    inserted = 0
    for doc in _to_event_docs(kind, query, articles):
        result = db["live_events"].update_one(
            {"fingerprint": doc["fingerprint"]},
            {"$set": doc},
            upsert=True,
        )
        if result.upserted_id is not None:
            inserted += 1
    return inserted


def ingest_queries(queries: list, db=None) -> dict:
    stats = {"queries": len(queries), "news_events": 0, "gdelt_events": 0}
    for query in queries:
        news = fetch_live_news(query, db=db)
        gdelt = fetch_gdelt_events(query, db=db)
        stats["news_events"] += upsert_live_events(db, "newsapi", query, news)
        stats["gdelt_events"] += upsert_live_events(db, "gdelt", query, gdelt)
    return stats


def ingest_default_event_set(db=None) -> dict:
    default_queries = [
        "India markets RBI SEBI oil war ceasefire",
        "India defense procurement military border tensions",
        "India oil crude LNG energy sanctions RBI inflation",
        "India banks RBI rates liquidity regulation SEBI",
        "India ports shipping Red Sea supply chain freight",
    ]
    for company in COMPANIES[:12]:
        default_queries.append(f"\"{company['name']}\" OR {company['ticker'].replace('.NS', '').replace('.BO', '')} stock India")
    deduped = list(dict.fromkeys(default_queries))
    return ingest_queries(deduped, db=db)


def get_recent_stored_events(message: str, db=None, portfolio_holdings: list | None = None, limit: int = 8) -> list:
    if db is None:
        return []
    companies = detect_companies(message, portfolio_holdings)
    tickers = {(holding.get("ticker") or "").upper() for holding in (portfolio_holdings or []) if holding.get("ticker")}
    tickers.update(company[1].upper() for company in companies)
    sectors = {(holding.get("sector") or "").lower() for holding in (portfolio_holdings or []) if holding.get("sector")}
    sectors.update(company[2].lower() for company in companies if len(company) > 2)
    macro_hits = _extract_macro_hits(message)

    query_filter = {"$or": []}
    if tickers:
        query_filter["$or"].append({"tickers": {"$in": sorted(tickers)}})
    if sectors:
        query_filter["$or"].append({"sectors": {"$in": sorted(sectors)}})
    for hit in macro_hits[:3]:
        query_filter["$or"].append({"query": {"$regex": re.escape(hit), "$options": "i"}})
        query_filter["$or"].append({"title": {"$regex": re.escape(hit), "$options": "i"}})
    if not query_filter["$or"]:
        query_filter = {}

    cursor = db["live_events"].find(query_filter).sort([("event_date", -1), ("fetched_at", -1)]).limit(limit)
    return list(cursor)


def _build_event_memory(message: str, db=None, portfolio_holdings: list | None = None) -> str:
    companies = detect_companies(message, portfolio_holdings)
    queries = _build_queries(message, companies, portfolio_holdings)

    ingest_queries(queries, db=db)

    seen_titles = set()
    combined = []
    for doc in get_recent_stored_events(message, db=db, portfolio_holdings=portfolio_holdings, limit=12):
        title_key = doc["title"].strip().lower()
        if title_key not in seen_titles:
            combined.append(
                {
                    "title": doc["title"],
                    "source": doc.get("source", ""),
                    "date": doc.get("event_date", ""),
                    "signal": doc.get("signal", "neutral"),
                }
            )
            seen_titles.add(title_key)

    if not combined:
        return ""

    combined = sorted(combined, key=lambda item: item.get("date", ""), reverse=True)[:10]
    lines = ["╔══ AUTONOMOUS LIVE EVENT MEMORY ══╗"]
    for article in combined[:8]:
        signal = article.get("signal") or _classify_event(article["title"])
        marker = "▲" if signal == "positive" else ("▼" if signal == "negative" else "•")
        lines.append(f"{marker} [{article.get('date', 'unknown')}] {article.get('source', '')}: {article['title']}")
    lines.append(
        "╚══ Treat these as the freshest relevant events. If ceasefire/de-escalation headlines appear, update the thesis immediately. ══╝"
    )
    return "\n".join(lines)


def build_context(message: str, db=None, portfolio_holdings: list | None = None) -> str:
    companies = detect_companies(message, portfolio_holdings)
    now = datetime.now().strftime("%d %b %Y %H:%M IST")
    blocks = []

    if companies:
        blocks.append(f"╔══ LIVE MARKET DATA — {now} ══╗")
        for name, ticker, sector, role in companies[:3]:
            snap = fetch_live_snapshot(ticker)
            if not snap:
                blocks.append(f"{name} ({ticker}) | {sector.upper()} | role={role} | Data unavailable")
                continue
            pct = f"{snap['pct_5d']:+.2f}%" if snap["pct_5d"] is not None else "n/a"
            trend = " → ".join(f"₹{price}" for price in snap["recent_closes"])
            blocks.append(
                f"{name} ({ticker}) | {sector.upper()} | role={role}\n"
                f"Current price: ₹{snap['live_price']} (live, NSE) | 5D: {pct}\n"
                f"52W high: ₹{snap['hi_52w']} | 52W low: ₹{snap['lo_52w']}\n"
                f"Recent closes: {trend}"
            )
        blocks.append("╚══ USE THESE EXACT NUMBERS. DO NOT INVENT PRICES. ══╝")

    event_memory = _build_event_memory(message, db=db, portfolio_holdings=portfolio_holdings)
    if event_memory:
        blocks.append(event_memory)

    return "\n\n".join(blocks).strip()

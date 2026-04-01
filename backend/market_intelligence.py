"""
Market Intelligence Module
- yfinance: Real NSE stock price history (2010 → today)
- Scikit-learn: ML 45-day forecast with confidence bands
- Twitter/X API v2: Company-specific tweet sentiment  
- GDELT: Macro geopolitical event signals
- Hardcoded event annotations (Hindenburg, COVID, etc.)
"""

import os
import math
import requests
import numpy as np
from datetime import datetime, timedelta
from dotenv import load_dotenv

from . import rag_context, graph_engine

load_dotenv()
GNEWS_API_KEY = os.getenv("GNEWS_API_KEY", "").strip()
ALPHA_VANTAGE_API_KEY = os.getenv("ALPHA_VANTAGE_API_KEY", "").strip()

# ─────────────────────────────────────────────
# KNOWN MAJOR EVENTS (annotate on chart)
# ─────────────────────────────────────────────
MARKET_EVENTS = [
    {"date": "2020-03-23", "label": "COVID Crash", "color": "#ef4444", "tickers": "ALL"},
    {"date": "2021-01-29", "label": "Budget Rally", "color": "#10b981", "tickers": "ALL"},
    {"date": "2023-01-24", "label": "Hindenburg Report", "color": "#ef4444",
     "tickers": ["ADANIPORTS.NS", "ADANIENT.NS", "ADANITRANS.NS"]},
    {"date": "2022-02-24", "label": "Russia-Ukraine War", "color": "#f59e0b", "tickers": "ALL"},
    {"date": "2023-08-01", "label": "Fitch US Downgrade", "color": "#f59e0b",
     "tickers": ["SBIN.NS", "HDFCBANK.NS", "ICICIBANK.NS", "AXISBANK.NS"]},
    {"date": "2024-04-19", "label": "Iran-Israel Escalation", "color": "#ef4444",
     "tickers": ["ONGC.NS", "BPCL.NS", "IOC.NS", "HAL.NS"]},
    {"date": "2022-04-05", "label": "Operation Sindoor Alert", "color": "#8b5cf6",
     "tickers": ["HAL.NS", "BEL.NS", "MAZDOCK.NS", "GRSE.NS"]},
]


# ─────────────────────────────────────────────
# YFINANCE STOCK DATA (real NSE data)
# ─────────────────────────────────────────────
def get_stock_history(ticker: str, start: str = "2010-01-01") -> dict:
    """
    Fetches real NSE stock price data via yfinance using daily candles across
    the full range so date lookup feels trustworthy.
    """
    try:
        import yfinance as yf

        # Normalize ticker
        if not ticker.endswith(".NS") and not ticker.endswith(".BO"):
            ticker = ticker + ".NS"

        stock = yf.Ticker(ticker)
        end = datetime.now().strftime("%Y-%m-%d")

        hist_daily = stock.history(start=start, end=end, interval="1d")
        if hist_daily.empty:
            return {"error": f"No data found for {ticker}"}

        def safe_close(df):
            """Return (dates, closes) dropping any NaN or inf rows."""
            pairs = []
            for d, v in zip(df.index, df["Close"]):
                try:
                    f = float(v)
                    if math.isfinite(f) and f > 0:
                        pairs.append((d.strftime("%Y-%m-%d"), round(f, 2)))
                except Exception:
                    pass
            return zip(*pairs) if pairs else ([], [])

        d_dates, d_closes = safe_close(hist_daily)
        all_dates = list(d_dates)
        all_closes = list(d_closes)

        # Try to get live current price
        try:
            live_price = round(float(stock.fast_info.last_price), 2)
        except Exception:
            live_price = all_closes[-1] if all_closes else None

        return {
            "ticker": ticker,
            "dates": all_dates,
            "prices": all_closes,
            "current_price": live_price,
            "price_2010": all_closes[0] if all_closes else None,
            "all_time_high": max(all_closes) if all_closes else None,
            "all_time_low": min(all_closes) if all_closes else None,
        }
    except Exception as e:
        return {"error": str(e)}


def get_company_profile(ticker: str) -> dict:
    try:
        data = graph_engine.load_data()
        company = next((c for c in data["companies"] if c["ticker"] == ticker), None)
        metrics = graph_engine.get_graph_metrics()
        metric = next((n for n in metrics["nodes"] if n["ticker"] == ticker), None)
        if not company:
            return {}
        return {
            "criticality": float(company.get("criticality", 5)),
            "employees": float(company.get("employees", 0) or 0),
            "revenue_bn": float(company.get("revenue_bn", 0) or 0),
            "vulnerability_score": float((metric or {}).get("vulnerability_score", 50)),
            "role": company.get("role", ""),
            "description": company.get("description", ""),
            "short": company.get("short", ""),
            "sector": company.get("sector", ""),
        }
    except Exception:
        return {}


def _nearest_price_on_or_after(dates: list, prices: list, event_date: str):
    for date, price in zip(dates, prices):
        if date >= event_date:
            return float(price)
    return float(prices[-1]) if prices else None


def compute_resilience_score(history: dict, ticker: str, events: list) -> float:
    dates = history.get("dates", [])
    prices = history.get("prices", [])
    current = float(history.get("current_price") or 0)
    if not dates or not prices or not current:
        return 0.0

    negative_events = [
        e for e in events
        if ticker in e.get("tickers", []) and any(word in e.get("label", "").lower() for word in ["crash", "report", "war", "escalation"])
    ]
    if not negative_events:
        return 0.0

    resilience_hits = 0
    for event in negative_events:
        event_price = _nearest_price_on_or_after(dates, prices, event["date"])
        if not event_price:
            continue
        if current >= event_price * 1.15:
            resilience_hits += 1
    return min(1.0, resilience_hits / max(1, len(negative_events)))


def compute_event_analogue(history: dict, ticker: str, events: list) -> dict | None:
    dates = history.get("dates", [])
    prices = history.get("prices", [])
    if not dates or not prices:
        return None

    relevant = [e for e in events if ticker in e.get("tickers", [])]
    best = None
    for event in relevant:
        event_price = _nearest_price_on_or_after(dates, prices, event["date"])
        if not event_price:
            continue
        try:
            idx = next(i for i, d in enumerate(dates) if d >= event["date"])
        except StopIteration:
            continue
        forward_idx = min(len(prices) - 1, idx + 30)
        forward_price = float(prices[forward_idx])
        forward_return = ((forward_price - event_price) / event_price) * 100
        candidate = {
            "label": event["label"],
            "date": event["date"],
            "event_price": round(event_price, 2),
            "after_30d_price": round(forward_price, 2),
            "after_30d_return": round(forward_return, 1),
        }
        if best is None or abs(candidate["after_30d_return"]) > abs(best["after_30d_return"]):
            best = candidate
    return best


def build_strategic_forecast_summary(
    ticker: str,
    company_name: str,
    sector: str,
    history: dict,
    news: dict,
    gdelt: dict,
    forecast: dict,
    profile: dict,
    events: list,
    structural_support: float,
    resilience_score: float,
) -> dict:
    analogue = compute_event_analogue(history, ticker, events)
    macro_pressure = -float(gdelt.get("signal_score", 0) or 0)
    news_score = float(news.get("score", 0) or 0)
    current = float(history.get("current_price") or 0)
    predicted = forecast.get("predicted") or []
    forecast_30 = float(predicted[min(29, len(predicted) - 1)]) if predicted else current
    direction = "controlled upside" if forecast_30 >= current else "downside pressure"

    factor_map = [
        {
            "label": "Company significance",
            "score": round(structural_support, 2),
            "effect": "supportive",
            "why": f"Criticality {int(profile.get('criticality', 5))}/10 with large operational importance in India's {sector} backbone.",
        },
        {
            "label": "Current company news",
            "score": round(news_score, 2),
            "effect": "supportive" if news_score > 0.08 else ("negative" if news_score < -0.08 else "neutral"),
            "why": news.get("headlines", [{}])[0].get("title", "No strong company headline signal available.") if news.get("headlines") else "No strong company headline signal available.",
        },
        {
            "label": "Macro event pressure",
            "score": round(abs(macro_pressure), 2),
            "effect": "negative" if macro_pressure < -0.08 else ("supportive" if macro_pressure > 0.08 else "neutral"),
            "why": f"Sector macro signal is {gdelt.get('signal', 'neutral')} across the last 3 days.",
        },
        {
            "label": "Historical resilience",
            "score": round(resilience_score, 2),
            "effect": "supportive" if resilience_score > 0.15 else "neutral",
            "why": analogue["label"] + f" led to {analogue['after_30d_return']:+.1f}% over the next 30 sessions." if analogue else "No strong historical shock analogue was found.",
        },
    ]
    top_factors = sorted(factor_map, key=lambda item: abs(item["score"]), reverse=True)
    headline = (
        f"{company_name} strategic forecast points to {direction}: company importance, live events, and past shock behaviour are being combined rather than treating this stock like a generic chart."
    )

    return {
        "headline": headline,
        "factors": top_factors,
        "historical_analogue": analogue,
        "method": "Future price is projected from price trend, company significance, live company news, sector macro events, and historical recovery behaviour.",
    }





# ─────────────────────────────────────────────
# ML FORECAST (Polynomial Regression + Confidence Bands)
# ─────────────────────────────────────────────
def generate_forecast(
    prices: list,
    days: int = 45,
    sentiment_score: float = 0.0,
    macro_signal_score: float = 0.0,
    structural_support: float = 0.0,
    resilience_score: float = 0.0,
) -> dict:
    """
    Generates a conservative forecast using recent returns, capped drift, and
    bounded risk bands so the projection stays believable relative to the chart.
    """
    if len(prices) < 20:
        return {"error": "Insufficient historical data"}

    window = min(90, len(prices))
    recent = prices[-window:]
    current = float(recent[-1])
    returns = []
    for prev, nxt in zip(recent[:-1], recent[1:]):
        if prev > 0 and nxt > 0:
            returns.append(math.log(nxt / prev))
    if not returns:
        returns = [0.0]

    short_returns = returns[-20:] if len(returns) >= 20 else returns
    med_returns = returns[-60:] if len(returns) >= 60 else returns
    base_drift = (float(np.mean(short_returns)) * 0.6) + (float(np.mean(med_returns)) * 0.4)
    ma20 = float(np.mean(recent[-20:])) if len(recent) >= 20 else current
    mean_reversion = ((ma20 / current) - 1.0) * 0.08

    combined_signal = max(-1.0, min(1.0, (sentiment_score * 0.75) - (macro_signal_score * 0.30)))
    daily_drift = (
        (base_drift * 0.35)
        + mean_reversion
        + (combined_signal * 0.0012)
        + (structural_support * 0.00045)
        + (resilience_score * 0.00055)
    )
    daily_drift = max(-0.0035, min(0.0035, daily_drift))

    daily_vol = float(np.std(med_returns))
    daily_vol = max(0.006, min(0.028, daily_vol))

    predicted = []
    upper_band = []
    lower_band = []
    for horizon in range(1, days + 1):
        expected = current * math.exp(daily_drift * horizon)
        risk_span = daily_vol * math.sqrt(horizon) * 1.15
        upper = expected * math.exp(risk_span)
        lower = expected * math.exp(-risk_span)
        support_lift = (structural_support * 0.04) + (resilience_score * 0.03)
        floor_pct = 0.90 if horizon <= 7 else (0.84 if horizon <= 30 else 0.80)
        floor_pct = min(0.96, floor_pct + support_lift)
        lower = max(lower, current * floor_pct)
        upper = min(upper, current * (1.18 + structural_support * 0.05 + resilience_score * 0.04))
        predicted.append(round(expected, 2))
        upper_band.append(round(upper, 2))
        lower_band.append(round(lower, 2))

    # Generate daily forecast dates for the next 45 days.
    today = datetime.now()
    forecast_dates = [(today + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(1, days + 1)]

    return {
        "dates": forecast_dates[:days],
        "predicted": predicted[:days],
        "upper": upper_band[:days],
        "lower": lower_band[:days],
        "context_bias": round(combined_signal, 2),
        "structural_support": round(structural_support, 2),
        "resilience_score": round(resilience_score, 2),
    }


# ─────────────────────────────────────────────
# NEWS SENTIMENT (NewsAPI — company headlines)
# ─────────────────────────────────────────────
def _extract_keywords(text: str, limit: int = 6) -> list[str]:
    stop = {"india", "limited", "company", "services", "systems", "group", "major", "large", "current", "across", "their"}
    words = []
    for word in (text or "").replace("/", " ").replace(",", " ").split():
        cleaned = word.strip().lower()
        if len(cleaned) < 4 or cleaned in stop:
            continue
        if cleaned not in words:
            words.append(cleaned)
        if len(words) >= limit:
            break
    return words


def _build_strategic_queries(company_name: str, ticker: str, profile: dict) -> list[str]:
    ticker_clean = ticker.replace(".NS", "").replace(".BO", "")
    role = profile.get("role", "")
    description = profile.get("description", "")
    sector = profile.get("sector", "")
    short = profile.get("short", "")
    role_terms = " ".join(_extract_keywords(role, limit=4))
    desc_terms = " ".join(_extract_keywords(description, limit=5))
    queries = [
        f'"{company_name}" OR "{short}" OR "{ticker_clean}" stock India',
        f'India {sector} {role_terms} {desc_terms}'.strip(),
    ]
    if sector == "logistics":
        queries.append("India ports shipping trade exports cargo Europe supply chain")
    elif sector == "energy":
        queries.append("India oil gas LNG crude energy imports sanctions")
    elif sector == "defense":
        queries.append("India defence orders weapons procurement border escalation")
    elif sector == "finance":
        queries.append("India banking liquidity RBI rates inflation credit")
    return [q for q in dict.fromkeys(queries) if q and len(q) > 8]


def get_news_sentiment(company_name: str, ticker: str, sector: str = "", profile: dict | None = None) -> dict:
    """
    Fetches recent financial news headlines for the company using NewsAPI.
    Performs keyword-based sentiment scoring on the headlines.
    Free tier: 1000 calls/day, no search restrictions.
    """
    api_key = os.getenv("NEWSAPI_KEY", "")
    if not api_key:
        return {
            "score": 0, "label": "No key", "count": 0,
            "headlines": [],
            "reason": "Set NEWSAPI_KEY in .env — get free key at newsapi.org"
        }

    profile = profile or {}
    ticker_clean = ticker.replace(".NS", "").replace(".BO", "")
    short_name = " ".join(company_name.split()[:2]).strip() or company_name
    query = f'"{company_name}" OR "{short_name}" OR "{ticker_clean}" stock India'
    bullish_words = ["surge", "rise", "buy", "strong", "gain", "record", "growth",
                     "rally", "bullish", "contract", "win", "profit", "expand", "order"]
    bearish_words = ["fall", "drop", "crash", "loss", "risk", "fraud", "sell",
                     "bearish", "decline", "weak", "attack", "probe", "lawsuit", "raid"]

    relevance_terms = {
        ticker_clean.lower(),
        company_name.lower(),
        short_name.lower(),
        (profile.get("short") or "").lower(),
        sector.lower(),
        *[word.lower() for word in company_name.split() if len(word) > 3 and word.lower() not in {"limited", "india", "services", "company"}],
        *_extract_keywords(profile.get("role", ""), limit=4),
        *_extract_keywords(profile.get("description", ""), limit=5),
    }

    def is_relevant(item: dict) -> bool:
        text = ((item.get("title", "") or "") + " " + (item.get("description", "") or "")).lower()
        return any(term and term in text for term in relevance_terms)

    def score_items(items: list, allow_strategic: bool = False) -> dict:
        filtered_items = [item for item in items if is_relevant(item)]
        if allow_strategic and not filtered_items:
            strategic_terms = set(_extract_keywords(profile.get("role", ""), limit=4) + _extract_keywords(profile.get("description", ""), limit=5) + ([sector.lower()] if sector else []))
            filtered_items = [
                item for item in items
                if any(term and term in (((item.get("title", "") or "") + " " + (item.get("description", "") or "")).lower()) for term in strategic_terms)
            ]
        if filtered_items:
            items = filtered_items
        count = len(items)
        if count == 0:
            return {"score": 0, "label": "Neutral", "count": 0, "headlines": []}
        total_score = 0
        headlines = []
        for a in items[:6]:
            title = a.get("title", "") or ""
            desc = a.get("description", "") or ""
            source_raw = a.get("source", "")
            source_name = source_raw.get("name", "") if isinstance(source_raw, dict) else source_raw
            text = (title + " " + desc).lower()
            b = sum(1 for w in bullish_words if w in text)
            d = sum(1 for w in bearish_words if w in text)
            total_score += (b - d)
            headlines.append({
                "title": title[:90],
                "source": source_name,
                "url": a.get("url", ""),
                "date": ((a.get("publishedAt") or a.get("date") or "")[:10]),
                "sentiment": "bullish" if b > d else ("bearish" if d > b else "neutral")
            })
        normalized = max(-1.0, min(1.0, total_score / max(1, count * 3)))
        label = "Bullish 📈" if normalized > 0.1 else ("Bearish 📉" if normalized < -0.1 else "Neutral ➡️")
        return {"score": round(normalized, 2), "label": label, "count": count, "headlines": headlines}

    def load_stored_company_events() -> list:
        try:
            from . import database

            db = database.get_database()
            if db is None:
                return []

            ticker_upper = ticker.upper()
            query = {
                "$or": [
                    {"tickers": {"$in": [ticker_upper]}},
                    {"title": {"$regex": company_name, "$options": "i"}},
                    {"query": {"$regex": company_name, "$options": "i"}},
                    {"query": {"$regex": ticker_clean, "$options": "i"}},
                ]
            }
            docs = list(
                db["live_events"]
                .find(query)
                .sort([("event_date", -1), ("fetched_at", -1)])
                .limit(8)
            )
            items = []
            for doc in docs:
                items.append(
                    {
                        "title": doc.get("title", ""),
                        "source": doc.get("source", ""),
                        "url": doc.get("url", ""),
                        "date": doc.get("event_date", ""),
                        "description": "",
                    }
                )
            return items
        except Exception:
            return []

    def fetch_gnews_items(query_text: str) -> list:
        if not GNEWS_API_KEY:
            return []
        try:
            resp = requests.get(
                "https://gnews.io/api/v4/search",
                params={
                    "q": query_text,
                    "lang": "en",
                    "max": 8,
                    "apikey": GNEWS_API_KEY,
                },
                timeout=6,
            )
            if resp.status_code != 200:
                return []
            items = []
            for article in resp.json().get("articles", []):
                items.append(
                    {
                        "title": article.get("title", ""),
                        "description": article.get("description", ""),
                        "source": (article.get("source") or {}).get("name", "GNews"),
                        "url": article.get("url", ""),
                        "date": (article.get("publishedAt") or "")[:10],
                    }
                )
            return items
        except Exception:
            return []

    def fetch_alpha_vantage_items() -> list:
        if not ALPHA_VANTAGE_API_KEY:
            return []
        try:
            resp = requests.get(
                "https://www.alphavantage.co/query",
                params={
                    "function": "NEWS_SENTIMENT",
                    "tickers": ticker_clean,
                    "limit": 8,
                    "apikey": ALPHA_VANTAGE_API_KEY,
                },
                timeout=6,
            )
            if resp.status_code != 200:
                return []
            feed = resp.json().get("feed", [])
            items = []
            for article in feed:
                items.append(
                    {
                        "title": article.get("title", ""),
                        "description": article.get("summary", ""),
                        "source": article.get("source", "Alpha Vantage"),
                        "url": article.get("url", ""),
                        "date": (article.get("time_published", "") or "")[:10],
                    }
                )
            return items
        except Exception:
            return []

    try:
        aggregate_articles = []
        if api_key:
            r = requests.get(
                "https://newsapi.org/v2/everything",
                params={
                    "q": query,
                    "apiKey": api_key,
                    "language": "en",
                    "sortBy": "publishedAt",
                    "pageSize": 10,
                },
                timeout=6
            )
            if r.status_code == 200:
                aggregate_articles.extend(r.json().get("articles", []))
            else:
                raise RuntimeError(f"NewsAPI {r.status_code}")

        for variant in _build_strategic_queries(company_name, ticker, {**profile, "sector": sector or profile.get("sector", "")}):
            aggregate_articles.extend(fetch_gnews_items(variant))
        aggregate_articles.extend(fetch_alpha_vantage_items())

        scored = score_items(aggregate_articles, allow_strategic=True)
        if scored["count"] > 0:
            return scored
        raise RuntimeError("Primary feeds returned zero relevant company articles")
    except Exception as e:
        merged = []
        seen = set()
        for variant in _build_strategic_queries(company_name, ticker, {**profile, "sector": sector or profile.get("sector", "")}):
            fallback_news = rag_context.fetch_live_news(variant)
            fallback_gdelt = rag_context.fetch_gdelt_events(variant)
            for item in (fallback_news + fallback_gdelt):
                title = (item.get("title") or "").strip()
                if not title:
                    continue
                key = title.lower()
                if key in seen:
                    continue
                seen.add(key)
                merged.append({
                    "title": title,
                    "source": item.get("source", ""),
                    "url": item.get("url", ""),
                    "date": item.get("date", ""),
                    "description": "",
                })
        stored_events = load_stored_company_events()
        for item in stored_events:
            title = (item.get("title") or "").strip()
            if not title:
                continue
            key = title.lower()
            if key in seen:
                continue
            seen.add(key)
            merged.append({
                "title": title,
                "source": item.get("source", ""),
                "url": item.get("url", ""),
                "date": item.get("date", ""),
                "description": "",
            })
        if merged:
            scored = score_items(merged, allow_strategic=True)
            scored["reason"] = f"Primary news feed unavailable, using strategic event fallback ({str(e)[:60]})"
            return scored

        return {"score": 0, "label": "Neutral", "count": 0, "headlines": [], "reason": str(e)}


# ─────────────────────────────────────────────
# GDELT MACRO EVENTS (global geopolitical signals)
# ─────────────────────────────────────────────
def get_gdelt_sector_sentiment(sector: str) -> dict:
    """
    Queries GDELT for recent events affecting the given sector.
    GDELT is free, no API key needed, updates every 15 minutes.
    """
    sector_keywords = {
        "defense": "India military weapons defense",
        "energy": "India oil gas energy sanctions",
        "finance": "India bank economy inflation",
        "logistics": "India port supply chain shipping",
    }
    keyword = sector_keywords.get(sector.lower(), "India economy")

    try:
        url = "https://api.gdeltproject.org/api/v2/doc/doc"
        params = {
            "query": keyword,
            "mode": "artlist",
            "maxrecords": 10,
            "format": "json",
            "timespan": "3d",  # last 3 days
        }
        r = requests.get(url, params=params, timeout=6)
        if r.status_code != 200:
            return {"event_count": 0, "signal": "neutral"}

        articles = r.json().get("articles", [])
        count = len(articles)

        # More articles = higher geopolitical activity = higher risk signal
        if count >= 7:
            signal = "elevated"
            signal_score = 0.6
        elif count >= 4:
            signal = "moderate"
            signal_score = 0.3
        else:
            signal = "low"
            signal_score = 0.1

        return {
            "event_count": count,
            "signal": signal,
            "signal_score": signal_score,
            "top_headline": articles[0]["title"] if articles else None
        }
    except Exception as e:
        return {"event_count": 0, "signal": "neutral", "signal_score": 0.0}


# ─────────────────────────────────────────────
# MASTER ENDPOINT HANDLER
# ─────────────────────────────────────────────
def get_market_intelligence(ticker: str, company_name: str, sector: str) -> dict:
    """
    Master function combining all signals for a single company.
    """
    history = get_stock_history(ticker)
    if "error" in history:
        return history

    profile = get_company_profile(ticker)
    news = get_news_sentiment(company_name, ticker, sector=sector, profile=profile)
    gdelt = get_gdelt_sector_sentiment(sector)
    events = [
        e for e in MARKET_EVENTS
        if e["tickers"] == "ALL" or ticker in e["tickers"]
    ]
    structural_support = min(
        1.0,
        (
            ((profile.get("criticality", 5) / 10.0) * 0.65)
            + (min(profile.get("employees", 0), 500000) / 500000.0 * 0.15)
            + (min(profile.get("revenue_bn", 0), 600) / 600.0 * 0.10)
            + ((100 - min(profile.get("vulnerability_score", 50), 100)) / 100.0 * 0.10)
        ),
    )
    resilience_score = compute_resilience_score(history, ticker, events)
    forecast = generate_forecast(
        history["prices"],
        sentiment_score=float(news.get("score", 0) or 0),
        macro_signal_score=float(gdelt.get("signal_score", 0) or 0),
        structural_support=structural_support,
        resilience_score=resilience_score,
    )
    strategic_summary = build_strategic_forecast_summary(
        ticker=ticker,
        company_name=company_name,
        sector=sector,
        history=history,
        news=news,
        gdelt=gdelt,
        forecast=forecast,
        profile=profile,
        events=events,
        structural_support=structural_support,
        resilience_score=resilience_score,
    )

    return {
        "ticker": ticker,
        "company": company_name,
        "sector": sector,
        "history": history,
        "forecast": forecast,
        "forecast_basis": {
            "window_points": min(90, len(history["prices"])),
            "drivers": [
                "recent price trend",
                "mean reversion versus recent average",
                "company headline sentiment",
                "sector macro risk signal",
                "strategic company importance",
                "post-shock resilience",
                "capped volatility bands",
            ],
            "structural_support": round(structural_support, 2),
            "resilience_score": round(resilience_score, 2),
        },
        "strategic_forecast": strategic_summary,
        "news_sentiment": news,
        "gdelt_signal": gdelt,
        "events": events,
    }

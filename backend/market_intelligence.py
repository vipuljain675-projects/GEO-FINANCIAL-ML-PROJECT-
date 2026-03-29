"""
Market Intelligence Module
- yfinance: Real NSE stock price history (2010 → today)
- Scikit-learn: ML 45-day forecast with confidence bands
- Twitter/X API v2: Company-specific tweet sentiment  
- GDELT: Macro geopolitical event signals
- Hardcoded event annotations (Hindenburg, COVID, etc.)
"""

import os
import json
import math
import random
import requests
import numpy as np
from datetime import datetime, timedelta
from urllib.parse import unquote
from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import PolynomialFeatures
from sklearn.pipeline import make_pipeline
from dotenv import load_dotenv

load_dotenv()

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
    Fetches real NSE stock price data via yfinance.
    Uses weekly candles for long history + daily for last year to get accurate recent price.
    """
    try:
        import yfinance as yf

        # Normalize ticker
        if not ticker.endswith(".NS") and not ticker.endswith(".BO"):
            ticker = ticker + ".NS"

        stock = yf.Ticker(ticker)
        end = datetime.now().strftime("%Y-%m-%d")

        # Long history: weekly candles from 2010
        hist_weekly = stock.history(start=start, end=end, interval="1wk")
        if hist_weekly.empty:
            return {"error": f"No data found for {ticker}"}

        # Recent 1 year: daily candles for accurate current price
        one_year_ago = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
        hist_daily = stock.history(start=one_year_ago, end=end, interval="1d")

        # Merge: weekly for long history, daily for last year
        cutoff = one_year_ago
        weekly_filtered = hist_weekly[hist_weekly.index.strftime("%Y-%m-%d") < cutoff]

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

        w_dates, w_closes = safe_close(weekly_filtered)
        d_dates, d_closes = safe_close(hist_daily)

        all_dates = list(w_dates) + list(d_dates)
        all_closes = list(w_closes) + list(d_closes)

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





# ─────────────────────────────────────────────
# ML FORECAST (Polynomial Regression + Confidence Bands)
# ─────────────────────────────────────────────
def generate_forecast(prices: list, days: int = 45) -> dict:
    """
    Generates a realistic ML forecast using Polynomial Regression.
    Uses last 104 weeks (2 years) of data for trend-fitting.
    Returns predicted prices + upper/lower confidence bands.
    """
    if len(prices) < 20:
        return {"error": "Insufficient historical data"}

    # Use last 2 years (104 weeks) for the model
    window = min(104, len(prices))
    recent = prices[-window:]

    X = np.arange(len(recent)).reshape(-1, 1)
    y = np.array(recent)

    # Polynomial degree 3 captures realistic market curves (not just linear)
    model = make_pipeline(PolynomialFeatures(degree=3), LinearRegression())
    model.fit(X, y)

    # Future indices for forecast
    future_X = np.arange(len(recent), len(recent) + days).reshape(-1, 1)
    predicted = model.predict(future_X).tolist()

    # Confidence bands from historical volatility
    residuals = y - model.predict(X)
    std_dev = float(np.std(residuals))
    volatility_scale = 1.0  # grows over time

    upper_band = []
    lower_band = []
    for i, p in enumerate(predicted):
        scale = std_dev * (1 + i * 0.02)  # widening uncertainty
        upper_band.append(round(p + scale, 2))
        lower_band.append(round(p - scale, 2))

    predicted = [round(p, 2) for p in predicted]

    # Generate forecast dates (weekly)
    today = datetime.now()
    forecast_dates = [(today + timedelta(weeks=i)).strftime("%Y-%m-%d") for i in range(1, days // 7 + 2)][:days // 7]

    return {
        "dates": forecast_dates,
        "predicted": predicted[:len(forecast_dates)],
        "upper": upper_band[:len(forecast_dates)],
        "lower": lower_band[:len(forecast_dates)],
    }


# ─────────────────────────────────────────────
# NEWS SENTIMENT (NewsAPI — company headlines)
# ─────────────────────────────────────────────
def get_news_sentiment(company_name: str, ticker: str) -> dict:
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

    search_name = company_name.split()[0]  # e.g. "Adani" from "Adani Ports"
    ticker_clean = ticker.replace(".NS", "").replace(".BO", "")
    query = f'{search_name} OR {ticker_clean} stock'

    try:
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
        if r.status_code != 200:
            return {"score": 0, "label": "Neutral", "count": 0, "headlines": [],
                    "reason": f"NewsAPI {r.status_code}"}

        articles = r.json().get("articles", [])
        count = len(articles)
        if count == 0:
            return {"score": 0, "label": "Neutral", "count": 0, "headlines": []}

        bullish_words = ["surge", "rise", "buy", "strong", "gain", "record", "growth",
                         "rally", "bullish", "contract", "win", "profit", "expand", "order"]
        bearish_words = ["fall", "drop", "crash", "loss", "risk", "fraud", "sell",
                         "bearish", "decline", "weak", "attack", "probe", "lawsuit", "raid"]

        total_score = 0
        headlines = []
        for a in articles[:6]:
            title = a.get("title", "") or ""
            desc = a.get("description", "") or ""
            text = (title + " " + desc).lower()
            b = sum(1 for w in bullish_words if w in text)
            d = sum(1 for w in bearish_words if w in text)
            total_score += (b - d)
            headlines.append({
                "title": title[:90],
                "source": a.get("source", {}).get("name", ""),
                "url": a.get("url", ""),
                "sentiment": "bullish" if b > d else ("bearish" if d > b else "neutral")
            })

        normalized = max(-1.0, min(1.0, total_score / (count * 3)))
        label = "Bullish 📈" if normalized > 0.1 else ("Bearish 📉" if normalized < -0.1 else "Neutral ➡️")

        return {
            "score": round(normalized, 2),
            "label": label,
            "count": count,
            "headlines": headlines
        }
    except Exception as e:
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

    forecast = generate_forecast(history["prices"])
    news = get_news_sentiment(company_name, ticker)
    gdelt = get_gdelt_sector_sentiment(sector)

    # Filter events relevant to this ticker
    events = [
        e for e in MARKET_EVENTS
        if e["tickers"] == "ALL" or ticker in e["tickers"]
    ]

    return {
        "ticker": ticker,
        "company": company_name,
        "sector": sector,
        "history": history,
        "forecast": forecast,
        "news_sentiment": news,
        "gdelt_signal": gdelt,
        "events": events,
    }


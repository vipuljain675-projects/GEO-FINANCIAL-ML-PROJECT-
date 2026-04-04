# Artha Sentinel

Artha Sentinel is a strategic market and infrastructure intelligence platform built around one idea: the Indian economy is not just a list of stocks, it is a living network of logistics, energy, finance, defense, policy, and geopolitical dependencies.

The platform combines live market tracking, event-aware AI analysis, strategic company profiling, portfolio intelligence, and a cinematic command-center interface. It is designed to help a user answer questions like:

- What changed in the last few days that affects a company?
- Which holding is my biggest risk right now?
- Should I buy more, hold, trim, or redeploy capital?
- How do war, trade deals, inflation, oil shocks, and defense policy affect Indian strategic companies?

This is not a generic stock dashboard. It is a position-aware intelligence system for strategic Indian equities.

## What The Project Does

Artha Sentinel has five major working layers:

- `Overview`
  - a live operating picture of critical sectors and system threat posture
- `Network Graph`
  - dependency mapping across India's critical listed companies
- `Scenario Engine`
  - attack, disruption, and cascade-style stress simulation
- `Market Intelligence`
  - past and present tracking with company news, macro signals, and event-marked charts
- `Strategic Forecast`
  - a separate future-facing forecast view built on price trend, company significance, event pressure, and historical analogues
- `AI Analyst`
  - a strategic question-answering agent for macro, company, and geopolitical intelligence
- `Personal Advisor`
  - a portfolio-aware copilot that uses holdings, buy prices, risk mode, and live context to advise whether to buy, hold, trim, or avoid

## Why It Exists

Traditional dashboards treat companies as isolated tickers. Artha Sentinel treats them as strategic entities.

Examples:

- Adani Ports is not just a port stock. It sits at the intersection of trade flows, maritime chokepoints, energy logistics, and India’s export capacity.
- ONGC is not just an oil stock. It is an upstream strategic producer whose earnings react differently to crude shocks than downstream refiners like IOC or BPCL.
- HAL is not just a defense stock. Its relevance depends on procurement cycles, execution capacity, indigenous defense priorities, and project-specific developments like AMCA.

That is the core philosophy of the project: price should be interpreted through structure, not only charts.

## Core Features

### 1. Strategic Company Universe

The platform tracks a curated universe of Indian strategic companies across:

- defense
- energy
- finance
- logistics

Each company has a role in the wider national system, such as:

- maritime trade gateways
- crude oil production
- fuel distribution
- private liquidity and banking
- air defense and aerospace manufacturing

### 2. Live Market Intelligence

For each tracked company, the platform can show:

- current price
- long-term historical chart
- date inspector for past prices
- event ribbon with major historical shocks
- company news
- macro signal context

This section is intentionally focused on `past + present`, not future prediction.

### 3. Strategic Forecast Engine

Forecasting is separated from tracking.

The forecast engine combines:

- recent price behavior
- company significance
- live company and sector events
- macro pressure
- historical shock/recovery analogues

This allows the system to think more like:

- is the thesis broken?
- is this temporary fear?
- is this a buy-on-weakness setup?
- is this hold, not add?

instead of blindly extrapolating a chart.

### 4. AI Analyst

The AI Analyst is the strategic research layer. It can answer questions about:

- geopolitics
- supply chains
- company-specific developments
- defense programmes
- macro-economic risk
- strategic dependencies

It now includes live-search-style handling for current factual claims, especially for time-sensitive topics like:

- government approvals
- contracts
- defence programmes
- project participation
- current company developments

### 5. Personal Advisor

The Personal Advisor is where the project becomes position-aware.

It does not only look at a stock. It looks at:

- your buy price
- your quantity
- your unrealized P&L
- your concentration
- your investor mode
- current live context

That means it can distinguish:

- a good company with a bad entry
- a bad company with temporary strength
- a strong winner that should be trimmed
- a conviction holding that should be held, not averaged blindly

It can also express actions more intelligently:

- `BUY MORE`
- `BUY ON WEAKNESS`
- `HOLD`
- `HOLD, DO NOT ADD`
- `TRIM ON STRENGTH`
- `EXIT IF THESIS BROKEN`

## How To Use It

### Step 1: Run the app

```bash
python3 -m uvicorn backend.app:app --host 127.0.0.1 --port 8000 --reload
```

Then open:

```text
http://127.0.0.1:8000
```

### Step 2: Explore the system

Suggested flow:

1. Open `Market Intelligence` and inspect a company’s history and current context.
2. Open `Strategic Forecast` to see the future-facing thesis and projected path.
3. Use `AI Analyst` for company, sector, or geopolitical questions.
4. Add holdings in `Personal Advisor`.
5. Set investor preferences and test the portfolio copilot.

### Step 3: Ask the right kind of questions

Good examples:

- `What changed in the last few days that affects Adani Ports?`
- `As of 4 Feb 2026, has HAL been kicked out of the AMCA programme?`
- `If I bought Adani Ports at 1580 instead of 612, should I hold, add, or reduce?`
- `ONGC is low because of war fear, but if that fear fades or crude stays high, is this a buy-on-weakness case?`
- `Which holding is my biggest risk right now?`

## Setup

### Environment

Create a `.env` file in the project root.

Typical keys used by the project:

```bash
SECRET_KEY=your_secret_key
GEMINI_API_KEY=your_gemini_key
GROQ_API_KEY=your_groq_key
GNEWS_API_KEY=your_gnews_key
ALPHA_VANTAGE_API_KEY=your_alpha_vantage_key
ACLED_EMAIL=your_acled_email
ACLED_PASSWORD=your_acled_password
```

### Installation

```bash
pip install -r requirements.txt
```

### Notes

- Frontend is served directly by FastAPI.
- MongoDB is used for users, portfolios, chat memory, live events, and preferences.
- Live prices and company intelligence are integrated into the same UI.

## Education

This section is for anyone trying to understand what this project is doing from an engineering or learning perspective.

### What You Learn From This Project

Artha Sentinel is not just a UI build. It is a compact system design exercise in:

- event-aware AI
- portfolio intelligence
- strategic company modeling
- frontend product design
- live data integration
- memory-aware chat systems

It teaches an important concept:

`good investing AI is not only about prices; it is about context, structure, and decision framing`

### The ML / Intelligence Philosophy

The project intentionally avoids pretending that one pure ML curve can explain everything.

Instead, the intelligence stack is hybrid:

- `market behavior`
  - trend
  - volatility
  - recent price movement
- `company structure`
  - significance to India
  - sector role
  - strategic criticality
- `event layer`
  - live news
  - macro events
  - geopolitical developments
- `historical analogue layer`
  - what happened to this company or sector under similar shocks
- `portfolio layer`
  - entry price
  - concentration
  - investor style

This is why the project can reason differently for:

- `Adani Ports bought at ₹612`
- `Adani Ports bought at ₹1580`

even though the stock is the same.

### What The Forecast Is Actually Based On

The future-price logic is not magic and it is not perfect prediction.

It is a strategic projection built from:

- recent price trend
- company significance
- current company/sector news
- macro pressure
- event memory
- historical recovery behavior

This is closer to:

- `disciplined scenario forecasting`

than:

- `guaranteed target price prediction`

### Why Separate Market Intelligence From Strategic Forecast

This project deliberately separates:

- `tracking`
- from
- `forecasting`

Because:

- current and past prices are market facts
- future price is a model output

That separation makes the product more honest and easier to understand.

## Codebase Guide

### Backend

- [backend/app.py](/Users/vipuljain675/Documents/StrategicShield/backend/app.py)
  - FastAPI entrypoint, API routes, portfolio intelligence, chat orchestration
- [backend/llm.py](/Users/vipuljain675/Documents/StrategicShield/backend/llm.py)
  - Gemini/Groq orchestration, system prompt, live-search-aware answer generation
- [backend/rag_context.py](/Users/vipuljain675/Documents/StrategicShield/backend/rag_context.py)
  - event memory, live context building, news/event ingestion
- [backend/market_intelligence.py](/Users/vipuljain675/Documents/StrategicShield/backend/market_intelligence.py)
  - market data, company news, strategic forecast inputs, chart data
- [backend/database.py](/Users/vipuljain675/Documents/StrategicShield/backend/database.py)
  - Mongo setup and collection/index initialization
- [backend/graph_engine.py](/Users/vipuljain675/Documents/StrategicShield/backend/graph_engine.py)
  - dependency graph logic
- [backend/threat_engine.py](/Users/vipuljain675/Documents/StrategicShield/backend/threat_engine.py)
  - sector threat summaries
- [backend/ml_advanced.py](/Users/vipuljain675/Documents/StrategicShield/backend/ml_advanced.py)
  - scenario, threat forecast, and cluster logic

### Frontend

- [frontend/index.html](/Users/vipuljain675/Documents/StrategicShield/frontend/index.html)
  - main application structure and all major views
- [frontend/css/style.css](/Users/vipuljain675/Documents/StrategicShield/frontend/css/style.css)
  - core app styling and brand/splash presentation
- [frontend/css/market.css](/Users/vipuljain675/Documents/StrategicShield/frontend/css/market.css)
  - market intelligence and forecast view styling
- [frontend/js/main.js](/Users/vipuljain675/Documents/StrategicShield/frontend/js/main.js)
  - main UI logic, personal advisor, preferences, auth state, portfolio flows
- [frontend/js/chat.js](/Users/vipuljain675/Documents/StrategicShield/frontend/js/chat.js)
  - AI Analyst chat behavior and thinking/progress states
- [frontend/js/market.js](/Users/vipuljain675/Documents/StrategicShield/frontend/js/market.js)
  - market charts, forecast charts, inspectors, and live company context
- [frontend/js/graph.js](/Users/vipuljain675/Documents/StrategicShield/frontend/js/graph.js)
  - network graph rendering and interaction
- [frontend/js/audio.js](/Users/vipuljain675/Documents/StrategicShield/frontend/js/audio.js)
  - ambient/splash audio controls

### Data / Profiles

- [backend/data/companies.json](/Users/vipuljain675/Documents/StrategicShield/backend/data/companies.json)
  - strategic company definitions, sectors, roles, criticality, dependencies

## Suggested Future Improvements

- stronger multi-source live news reliability
- structured event-scoring engine for all 50 companies
- better source ranking and credibility filtering
- clearer confidence and thesis-state visualization
- test suite for position logic and forecast reasoning
- explicit source cards with links in the UI

## Final Note

Artha Sentinel was built to feel like a real strategic operating system, not just another finance demo.

Its strongest idea is simple:

`markets move through structure, conflict, policy, and psychology — not price charts alone.`

"""
SENTINEL LLM — powered by Gemini 2.5 Flash (google-genai SDK).
Falls back to Groq/Llama-3.3-70b if Gemini is unavailable.
"""
import os
import re
from dotenv import load_dotenv

load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

# ─── Primary Gemini model ──────────────────────────────────────────────────────
GEMINI_MODEL = "gemini-2.5-flash"  # Confirmed available on free tier

# ─── System Prompt ─────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are SENTINEL — an elite AI strategic analyst embedded within India's National Security Council and Strategic Intelligence Directorate. Clearance: COSMIC TOP SECRET.

CURRENT DATE: March 28, 2026.

╔══════════════════════════════════════════╗
⚠ CRITICAL DATA RULE
╚══════════════════════════════════════════╝
If the chat includes a LIVE MARKET DATA block:
→ Use ONLY those exact prices. NEVER invent different numbers.
→ Cite the price clearly: "Current price: ₹X (live, NSE)"

If asked for a price and NO live data is present:
→ Use your search/knowledge. Clearly state date context.
→ NEVER guess a price — say "check Market Intelligence tab for live NSE data"

If the user asks about a time-sensitive factual claim, policy decision, government approval, project award, contract loss, regulation, management change, or says "as of today/latest/current":
→ Verify it with live web search before answering.
→ If live verification is unavailable, say that clearly.
→ NEVER deny or confirm a current claim from stale memory alone.

═══════════════════════════════════════════
⚡ 2026 GEOPOLITICAL GROUND TRUTH
═══════════════════════════════════════════

1. IRAN-ISRAEL-USA WEST ASIA CONFLICT:
   - ROOT CAUSE: Oct 7, 2023 — Hamas launched surprise attack on Israel from Gaza.
   - ESCALATION: Iran, Hezbollah, Houthis opened additional fronts through 2024.
   - Apr 2024: Iran fired ~300 drones & missiles directly at Israel for the first time.
   - Oct 2024: India-China LAC buffer zones agreed; tensions de-escalated on that border.
   - 2025-2026: Conflict is ongoing; US 5th Fleet engaged; Strait of Hormuz threatened.
   - Indian logistics (ADANIPORTS, CONCOR): Red Sea rerouting = 40% higher shipping costs
   - Brent crude volatile $85-$110/barrel → supports upstream producers like ONGC, but can hurt refiners/distributors like BPCL and IOC
   - Defense surge: HAL, BEL, GRSE on elevated procurement orders

2. ADANI GROUP (Post-Hindenburg Jan 2023 → 2026):
   - Hindenburg short attack Jan 2023: stocks crashed 40-60%
   - GQG Partners $1.9B investment (Mar 2023): recovery began
   - Current 2026 weakness = Red Sea disruption + SEBI overhang, NOT Hindenburg
   - ADANIENT now eyeing data centre partnerships with Meta/Google

3. INDIA-CHINA LAC: Buffer zones agreed Oct 2024; PLA buildup continues; HAL/BDL on high alert
4. INDIA ECONOMY 2026: GDP ~6.8%, Rupee ₹88-92/USD, RBI rates steady
5. PLI scheme bearing fruit: BHARATFORG, M&M, L&T seeing strong order books

═══════════════════════════════════════════
🏭 INDIA'S 50 CRITICAL ENTITIES
═══════════════════════════════════════════
DEFENSE: HAL, BEL, BDL, MAZDOCK, GRSE, COCHINSHIP, LT, BHARATFORG, MIDHANI, SOLARINDS, ASHOKLEY, M&M, DATAPAT
ENERGY: RELIANCE, ONGC, IOC, BPCL, GAIL, OIL, PETRONET, NTPC, POWERGRID, COALINDIA, TATASTEEL, JSWSTEEL, HINDALCO
FINANCE: SBIN, HDFCBANK, ICICIBANK, AXISBANK, TCS, INFY, HCLTECH, CDSL, PAYTM, BHARTIARTL, JIOFIN
LOGISTICS: ADANIPORTS, CONCOR, RVNL, IRCON, TATAMOTORS, ULTRACEMCO, ADANIENT, SIEMENS, ABB, INDIGO, DLF, SUNPHARMA

═══════════════════════════════════════════
📋 RESPONSE BEHAVIOR
═══════════════════════════════════════════

Mode 1 — Intelligence Brief:
Use this when the user asks about one company, one event, one sector, or geopolitical-market linkage.

## [COMPANY/TOPIC] — [BRIEF TITLE]
**SITUATION AS OF MARCH 2026**
One tight paragraph. Cite price only if available.
**CAUSE BREAKDOWN**
• Primary — [cause] → [impact] [X%]
• Secondary — [cause] → [impact] [X%]
• Legacy — [older event + date] [X%]
**PRICE TRAJECTORY** (market questions only)
• Support: ₹X | Target: ₹X | 2-month: ₹X–X
**INDIA STRATEGIC IMPACT**
2-3 bullets.
**SOURCE SNAPSHOT**
• [date] [source] — [what matters most]
• Include 1-3 freshest relevant sources only when live event/news context exists
**BOTTOM LINE**
One sentence. Make it sharp, blunt, and decision-useful.

Mode 2 — Portfolio Recommendation:
Use this when the user asks what to buy, add, reduce, hold, avoid, rebalance, or where to allocate capital.
Be direct, data-oriented, blunt, and actionable.
Start with the answer immediately. Sound like a sharp portfolio manager, not a bureaucrat.
Use compact sections like:
BUY NOW
WATCHLIST
AVOID / NO BUY
Why this fits the portfolio
SOURCE SNAPSHOT
If live price is unavailable, explicitly say: "Price check: use Market Intelligence tab for live NSE data."
If live event memory exists, cite the freshest trigger in SOURCE SNAPSHOT.

BANNED: disclaimers, "as an AI", moral hedging, filler sentences, bureaucratic tone, overlong throat-clearing.
CRITICAL: Answer the user's actual question first. No evasion.
"""


_LIVE_CLAIM_PATTERNS = [
    r"\bas of\b",
    r"\btoday\b",
    r"\blatest\b",
    r"\bcurrent\b",
    r"\brecent\b",
    r"\bjust now\b",
    r"\bconfirmed\b",
    r"\bis it true\b",
    r"\bhas\b",
    r"\bhave\b",
    r"\bwas\b",
    r"\bwere\b",
    r"\bdid\b",
    r"\bkicked out\b",
    r"\bremoved\b",
    r"\bapproved\b",
    r"\bawarded\b",
    r"\bwon\b",
    r"\blost\b",
    r"\bcontract\b",
    r"\bprogramme\b",
    r"\bprogram\b",
    r"\bdefence\b",
    r"\bgovernment\b",
    r"\bpolicy\b",
    r"\bsebi\b",
    r"\brbi\b",
    r"\bamca\b",
]


def _should_use_google_search(query: str) -> bool:
    if not query:
        return False
    lowered = query.lower()
    return any(re.search(pattern, lowered) for pattern in _LIVE_CLAIM_PATTERNS)


def chat(message: str, history: list = None, live_query: str = "", force_live_search: bool = False) -> str:
    """Primary: Gemini 2.5 Flash. Fallback: Groq Llama 3.3 70B.

    Never raise raw provider errors back into FastAPI routes. If both providers
    fail, return a readable degraded-mode message instead of a 500.
    """
    use_google_search = force_live_search or _should_use_google_search(live_query or message)

    if GEMINI_API_KEY:
        try:
            return _gemini_chat(message, history, use_google_search=use_google_search)
        except Exception as e:
            err = str(e)
            if use_google_search:
                return (
                    "SENTINEL could not complete live verification for this current claim right now. "
                    "Please retry in a few seconds."
                )
            if GROQ_API_KEY:
                try:
                    return _groq_chat(message, history)
                except Exception as groq_err:
                    return (
                        "SENTINEL response channel degraded.\n\n"
                        f"Primary model error: {err[:180]}\n"
                        f"Fallback model error: {str(groq_err)[:180]}\n\n"
                        "Try again in a few seconds."
                    )
            return f"SENTINEL response channel degraded. Primary model error: {err[:180]}"

    if GROQ_API_KEY:
        try:
            return _groq_chat(message, history)
        except Exception as groq_err:
            return f"SENTINEL response channel degraded. Fallback model error: {str(groq_err)[:180]}"

    return "⚠️ SENTINEL offline — no API keys configured."


def _gemini_chat(message: str, history: list = None, use_google_search: bool = False) -> str:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=GEMINI_API_KEY)

    contents = []
    for h in (history or [])[-10:]:
        role = "user" if h["role"] == "user" else "model"
        contents.append(types.Content(role=role, parts=[types.Part(text=h["content"])]))
    contents.append(types.Content(role="user", parts=[types.Part(text=message)]))

    config_kwargs = {
        "system_instruction": SYSTEM_PROMPT,
        "temperature": 0.75,
        "max_output_tokens": 8192,
    }
    if use_google_search:
        config_kwargs["tools"] = [types.Tool(google_search=types.GoogleSearch())]
    config = types.GenerateContentConfig(**config_kwargs)

    print(f"--- CALLING GEMINI ---")
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=contents,
        config=config,
    )
    
    print("--- GEMINI RESPONSE ---")
    try:
        finish_reason = getattr(response.candidates[0], 'finish_reason', 'None')
        print("Finish Reason:", finish_reason)
        if finish_reason == 'SAFETY' or finish_reason == 'OTHER':
            raise Exception(f"Gemini Blocked: {finish_reason}")
    except (IndexError, AttributeError) as e:
        print("No candidates in response:", e)
        raise Exception("Gemini returned no candidates")

    try:
        text = response.text
        if not text or len(text) < 10:
             raise Exception("Gemini returned empty/too short response")
        print(f"RAW TEXT LEN: {len(text)}")
        print("--- END GEMINI ---")
        return text
    except Exception as e:
        print("Error getting response text:", e)
        raise Exception(f"Gemini Text Error: {str(e)}")


def _groq_chat(message: str, history: list = None) -> str:
    if not GROQ_API_KEY:
        return "⚠️ SENTINEL offline — no API keys configured."
    from groq import Groq
    client = Groq(api_key=GROQ_API_KEY)
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for h in (history or [])[-8:]:
        messages.append({"role": h["role"], "content": h["content"]})
    messages.append({"role": "user", "content": message})
    resp = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=messages,
        max_tokens=2000,
        temperature=0.75,
    )
    return resp.choices[0].message.content

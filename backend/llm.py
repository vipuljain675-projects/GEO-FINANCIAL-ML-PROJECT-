"""
SENTINEL LLM — powered by Gemini 2.5 Flash (google-genai SDK).
Falls back to Groq/Llama-3.3-70b if Gemini is unavailable.
"""
import os
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
   - Brent crude volatile $85-$110/barrel → hurts BPCL, ONGC, IOC
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
**BOTTOM LINE**
One sentence.

Mode 2 — Portfolio Recommendation:
Use this when the user asks what to buy, add, reduce, hold, avoid, rebalance, or where to allocate capital.
Be direct, data-oriented, blunt, and actionable.
Start with the answer immediately. Do not dodge.
Use compact sections like:
BUY NOW
WATCHLIST
AVOID / NO BUY
Why this fits the portfolio
If live price is unavailable, explicitly say: "Price check: use Market Intelligence tab for live NSE data."

BANNED: disclaimers, "as an AI", moral hedging, filler sentences.
CRITICAL: Answer the user's actual question first. No evasion.
"""


def chat(message: str, history: list = None) -> str:
    """Primary: Gemini 2.5 Flash. Fallback: Groq Llama 3.3 70B."""
    if GEMINI_API_KEY:
        try:
            return _gemini_chat(message, history)
        except Exception as e:
            err = str(e)
            # Silent fallback on quota/rate errors
            if "429" in err or "quota" in err.lower() or "exhausted" in err.lower():
                return _groq_chat(message, history, note="⚡ [Groq fallback — Gemini rate limited] ")
            return _groq_chat(message, history, note=f"⚡ [Groq fallback — {err[:60]}] ")

    return _groq_chat(message, history)


def _gemini_chat(message: str, history: list = None) -> str:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=GEMINI_API_KEY)

    contents = []
    for h in (history or [])[-10:]:
        role = "user" if h["role"] == "user" else "model"
        contents.append(types.Content(role=role, parts=[types.Part(text=h["content"])]))
    contents.append(types.Content(role="user", parts=[types.Part(text=message)]))

    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        temperature=0.75,
        max_output_tokens=8192,
    )

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


def _groq_chat(message: str, history: list = None, note: str = "") -> str:
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
    return note + resp.choices[0].message.content

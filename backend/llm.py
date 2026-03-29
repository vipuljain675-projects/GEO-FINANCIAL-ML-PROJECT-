import os
from groq import Groq

client = None

def get_client():
    global client
    if client is None:
        api_key = os.getenv("GROQ_API_KEY", "")
        if not api_key:
            return None
        client = Groq(api_key=api_key)
    return client

SYSTEM_PROMPT = """You are SENTINEL — a top-secret AI strategic analyst for India's National Security Council.
You specialize in critical infrastructure protection, threat assessment, and geopolitical analysis.
Your analysis covers 50 of India's most strategically important companies across defense, energy, finance, and logistics.

You give direct, precise, intelligence-grade responses. You identify threats, assess vulnerabilities, recommend countermeasures, and analyze inter-company dependencies.

You know that:
- Defense sector (HAL, BEL, BDL, MAZDOCK, GRSE, COCHINSHIP, LT, BHARATFORG, MIDHANI, ASTRAL, ASHOKLEY, M&M, SOLARINDS, DATAPAT) = air/sea/land warfare capability
- Energy sector (RELIANCE, ONGC, IOC, BPCL, GAIL, OIL, PETRONET, NTPC, POWERGRID, COALINDIA, TATASTEEL, JSWSTEEL, HINDALCO) = economic and military fuel
- Finance sector (SBIN, HDFCBANK, ICICIBANK, AXISBANK, TCS, INFY, HCLTECH, CDSL, PAYTM, BHARTIARTL, JIOFIN) = economic nervous system
- Logistics sector (ADANIPORTS, CONCOR, RVNL, IRCON, TATAMOTORS, ULTRACEMCO, ADANIENT, SIEMENS, ABB, INDIGO, DLF, SUNPHARMA) = physical supply chain

Keep responses under 300 words unless asked for deep analysis. No fluff. Use military/intelligence vocabulary.
"""

def chat(message: str, history: list = None) -> str:
    cli = get_client()
    if cli is None:
        return "⚠️ SENTINEL offline — GROQ_API_KEY not configured. Set it in your environment to activate AI analysis."

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if history:
        for h in history[-6:]:
            messages.append({"role": h["role"], "content": h["content"]})
    messages.append({"role": "user", "content": message})

    try:
        response = cli.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            max_tokens=600,
            temperature=0.7,
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"⚠️ Analysis failed: {str(e)}"

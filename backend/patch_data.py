import json
from pathlib import Path

# The new metadata mapping ticker against Leader, Valuation, and Employees
METADATA = {
    "HAL.NS": {"leader": "C.B. Ananthakrishnan", "valuation_t": 3.8, "employees": 28000},
    "BDL.NS": {"leader": "Commodore A. Madhavarao", "valuation_t": 0.9, "employees": 3200},
    "BEL.NS": {"leader": "Bhanu Prakash Srivastava", "valuation_t": 2.1, "employees": 9000},
    "MAZDOCK.NS": {"leader": "Sanjeev Singhal", "valuation_t": 0.8, "employees": 3500},
    "LT.NS": {"leader": "S.N. Subrahmanyan", "valuation_t": 5.2, "employees": 350000},
    "RELIANCE.NS": {"leader": "Mukesh Ambani", "valuation_t": 19.5, "employees": 400000},
    "ONGC.NS": {"leader": "Arun Kumar Singh", "valuation_t": 3.5, "employees": 26000},
    "NTPC.NS": {"leader": "Gurdeep Singh", "valuation_t": 3.2, "employees": 17000},
    "GAIL.NS": {"leader": "Sandeep Kumar Gupta", "valuation_t": 1.4, "employees": 4800},
    "SBIN.NS": {"leader": "Dinesh Kumar Khara", "valuation_t": 6.8, "employees": 235000},
    "HDFCBANK.NS": {"leader": "Sashidhar Jagdishan", "valuation_t": 11.5, "employees": 175000},
    "TCS.NS": {"leader": "K. Krithivasan", "valuation_t": 14.2, "employees": 600000},
    "ADANIPORTS.NS": {"leader": "Karan Adani", "valuation_t": 2.8, "employees": 3000},
    "CONCOR.NS": {"leader": "Sanjay Swarup", "valuation_t": 0.6, "employees": 1500},
    "TATAMOTORS.NS": {"leader": "Girish Wagh", "valuation_t": 3.6, "employees": 80000}
}

DATA_PATH = Path("/Users/vipuljain675/.gemini/antigravity/playground/charged-exoplanet/backend/data/companies.json")

def patch_data():
    with open(DATA_PATH, "r") as f:
        data = json.load(f)
        
    for comp in data["companies"]:
        ticker = comp["ticker"]
        if ticker in METADATA:
            comp.update(METADATA[ticker])
            
    with open(DATA_PATH, "w") as f:
        json.dump(data, f, indent=2)

if __name__ == "__main__":
    patch_data()
    print("Database patched with VAJRA Leader/Valuation metadata.")

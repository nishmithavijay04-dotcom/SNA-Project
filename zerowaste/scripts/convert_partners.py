"""Convert the researched Excel file into data/partners.csv (the app's schema).
Run once:  python scripts/convert_partners.py
Coordinates are APPROXIMATE area-level points typed in by hand (not geocoded).
Check/fix them in data/partners.csv (Google Maps: right-click pin -> click the numbers)."""
import re, sys, os
import pandas as pd

SRC = os.path.join(os.path.dirname(__file__), "..", "data", "source_partners.xlsx")
OUT = os.path.join(os.path.dirname(__file__), "..", "data", "partners.csv")

# organisation (as in the Excel) -> (lat, lon, quality)
APPROX = "approx (area centre)"
TWO = "approx (two addresses listed)"
COORDS = {
 "Bangalore Food Bank / Feeding Bangalore Foundation": (13.1010, 77.5960, APPROX),
 "Rise Against Hunger India": (13.0230, 77.6410, APPROX),
 "Roti Charity Trust": (12.9230, 77.5880, APPROX),
 "The Public Fridge / The Public Foundation": (12.9165, 77.6100, APPROX),
 "Ashiana Food Bank / Al-Aman Educational & Welfare Trust": (13.0010, 77.6150, TWO),
 "Amrutha Bindu": (12.9720, 77.7480, APPROX),
 "Vallalar Poor Feeding": (13.0075, 77.6960, APPROX),
 "The Akshaya Patra Foundation": (13.0010, 77.5500, APPROX),
 "Vidyaranya": (12.9890, 77.6010, TWO),
 "Yuktha Charitable Trust": (13.0230, 77.5950, APPROX),
 "Snehashraya Foundation": (13.0150, 77.6700, APPROX),
 "Mamatheya Madilu Social Foundation": (13.0430, 77.6070, APPROX),
 "Vara Foundations": (12.8900, 77.5850, APPROX),
 "INCAFO Charitable Foundation": (13.0400, 77.6450, APPROX),
 "Rishika Charitable Trust": (12.9170, 77.5450, APPROX),
 "FEED INDIA / Arya Ved Trust": (13.0140, 77.5780, APPROX),
 "ISKCON Bengaluru Nitya Annadana Hall": (13.0098, 77.5511, APPROX),
 "Adarane Charitable Trust": (13.1250, 77.6200, APPROX),
 "Rahmath Group": (13.0030, 77.6060, APPROX),
 "Kritagyata Trust": (13.1000, 77.5900, APPROX),
 "Atria Foundation – No One Goes Hungry Bengaluru": (13.0350, 77.5980, APPROX),
 "Deshabhakti Foundation": (12.9170, 77.4830, APPROX),
 "RAKVIH Foundation": (13.1005, 77.5960, APPROX),
 "Adarsh Seva Kendra Foundation": (12.9150, 77.5560, APPROX),
 "Yashodha Education And Charitable Trust": (12.8900, 77.6300, APPROX),
 "Hosa Sadhane Angavikalara Seva Charitable Trust": (12.8870, 77.6030, APPROX),
 "Fly Higher NGO – FHI": (12.9900, 77.5880, APPROX),
}  # Robin Hood Army & Swabhimaan NGO: no address in source -> left blank on purpose

EMAIL = re.compile(r"^[\w.+-]+@[\w-]+(\.[\w-]+)+$")

def clean_emails(v):
    if pd.isna(v): return ""
    toks = [t.strip() for t in re.split(r"[;,]", str(v)) if t.strip()]
    return "; ".join(t for t in toks if EMAIL.match(t))

def tri(v):
    s = "" if pd.isna(v) else str(v).strip()
    if re.match(r"^Yes\b", s): return "yes"
    if re.match(r"^No\b", s): return "no"      # \b so that "Not confirmed" is NOT read as "No"
    return "unconfirmed"

def surplus_level(v):
    s = "" if pd.isna(v) else str(v).strip()
    if re.match(r"^Yes\b", s): return "yes"
    if re.match(r"^Not\b", s) or not s: return "unconfirmed"
    return "likely"          # partnership / donation-centred, intake rules still unclear

def conf(v):
    s = str(v)
    return "High" if s.startswith("High") else "Medium/High" if s.startswith("Medium/High") else "Medium"

def main():
    d = pd.read_excel(SRC, sheet_name=0)
    key = d["Organization"].str.split(" / ").str[0].str.strip().str.lower()
    d = d[~key.duplicated(keep="first")].reset_index(drop=True)       # drops duplicate Ashiana row
    rows = []
    for _, r in d.iterrows():
        lat, lon, q = COORDS.get(r["Organization"], (None, None, "none"))
        rows.append({
            "name": r["Organization"], "type": r["Type"], "area": str(r["Area"]).replace(", Bengaluru", ""),
            "address": r["Address"], "latitude": lat, "longitude": lon, "coord_quality": q,
            "phone": "" if pd.isna(r["Phone"]) else str(r["Phone"]).strip(),
            "email": clean_emails(r["Email"]), "website": "" if pd.isna(r["Website"]) else r["Website"],
            "accepts_surplus": surplus_level(r["Accepts surplus food"]),
            "accepts_cooked": tri(r["Cooked food"]), "pickup": tri(r["Pickup/collection"]),
            "accepts_nonveg": "unknown", "capacity_kg": "", "pickup_start": "", "pickup_end": "",
            "verified": "no", "last_checked": "", "source_confidence": conf(r["Verification"]),
            "cooked_note": str(r["Cooked food"])[:160] if not pd.isna(r["Cooked food"]) else "",
            "source_url": "" if pd.isna(r["Source"]) else r["Source"],
        })
    out = pd.DataFrame(rows)
    out.to_csv(OUT, index=False, encoding="utf-8-sig")
    print(f"Wrote {len(out)} partners -> {OUT}")
    print("with location:", out.latitude.notna().sum(), "| no location:", out.latitude.isna().sum())
    print(out.accepts_surplus.value_counts().to_dict(), out.accepts_cooked.value_counts().to_dict())

if __name__ == "__main__":
    main()

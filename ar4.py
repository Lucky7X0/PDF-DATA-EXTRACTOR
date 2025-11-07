import streamlit as st
import pdfplumber
import re
import pandas as pd
from io import BytesIO

st.set_page_config(page_title="Account-based PDF Extractor", layout="wide")
st.title("📄 Clean Account-Based PDF Extractor")

st.write("""
This tool extracts **Account Number**, **Patient Name**, **Date of Service**, and **CPT Codes** from PDFs where each section starts with `Account: ####`.

🧠 Notes:
- Ignores irrelevant uppercase text like `SECONDARY`, `PRIMARY`, `DOL PAY`.
- Ensures only **one row per account** — no duplicates.
""")

# --- Upload PDF ---
uploaded_file = st.file_uploader("📤 Upload your PDF", type=["pdf"])
if not uploaded_file:
    st.info("👆 Upload a PDF file to start.")
    st.stop()

# --- Extract all text ---
full_text = ""
with pdfplumber.open(uploaded_file) as pdf:
    for page in pdf.pages:
        txt = page.extract_text()
        if txt:
            full_text += txt + "\n"

if not full_text.strip():
    st.error("❌ No text found in PDF.")
    st.stop()

# --- Split by "Account:" ---
blocks = re.split(r"(?=Account:\s*\d{4})", full_text)
records = []

# --- Regex patterns ---
account_pattern = re.compile(r"Account:\s*(\d{4,5})")

date_pattern = re.compile(r"\b\d{2}/\d{2}/\d{4}\b")
# ✅ CPT: only 5-digit or 7-char format like 90000-3D
# CPT = exactly 5 digits OR 5 digits followed by hyphen + 2 alphanumeric chars
cpt_pattern = re.compile(r"\b\d{5}(?:-[A-Z0-9]{2})?\b", re.IGNORECASE)


ignore_words = {
    "SECONDARY", "PRIMARY", "DOL", "PAY", "INSURANCE", "PPO", "PLAN",
    "TOTALS", "BALANCE", "OVERPD", "GENESICARE", "YES", "NO", "FLORIDA", "USA"
}

# --- Helper functions ---
def extract_patient_name(block):
    """
    Extracts patient name:
    1️⃣ Prefer fully uppercase names.
    2️⃣ Fallback to Title/Mixed case if uppercase not found.
    """
    ignore_words = {
        "SECONDARY", "PRIMARY", "DOL", "PAY", "INSURANCE", "PPO", "PLAN",
        "TOTALS", "BALANCE", "OVERPD", "GENESISC", "GENESICARE", "FLORIDA",
        "USA", "NOT", "USE", "BCBS", "FBU"
    }

    # Step 1: Fully UPPERCASE names (e.g., CORBITT III, MORRIS E)
    upper_names = re.findall(r"\b[A-Z ,.'\-]{3,}\b", block)
    clean_upper = [
        n.strip()
        for n in upper_names
        if not any(w in ignore_words for w in n.split())
        and len(n.split()) >= 2
    ]
    if clean_upper:
        return max(clean_upper, key=len).title()

    # Step 2: Mixed/Title case fallback (e.g., McCrodden, Susan J)
    mixed_names = re.findall(
        r"[A-Z][a-z]+(?: [A-Z][a-z]+)*, [A-Z][a-z]+(?: [A-Z]\.?)?",
        block
    )
    mixed_clean = [
        m for m in mixed_names if not any(w.upper() in ignore_words for w in m.split())
    ]
    if mixed_clean:
        return max(mixed_clean, key=len).strip()

    return ""

def extract_date_of_service(block):
    """Extracts first valid service date after Account line."""
    account_line_match = re.search(r"Account:\s*\d{4}.*?\n(.*)", block)
    if account_line_match:
        possible_line = account_line_match.group(1)
        date_match = date_pattern.search(possible_line)
        if date_match:
            return date_match.group(0)

    dates = date_pattern.findall(block)
    if dates:
        return dates[0]
    return ""

def extract_cpt_codes(block):
    """Extracts only valid CPT codes (5 digits or 90000-3D style)."""
    cpt_codes = re.findall(cpt_pattern, block)
    if not cpt_codes:
        return ""
    unique_codes = sorted(set(cpt_codes))
    return ", ".join(unique_codes)

# --- Parse each block ---
for block in blocks:
    if not block.strip():
        continue

    acc_match = account_pattern.search(block)
    if not acc_match:
        continue
    account_no = acc_match.group(1)

    patient_name = extract_patient_name(block)
    date_of_service = extract_date_of_service(block)
    cpt_joined = extract_cpt_codes(block)

    if not cpt_joined:
        continue

    records.append({
        "Account Number": account_no,
        "Patient Name": patient_name,
        "Date of Service": date_of_service,
        "CPT Codes": cpt_joined
    })

# --- DataFrame ---
df = pd.DataFrame(records)
df.drop_duplicates(subset=["Account Number"], inplace=True)
df.reset_index(drop=True, inplace=True)

# --- Display results ---
if df.empty:
    st.warning("⚠️ No valid account data extracted. Check PDF structure.")
else:
    st.success(f"✅ Extracted {len(df)} clean account records!")
    st.dataframe(df, use_container_width=True)

    # --- Excel download ---
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Extracted")

    st.download_button(
        label="📥 Download Excel",
        data=buffer.getvalue(),
        file_name="clean_accounts.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

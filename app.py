import streamlit as st
from supabase import create_client
import pandas as pd
from datetime import date
import logging
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

# ---------------- LOGGING ---------------- #
logging.basicConfig(level=logging.INFO)
logging.info("App started")

# ---------------- SECRETS ---------------- #
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
OWNER_PASSWORD = st.secrets["OWNER_PASSWORD"]

# ---------------- SUPABASE ---------------- #
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ---------------- STREAMLIT CONFIG ---------------- #
st.set_page_config(page_title="Gas Cylinder Manager", layout="wide")

# ---------------- AUTH ---------------- #
if "auth" not in st.session_state:
    st.session_state.auth = False

if not st.session_state.auth:
    st.title("🔐 Owner Login")
    pwd = st.text_input("Password", type="password")
    if st.button("Login"):
        if pwd == OWNER_PASSWORD:
            st.session_state.auth = True
            st.rerun()
        else:
            st.error("Wrong password")
    st.stop()

# ---------------- HELPERS ---------------- #
def get_shops():
    return supabase.table("shops").select("*").order("shop_name").execute().data

def get_last_balance(shop_id):
    res = supabase.table("daily_transactions") \
        .select("balance_after_transaction") \
        .eq("shop_id", shop_id) \
        .order("created_at", desc=True) \
        .limit(1).execute().data
    return float(res[0]["balance_after_transaction"]) if res else 0.0

def generate_pdf(shop, summary_df):
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)

    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, 800, "Gas Cylinder Delivery Report")

    c.setFont("Helvetica", 10)
    c.drawString(50, 780, f"Shop: {shop['shop_name']}")
    c.drawString(50, 765, f"Mobile: {shop['mobile_number']}")
    c.drawString(50, 750, f"Address: {shop['address']}")

    y = 710
    c.setFont("Helvetica-Bold", 11)
    c.drawString(50, y, "Summary")
    y -= 20

    c.setFont("Helvetica", 10)
    for _, row in summary_df.iterrows():
        c.drawString(50, y, row["Metric"])
        c.drawString(300, y, str(row["Value"]))
        y -= 18

    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer

def build_whatsapp_text(shop, summary):
    return f"""
Gas Cylinder Delivery Report

Shop: {shop['shop_name']}
Period: {summary['From Date']} to {summary['To Date']}

Cylinders Delivered: {summary['Cylinders Delivered']}
Empty Received: {summary['Empty Cylinders Received']}
Empty Pending: {summary['Empty Cylinders Pending']}

Total Amount: ₹{summary['Total Amount (₹)']}
Paid (Cash): ₹{summary['Paid in Cash (₹)']}
Paid (UPI): ₹{summary['Paid in UPI (₹)']}
Total Paid: ₹{summary['Total Paid (₹)']}
Balance Due: ₹{summary['Balance (₹)']}

Thank you.
""".strip()

# ---------------- UI ---------------- #
st.title("🛢️ Gas Cylinder Delivery Management")

tabs = st.tabs(["🏪 Shops", "📝 Daily Entry", "📊 Reports"])

# ==================== SHOPS ==================== #
with tabs[0]:
    st.subheader("➕ Add Shop")

    with st.form("add_shop"):
        name = st.text_input("Shop Name")
        mobile = st.text_input("Mobile Number")
        address = st.text_area("Address")
        if st.form_submit_button("Add Shop") and name:
            supabase.table("shops").insert({
                "shop_name": name,
                "mobile_number": mobile,
                "address": address
            }).execute()
            st.success("Shop added")

    st.subheader("📋 Shops")
    st.dataframe(pd.DataFrame(get_shops()), use_container_width=True)

# ==================== DAILY ENTRY ==================== #
with tabs[1]:
    st.subheader("📝 Daily Entry")

    shops = get_shops()
    shop_map = {s["shop_name"]: s for s in shops}
    shop_name = st.selectbox("Shop", shop_map.keys())
    shop = shop_map[shop_name]

    txn_date = st.date_input("Date", date.today())
    d, e = st.columns(2)
    delivered = d.number_input("Cylinders Delivered", 0)
    empty = e.number_input("Empty Received", 0)

    p, c, u = st.columns(3)
    price = p.number_input("Price per Cylinder", 0.0)
    cash = c.number_input("Cash Paid", 0.0)
    upi = u.number_input("UPI Paid", 0.0)

    total_amount = delivered * price
    prev_balance = get_last_balance(shop["shop_id"])
    balance = prev_balance + total_amount - (cash + upi)

    st.info(f"Total Amount: ₹{total_amount:,.2f}")
    st.warning(f"Balance After Entry: ₹{balance:,.2f}")

    if st.button("Save Entry"):
        supabase.table("daily_transactions").insert({
            "shop_id": shop["shop_id"],
            "transaction_date": txn_date.isoformat(),
            "cylinders_delivered": delivered,
            "empty_cylinders_received": empty,
            "price_per_cylinder": price,
            "total_amount": total_amount,
            "payment_cash": cash,
            "payment_upi": upi,
            "balance_after_transaction": balance
        }).execute()
        st.success("Saved")

# ==================== REPORTS ==================== #
with tabs[2]:
    st.subheader("📊 Report")

    shop_name = st.selectbox("Shop", shop_map.keys(), key="rshop")
    shop = shop_map[shop_name]

    f, t = st.columns(2)
    from_date = f.date_input("From")
    to_date = t.date_input("To")

    if st.button("Generate Report"):
        data = supabase.table("daily_transactions") \
            .select("*") \
            .eq("shop_id", shop["shop_id"]) \
            .gte("transaction_date", from_date.isoformat()) \
            .lte("transaction_date", to_date.isoformat()) \
            .order("transaction_date") \
            .execute().data

        if not data:
            st.warning("No records")
            st.stop()

        df = pd.DataFrame(data)
        st.dataframe(df, use_container_width=True)

        # -------- SUMMARY LOGIC -------- #
        summary = {
            "Shop Name": shop_name,
            "From Date": from_date.strftime("%d-%m-%Y"),
            "To Date": to_date.strftime("%d-%m-%Y"),
            "Cylinders Delivered": int(df["cylinders_delivered"].sum()),
            "Empty Cylinders Received": int(df["empty_cylinders_received"].sum()),
            "Empty Cylinders Pending": int(df["cylinders_delivered"].sum() - df["empty_cylinders_received"].sum()),
            "Total Amount (₹)": float(df["total_amount"].sum()),
            "Paid in Cash (₹)": float(df["payment_cash"].sum()),
            "Paid in UPI (₹)": float(df["payment_upi"].sum()),
            "Total Paid (₹)": float(df["payment_cash"].sum() + df["payment_upi"].sum()),
            "Balance (₹)": float(df.iloc[-1]["balance_after_transaction"])
        }

        summary_df = pd.DataFrame(summary.items(), columns=["Metric", "Value"])

        st.subheader("📌 Summary")
        st.table(summary_df)

        # -------- PDF -------- #
        pdf = generate_pdf(shop, summary_df)
        st.download_button(
            "📄 Export Summary as PDF",
            data=pdf,
            file_name=f"{shop_name}_report.pdf",
            mime="application/pdf"
        )

        # -------- WHATSAPP TEXT -------- #
        st.subheader("📱 Copy to WhatsApp")
        whatsapp_text = build_whatsapp_text(shop, summary)
        st.text_area("Message", whatsapp_text, height=250)

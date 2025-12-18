import streamlit as st
from supabase import create_client
import pandas as pd
from datetime import date
import logging

# ---------------- LOGGING (TERMINAL DEBUG) ---------------- #
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

logging.info("🚀 App started")

# ---------------- CONFIG ---------------- #
try:
    SUPABASE_URL = st.secrets["SUPABASE_URL"]
    SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
    OWNER_PASSWORD = st.secrets["OWNER_PASSWORD"]
    logging.info("✅ Secrets loaded successfully")
except Exception as e:
    logging.error("❌ Failed to load secrets")
    st.error("Secrets not found. Check Streamlit Cloud settings.")
    st.stop()

# ---------------- SUPABASE CLIENT ---------------- #
try:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    logging.info("✅ Supabase client created")
except Exception as e:
    logging.error(f"❌ Supabase connection failed: {e}")
    st.error("Supabase connection failed")
    st.stop()

# ---------------- STREAMLIT CONFIG ---------------- #
st.set_page_config(page_title="Gas Cylinder Manager", layout="wide")

# ---------------- AUTH ---------------- #
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.title("🔐 Owner Login")

    password = st.text_input("Enter Password", type="password")

    if st.button("Login"):
        if password == OWNER_PASSWORD:
            st.session_state.authenticated = True
            logging.info("🔓 Owner logged in")
            st.success("Login successful")
            st.rerun()
        else:
            logging.warning("❌ Wrong password attempt")
            st.error("Wrong password")

    st.stop()

# ---------------- HELPER FUNCTIONS ---------------- #
def get_shops():
    logging.info("📥 Fetching shops")
    res = supabase.table("shops").select("*").order("shop_name").execute()
    return res.data

def get_last_balance(shop_id):
    logging.info(f"📥 Fetching last balance for shop {shop_id}")
    res = supabase.table("daily_transactions") \
        .select("balance_after_transaction") \
        .eq("shop_id", shop_id) \
        .order("created_at", desc=True) \
        .limit(1) \
        .execute()

    if res.data:
        return float(res.data[0]["balance_after_transaction"])
    return 0.0

# ---------------- UI ---------------- #
st.title("🛢️ Gas Cylinder Delivery Management System")

tabs = st.tabs(["🏪 Shops", "📝 Daily Entry", "📊 Reports"])

# ===================== SHOPS ===================== #
with tabs[0]:
    st.subheader("➕ Add New Shop")

    with st.form("add_shop"):
        shop_name = st.text_input("Shop Name")
        mobile = st.text_input("Mobile Number")
        address = st.text_area("Address")

        submitted = st.form_submit_button("Add Shop")

        if submitted:
            if not shop_name:
                st.error("Shop name is required")
            else:
                supabase.table("shops").insert({
                    "shop_name": shop_name,
                    "mobile_number": mobile,
                    "address": address
                }).execute()

                logging.info(f"🏪 Shop added: {shop_name}")
                st.success("Shop added successfully")

    st.divider()
    st.subheader("📋 All Shops")

    shops = get_shops()
    if shops:
        st.dataframe(pd.DataFrame(shops), use_container_width=True)
    else:
        st.info("No shops found")

# ===================== DAILY ENTRY ===================== #
with tabs[1]:
    st.subheader("📝 Daily Cylinder Entry")

    shops = get_shops()
    if not shops:
        st.warning("Add shops first")
        st.stop()

    shop_map = {s["shop_name"]: s["shop_id"] for s in shops}

    shop_name = st.selectbox("Select Shop", shop_map.keys())
    shop_id = shop_map[shop_name]

    txn_date = st.date_input("Transaction Date", date.today())

    col1, col2, col3 = st.columns(3)

    with col1:
        delivered = st.number_input("Cylinders Delivered", min_value=0)
        empty_received = st.number_input("Empty Cylinders Received", min_value=0)

    with col2:
        price = st.number_input("Price per Cylinder", min_value=0.0)

    with col3:
        cash = st.number_input("Payment Cash", min_value=0.0)
        upi = st.number_input("Payment UPI", min_value=0.0)

    total_amount = delivered * price
    total_paid = cash + upi
    prev_balance = get_last_balance(shop_id)
    balance = prev_balance + total_amount - total_paid

    st.info(f"💰 Total Amount: ₹{total_amount:,.2f}")
    st.info(f"📌 Previous Balance: ₹{prev_balance:,.2f}")
    st.warning(f"🔴 Balance After Entry: ₹{balance:,.2f}")

    if st.button("Save Entry"):
        logging.info(f"💾 Saving transaction for {shop_name}")

        supabase.table("daily_transactions").insert({
            "shop_id": shop_id,
            "transaction_date": txn_date,
            "cylinders_delivered": delivered,
            "empty_cylinders_received": empty_received,
            "price_per_cylinder": price,
            "total_amount": total_amount,
            "payment_cash": cash,
            "payment_upi": upi,
            "balance_after_transaction": balance
        }).execute()

        logging.info("✅ Transaction saved")
        st.success("Transaction saved successfully")

# ===================== REPORTS ===================== #
with tabs[2]:
    st.subheader("📊 Shop Report")

    shop_name = st.selectbox("Select Shop", shop_map.keys(), key="report_shop")
    shop_id = shop_map[shop_name]

    col1, col2 = st.columns(2)
    with col1:
        from_date = st.date_input("From Date")
    with col2:
        to_date = st.date_input("To Date")

    if st.button("Generate Report"):
        logging.info(f"📊 Generating report for {shop_name}")

        res = supabase.table("daily_transactions") \
            .select("*") \
            .eq("shop_id", shop_id) \
            .gte("transaction_date", from_date) \
            .lte("transaction_date", to_date) \
            .order("transaction_date") \
            .execute()

        if not res.data:
            st.warning("No records found")
            logging.warning("⚠️ No records for selected range")
        else:
            df = pd.DataFrame(res.data)

            st.dataframe(df, use_container_width=True)

            st.subheader("📌 Summary")
            st.metric("Cylinders Delivered", int(df["cylinders_delivered"].sum()))
            st.metric("Empty Received", int(df["empty_cylinders_received"].sum()))
            st.metric("Total Amount", f"₹{df['total_amount'].sum():,.2f}")
            st.metric("Total Paid", f"₹{(df['payment_cash'] + df['payment_upi']).sum():,.2f}")
            st.metric("Balance", f"₹{df.iloc[-1]['balance_after_transaction']:,.2f}")

            logging.info("✅ Report generated successfully")

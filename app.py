import streamlit as st
from supabase import create_client
import pandas as pd
from datetime import date
import logging

# ---------------- LOGGING ---------------- #
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

logging.info("🚀 App started")

# ---------------- SECRETS ---------------- #
try:
    SUPABASE_URL = st.secrets["SUPABASE_URL"]
    SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
    OWNER_PASSWORD = st.secrets["OWNER_PASSWORD"]
    logging.info("✅ Secrets loaded")
except Exception:
    st.error("Secrets not found. Add them in Streamlit Cloud → Settings → Secrets")
    logging.error("❌ Secrets missing")
    st.stop()

# ---------------- SUPABASE ---------------- #
try:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    logging.info("✅ Supabase connected")
except Exception as e:
    st.error("Supabase connection failed")
    logging.error(e)
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
            logging.info("🔓 Login success")
            st.rerun()
        else:
            logging.warning("❌ Wrong password")
            st.error("Wrong password")
    st.stop()

# ---------------- HELPERS ---------------- #
def get_shops():
    res = supabase.table("shops").select("*").order("shop_name").execute()
    return res.data

def get_last_balance(shop_id):
    res = supabase.table("daily_transactions") \
        .select("balance_after_transaction") \
        .eq("shop_id", shop_id) \
        .order("created_at", desc=True) \
        .limit(1).execute()

    return float(res.data[0]["balance_after_transaction"]) if res.data else 0.0

# ---------------- UI ---------------- #
st.title("🛢️ Gas Cylinder Delivery Management")

tabs = st.tabs(["🏪 Shops", "📝 Daily Entry", "📊 Reports"])

# ==================== SHOPS ==================== #
with tabs[0]:
    st.subheader("➕ Add New Shop")

    with st.form("add_shop"):
        shop_name = st.text_input("Shop Name")
        mobile = st.text_input("Mobile Number")
        address = st.text_area("Address")

        if st.form_submit_button("Add Shop"):
            if not shop_name:
                st.error("Shop name is required")
            else:
                supabase.table("shops").insert({
                    "shop_name": shop_name,
                    "mobile_number": mobile,
                    "address": address
                }).execute()
                logging.info(f"🏪 Shop added: {shop_name}")
                st.success("Shop added")

    st.divider()
    st.subheader("📋 Shops List")
    shops = get_shops()
    st.dataframe(pd.DataFrame(shops), use_container_width=True)

# ==================== DAILY ENTRY ==================== #
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

    c1, c2, c3 = st.columns(3)

    with c1:
        delivered = st.number_input("Cylinders Delivered", min_value=0)
        empty_received = st.number_input("Empty Cylinders Received", min_value=0)

    with c2:
        price = st.number_input("Price per Cylinder", min_value=0.0)

    with c3:
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
        logging.info("💾 Saving transaction")

        supabase.table("daily_transactions").insert({
            "shop_id": shop_id,
            "transaction_date": txn_date.isoformat(),  # FIXED
            "cylinders_delivered": delivered,
            "empty_cylinders_received": empty_received,
            "price_per_cylinder": price,
            "total_amount": total_amount,
            "payment_cash": cash,
            "payment_upi": upi,
            "balance_after_transaction": balance
        }).execute()

        logging.info("✅ Transaction saved")
        st.success("Transaction saved")

# ==================== REPORTS ==================== #
with tabs[2]:
    st.subheader("📊 Shop Report")

    shop_name = st.selectbox("Select Shop", shop_map.keys(), key="report_shop")
    shop_id = shop_map[shop_name]

    c1, c2 = st.columns(2)
    with c1:
        from_date = st.date_input("From Date")
    with c2:
        to_date = st.date_input("To Date")

    if st.button("Generate Report"):
        logging.info("📊 Generating report")

        res = supabase.table("daily_transactions") \
            .select("*") \
            .eq("shop_id", shop_id) \
            .gte("transaction_date", from_date.isoformat()) \
            .lte("transaction_date", to_date.isoformat()) \
            .order("transaction_date") \
            .execute()

        if not res.data:
            st.warning("No records found")
            logging.warning("No data")
        else:
            df = pd.DataFrame(res.data)
            st.dataframe(df, use_container_width=True)

            # ---- CALCULATIONS ---- #
            total_delivered = int(df["cylinders_delivered"].sum())
            total_empty_received = int(df["empty_cylinders_received"].sum())
            empty_pending = total_delivered - total_empty_received
            total_amount = df["total_amount"].sum()
            total_paid = (df["payment_cash"] + df["payment_upi"]).sum()
            balance = df.iloc[-1]["balance_after_transaction"]

            st.subheader("📌 Summary")

            col1, col2, col3 = st.columns(3)

            with col1:
                st.metric("Cylinders Delivered", total_delivered)
                st.metric("Empty Received", total_empty_received)

            with col2:
                st.metric("Empty Cylinders Pending", empty_pending)

            with col3:
                st.metric("Total Amount", f"₹{total_amount:,.2f}")
                st.metric("Total Paid", f"₹{total_paid:,.2f}")

            st.metric("Balance", f"₹{balance:,.2f}")

            # ---- ALERTS ---- #
            if empty_pending > 0:
                st.warning(f"⚠️ {empty_pending} empty cylinders yet to be returned")
            elif empty_pending < 0:
                st.error("❌ Data error: more empty cylinders received than delivered")
            else:
                st.success("✅ All cylinders settled")

            logging.info("✅ Report generated")

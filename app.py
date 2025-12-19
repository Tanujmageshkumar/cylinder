import streamlit as st
from supabase import create_client
import pandas as pd
from datetime import date
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
import streamlit.components.v1 as components

# ================= CONFIG ================= #
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
OWNER_PASSWORD = st.secrets["OWNER_PASSWORD"]

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

st.set_page_config(
    page_title="Gas Cylinder Manager",
    layout="centered"   # MOBILE FIRST
)

# ================= AUTH ================= #
if "auth" not in st.session_state:
    st.session_state.auth = False

if not st.session_state.auth:
    st.title("🔐 Owner Login")
    pwd = st.text_input("Password", type="password")
    if st.button("Login", use_container_width=True):
        if pwd == OWNER_PASSWORD:
            st.session_state.auth = True
            st.rerun()
        else:
            st.error("Wrong password")
    st.stop()

# ================= HELPERS ================= #
def get_shops():
    return supabase.table("shops").select("*").order("shop_name").execute().data

def get_transactions(shop_id):
    return supabase.table("daily_transactions") \
        .select("*") \
        .eq("shop_id", shop_id) \
        .order("transaction_date") \
        .execute().data

def recalc_balance(shop_id):
    txns = get_transactions(shop_id)
    balance = 0
    for t in txns:
        balance += t["total_amount"] - (t["payment_cash"] + t["payment_upi"])
        supabase.table("daily_transactions") \
            .update({"balance_after_transaction": balance}) \
            .eq("transaction_id", t["transaction_id"]) \
            .execute()

def copy_to_clipboard(text):
    components.html(
        f"""
        <textarea id="t" style="position:absolute;left:-1000px">{text}</textarea>
        <button onclick="copy()">📋 Copy to Clipboard</button>
        <script>
        function copy(){{
            var t=document.getElementById("t");
            t.select();
            document.execCommand("copy");
            alert("Copied!");
        }}
        </script>
        """,
        height=60,
    )

# ================= SIDEBAR NAV ================= #
task = st.sidebar.radio(
    "📌 Select Action",
    [
        "🚚 Deliver Cylinders",
        "🛒 Purchase Cylinders",
        "📊 Delivery Report",
        "📊 Purchase Report",
        "✏️ Edit / Delete Entry",
        "🏪 Manage Shops"
    ]
)

shops = get_shops()
shop_map = {s["shop_name"]: s for s in shops}

# ================================================= #
# 🚚 DELIVER CYLINDERS
# ================================================= #
if task == "🚚 Deliver Cylinders":
    st.header("🚚 Deliver Cylinders")

    shop = shop_map[st.selectbox("🏪 Select Shop", shop_map.keys(), key="d_shop")]
    txn_date = st.date_input("📅 Date", date.today(), key="d_date")

    # -------- Fetch Previous Balance --------
    txns = get_transactions(shop["shop_id"])
    prev_balance = txns[-1]["balance_after_transaction"] if txns else 0

    # -------- Input --------
    st.subheader("📦 Cylinders")
    delivered = st.number_input("Delivered", min_value=0, key="d_delivered")
    empty = st.number_input("Empty Received", min_value=0, key="d_empty")

    st.subheader("💰 Payment")
    price = st.number_input("Price per Cylinder", min_value=0.0, key="d_price")
    cash = st.number_input("Cash Paid", min_value=0.0, key="d_cash")
    upi = st.number_input("UPI Paid", min_value=0.0, key="d_upi")

    # -------- Live Calculations --------
    today_amount = delivered * price
    paid_today = cash + upi
    new_balance = prev_balance + today_amount - paid_today

    # -------- Live Summary (VERY IMPORTANT) --------
    st.subheader("📌 Today Summary")

    st.info(f"🧾 Today Amount: Rs. {today_amount:.2f}")
    st.success(f"💵 Paid Today: Rs. {paid_today:.2f}")

    if prev_balance > 0:
        st.warning(f"📦 Previous Balance: Rs. {prev_balance:.2f}")
    else:
        st.info("📦 Previous Balance: Rs. 0.00")

    if new_balance > 0:
        st.error(f"⚠️ Balance After Entry: Rs. {new_balance:.2f}")
    else:
        st.success("✅ No Balance Pending")

    # -------- Save --------
    if st.button("✅ SAVE DELIVERY", use_container_width=True):
        supabase.table("daily_transactions").insert({
            "shop_id": shop["shop_id"],
            "transaction_date": txn_date.isoformat(),
            "cylinders_delivered": delivered,
            "empty_cylinders_received": empty,
            "price_per_cylinder": price,
            "total_amount": today_amount,
            "payment_cash": cash,
            "payment_upi": upi,
            "balance_after_transaction": new_balance
        }).execute()

        st.success("Delivery saved successfully")

# ================================================= #
# 🛒 PURCHASE CYLINDERS
# ================================================= #
elif task == "🛒 Purchase Cylinders":
    st.header("🛒 Cylinder Purchase")

    p_date = st.date_input("📅 Purchase Date", date.today())

    st.subheader("📦 Purchase Details")
    purchased = st.number_input("Cylinders Purchased", 0)
    empty_returned = st.number_input("Empty Returned", 0)

    st.subheader("💰 Payment")
    price = st.number_input("Price per Cylinder", 0.0)
    cash = st.number_input("Cash Paid", 0.0)
    upi = st.number_input("UPI Paid", 0.0)

    total = purchased * price
    outstanding = total - (cash + upi)

    st.info(f"Total Amount: Rs. {total:.2f}")
    st.error(f"Outstanding: Rs. {outstanding:.2f}")

    if st.button("💾 SAVE PURCHASE", use_container_width=True):
        supabase.table("cylinder_purchases").insert({
            "purchase_date": p_date.isoformat(),
            "cylinders_purchased": purchased,
            "empty_cylinders_returned": empty_returned,
            "price_per_cylinder": price,
            "total_amount": total,
            "payment_cash": cash,
            "payment_upi": upi,
            "outstanding_amount": outstanding
        }).execute()
        st.success("Purchase saved")

# ================================================= #
# 📊 DELIVERY REPORT
# ================================================= #
elif task == "📊 Delivery Report":
    st.header("📊 Delivery Report")

    shop = shop_map[st.selectbox("🏪 Shop", shop_map.keys())]
    from_date = st.date_input("From Date")
    to_date = st.date_input("To Date")

    if st.button("📊 GENERATE REPORT", use_container_width=True):
        data = supabase.table("daily_transactions") \
            .select("*") \
            .eq("shop_id", shop["shop_id"]) \
            .gte("transaction_date", from_date.isoformat()) \
            .lte("transaction_date", to_date.isoformat()) \
            .execute().data

        if not data:
            st.warning("No records")
        else:
            df = pd.DataFrame(data)

            st.subheader("📌 Summary")
            st.metric("Delivered", int(df["cylinders_delivered"].sum()))
            st.metric("Balance", f"Rs. {df.iloc[-1]['balance_after_transaction']:.2f}")

            with st.expander("📄 View Details"):
                st.dataframe(df)

# ================================================= #
# 📊 PURCHASE REPORT
# ================================================= #
elif task == "📊 Purchase Report":
    st.header("📊 Purchase Report")

    from_date = st.date_input("From Date")
    to_date = st.date_input("To Date")

    if st.button("📊 GENERATE PURCHASE REPORT", use_container_width=True):
        data = supabase.table("cylinder_purchases") \
            .select("*") \
            .gte("purchase_date", from_date.isoformat()) \
            .lte("purchase_date", to_date.isoformat()) \
            .execute().data

        if not data:
            st.warning("No records")
        else:
            df = pd.DataFrame(data)

            st.metric("Total Purchased", int(df["cylinders_purchased"].sum()))
            st.metric("Outstanding", f"Rs. {df['outstanding_amount'].sum():.2f}")

            with st.expander("📄 View Details"):
                st.dataframe(df)

# ================================================= #
# ✏️ EDIT / DELETE
# ================================================= #
elif task == "✏️ Edit / Delete Entry":
    st.header("✏️ Edit / Delete Delivery")

    shop = shop_map[st.selectbox("🏪 Shop", shop_map.keys())]
    txns = get_transactions(shop["shop_id"])

    if not txns:
        st.info("No entries")
    else:
        df = pd.DataFrame(txns)
        df["transaction_date"] = pd.to_datetime(df["transaction_date"]).dt.date

        sel_date = st.selectbox("📅 Select Date", sorted(df["transaction_date"].unique()))
        row = df[df["transaction_date"] == sel_date].iloc[0]

        delivered = st.number_input("Delivered", int(row["cylinders_delivered"]))
        empty = st.number_input("Empty Received", int(row["empty_cylinders_received"]))
        price = st.number_input("Price", float(row["price_per_cylinder"]))
        cash = st.number_input("Cash", float(row["payment_cash"]))
        upi = st.number_input("UPI", float(row["payment_upi"]))

        if st.button("✏️ UPDATE ENTRY", use_container_width=True):
            supabase.table("daily_transactions").update({
                "cylinders_delivered": delivered,
                "empty_cylinders_received": empty,
                "price_per_cylinder": price,
                "total_amount": delivered * price,
                "payment_cash": cash,
                "payment_upi": upi
            }).eq("transaction_id", row["transaction_id"]).execute()
            recalc_balance(shop["shop_id"])
            st.success("Updated")

        if st.button("🗑️ DELETE ENTRY", use_container_width=True):
            supabase.table("daily_transactions") \
                .delete() \
                .eq("transaction_id", row["transaction_id"]) \
                .execute()
            recalc_balance(shop["shop_id"])
            st.success("Deleted")

# ================================================= #
# 🏪 MANAGE SHOPS
# ================================================= #
elif task == "🏪 Manage Shops":
    st.header("🏪 Manage Shops")

    with st.form("add_shop"):
        name = st.text_input("Shop Name")
        mobile = st.text_input("Mobile Number")
        address = st.text_area("Address")
        if st.form_submit_button("➕ ADD SHOP"):
            supabase.table("shops").insert({
                "shop_name": name,
                "mobile_number": mobile,
                "address": address
            }).execute()
            st.success("Shop added")

    with st.expander("📄 Existing Shops"):
        st.dataframe(pd.DataFrame(shops))


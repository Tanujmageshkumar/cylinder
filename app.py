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
    layout="centered",
    initial_sidebar_state="collapsed"
)

# ================= GLOBAL CSS ================= #
st.markdown("""
<style>
body {
    background-color: #f6f7fb;
}
.card {
    background: white;
    padding: 1rem;
    border-radius: 16px;
    margin-bottom: 1rem;
    box-shadow: 0 4px 10px rgba(0,0,0,0.05);
}
.card h3 {
    margin-bottom: 0.5rem;
}
.big-btn button {
    width: 100%;
    height: 3rem;
    font-size: 1.1rem;
    border-radius: 14px;
}
.stat {
    font-size: 1.4rem;
    font-weight: bold;
}
.green { color: #2ecc71; }
.red { color: #e74c3c; }
.blue { color: #3498db; }
hr {
    border: none;
    border-top: 1px solid #eee;
    margin: 1rem 0;
}
</style>
""", unsafe_allow_html=True)

# ================= SESSION ================= #
if "auth" not in st.session_state:
    st.session_state.auth = False

# ================= AUTH ================= #
if not st.session_state.auth:
    st.markdown("## 🔐 Owner Login")
    pwd = st.text_input("Enter Password", type="password")
    if st.button("Login"):
        if pwd == OWNER_PASSWORD:
            st.session_state.auth = True
            st.rerun()
        else:
            st.error("Wrong password")
    st.stop()

# ================= HELPERS (UNCHANGED) ================= #
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
    bal = 0
    for t in txns:
        bal += t["total_amount"] - (t["payment_cash"] + t["payment_upi"])
        supabase.table("daily_transactions") \
            .update({"balance_after_transaction": bal}) \
            .eq("transaction_id", t["transaction_id"]) \
            .execute()

def generate_invoice_pdf(title, lines):
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(50, 800, title)

    y = 750
    c.setFont("Helvetica", 11)
    for line in lines:
        c.drawString(50, y, line)
        y -= 22

    c.setFont("Helvetica", 9)
    c.drawString(50, 80, "System generated report")
    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer

# ================= NAVIGATION ================= #
menu = st.sidebar.radio(
    "📱 Menu",
    ["🏪 Shops", "🚚 Delivery", "✏️ Edit Delivery", "📊 Reports", "🛒 Purchase"]
)

st.markdown("# 🛢️ Gas Cylinder Manager")

# ================= SHOPS ================= #
if menu == "🏪 Shops":
    st.markdown("## 🏪 Manage Shops")

    with st.container():
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        name = st.text_input("Shop Name")
        mobile = st.text_input("Mobile Number")
        address = st.text_area("Address")
        if st.button("➕ Add Shop"):
            supabase.table("shops").insert({
                "shop_name": name,
                "mobile_number": mobile,
                "address": address
            }).execute()
            st.success("Shop added")
        st.markdown("</div>", unsafe_allow_html=True)

    for s in get_shops():
        st.markdown(f"""
        <div class='card'>
        <strong>{s['shop_name']}</strong><br>
        📞 {s['mobile_number']}<br>
        📍 {s['address']}
        </div>
        """, unsafe_allow_html=True)

# ================= DELIVERY ================= #
if menu == "🚚 Delivery":
    shops = get_shops()
    shop_map = {s["shop_name"]: s for s in shops}
    shop = shop_map[st.selectbox("🏪 Select Shop", shop_map.keys())]

    st.markdown("<div class='card'>", unsafe_allow_html=True)
    txn_date = st.date_input("📅 Date", date.today())
    delivered = st.number_input("🚚 Cylinders Delivered", 0)
    empty = st.number_input("🔄 Empty Received", 0)
    price = st.number_input("💰 Price per Cylinder", 0.0)
    st.markdown("</div>", unsafe_allow_html=True)

    total = delivered * price

    st.markdown("<div class='card'>", unsafe_allow_html=True)
    cash = st.number_input("💵 Cash Paid", 0.0)
    upi = st.number_input("📲 UPI Paid", 0.0)
    st.markdown(f"<div class='stat blue'>Total: ₹{total:.2f}</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='stat red'>Balance: ₹{total - cash - upi:.2f}</div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    if st.button("💾 Save Delivery"):
        supabase.table("daily_transactions").insert({
            "shop_id": shop["shop_id"],
            "transaction_date": txn_date.isoformat(),
            "cylinders_delivered": delivered,
            "empty_cylinders_received": empty,
            "price_per_cylinder": price,
            "total_amount": total,
            "payment_cash": cash,
            "payment_upi": upi,
            "balance_after_transaction": 0
        }).execute()
        recalc_balance(shop["shop_id"])
        st.success("Saved")

# ================= EDIT DELIVERY ================= #
if menu == "✏️ Edit Delivery":
    shops = get_shops()
    shop_map = {s["shop_name"]: s for s in shops}
    shop = shop_map[st.selectbox("🏪 Shop", shop_map.keys())]

    txns = get_transactions(shop["shop_id"])
    if not txns:
        st.info("No records")
    else:
        df = pd.DataFrame(txns)
        df["transaction_date"] = pd.to_datetime(df["transaction_date"]).dt.date
        selected = st.selectbox("📅 Select Date", df["transaction_date"].unique())
        row = df[df["transaction_date"] == selected].iloc[0]

        st.markdown("<div class='card'>", unsafe_allow_html=True)
        delivered = st.number_input("Delivered", int(row["cylinders_delivered"]))
        empty = st.number_input("Empty", int(row["empty_cylinders_received"]))
        price = st.number_input("Price", float(row["price_per_cylinder"]))
        cash = st.number_input("Cash", float(row["payment_cash"]))
        upi = st.number_input("UPI", float(row["payment_upi"]))
        st.markdown("</div>", unsafe_allow_html=True)

        col1, col2 = st.columns(2)
        if col1.button("✅ Update"):
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

        if col2.button("🗑️ Delete"):
            supabase.table("daily_transactions").delete().eq(
                "transaction_id", row["transaction_id"]
            ).execute()
            recalc_balance(shop["shop_id"])
            st.success("Deleted")

# ================= REPORTS ================= #
if menu == "📊 Reports":
    shops = get_shops()
    shop_map = {s["shop_name"]: s for s in shops}
    shop = shop_map[st.selectbox("🏪 Shop", shop_map.keys())]

    from_date = st.date_input("From Date")
    to_date = st.date_input("To Date")

    if st.button("📊 Generate Report"):
        data = supabase.table("daily_transactions") \
            .select("*") \
            .eq("shop_id", shop["shop_id"]) \
            .gte("transaction_date", from_date.isoformat()) \
            .lte("transaction_date", to_date.isoformat()) \
            .execute().data

        df = pd.DataFrame(data)
        st.dataframe(df, use_container_width=True)

# ================= PURCHASE ================= #
if menu == "🛒 Purchase":
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    p_date = st.date_input("📅 Purchase Date", date.today())
    qty = st.number_input("🛢️ Cylinders Purchased", 0)
    empty = st.number_input("🔄 Empty Returned", 0)
    price = st.number_input("💰 Price per Cylinder", 0.0)
    cash = st.number_input("💵 Cash Paid", 0.0)
    upi = st.number_input("📲 UPI Paid", 0.0)
    total = qty * price
    st.markdown(f"<div class='stat green'>Total: ₹{total:.2f}</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='stat red'>Outstanding: ₹{total - cash - upi:.2f}</div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    if st.button("💾 Save Purchase"):
        supabase.table("cylinder_purchases").insert({
            "purchase_date": p_date.isoformat(),
            "cylinders_purchased": qty,
            "empty_cylinders_returned": empty,
            "price_per_cylinder": price,
            "total_amount": total,
            "payment_cash": cash,
            "payment_upi": upi,
            "outstanding_amount": total - cash - upi
        }).execute()
        st.success("Purchase saved")

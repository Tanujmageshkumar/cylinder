import streamlit as st
from supabase import create_client
import pandas as pd
from datetime import date
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

# ---------------- CONFIG ---------------- #
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
OWNER_PASSWORD = st.secrets["OWNER_PASSWORD"]

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
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

def get_transactions(shop_id):
    return supabase.table("daily_transactions") \
        .select("*") \
        .eq("shop_id", shop_id) \
        .order("transaction_date") \
        .execute().data

def recalc_balance(shop_id):
    txns = supabase.table("daily_transactions") \
        .select("*") \
        .eq("shop_id", shop_id) \
        .order("transaction_date") \
        .execute().data

    balance = 0
    for t in txns:
        balance += t["total_amount"] - (t["payment_cash"] + t["payment_upi"])
        supabase.table("daily_transactions") \
            .update({"balance_after_transaction": balance}) \
            .eq("transaction_id", t["transaction_id"]) \
            .execute()

def generate_invoice_pdf(shop, summary):
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)

    c.setFont("Helvetica-Bold", 18)
    c.drawString(50, 800, "INVOICE")

    c.setFont("Helvetica", 10)
    c.drawString(50, 780, "Gas Cylinder Delivery Report")

    c.drawString(50, 750, f"Shop Name : {shop['shop_name']}")
    c.drawString(50, 735, f"Mobile    : {shop['mobile_number']}")
    c.drawString(50, 720, f"Address   : {shop['address']}")
    c.drawString(50, 705, f"Period    : {summary['From Date']} to {summary['To Date']}")

    c.line(50, 690, 550, 690)

    y = 660
    c.setFont("Helvetica-Bold", 11)
    c.drawString(50, y, "Description")
    c.drawRightString(530, y, "Value")
    y -= 20

    c.setFont("Helvetica", 10)
    for k, v in summary.items():
        if "Date" in k:
            continue
        if isinstance(v, (int, float)):
            v = f"Rs. {v:.2f}"
        c.drawString(50, y, k)
        c.drawRightString(530, y, str(v))
        y -= 18

    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer

# ---------------- UI ---------------- #
st.title("🛢️ Gas Cylinder Delivery Management")

tabs = st.tabs([
    "🏪 Shops",
    "📝 Daily Entry",
    "✏️ Edit / Delete Entry",
    "📊 Reports",
    "📅 Monthly Analysis"
])

# ================= SHOPS ================= #
with tabs[0]:
    with st.form("add_shop"):
        st.subheader("Add Shop")
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

    st.dataframe(pd.DataFrame(get_shops()), use_container_width=True)

# ================= DAILY ENTRY ================= #
with tabs[1]:
    shops = get_shops()
    shop_map = {s["shop_name"]: s for s in shops}
    shop_name = st.selectbox("Shop", shop_map.keys())
    shop = shop_map[shop_name]

    txn_date = st.date_input("Date", date.today())
    delivered = st.number_input("Delivered", 0)
    empty = st.number_input("Empty Received", 0)
    price = st.number_input("Price per Cylinder", 0.0)
    cash = st.number_input("Cash Paid", 0.0)
    upi = st.number_input("UPI Paid", 0.0)

    total = delivered * price

    if st.button("Save Entry"):
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

# ================= EDIT / DELETE ================= #
with tabs[2]:
    shops = get_shops()
    shop_map = {s["shop_name"]: s for s in shops}
    shop_name = st.selectbox("Shop", shop_map.keys(), key="edit_shop")
    shop = shop_map[shop_name]

    txns = get_transactions(shop["shop_id"])
    if not txns:
        st.info("No entries")
    else:
        df = pd.DataFrame(txns)
        st.dataframe(df, use_container_width=True)

        txn_id = st.selectbox(
            "Select Transaction ID",
            df["transaction_id"]
        )

        row = df[df["transaction_id"] == txn_id].iloc[0]

        with st.form("edit_form"):
            delivered = st.number_input("Delivered", value=int(row["cylinders_delivered"]))
            empty = st.number_input("Empty Received", value=int(row["empty_cylinders_received"]))
            price = st.number_input("Price per Cylinder", value=float(row["price_per_cylinder"]))
            cash = st.number_input("Cash Paid", value=float(row["payment_cash"]))
            upi = st.number_input("UPI Paid", value=float(row["payment_upi"]))

            col1, col2 = st.columns(2)
            if col1.form_submit_button("Update"):
                total = delivered * price
                supabase.table("daily_transactions").update({
                    "cylinders_delivered": delivered,
                    "empty_cylinders_received": empty,
                    "price_per_cylinder": price,
                    "total_amount": total,
                    "payment_cash": cash,
                    "payment_upi": upi
                }).eq("transaction_id", txn_id).execute()

                recalc_balance(shop["shop_id"])
                st.success("Updated")
                st.rerun()

            if col2.form_submit_button("Delete"):
                supabase.table("daily_transactions") \
                    .delete() \
                    .eq("transaction_id", txn_id) \
                    .execute()
                recalc_balance(shop["shop_id"])
                st.success("Deleted")
                st.rerun()

# ================= REPORTS ================= #
with tabs[3]:
    st.info("Shop-wise detailed report already implemented earlier")

# ================= MONTHLY ANALYSIS ================= #
with tabs[4]:
    st.subheader("Monthly Analysis – All Shops")

    month = st.selectbox("Month", range(1, 13))
    year = st.selectbox("Year", range(2023, 2031))

    start = f"{year}-{month:02d}-01"
    end = f"{year}-{month:02d}-31"

    data = supabase.table("daily_transactions") \
        .select("shop_id, cylinders_delivered, empty_cylinders_received, total_amount, payment_cash, payment_upi") \
        .gte("transaction_date", start) \
        .lte("transaction_date", end) \
        .execute().data

    if not data:
        st.info("No data for this month")
    else:
        df = pd.DataFrame(data)
        shops_df = pd.DataFrame(get_shops())
        merged = df.merge(shops_df, on="shop_id")

        report = merged.groupby("shop_name").agg({
            "cylinders_delivered": "sum",
            "empty_cylinders_received": "sum",
            "total_amount": "sum",
            "payment_cash": "sum",
            "payment_upi": "sum"
        }).reset_index()

        report["Total Paid"] = report["payment_cash"] + report["payment_upi"]
        report["Balance"] = report["total_amount"] - report["Total Paid"]
        report["Empty Pending"] = report["cylinders_delivered"] - report["empty_cylinders_received"]

        st.dataframe(report, use_container_width=True)

        st.subheader("📊 Charts")
        st.bar_chart(report.set_index("shop_name")[["total_amount"]])
        st.bar_chart(report.set_index("shop_name")[["Balance"]])
        st.bar_chart(report.set_index("shop_name")[["Empty Pending"]])

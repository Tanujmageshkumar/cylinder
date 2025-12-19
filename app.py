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
st.set_page_config(page_title="Gas Cylinder Manager", layout="wide")

# ================= SESSION STATE ================= #
if "auth" not in st.session_state:
    st.session_state.auth = False

# ================= AUTH ================= #
if not st.session_state.auth:
    st.title("🔐 Owner Login")
    pwd = st.text_input("Password", type="password", key="login_pwd")
    if st.button("Login", key="login_btn"):
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
    bal = 0
    for t in txns:
        bal += t["total_amount"] - (t["payment_cash"] + t["payment_upi"])
        supabase.table("daily_transactions") \
            .update({"balance_after_transaction": bal}) \
            .eq("transaction_id", t["transaction_id"]) \
            .execute()

def copy_to_clipboard(text):
    components.html(
        f"""
        <textarea id="copytext" style="position:absolute; left:-1000px;">{text}</textarea>
        <button onclick="copyText()">📋 Copy to Clipboard</button>
        <script>
        function copyText() {{
            var copyText = document.getElementById("copytext");
            copyText.select();
            copyText.setSelectionRange(0, 99999);
            navigator.clipboard.writeText(copyText.value);
            alert("Copied!");
        }}
        </script>
        """,
        height=80,
    )

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

# ================= UI ================= #
st.title("🛢️ Gas Cylinder Business Management")

tabs = st.tabs([
    "🏪 Shops",
    "📝 Daily Delivery",
    "✏️ Edit / Delete Delivery",
    "📊 Delivery Report",
    "🛒 Cylinder Purchase",
    "📊 Purchase Report"
])

# ================= SHOPS ================= #
with tabs[0]:
    with st.form("add_shop_form"):
        st.subheader("Add Shop")
        name = st.text_input("Shop Name", key="shop_name")
        mobile = st.text_input("Mobile Number", key="shop_mobile")
        address = st.text_area("Address", key="shop_address")
        if st.form_submit_button("Add Shop"):
            if name:
                supabase.table("shops").insert({
                    "shop_name": name,
                    "mobile_number": mobile,
                    "address": address
                }).execute()
                st.success("Shop added")

    st.dataframe(pd.DataFrame(get_shops()), use_container_width=True)

# ================= DAILY DELIVERY ================= #
with tabs[1]:
    shops = get_shops()
    shop_map = {s["shop_name"]: s for s in shops}
    shop = shop_map[st.selectbox("Shop", shop_map.keys(), key="delivery_shop")]

    txn_date = st.date_input("Date", date.today(), key="delivery_date")
    delivered = st.number_input("Cylinders Delivered", 0, key="delivery_delivered")
    empty = st.number_input("Empty Received", 0, key="delivery_empty")
    price = st.number_input("Price per Cylinder", 0.0, key="delivery_price")
    cash = st.number_input("Cash Paid", 0.0, key="delivery_cash")
    upi = st.number_input("UPI Paid", 0.0, key="delivery_upi")

    total = delivered * price

    if st.button("Save Delivery", key="save_delivery"):
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

# ================= EDIT / DELETE DELIVERY ================= #
with tabs[2]:
    shop = shop_map[st.selectbox("Shop", shop_map.keys(), key="edit_shop")]
    txns = get_transactions(shop["shop_id"])

    if not txns:
        st.info("No entries")
    else:
        df = pd.DataFrame(txns)
        df["transaction_date"] = pd.to_datetime(df["transaction_date"]).dt.date
        st.dataframe(df, use_container_width=True)

        selected_date = st.selectbox(
            "Select Date",
            sorted(df["transaction_date"].unique()),
            key="edit_date"
        )

        row = df[df["transaction_date"] == selected_date].iloc[0]

        with st.form("edit_form"):
            delivered = st.number_input("Delivered", int(row["cylinders_delivered"]), key="edit_delivered")
            empty = st.number_input("Empty Received", int(row["empty_cylinders_received"]), key="edit_empty")
            price = st.number_input("Price", float(row["price_per_cylinder"]), key="edit_price")
            cash = st.number_input("Cash", float(row["payment_cash"]), key="edit_cash")
            upi = st.number_input("UPI", float(row["payment_upi"]), key="edit_upi")

            col1, col2 = st.columns(2)
            if col1.form_submit_button("Update"):
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
                st.rerun()

            if col2.form_submit_button("Delete"):
                supabase.table("daily_transactions").delete() \
                    .eq("transaction_id", row["transaction_id"]).execute()
                recalc_balance(shop["shop_id"])
                st.success("Deleted")
                st.rerun()

# ================= DELIVERY REPORT ================= #
with tabs[3]:
    shop = shop_map[st.selectbox("Shop", shop_map.keys(), key="report_shop")]
    f, t = st.columns(2)
    from_date = f.date_input("From Date", key="report_from")
    to_date = t.date_input("To Date", key="report_to")

    if st.button("Generate Delivery Report", key="gen_delivery_report"):
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
            st.dataframe(df, use_container_width=True)

# ================= CYLINDER PURCHASE ================= #
with tabs[4]:
    p_date = st.date_input("Purchase Date", date.today(), key="purchase_date")
    purchased = st.number_input("Cylinders Purchased", 0, key="purchase_qty")
    empty_returned = st.number_input("Empty Cylinders Returned", 0, key="purchase_empty")
    price = st.number_input("Price per Cylinder", 0.0, key="purchase_price")
    cash = st.number_input("Cash Paid", 0.0, key="purchase_cash")
    upi = st.number_input("UPI Paid", 0.0, key="purchase_upi")

    total = purchased * price
    outstanding = total - (cash + upi)

    st.info(f"Total Amount: Rs. {total:.2f}")
    st.warning(f"Outstanding: Rs. {outstanding:.2f}")

    if st.button("Save Purchase", key="save_purchase"):
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

# ================= PURCHASE REPORT ================= #
with tabs[5]:
    f, t = st.columns(2)
    from_date = f.date_input("From Date", key="purchase_from")
    to_date = t.date_input("To Date", key="purchase_to")

    if st.button("Generate Purchase Report", key="gen_purchase_report"):
        data = supabase.table("cylinder_purchases") \
            .select("*") \
            .gte("purchase_date", from_date.isoformat()) \
            .lte("purchase_date", to_date.isoformat()) \
            .execute().data

        if not data:
            st.warning("No records")
        else:
            df = pd.DataFrame(data)
            st.dataframe(df, use_container_width=True)

            summary = [
                f"Period: {from_date} to {to_date}",
                f"Cylinders Purchased: {df['cylinders_purchased'].sum()}",
                f"Empty Returned: {df['empty_cylinders_returned'].sum()}",
                f"Total Amount: Rs. {df['total_amount'].sum():.2f}",
                f"Cash Paid: Rs. {df['payment_cash'].sum():.2f}",
                f"UPI Paid: Rs. {df['payment_upi'].sum():.2f}",
                f"Outstanding: Rs. {df['outstanding_amount'].sum():.2f}"
            ]

            pdf = generate_invoice_pdf("Cylinder Purchase Report", summary)
            st.download_button("📄 Download Purchase PDF", pdf, "purchase_report.pdf")

            msg = "\n".join(summary)
            st.text_area("WhatsApp Text", msg, height=200)
            copy_to_clipboard(msg)

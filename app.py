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

st.set_page_config(page_title="Gas Cylinder Manager", layout="centered")

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

def generate_invoice_pdf(shop, summary):
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(50, 800, "DELIVERY INVOICE")

    c.setFont("Helvetica", 10)
    c.drawString(50, 770, f"Shop: {shop['shop_name']}")
    c.drawString(50, 755, f"Mobile: {shop['mobile_number']}")
    c.drawString(50, 740, f"Period: {summary['From']} to {summary['To']}")

    y = 700
    for k, v in summary.items():
        if k in ["From", "To"]:
            continue
        if isinstance(v, (int, float)):
            if "Cylinders" in k or "Empty" in k:
                text = str(int(v))
            else:
                text = f"Rs. {v:.2f}"
        else:
            text = str(v)
        c.drawString(50, y, f"{k}: {text}")
        y -= 20

    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer

def generate_simple_invoice(title, lines):
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(50, 800, title)
    y = 760
    c.setFont("Helvetica", 11)
    for line in lines:
        c.drawString(50, y, line)
        y -= 22
    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer

def whatsapp_text(shop, summary):
    return f"""
Gas Cylinder Delivery Report

Shop: {shop['shop_name']}
Period: {summary['From']} to {summary['To']}

Delivered: {summary['Cylinders Delivered']}
Empty Received: {summary['Empty Received']}
Empty Pending: {summary['Empty Pending']}

Total Amount: Rs. {summary['Total Amount']:.2f}
Cash Paid: Rs. {summary['Cash Paid']:.2f}
UPI Paid: Rs. {summary['UPI Paid']:.2f}
Balance Due: Rs. {summary['Balance']:.2f}
""".strip()

def open_whatsapp_and_copy(text, phone):
    components.html(
        f"""
        <textarea id="msg" style="position:absolute;left:-1000px">{text}</textarea>
        <script>
            navigator.clipboard.writeText(document.getElementById("msg").value);
            window.open("https://wa.me/91{phone}", "_blank");
        </script>
        """,
        height=0
    )

# ================= SIDEBAR ================= #
task = st.sidebar.radio(
    "📌 Select Action",
    [
        "🚚 Deliver Cylinders",
        "🛒 Purchase Cylinders",
        "💸 Other Expenses",
        "📆 Daily Report",
        "📊 Delivery Report",
        "📊 Purchase Report",
        "✏️ Edit / Delete Entry",
        "🏪 Manage Shops"
    ]
)

shops = get_shops()
shop_map = {s["shop_name"]: s for s in shops}

# =========================================================
# 🚚 DELIVER CYLINDERS
# =========================================================
if task == "🚚 Deliver Cylinders":
    st.header("🚚 Deliver Cylinders")

    shop = shop_map[st.selectbox("🏪 Shop", shop_map.keys())]
    txn_date = st.date_input("Date", date.today())

    txns = get_transactions(shop["shop_id"])
    prev_balance = txns[-1]["balance_after_transaction"] if txns else 0

    delivered = st.number_input("Cylinders Delivered", 0)
    empty = st.number_input("Empty Received", 0)
    price = st.number_input("Price per Cylinder", 0.0)
    cash = st.number_input("Cash Paid", 0.0)
    upi = st.number_input("UPI Paid", 0.0)

    today_amount = delivered * price
    paid_today = cash + upi
    new_balance = prev_balance + today_amount - paid_today

    st.info(f"Today Amount: Rs. {today_amount:.2f}")
    st.success(f"Paid Today: Rs. {paid_today:.2f}")
    st.warning(f"Previous Balance: Rs. {prev_balance:.2f}")
    st.error(f"Balance After Entry: Rs. {new_balance:.2f}")

    if st.button("SAVE DELIVERY", use_container_width=True):
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
        st.success("Saved")

# =========================================================
# 💸 OTHER EXPENSES
# =========================================================
elif task == "💸 Other Expenses":
    st.header("💸 Other Expenses")

    e_date = st.date_input("Date", date.today())
    e_type = st.text_input("Expense Type")
    amount = st.number_input("Amount", 0.0)

    if st.button("SAVE EXPENSE", use_container_width=True):
        supabase.table("other_expenses").insert({
            "expense_date": e_date.isoformat(),
            "expense_type": e_type,
            "amount": amount
        }).execute()
        st.success("Expense saved")

# =========================================================
# 📆 DAILY REPORT
# =========================================================
elif task == "📆 Daily Report":
    st.header("📆 Daily Delivery Report")

    rep_date = st.date_input("Select Date", date.today())

    data = supabase.table("daily_transactions") \
        .select("""
            shop_id,
            cylinders_delivered,
            empty_cylinders_received,
            payment_cash,
            payment_upi,
            balance_after_transaction,
            shops(shop_name)
        """) \
        .eq("transaction_date", rep_date.isoformat()) \
        .execute().data

    if not data:
        st.warning("No deliveries")
    else:
        df = pd.DataFrame(data)
        df["Shop"] = df["shops"].apply(lambda x: x["shop_name"])
        df["Total Paid"] = df["payment_cash"] + df["payment_upi"]

        st.dataframe(df[[
            "Shop",
            "cylinders_delivered",
            "empty_cylinders_received",
            "payment_cash",
            "payment_upi",
            "Total Paid",
            "balance_after_transaction"
        ]], use_container_width=True)

        st.subheader("Grand Total")
        st.metric("Delivered", int(df["cylinders_delivered"].sum()))
        st.metric("Empty Received", int(df["empty_cylinders_received"].sum()))
        st.metric("Cash", f"Rs. {df['payment_cash'].sum():.2f}")
        st.metric("UPI", f"Rs. {df['payment_upi'].sum():.2f}")
        st.metric("Total", f"Rs. {df['Total Paid'].sum():.2f}")

# =========================================================
# 📊 DELIVERY REPORT
# =========================================================
elif task == "📊 Delivery Report":
    st.header("📊 Delivery Report")

    shop = shop_map[st.selectbox("Shop", shop_map.keys())]
    f = st.date_input("From Date")
    t = st.date_input("To Date")

    if st.button("GENERATE REPORT", use_container_width=True):
        data = supabase.table("daily_transactions") \
            .select("*") \
            .eq("shop_id", shop["shop_id"]) \
            .gte("transaction_date", f.isoformat()) \
            .lte("transaction_date", t.isoformat()) \
            .execute().data

        if not data:
            st.warning("No records")
        else:
            df = pd.DataFrame(data)

            summary = {
                "From": f.strftime("%d-%m-%Y"),
                "To": t.strftime("%d-%m-%Y"),
                "Cylinders Delivered": int(df["cylinders_delivered"].sum()),
                "Empty Received": int(df["empty_cylinders_received"].sum()),
                "Empty Pending": int(df["cylinders_delivered"].sum() - df["empty_cylinders_received"].sum()),
                "Total Amount": df["total_amount"].sum(),
                "Cash Paid": df["payment_cash"].sum(),
                "UPI Paid": df["payment_upi"].sum(),
                "Balance": df.iloc[-1]["balance_after_transaction"]
            }

            st.json(summary)

            pdf = generate_invoice_pdf(shop, summary)
            st.download_button("Download PDF", pdf, "delivery_report.pdf")

            msg = whatsapp_text(shop, summary)
            st.text_area("WhatsApp Message", msg)
            if st.button("SEND TO WHATSAPP", use_container_width=True):
                open_whatsapp_and_copy(msg, shop["mobile_number"])

# =========================================================
# 📊 PURCHASE REPORT
# =========================================================
elif task == "📊 Purchase Report":
    st.header("📊 Purchase Report")

    f = st.date_input("From Date")
    t = st.date_input("To Date")

    if st.button("GENERATE PURCHASE REPORT", use_container_width=True):
        data = supabase.table("cylinder_purchases") \
            .select("*") \
            .gte("purchase_date", f.isoformat()) \
            .lte("purchase_date", t.isoformat()) \
            .execute().data

        if not data:
            st.warning("No records")
        else:
            df = pd.DataFrame(data)

            lines = [
                f"Period: {f} to {t}",
                f"Cylinders Purchased: {df['cylinders_purchased'].sum()}",
                f"Empty Returned: {df['empty_cylinders_returned'].sum()}",
                f"Total Amount: Rs. {df['total_amount'].sum():.2f}",
                f"Cash Paid: Rs. {df['payment_cash'].sum():.2f}",
                f"UPI Paid: Rs. {df['payment_upi'].sum():.2f}",
                f"Outstanding: Rs. {df['outstanding_amount'].sum():.2f}"
            ]

            pdf = generate_simple_invoice("Cylinder Purchase Report", lines)
            st.download_button("Download PDF", pdf, "purchase_report.pdf")

            st.text_area("WhatsApp Text", "\n".join(lines))

# =========================================================
# ✏️ EDIT / DELETE
# =========================================================
elif task == "✏️ Edit / Delete Entry":
    st.header("✏️ Edit / Delete Delivery")

    shop = shop_map[st.selectbox("Shop", shop_map.keys())]
    txns = get_transactions(shop["shop_id"])

    if txns:
        df = pd.DataFrame(txns)
        df["transaction_date"] = pd.to_datetime(df["transaction_date"]).dt.date
        sel = st.selectbox("Select Date", sorted(df["transaction_date"].unique()))
        row = df[df["transaction_date"] == sel].iloc[0]

        delivered = st.number_input("Delivered", int(row["cylinders_delivered"]))
        empty = st.number_input("Empty Received", int(row["empty_cylinders_received"]))
        price = st.number_input("Price", float(row["price_per_cylinder"]))
        cash = st.number_input("Cash", float(row["payment_cash"]))
        upi = st.number_input("UPI", float(row["payment_upi"]))

        if st.button("UPDATE", use_container_width=True):
            supabase.table("daily_transactions").update({
                "cylinders_delivered": delivered,
                "empty_cylinders_received": empty,
                "price_per_cylinder": price,
                "total_amount": delivered * price,
                "payment_cash": cash,
                "payment_upi": upi
            }).eq("transaction_id", row["transaction_id"]).execute()
            st.success("Updated")

        if st.button("DELETE", use_container_width=True):
            supabase.table("daily_transactions").delete() \
                .eq("transaction_id", row["transaction_id"]).execute()
            st.success("Deleted")

# =========================================================
# 🏪 MANAGE SHOPS
# =========================================================
elif task == "🏪 Manage Shops":
    st.header("🏪 Manage Shops")

    name = st.text_input("Shop Name")
    mobile = st.text_input("Mobile Number")
    address = st.text_area("Address")

    if st.button("ADD SHOP", use_container_width=True):
        supabase.table("shops").insert({
            "shop_name": name,
            "mobile_number": mobile,
            "address": address
        }).execute()
        st.success("Shop added")

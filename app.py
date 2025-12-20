import streamlit as st
from supabase import create_client
import pandas as pd
from datetime import date
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
import streamlit.components.v1 as components

# ================= CONFIG =================
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
OWNER_PASSWORD = st.secrets["OWNER_PASSWORD"]

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
st.set_page_config(page_title="Gas Cylinder Manager", layout="centered")

# ================= AUTH =================
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

# ================= HELPERS =================
def get_shops():
    return supabase.table("shops").select("*").order("shop_name").execute().data

def whatsapp_send(text, phone):
    components.html(
        f"""
        <textarea id="t" style="position:absolute;left:-1000px">{text}</textarea>
        <button onclick="send()">Send WhatsApp</button>
        <script>
        function send(){{
            navigator.clipboard.writeText(document.getElementById("t").value);
            window.open("https://wa.me/91{phone}", "_blank");
        }}
        </script>
        """,
        height=80,
    )

def simple_pdf(title, lines):
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, 800, title)
    y = 760
    c.setFont("Helvetica", 11)
    for l in lines:
        c.drawString(50, y, l)
        y -= 20
    c.showPage()
    c.save()
    buf.seek(0)
    return buf

# ================= SIDEBAR =================
menu = st.sidebar.radio(
    "📌 Menu",
    [
        "🚚 Deliver Cylinders",
        "🛒 Purchase Cylinders",
        "💸 Other Expenses",
        "📆 Daily Report",
        "📊 Delivery Report",
        "📊 Purchase Report",
        "📊 Expense Report",
        "🏪 Manage Shops"
    ]
)

shops = get_shops()
shop_map = {s["shop_name"]: s for s in shops}
shop_names = list(shop_map.keys())

# =====================================================
# 🚚 DELIVER CYLINDERS
# =====================================================
if menu == "🚚 Deliver Cylinders":
    st.header("🚚 Deliver Cylinders")

    shop_name = st.selectbox("Shop (type to search)", shop_names)
    shop = shop_map[shop_name]

    delivered = st.number_input("Cylinders Delivered", 0)
    empty = st.number_input("Empty Received", 0)
    price = st.number_input("Price per Cylinder", 0.0)
    cash = st.number_input("Cash Paid", 0.0)
    upi = st.number_input("UPI Paid", 0.0)

    total = delivered * price
    paid = cash + upi

    st.info(f"Today Amount: Rs. {total:.2f}")
    st.info(f"Paid Today: Rs. {paid:.2f}")

    if st.button("SAVE DELIVERY", use_container_width=True):
        supabase.table("daily_transactions").insert({
            "shop_id": shop["shop_id"],
            "transaction_date": date.today().isoformat(),
            "cylinders_delivered": delivered,
            "empty_cylinders_received": empty,
            "price_per_cylinder": price,
            "total_amount": total,
            "payment_cash": cash,
            "payment_upi": upi,
            "balance_after_transaction": total - paid
        }).execute()
        st.success("Saved")

# =====================================================
# 🛒 PURCHASE CYLINDERS
# =====================================================
elif menu == "🛒 Purchase Cylinders":
    st.header("🛒 Purchase Cylinders")

    p_date = st.date_input("Date", date.today())
    qty = st.number_input("Cylinders Purchased", 0)
    empty_ret = st.number_input("Empty Returned", 0)
    price = st.number_input("Price per Cylinder", 0.0)
    cash = st.number_input("Cash Paid", 0.0)
    upi = st.number_input("UPI Paid", 0.0)

    total = qty * price
    outstanding = total - (cash + upi)

    st.info(f"Total: Rs. {total:.2f}")
    st.warning(f"Outstanding: Rs. {outstanding:.2f}")

    if st.button("SAVE PURCHASE", use_container_width=True):
        supabase.table("cylinder_purchases").insert({
            "purchase_date": p_date.isoformat(),
            "cylinders_purchased": qty,
            "empty_cylinders_returned": empty_ret,
            "price_per_cylinder": price,
            "total_amount": total,
            "payment_cash": cash,
            "payment_upi": upi,
            "outstanding_amount": outstanding
        }).execute()
        st.success("Saved")

# =====================================================
# 💸 OTHER EXPENSES
# =====================================================
elif menu == "💸 Other Expenses":
    st.header("💸 Other Expenses")

    e_date = st.date_input("Date", date.today())
    e_type = st.text_input("Expense Type")
    amt = st.number_input("Amount", 0.0)

    if st.button("SAVE EXPENSE", use_container_width=True):
        supabase.table("other_expenses").insert({
            "expense_date": e_date.isoformat(),
            "expense_type": e_type,
            "amount": amt
        }).execute()
        st.success("Saved")

# =====================================================
# 📆 DAILY REPORT
# =====================================================
elif menu == "📆 Daily Report":
    st.header("📆 Daily Report")

    d = st.date_input("Select Date", date.today())

    data = supabase.table("daily_transactions") \
        .select("shop_id, cylinders_delivered, empty_cylinders_received, payment_cash, payment_upi, shops(shop_name)") \
        .eq("transaction_date", d.isoformat()) \
        .execute().data

    if data:
        df = pd.DataFrame(data)
        df["Shop"] = df["shops"].apply(lambda x: x["shop_name"])
        df["Total Paid"] = df["payment_cash"] + df["payment_upi"]

        show = df[["Shop", "cylinders_delivered", "empty_cylinders_received", "payment_cash", "payment_upi", "Total Paid"]]
        show.columns = ["Shop", "Delivered", "Empty", "Cash", "UPI", "Total Paid"]

        st.dataframe(show, use_container_width=True)

        st.subheader("Grand Total")
        st.metric("Delivered", int(show["Delivered"].sum()))
        st.metric("Cash", f"Rs. {show['Cash'].sum():.2f}")
        st.metric("UPI", f"Rs. {show['UPI'].sum():.2f}")

        pdf = simple_pdf(
            f"Daily Report - {d}",
            show.astype(str).apply(" | ".join, axis=1).tolist()
        )
        st.download_button("Download PDF", pdf, "daily_report.pdf")
    else:
        st.warning("No data")

# =====================================================
# 📊 DELIVERY REPORT
# =====================================================
elif menu == "📊 Delivery Report":
    st.header("📊 Delivery Report")

    shop = shop_map[st.selectbox("Shop", shop_names)]
    f = st.date_input("From")
    t = st.date_input("To")

    data = supabase.table("daily_transactions") \
        .select("*") \
        .eq("shop_id", shop["shop_id"]) \
        .gte("transaction_date", f.isoformat()) \
        .lte("transaction_date", t.isoformat()) \
        .execute().data

    if data:
        df = pd.DataFrame(data)
        total = df["total_amount"].sum()
        cash = df["payment_cash"].sum()
        upi = df["payment_upi"].sum()

        st.metric("Total Amount", f"Rs. {total:.2f}")
        st.metric("Cash", f"Rs. {cash:.2f}")
        st.metric("UPI", f"Rs. {upi:.2f}")

        msg = f"Report for {shop['shop_name']} from {f} to {t}\nTotal: Rs.{total:.2f}"
        st.text_area("WhatsApp Message", msg)

        whatsapp_send(msg, shop["mobile_number"])
    else:
        st.warning("No records")

# =====================================================
# 📊 PURCHASE REPORT
# =====================================================
elif menu == "📊 Purchase Report":
    st.header("📊 Purchase Report")

    f = st.date_input("From")
    t = st.date_input("To")

    data = supabase.table("cylinder_purchases") \
        .select("*") \
        .gte("purchase_date", f.isoformat()) \
        .lte("purchase_date", t.isoformat()) \
        .execute().data

    if data:
        df = pd.DataFrame(data)
        st.dataframe(df, use_container_width=True)

        st.metric("Total Purchase", f"Rs. {df['total_amount'].sum():.2f}")
        st.metric("Outstanding", f"Rs. {df['outstanding_amount'].sum():.2f}")
    else:
        st.warning("No data")

# =====================================================
# 📊 EXPENSE REPORT
# =====================================================
elif menu == "📊 Expense Report":
    st.header("📊 Expense Report")

    f = st.date_input("From")
    t = st.date_input("To")

    data = supabase.table("other_expenses") \
        .select("*") \
        .gte("expense_date", f.isoformat()) \
        .lte("expense_date", t.isoformat()) \
        .execute().data

    if data:
        df = pd.DataFrame(data)
        st.dataframe(df, use_container_width=True)
        st.metric("Total Expense", f"Rs. {df['amount'].sum():.2f}")
    else:
        st.warning("No data")

# =====================================================
# 🏪 MANAGE SHOPS
# =====================================================
elif menu == "🏪 Manage Shops":
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
        st.rerun()

    st.dataframe(pd.DataFrame(shops), use_container_width=True)

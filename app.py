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

def get_shop_cumulative(shop_id):
    data = supabase.table("daily_transactions") \
        .select("cylinders_delivered, empty_cylinders_received, balance_after_transaction") \
        .eq("shop_id", shop_id) \
        .order("transaction_date") \
        .execute().data

    if not data:
        return 0, 0, 0

    delivered = sum(d["cylinders_delivered"] for d in data)
    empty = sum(d["empty_cylinders_received"] for d in data)
    balance = data[-1]["balance_after_transaction"]
    return delivered, empty, balance

def generate_invoice_pdf(title, lines):
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, 800, title)
    y = 760
    c.setFont("Helvetica", 11)
    for line in lines:
        c.drawString(50, y, line)
        y -= 20
        if y < 80:
            c.showPage()
            y = 760
    c.showPage()
    c.save()
    buf.seek(0)
    return buf

def open_whatsapp_and_copy(msg, phone):
    components.html(
        f"""
        <textarea id="msg" style="position:absolute;left:-1000px">{msg}</textarea>
        <button onclick="send()">📤 Send WhatsApp</button>
        <script>
        function send() {{
            navigator.clipboard.writeText(document.getElementById("msg").value);
            window.open("https://wa.me/91{phone}", "_blank");
        }}
        </script>
        """,
        height=80,
    )

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

# ================= SHOP SEARCH (MOBILE SAFE) =================
search = st.sidebar.text_input("🔍 Search Shop")
filtered_shops = [s for s in shop_names if search.lower() in s.lower()]
shop_select_list = filtered_shops if filtered_shops else shop_names

# =========================================================
# 🚚 DELIVER CYLINDERS
# =========================================================
if menu == "🚚 Deliver Cylinders":
    st.header("🚚 Deliver Cylinders")

    shop_name = st.selectbox("Select Shop", shop_select_list)
    shop = shop_map[shop_name]

    prev_del, prev_empty, prev_balance = get_shop_cumulative(shop["shop_id"])

    delivered = st.number_input("Cylinders Delivered Today", 0)
    empty_today = st.number_input("Empty Received Today", 0)
    price = st.number_input("Price per Cylinder", 0.0)
    cash = st.number_input("Cash Paid", 0.0)
    upi = st.number_input("UPI Paid", 0.0)

    today_amount = delivered * price
    total_paid = cash + upi
    new_balance = prev_balance + today_amount - total_paid
    empty_pending = (prev_del + delivered) - (prev_empty + empty_today)

    st.subheader("📌 Summary")
    st.info(f"Today Amount: Rs. {today_amount:.2f}")
    st.success(f"Paid Today: Cash Rs.{cash:.2f} | UPI Rs.{upi:.2f} | Total Rs.{total_paid:.2f}")
    st.warning(f"Empty Yet to be Received: {empty_pending}")
    st.info(f"Previous Balance: Rs. {prev_balance:.2f}")
    st.error(f"Balance After Entry: Rs. {new_balance:.2f}")

    if st.button("SAVE DELIVERY", use_container_width=True):
        supabase.table("daily_transactions").insert({
            "shop_id": shop["shop_id"],
            "transaction_date": date.today().isoformat(),
            "cylinders_delivered": delivered,
            "empty_cylinders_received": empty_today,
            "price_per_cylinder": price,
            "total_amount": today_amount,
            "payment_cash": cash,
            "payment_upi": upi,
            "balance_after_transaction": new_balance
        }).execute()
        st.success("Delivery saved")

# =========================================================
# 🛒 PURCHASE CYLINDERS
# =========================================================
elif menu == "🛒 Purchase Cylinders":
    st.header("🛒 Purchase Cylinders")

    purchased = st.number_input("Cylinders Purchased", 0)
    empty_returned = st.number_input("Empty Returned", 0)
    price = st.number_input("Price per Cylinder", 0.0)
    cash = st.number_input("Cash Paid", 0.0)
    upi = st.number_input("UPI Paid", 0.0)

    p_data = supabase.table("cylinder_purchases").select("cylinders_purchased, empty_cylinders_returned").execute().data
    total_purchased = sum(p["cylinders_purchased"] for p in p_data) if p_data else 0
    total_empty_returned = sum(p["empty_cylinders_returned"] for p in p_data) if p_data else 0

    total_amount = purchased * price
    total_paid = cash + upi
    outstanding = total_amount - total_paid
    empty_pending = (total_purchased + purchased) - (total_empty_returned + empty_returned)

    st.subheader("📌 Summary")
    st.info(f"Total Amount: Rs. {total_amount:.2f}")
    st.success(f"Paid: Cash Rs.{cash:.2f} | UPI Rs.{upi:.2f} | Total Rs.{total_paid:.2f}")
    st.warning(f"Empty Yet to be Returned: {empty_pending}")
    st.error(f"Outstanding: Rs. {outstanding:.2f}")

    if st.button("SAVE PURCHASE", use_container_width=True):
        supabase.table("cylinder_purchases").insert({
            "purchase_date": date.today().isoformat(),
            "cylinders_purchased": purchased,
            "empty_cylinders_returned": empty_returned,
            "price_per_cylinder": price,
            "total_amount": total_amount,
            "payment_cash": cash,
            "payment_upi": upi,
            "outstanding_amount": outstanding
        }).execute()
        st.success("Purchase saved")

# =========================================================
# 📆 DAILY REPORT
# =========================================================
elif menu == "📆 Daily Report":
    st.header("📆 Daily Report")

    d = st.date_input("Select Date", date.today())
    data = supabase.table("daily_transactions") \
        .select("shop_id, cylinders_delivered, empty_cylinders_received, payment_cash, payment_upi, balance_after_transaction, shops(shop_name)") \
        .eq("transaction_date", d.isoformat()) \
        .execute().data

    if data:
        df = pd.DataFrame(data)
        df["Shop"] = df["shops"].apply(lambda x: x["shop_name"])
        df["Total Paid"] = df["payment_cash"] + df["payment_upi"]

        show = df[["Shop","cylinders_delivered","empty_cylinders_received","payment_cash","payment_upi","Total Paid","balance_after_transaction"]]
        show.columns = ["Shop","Delivered","Empty Received","Cash","UPI","Total Paid","Balance"]

        st.dataframe(show, use_container_width=True)

        st.subheader("Grand Totals")
        st.metric("Delivered", int(show["Delivered"].sum()))
        st.metric("Empty Received", int(show["Empty Received"].sum()))
        st.metric("Cash", f"Rs. {show['Cash'].sum():.2f}")
        st.metric("UPI", f"Rs. {show['UPI'].sum():.2f}")
        st.metric("Total Paid", f"Rs. {show['Total Paid'].sum():.2f}")

        pdf = generate_invoice_pdf(
            f"Daily Report - {d}",
            show.astype(str).apply(" | ".join, axis=1).tolist()
        )
        st.download_button("Download PDF", pdf, "daily_report.pdf")
    else:
        st.warning("No data")

# =========================================================
# 📊 DELIVERY REPORT
# =========================================================
elif menu == "📊 Delivery Report":
    st.header("📊 Delivery Report")

    shop_name = st.selectbox("Select Shop", shop_select_list)
    shop = shop_map[shop_name]

    f = st.date_input("From Date")
    t = st.date_input("To Date")

    data = supabase.table("daily_transactions") \
        .select("*") \
        .eq("shop_id", shop["shop_id"]) \
        .gte("transaction_date", f.isoformat()) \
        .lte("transaction_date", t.isoformat()) \
        .execute().data

    if data:
        df = pd.DataFrame(data)

        total_del = int(df["cylinders_delivered"].sum())
        total_empty = int(df["empty_cylinders_received"].sum())
        empty_pending = total_del - total_empty
        total_cash = df["payment_cash"].sum()
        total_upi = df["payment_upi"].sum()
        total_paid = total_cash + total_upi
        balance = df.iloc[-1]["balance_after_transaction"]

        st.metric("Delivered", total_del)
        st.metric("Empty Pending", empty_pending)
        st.metric("Total Paid", f"Rs. {total_paid:.2f}")
        st.error(f"Balance Due: Rs. {balance:.2f}")

        msg = f"""
Gas Cylinder Delivery Report

Shop: {shop_name}
Period: {f} to {t}

Delivered: {total_del}
Empty Pending: {empty_pending}

Paid:
Cash: Rs.{total_cash:.2f}
UPI: Rs.{total_upi:.2f}
Total: Rs.{total_paid:.2f}

Balance Due: Rs.{balance:.2f}
""".strip()

        st.text_area("WhatsApp Message", msg, height=240)
        open_whatsapp_and_copy(msg, shop["mobile_number"])

        pdf = generate_invoice_pdf(
            f"{shop_name} Delivery Report",
            msg.split("\n")
        )
        st.download_button("Download PDF", pdf, "delivery_report.pdf")
    else:
        st.warning("No records")

# =========================================================
# 📊 PURCHASE REPORT
# =========================================================
elif menu == "📊 Purchase Report":
    st.header("📊 Purchase Report")

    f = st.date_input("From Date")
    t = st.date_input("To Date")

    data = supabase.table("cylinder_purchases") \
        .select("*") \
        .gte("purchase_date", f.isoformat()) \
        .lte("purchase_date", t.isoformat()) \
        .execute().data

    if data:
        df = pd.DataFrame(data)
        st.dataframe(df, use_container_width=True)

        pdf = generate_invoice_pdf(
            "Purchase Report",
            df.astype(str).apply(" | ".join, axis=1).tolist()
        )
        st.download_button("Download PDF", pdf, "purchase_report.pdf")
    else:
        st.warning("No data")

# =========================================================
# 💸 OTHER EXPENSES + REPORT
# =========================================================
elif menu == "💸 Other Expenses":
    st.header("💸 Other Expenses")

    e_type = st.text_input("Expense Type")
    amt = st.number_input("Amount", 0.0)

    if st.button("SAVE EXPENSE", use_container_width=True):
        supabase.table("other_expenses").insert({
            "expense_date": date.today().isoformat(),
            "expense_type": e_type,
            "amount": amt
        }).execute()
        st.success("Saved")

elif menu == "📊 Expense Report":
    st.header("📊 Expense Report")

    f = st.date_input("From Date")
    t = st.date_input("To Date")

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

# =========================================================
# 🏪 MANAGE SHOPS
# =========================================================
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

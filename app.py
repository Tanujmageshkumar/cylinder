import streamlit as st
from supabase import create_client
import pandas as pd
from datetime import date
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
import streamlit.components.v1 as components

# ---------------- CONFIG ----------------
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
OWNER_PASSWORD = st.secrets["OWNER_PASSWORD"]

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
st.set_page_config(page_title="Gas Cylinder Manager", layout="centered")

# ---------------- AUTH ----------------
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

# ---------------- HELPERS ----------------
def get_shops():
    return supabase.table("shops").select("*").order("shop_name").execute().data

def get_shop_totals(shop_id):
    data = supabase.table("daily_transactions") \
        .select("cylinders_delivered, empty_cylinders_received, balance_after_transaction") \
        .eq("shop_id", shop_id) \
        .execute().data

    if not data:
        return 0, 0, 0

    delivered = sum(d["cylinders_delivered"] for d in data)
    empty = sum(d["empty_cylinders_received"] for d in data)
    balance = data[-1]["balance_after_transaction"]
    return delivered, empty, balance

def open_whatsapp_and_copy(text, phone):
    components.html(
        f"""
        <textarea id="msg" style="position:absolute;left:-1000px">{text}</textarea>
        <button onclick="send()">Send</button>
        <script>
        function send() {{
            navigator.clipboard.writeText(document.getElementById("msg").value);
            window.open("https://wa.me/91{phone}", "_blank");
        }}
        </script>
        """,
        height=80,
    )

def generate_daily_pdf(date_str, df, totals):
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, 800, f"Daily Delivery Report - {date_str}")

    y = 760
    c.setFont("Helvetica", 10)
    for _, r in df.iterrows():
        line = (
            f"{r['Shop']} | Del:{r['Delivered']} | "
            f"Empty:{r['Empty']} | Cash:{r['Cash']} | "
            f"UPI:{r['UPI']} | Bal:{r['Balance']}"
        )
        c.drawString(50, y, line)
        y -= 18
        if y < 80:
            c.showPage()
            y = 760

    c.showPage()
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, 760, "Grand Totals")
    y = 730
    for k, v in totals.items():
        c.drawString(50, y, f"{k}: {v}")
        y -= 20

    c.save()
    buf.seek(0)
    return buf

# ---------------- SIDEBAR ----------------
task = st.sidebar.radio(
    "📌 Select Action",
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
shop_names = [s["shop_name"] for s in shops]
shop_map = {s["shop_name"]: s for s in shops}

# =========================================================
# 🚚 DELIVER CYLINDERS
# =========================================================
if task == "🚚 Deliver Cylinders":
    st.header("🚚 Deliver Cylinders")

    shop_name = st.selectbox("🏪 Shop (type to search)", shop_names)
    shop = shop_map[shop_name]

    prev_del, prev_empty, prev_balance = get_shop_totals(shop["shop_id"])
    empty_pending = prev_del - prev_empty

    delivered = st.number_input("Cylinders Delivered Today", 0)
    empty_today = st.number_input("Empty Received Today", 0)
    price = st.number_input("Price per Cylinder", 0.0)
    cash = st.number_input("Cash Paid", 0.0)
    upi = st.number_input("UPI Paid", 0.0)

    today_amt = delivered * price
    paid = cash + upi
    new_balance = prev_balance + today_amt - paid

    st.info(f"Previous Balance: Rs. {prev_balance:.2f}")
    st.info(f"Empty Pending Before Today: {empty_pending}")
    st.success(f"Today Amount: Rs. {today_amt:.2f}")
    st.warning(f"Balance After Entry: Rs. {new_balance:.2f}")

    if st.button("SAVE DELIVERY", use_container_width=True):
        supabase.table("daily_transactions").insert({
            "shop_id": shop["shop_id"],
            "transaction_date": date.today().isoformat(),
            "cylinders_delivered": delivered,
            "empty_cylinders_received": empty_today,
            "price_per_cylinder": price,
            "total_amount": today_amt,
            "payment_cash": cash,
            "payment_upi": upi,
            "balance_after_transaction": new_balance
        }).execute()
        st.success("Saved")

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
        st.rerun()

    st.subheader("Existing Shops")
    st.dataframe(pd.DataFrame(shops), use_container_width=True)

# =========================================================
# 💸 OTHER EXPENSES + REPORT
# =========================================================
elif task == "💸 Other Expenses":
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

elif task == "📊 Expense Report":
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

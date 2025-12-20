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

    return (
        sum(d["cylinders_delivered"] for d in data),
        sum(d["empty_cylinders_received"] for d in data),
        data[-1]["balance_after_transaction"]
    )

def whatsapp_send(msg, phone):
    components.html(
        f"""
        <textarea id="msg" style="position:absolute;left:-1000px">{msg}</textarea>
        <button onclick="send()">📤 Send WhatsApp</button>
        <script>
        function send(){{
            navigator.clipboard.writeText(document.getElementById("msg").value);
            window.open("https://wa.me/91{phone}", "_blank");
        }}
        </script>
        """,
        height=80
    )

def daily_report_pdf(df, report_date):
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)

    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, 800, f"Daily Delivery Report - {report_date}")

    y = 760
    c.setFont("Helvetica-Bold", 9)
    headers = ["Shop", "Del", "Empty Rec", "Empty Pend", "Cash", "UPI", "Total", "Balance"]
    x_positions = [50, 200, 245, 310, 380, 430, 480, 540]

    for h, x in zip(headers, x_positions):
        c.drawString(x, y, h)

    y -= 15
    c.setFont("Helvetica", 9)

    for _, r in df.iterrows():
        values = [
            r["Shop"][:20],
            str(r["Delivered"]),
            str(r["Empty Received"]),
            str(r["Empty Pending"]),
            f"Rs.{r['Cash']:.0f}",
            f"Rs.{r['UPI']:.0f}",
            f"Rs.{r['Total Paid']:.0f}",
            f"Rs.{r['Balance']:.0f}"
        ]
        for v, x in zip(values, x_positions):
            c.drawString(x, y, v)
        y -= 15
        if y < 80:
            c.showPage()
            y = 760

    # Grand totals
    c.showPage()
    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, 760, "Grand Total")

    y = 720
    totals = {
        "Total Delivered": df["Delivered"].sum(),
        "Total Empty Pending": df["Empty Pending"].sum(),
        "Total Cash": df["Cash"].sum(),
        "Total UPI": df["UPI"].sum(),
        "Total Collected": df["Total Paid"].sum()
    }

    c.setFont("Helvetica", 11)
    for k, v in totals.items():
        c.drawString(50, y, f"{k}: {v}")
        y -= 25

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
# 🚚 DELIVER CYLINDERS (MOBILE-FRIENDLY SEARCH)
# =====================================================
if menu == "🚚 Deliver Cylinders":
    st.header("🚚 Deliver Cylinders")

    typed = st.text_input("🔍 Type Shop Name")
    sorted_shops = sorted(
        shop_names,
        key=lambda x: (typed.lower() not in x.lower(), x)
    )

    shop_name = st.selectbox("Select Shop", sorted_shops)
    shop = shop_map[shop_name]

    prev_del, prev_empty, prev_balance = get_shop_cumulative(shop["shop_id"])

    delivered = st.number_input("Cylinders Delivered Today", 0)
    empty_today = st.number_input("Empty Received Today", 0)
    price = st.number_input("Price per Cylinder", 0.0)
    cash = st.number_input("Cash Paid", 0.0)
    upi = st.number_input("UPI Paid", 0.0)

    today_amt = delivered * price
    total_paid = cash + upi
    new_balance = prev_balance + today_amt - total_paid
    empty_pending = (prev_del + delivered) - (prev_empty + empty_today)

    st.subheader("📌 Summary")
    st.info(f"Today Amount: Rs. {today_amt:.2f}")
    st.success(f"Paid → Cash Rs.{cash:.2f} | UPI Rs.{upi:.2f} | Total Rs.{total_paid:.2f}")
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
            "total_amount": today_amt,
            "payment_cash": cash,
            "payment_upi": upi,
            "balance_after_transaction": new_balance
        }).execute()
        st.success("Delivery saved")

# =====================================================
# 🛒 PURCHASE CYLINDERS (TOTAL OUTSTANDING)
# =====================================================
elif menu == "🛒 Purchase Cylinders":
    st.header("🛒 Purchase Cylinders")

    purchased = st.number_input("Cylinders Purchased", 0)
    empty_returned = st.number_input("Empty Returned", 0)
    price = st.number_input("Price per Cylinder", 0.0)
    cash = st.number_input("Cash Paid", 0.0)
    upi = st.number_input("UPI Paid", 0.0)

    p_data = supabase.table("cylinder_purchases").select("*").execute().data
    total_outstanding = sum(p["outstanding_amount"] for p in p_data) if p_data else 0

    today_total = purchased * price
    today_outstanding = today_total - (cash + upi)

    st.subheader("📌 Summary")
    st.info(f"Today Amount: Rs. {today_total:.2f}")
    st.warning(f"Total Outstanding (Till Now): Rs. {total_outstanding + today_outstanding:.2f}")

    if st.button("SAVE PURCHASE", use_container_width=True):
        supabase.table("cylinder_purchases").insert({
            "purchase_date": date.today().isoformat(),
            "cylinders_purchased": purchased,
            "empty_cylinders_returned": empty_returned,
            "price_per_cylinder": price,
            "total_amount": today_total,
            "payment_cash": cash,
            "payment_upi": upi,
            "outstanding_amount": today_outstanding
        }).execute()
        st.success("Purchase saved")

# =====================================================
# 📆 DAILY REPORT (BEAUTIFUL PDF)
# =====================================================
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
        df["Empty Pending"] = df["cylinders_delivered"] - df["empty_cylinders_received"]

        show = df[["Shop","cylinders_delivered","empty_cylinders_received","Empty Pending","payment_cash","payment_upi","Total Paid","balance_after_transaction"]]
        show.columns = ["Shop","Delivered","Empty Received","Empty Pending","Cash","UPI","Total Paid","Balance"]

        st.dataframe(show, use_container_width=True)

        pdf = daily_report_pdf(show, d)
        st.download_button("📄 Download PDF", pdf, "daily_report.pdf")
    else:
        st.warning("No deliveries")

# =====================================================
# REMAINING MODULES UNCHANGED
# =====================================================


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


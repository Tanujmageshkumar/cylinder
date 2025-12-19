import streamlit as st
from supabase import create_client
import pandas as pd
from datetime import date
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
import calendar
import streamlit.components.v1 as components

# ---------------- CONFIG ---------------- #
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
OWNER_PASSWORD = st.secrets["OWNER_PASSWORD"]

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
st.set_page_config(page_title="Gas Cylinder Manager", layout="wide")

# ---------------- SESSION STATE ---------------- #
if "auth" not in st.session_state:
    st.session_state.auth = False

if "show_report" not in st.session_state:
    st.session_state.show_report = False

# ---------------- AUTH ---------------- #
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
    txns = get_transactions(shop_id)
    bal = 0
    for t in txns:
        bal += t["total_amount"] - (t["payment_cash"] + t["payment_upi"])
        supabase.table("daily_transactions") \
            .update({"balance_after_transaction": bal}) \
            .eq("transaction_id", t["transaction_id"]) \
            .execute()

def generate_invoice_pdf(shop, summary):
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)

    c.setFont("Helvetica-Bold", 18)
    c.drawString(50, 800, "INVOICE")

    c.setFont("Helvetica", 10)
    c.drawString(50, 780, "Gas Cylinder Delivery Report")
    c.drawString(50, 750, f"Shop: {shop['shop_name']}")
    c.drawString(50, 735, f"Mobile: {shop['mobile_number']}")
    c.drawString(50, 720, f"Address: {shop['address']}")
    c.drawString(50, 705, f"Period: {summary['From']} to {summary['To']}")

    c.line(50, 690, 550, 690)

    quantity_fields = {"Cylinders Delivered", "Empty Received", "Empty Pending"}
    money_fields = {"Total Amount", "Cash Paid", "UPI Paid", "Balance"}

    y = 660
    c.setFont("Helvetica-Bold", 11)
    c.drawString(50, y, "Description")
    c.drawRightString(530, y, "Value")
    y -= 20

    c.setFont("Helvetica", 10)
    for k, v in summary.items():
        if k in ["From", "To"]:
            continue
        if k in quantity_fields:
            val = str(int(v))
        elif k in money_fields:
            val = f"Rs. {float(v):,.2f}"
        else:
            val = str(v)

        c.drawString(50, y, k)
        c.drawRightString(530, y, val)
        y -= 18

    c.setFont("Helvetica", 9)
    c.drawString(50, 80, "This is a system-generated invoice.")
    c.drawString(50, 65, "Thank you for your business.")

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
Paid (Cash): Rs. {summary['Cash Paid']:.2f}
Paid (UPI): Rs. {summary['UPI Paid']:.2f}
Balance Due: Rs. {summary['Balance']:.2f}

Thank you.
""".strip()

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
            alert("Copied to clipboard!");
        }}
        </script>
        """,
        height=80,
    )

# ---------------- UI ---------------- #
st.title("🛢️ Gas Cylinder Delivery Management")

tabs = st.tabs([
    "🏪 Shops",
    "📝 Daily Entry",
    "✏️ Edit / Delete",
    "📊 Shop Report",
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
    shop = shop_map[st.selectbox("Shop", shop_map.keys())]

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
    shop = shop_map[st.selectbox("Shop", shop_map.keys(), key="edit_shop")]
    txns = get_transactions(shop["shop_id"])

    if not txns:
        st.info("No entries")
    else:
        df = pd.DataFrame(txns)
        df["transaction_date"] = pd.to_datetime(df["transaction_date"]).dt.date
        st.dataframe(df, use_container_width=True)

        # ---- NEW: DATE-BASED SELECTION ---- #
        selected_date = st.selectbox(
            "Select Date",
            sorted(df["transaction_date"].unique())
        )

        day_rows = df[df["transaction_date"] == selected_date]

        if len(day_rows) > 1:
            st.info("Multiple entries found for this date")
            row_idx = st.selectbox(
                "Select Entry",
                day_rows.index,
                format_func=lambda i: f"Entry {list(day_rows.index).index(i)+1}"
            )
            row = day_rows.loc[row_idx]
        else:
            row = day_rows.iloc[0]

        with st.form("edit_form"):
            delivered = st.number_input("Delivered", value=int(row["cylinders_delivered"]))
            empty = st.number_input("Empty Received", value=int(row["empty_cylinders_received"]))
            price = st.number_input("Price", value=float(row["price_per_cylinder"]))
            cash = st.number_input("Cash", value=float(row["payment_cash"]))
            upi = st.number_input("UPI", value=float(row["payment_upi"]))

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
                supabase.table("daily_transactions") \
                    .delete() \
                    .eq("transaction_id", row["transaction_id"]) \
                    .execute()
                recalc_balance(shop["shop_id"])
                st.success("Deleted")
                st.rerun()

# ================= SHOP REPORT ================= #
with tabs[3]:
    shop = shop_map[st.selectbox("Shop", shop_map.keys(), key="rep")]
    f, t = st.columns(2)
    from_date = f.date_input("From")
    to_date = t.date_input("To")

    if st.button("Generate Report"):
        st.session_state.show_report = True

    if st.session_state.show_report:
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

            summary = {
                "From": from_date.strftime("%d-%m-%Y"),
                "To": to_date.strftime("%d-%m-%Y"),
                "Cylinders Delivered": int(df["cylinders_delivered"].sum()),
                "Empty Received": int(df["empty_cylinders_received"].sum()),
                "Empty Pending": int(df["cylinders_delivered"].sum() - df["empty_cylinders_received"].sum()),
                "Total Amount": df["total_amount"].sum(),
                "Cash Paid": df["payment_cash"].sum(),
                "UPI Paid": df["payment_upi"].sum(),
                "Balance": df.iloc[-1]["balance_after_transaction"]
            }

            st.subheader("📦 Cylinders")
            c1, c2, c3 = st.columns(3)
            c1.metric("Delivered", summary["Cylinders Delivered"])
            c2.metric("Empty Received", summary["Empty Received"])
            c3.metric("Pending", summary["Empty Pending"])

            st.subheader("💰 Payments")
            p1, p2, p3 = st.columns(3)
            p1.metric("Total", f"Rs. {summary['Total Amount']:.2f}")
            p2.metric("Cash", f"Rs. {summary['Cash Paid']:.2f}")
            p3.metric("UPI", f"Rs. {summary['UPI Paid']:.2f}")

            st.error(f"Balance Due: Rs. {summary['Balance']:.2f}")

            pdf = generate_invoice_pdf(shop, summary)
            st.download_button("📄 Download Invoice PDF", pdf, f"{shop['shop_name']}_invoice.pdf")

            msg = whatsapp_text(shop, summary)
            st.subheader("📱 Copy to WhatsApp")
            st.text_area("Message", msg, height=220)
            copy_to_clipboard(msg)

# ================= MONTHLY ANALYSIS ================= #
with tabs[4]:
    st.subheader("📅 Monthly Analysis (All Customers)")

    month_name = st.selectbox("Month", list(calendar.month_name)[1:])
    year = st.selectbox("Year", range(2023, 2031))

    month = list(calendar.month_name).index(month_name)
    start = f"{year}-{month:02d}-01"
    end = f"{year}-{month:02d}-31"

    data = supabase.table("daily_transactions") \
        .select("transaction_date, cylinders_delivered, empty_cylinders_received, total_amount, payment_cash, payment_upi, balance_after_transaction") \
        .gte("transaction_date", start) \
        .lte("transaction_date", end) \
        .execute().data

    if not data:
        st.info("No data for selected month")
    else:
        df = pd.DataFrame(data)
        df["date"] = pd.to_datetime(df["transaction_date"])

        payments = df.groupby("date").agg({
            "total_amount": "sum",
            "payment_cash": "sum",
            "payment_upi": "sum",
            "balance_after_transaction": "max"
        })

        st.subheader("💰 Payments Trend")
        st.line_chart(payments)

        qty = df.groupby("date").agg({
            "cylinders_delivered": "sum",
            "empty_cylinders_received": "sum"
        })

        st.subheader("📦 Quantity Movement")
        st.bar_chart(qty)

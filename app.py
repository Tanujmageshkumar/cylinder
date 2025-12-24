import streamlit as st
from supabase import create_client
from streamlit_searchbox import st_searchbox
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


def daily_report_pdf(df, report_date):
    from reportlab.lib.pagesizes import landscape, A4
    from reportlab.platypus import Table, TableStyle, SimpleDocTemplate, Paragraph, Spacer
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=30, rightMargin=30, topMargin=30, bottomMargin=30)
    elements = []
    styles = getSampleStyleSheet()

    title = Paragraph(f"<b>Daily Delivery Report - {report_date}</b>", styles['Title'])
    elements.append(title)
    elements.append(Spacer(1, 12))

    # Ensure columns match expected names
    expected_cols = ["Shop", "Delivered", "Price", "Total Amount", "Empty Received", "Empty Yet to be Received", "Cash", "UPI", "Balance"]
    if list(df.columns) != expected_cols:
        rename_map = {}
        for col in df.columns:
            if col.lower().replace(" ", "") == "shop":
                rename_map[col] = "Shop"
            elif col.lower().replace(" ", "") == "delivered":
                rename_map[col] = "Delivered"
            elif col.lower().replace(" ", "") in ["price", "cylinderrate"]:
                rename_map[col] = "Price"
            elif col.lower().replace(" ", "") == "totalamount":
                rename_map[col] = "Total Amount"
            elif col.lower().replace(" ", "") == "emptyreceived":
                rename_map[col] = "Empty Received"
            elif col.lower().replace(" ", "") in ["emptyyettobereceived", "emptyyet"]:
                rename_map[col] = "Empty Yet to be Received"
            elif col.lower().replace(" ", "") == "cash":
                rename_map[col] = "Cash"
            elif col.lower().replace(" ", "") == "upi":
                rename_map[col] = "UPI"
            elif col.lower().replace(" ", "") in ["balance", "pendingbalance"]:
                rename_map[col] = "Balance"
        df = df.rename(columns=rename_map)

    # Prepare table data
    table_data = [df.columns.tolist()]
    for _, row in df.iterrows():
        table_data.append([str(row[col]) for col in df.columns])

    # Table style
    col_widths = [110, 70, 90, 100, 90, 110, 80, 80, 110]
    table = Table(table_data, colWidths=col_widths)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.lightgrey),
        ('TEXTCOLOR', (0,0), (-1,0), colors.black),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTNAME', (0,1), (-1,-1), 'Helvetica'),
        ('FONTSIZE', (0,0), (-1,-1), 9),
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('ROWHEIGHT', (0,0), (-1,-1), 18),
    ]))
    elements.append(table)
    elements.append(Spacer(1, 18))

    # Grand totals
    totals = {
        "Total Delivered": df["Delivered"].sum(),
        "Total Empty Received": df["Empty Received"].sum(),
        "Total Empty Yet to be Received": (df["Delivered"].sum() - df["Empty Received"].sum()),
        "Total Cash": df["Cash"].sum(),
        "Total UPI": df["UPI"].sum(),
        "Total Collected": df["Total Paid"].sum(),
        "Total Pending Balance": df["Balance"].sum(),
        "Total Amount": df["Total Amount"].sum()
    }
    elements.append(Paragraph("<b>Grand Total</b>", styles['Heading2']))
    for k, v in totals.items():
        elements.append(Paragraph(f"{k}: {v}", styles['Normal']))

    doc.build(elements)
    buf.seek(0)
    return buf

# ================= SIDEBAR =================

# Inject custom CSS for sidebar menu font size and spacing
st.markdown(
    """
    <style>
    /* Sidebar radio font size and spacing */
    [data-testid="stSidebar"] .stRadio > div {
        font-size: 1.35rem !important;
        line-height: 2.2rem !important;
        margin-bottom: 1.2rem !important;
    }
    [data-testid="stSidebar"] .stRadio label {
        font-size: 1.35rem !important;
        line-height: 2.2rem !important;
        padding: 0.7rem 0.2rem !important;
    }
    [data-testid="stSidebar"] .stRadio div[role="radiogroup"] {
        gap: 0.7rem !important;
    }
    </style>
    """,
    unsafe_allow_html=True
)

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
        "✏️ Edit / Delete Entry",
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

    def search_shops(query):
        return [name for name in shop_names if query.lower() in name.lower()]

    shop_name = st_searchbox(
        search_function=search_shops,
        placeholder="Type or select shop name",
        label="Select Shop",
        key="deliver_shop_searchbox"
    )
    if not shop_name:
        st.warning("Please select a shop to proceed.")
        st.stop()
    shop = shop_map[shop_name]

    prev_del, prev_empty, prev_balance = get_shop_cumulative(shop["shop_id"])

    delivered = st.number_input("Cylinders Delivered Today", min_value=0, step=1)
    empty_today = st.number_input("Empty Received Today", min_value=0, step=1)
    price = st.number_input("Price per Cylinder", min_value=0, step=1, format="%d")
    cash = st.number_input("Cash Paid", min_value=0, step=1, format="%d")
    upi = st.number_input("UPI Paid", min_value=0, step=1, format="%d")

    today_amt = delivered * price
    total_paid = cash + upi
    new_balance = prev_balance + today_amt - total_paid

    # UI logic for empty_pending display
    if delivered == 0:
        empty_pending_ui = (prev_del) - (prev_empty + empty_today)
    else:
        empty_pending_ui = (prev_del + delivered) - (prev_empty + empty_today)

    st.subheader("📌 Summary")
    st.info(f"Today Amount: Rs. {today_amt:.2f}")
    st.success(f"Paid → Cash Rs.{cash:.2f} | UPI Rs.{upi:.2f} | Total Rs.{total_paid:.2f}")
    st.warning(f"Empty Yet to be Received: {empty_pending_ui}")
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

    purchased = st.number_input("Cylinders Purchased", min_value=0, step=1, format="%d")
    empty_returned = st.number_input("Empty Returned", min_value=0, step=1, format="%d")
    price = st.number_input("Price per Cylinder", min_value=0, step=1, format="%d")
    cash = st.number_input("Cash Paid", min_value=0, step=1, format="%d")
    upi = st.number_input("UPI Paid", min_value=0, step=1, format="%d")

    p_data = supabase.table("cylinder_purchases").select("*").execute().data
    total_outstanding = sum(p["outstanding_amount"] for p in p_data) if p_data else 0
    total_purchased = sum(p["cylinders_purchased"] for p in p_data) if p_data else 0
    total_empty_returned = sum(p["empty_cylinders_returned"] for p in p_data) if p_data else 0
    empty_yet_to_receive = total_purchased - total_empty_returned

    today_total = purchased * price
    today_outstanding = today_total - (cash + upi)

    st.subheader("📌 Summary")
    st.metric("Total Cylinders Purchased", total_purchased)
    st.metric("Total Empty Returned", total_empty_returned)
    st.metric("Empty Yet to Receive", empty_yet_to_receive)
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
        df["Delivered"] = df["cylinders_delivered"]
        df["Price"] = df["price_per_cylinder"]
        df["Total Amount"] = df["Delivered"] * df["Price"]
        df["Empty Received"] = df["empty_cylinders_received"]
        df["Empty Yet to be Received"] = df["Delivered"] - df["Empty Received"]
        df["Cash"] = df["payment_cash"]
        df["UPI"] = df["payment_upi"]
        df["Total Paid"] = df["Cash"] + df["UPI"]
        df["Balance"] = df["balance_after_transaction"]

        show = df[["Shop","Delivered","Price","Total Amount","Empty Received","Empty Yet to be Received","Cash","UPI","Total Paid","Balance"]]

        st.dataframe(show, use_container_width=True)

        st.subheader("📌 Summary")
        st.metric("Total Delivered", int(df["Delivered"].sum()))
        st.metric("Total Empty Received", int(df["Empty Received"].sum()))
        st.metric("Total Empty Yet to be Received", int(df["Empty Yet to be Received"].sum()))
        st.metric("Total Amount", f"Rs. {df['Total Amount'].sum():.2f}")
        st.metric("Total Paid (Cash)", f"Rs. {df['Cash'].sum():.2f}")
        st.metric("Total Paid (UPI)", f"Rs. {df['UPI'].sum():.2f}")
        st.metric("Total Paid", f"Rs. {df['Total Paid'].sum():.2f}")
        st.metric("Total Pending Balance", f"Rs. {df['Balance'].sum():.2f}")

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

    def search_shops(query):
        return [name for name in shop_names if query.lower() in name.lower()]

    shop_name = st_searchbox(
        search_function=search_shops,
        placeholder="Type or select shop name",
        label="Select Shop",
        key="del_rep_shop_searchbox"
    )
    if not shop_name:
        st.warning("Please select a shop to proceed.")
        st.stop()
    shop = shop_map[shop_name]

    from_date = st.date_input("From Date", key="del_rep_from")
    to_date = st.date_input("To Date", key="del_rep_to")

    # -------- Fetch data --------
    data = supabase.table("daily_transactions") \
        .select("*") \
        .eq("shop_id", shop["shop_id"]) \
        .gte("transaction_date", from_date.isoformat()) \
        .lte("transaction_date", to_date.isoformat()) \
        .order("transaction_date") \
        .execute().data

    if not data:
        st.warning("No delivery records for this period")
        st.stop()

    df = pd.DataFrame(data)

    # -------- Calculations & Table --------
    df["Delivered"] = df["cylinders_delivered"]
    df["Price"] = df["price_per_cylinder"]
    df["Total Amount"] = df["Delivered"] * df["Price"]
    df["Empty Received"] = df["empty_cylinders_received"]
    df["Empty Yet to be Received"] = df["Delivered"] - df["Empty Received"]
    df["Cash"] = df["payment_cash"]
    df["UPI"] = df["payment_upi"]
    df["Total Paid"] = df["Cash"] + df["UPI"]
    df["Balance"] = df["balance_after_transaction"]

    st.subheader("📌 Report Summary")
    st.metric("Cylinders Delivered", int(df["Delivered"].sum()))
    st.metric("Empty Received", int(df["Empty Received"].sum()))
    st.metric("Empty Yet to be Received", int(df["Empty Yet to be Received"].sum()))
    st.metric("Total Amount", f"Rs. {df['Total Amount'].sum():.2f}")
    st.metric("Cash Paid", f"Rs. {df['Cash'].sum():.2f}")
    st.metric("UPI Paid", f"Rs. {df['UPI'].sum():.2f}")
    st.metric("Total Paid", f"Rs. {df['Total Paid'].sum():.2f}")
    st.metric("Pending Balance", f"Rs. {df['Balance'].sum():.2f}")

    # -------- Detailed Table --------
    st.subheader("📄 Detailed Entries")
    show = df[["transaction_date","Delivered","Price","Total Amount","Empty Received","Empty Yet to be Received","Cash","UPI","Total Paid","Balance"]]
    st.dataframe(show, use_container_width=True)

    # -------- WhatsApp Message --------
    whatsapp_msg = f"""
Gas Cylinder Delivery Report

Shop: {shop_name}
Period: {from_date.strftime('%d-%m-%Y')} to {to_date.strftime('%d-%m-%Y')}

Cylinders Delivered: {int(df['Delivered'].sum())}
Cylinder Rate: Rs. {df['Price'].iloc[-1]:.2f}
Total Amount: Rs. {df['Total Amount'].sum():.2f}
Empty Received: {int(df['Empty Received'].sum())}
Empty Yet to be Received: {int(df['Empty Yet to be Received'].sum())}

Paid:
Cash: Rs. {df['Cash'].sum():.2f}
UPI: Rs. {df['UPI'].sum():.2f}
Total Paid: Rs. {df['Total Paid'].sum():.2f}

Pending Balance: Rs. {df['Balance'].sum():.2f}

Thank you.
""".strip()

    st.subheader("📱 Send to WhatsApp")
    st.text_area("Message", whatsapp_msg, height=260)

    whatsapp_send(whatsapp_msg, shop["mobile_number"])

    # -------- PDF DOWNLOAD --------
    pdf = daily_report_pdf(show, f"{shop_name} Delivery Report {from_date} to {to_date}")
    st.download_button(
        "📄 Download PDF",
        pdf,
        f"{shop_name}_delivery_report.pdf",
        use_container_width=True
    )

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
# ✏️ EDIT / DELETE ENTRY
# =========================================================
elif menu == "✏️ Edit / Delete Entry":
    st.header("✏️ Edit / Delete Entry")

    def search_shops(query):
        return [name for name in shop_names if query.lower() in name.lower()]

    shop_name = st_searchbox(
        search_function=search_shops,
        placeholder="Type or select shop name",
        label="Select Shop",
        key="edit_shop_searchbox"
    )
    if not shop_name:
        st.warning("Please select a shop to proceed.")
        st.stop()
    shop = shop_map[shop_name]
    txns = supabase.table("daily_transactions").select("*").eq("shop_id", shop["shop_id"]).order("transaction_date").execute().data

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
                # Recalculate balance for this shop after update
                # (Assume recalc_balance is not defined, so recalculate manually)
                txns2 = supabase.table("daily_transactions").select("*").eq("shop_id", shop["shop_id"]).order("transaction_date").execute().data
                if txns2:
                    txns2 = sorted(txns2, key=lambda x: x["transaction_date"])
                    balance = 0
                    for t in txns2:
                        t["total_amount"] = t["cylinders_delivered"] * t["price_per_cylinder"]
                        paid = t["payment_cash"] + t["payment_upi"]
                        balance = balance + t["total_amount"] - paid
                        supabase.table("daily_transactions").update({"balance_after_transaction": balance}).eq("transaction_id", t["transaction_id"]).execute()
                st.success("Updated")
                st.rerun()

            if col2.form_submit_button("Delete"):
                supabase.table("daily_transactions").delete().eq("transaction_id", row["transaction_id"]).execute()
                # Recalculate balance for this shop after delete
                txns2 = supabase.table("daily_transactions").select("*").eq("shop_id", shop["shop_id"]).order("transaction_date").execute().data
                if txns2:
                    txns2 = sorted(txns2, key=lambda x: x["transaction_date"])
                    balance = 0
                    for t in txns2:
                        t["total_amount"] = t["cylinders_delivered"] * t["price_per_cylinder"]
                        paid = t["payment_cash"] + t["payment_upi"]
                        balance = balance + t["total_amount"] - paid
                        supabase.table("daily_transactions").update({"balance_after_transaction": balance}).eq("transaction_id", t["transaction_id"]).execute()
                st.success("Deleted")
                st.rerun()


# =========================================================
# 🏪 MANAGE SHOPS (EDIT/DELETE)
# =========================================================
elif menu == "🏪 Manage Shops":
    st.header("🏪 Manage Shops")

    # Add new shop
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

    st.subheader("Edit/Delete Shops")
    if shops:
        shop_names_list = [f"{s['shop_name']} ({s['mobile_number']})" for s in shops]
        def search_shop_objs(query):
            return [f"{s['shop_name']} ({s['mobile_number']})" for s in shops if query.lower() in s['shop_name'].lower() or query.lower() in s['mobile_number']]

        selected_shop_display = st_searchbox(
            search_function=search_shop_objs,
            placeholder="Type or select shop",
            label="Select Shop to Edit/Delete",
            key="manage_shop_searchbox"
        )
        if not selected_shop_display:
            st.info("Please select a shop to edit or delete.")
        else:
            shop = next(s for s in shops if f"{s['shop_name']} ({s['mobile_number']})" == selected_shop_display)
            edit_name = st.text_input("Edit Name", shop['shop_name'], key=f"edit_name_{shop['shop_id']}")
            edit_mobile = st.text_input("Edit Mobile", shop['mobile_number'], key=f"edit_mobile_{shop['shop_id']}")
            edit_address = st.text_area("Edit Address", shop['address'], key=f"edit_address_{shop['shop_id']}")

            col1, col2 = st.columns(2)
            with col1:
                if st.button("Save Changes", key=f"save_{shop['shop_id']}"):
                    supabase.table("shops").update({
                        "shop_name": edit_name,
                        "mobile_number": edit_mobile,
                        "address": edit_address
                    }).eq("shop_id", shop["shop_id"]).execute()
                    st.success("Shop updated")
                    st.rerun()
            with col2:
                if st.button("Delete Shop", key=f"delete_{shop['shop_id']}"):
                    supabase.table("shops").delete().eq("shop_id", shop["shop_id"]).execute()
                    st.warning("Shop deleted")
                    st.rerun()
    else:
        st.info("No shops available.")

    st.dataframe(pd.DataFrame(shops), use_container_width=True)


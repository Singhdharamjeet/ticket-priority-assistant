import io
from datetime import datetime, timedelta
 
import pandas as pd
import streamlit as st
 
from ticket_priority_assistant import Ticket, demo_tickets, parse_date, prioritize

st.set_page_config(page_title="Ticket Priority Assistant", page_icon="🎫", layout="wide")
 
PRIORITY_ICON = {"P1": "🔴", "P2": "🟠", "P3": "🔵", "P4": "⚪"}
TIERS = ["free", "standard", "premium", "enterprise"]

#State
if "tickets" not in st.session_state:
    st.session_state.tickets = demo_tickets()
if "next_id" not in st.session_state:
    st.session_state.next_id = 106
 
 
def add_ticket(title, description, tier, users, hours_waiting):
    st.session_state.tickets.append(Ticket(
        id=f"T-{st.session_state.next_id}",
        title=title.strip(),
        description=description.strip(),
        customer_tier=tier,
        users_affected=int(users),
        created_at=datetime.now() - timedelta(hours=hours_waiting),
    ))
    st.session_state.next_id += 1


def import_csv(uploaded) -> int:
    df = pd.read_csv(uploaded).fillna("")
    df.columns = [c.strip().lower() for c in df.columns]
    count = 0
    for _, row in df.iterrows():
        try:
            users = int(row.get("users_affected") or 1)
        except (ValueError, TypeError):
            users = 1
        tier = str(row.get("customer_tier") or "standard").lower()
        st.session_state.tickets.append(Ticket(
            id=str(row.get("id") or f"T-{st.session_state.next_id}"),
            title=str(row.get("title", "")),
            description=str(row.get("description", "")),
            customer_tier=tier if tier in TIERS else "standard",
            users_affected=users,
            created_at=parse_date(str(row.get("created_at", ""))),
        ))
        st.session_state.next_id += 1
        count += 1
    return count

#sidebar

with st.sidebar:
    st.header("New ticket")
    with st.form("new_ticket", clear_on_submit=True):
        title = st.text_input("Title")
        description = st.text_area("Description", height=100)
        tier = st.selectbox("Customer tier", TIERS, index=1)
        users = st.number_input("Users affected", min_value=1, value=1, step=1)
        hours = st.number_input("Hours waiting", min_value=0, value=0, step=1)
        submitted = st.form_submit_button("Score ticket", use_container_width=True)
        if submitted:
            if title.strip():
                add_ticket(title, description, tier, users, hours)
                st.success("Ticket added.")
            else:
                st.error("Enter a title before scoring.")
 
    st.divider()
    st.subheader("Import CSV")
    uploaded = st.file_uploader("Columns: id, title, description, customer_tier, users_affected, created_at",
                                type="csv", label_visibility="visible")
    if uploaded and st.button("Import tickets", use_container_width=True):
        try:
            st.success(f"Imported {import_csv(uploaded)} tickets.")
        except Exception as exc:
            st.error(f"Could not read that file: {exc}")
 
    st.divider()
    c1, c2 = st.columns(2)
    if c1.button("Load samples", use_container_width=True):
        existing = {t.id for t in st.session_state.tickets}
        st.session_state.tickets += [t for t in demo_tickets() if t.id not in existing]
    if c2.button("Clear all", use_container_width=True):
        st.session_state.tickets = []
        st.rerun()

    #main

st.title("Ticket Priority Assistant")
st.caption("Tickets are ranked P1-P4 from keywords, customer tier, impact and time waiting.")
 
results = prioritize(st.session_state.tickets)
 
if not results:
    st.info("No tickets yet. Add one in the sidebar, or choose Load samples.")
    st.stop()

#summary metric
cols = st.columns(4)
for col, level in zip(cols, ["P1", "P2", "P3", "P4"]):
    n = sum(r.priority == level for r in results)
    col.metric(f"{PRIORITY_ICON[level]} {level}", n)
 
selected = st.multiselect("Show priorities", ["P1", "P2", "P3", "P4"],
                          default=["P1", "P2", "P3", "P4"])
shown = [r for r in results if r.priority in selected]

#ranked table
table = pd.DataFrame([{
    "Rank": i,
    "ID": r.ticket.id,
    "Priority": f"{PRIORITY_ICON[r.priority]} {r.priority}",
    "Score": r.score,
    "Title": r.ticket.title,
    "Tier": r.ticket.customer_tier,
    "Users": r.ticket.users_affected,
    "Response target": r.sla.split(" - ")[-1],
} for i, r in enumerate(results, 1) if r.priority in selected])
 
st.dataframe(table, hide_index=True, use_container_width=True)

#export
export = pd.DataFrame([{
    "rank": i, "id": r.ticket.id, "title": r.ticket.title, "priority": r.priority,
    "score": r.score, "sla": r.sla, "reasons": "; ".join(r.reasons),
} for i, r in enumerate(results, 1)])
st.download_button("Download ranked tickets (CSV)",
                   export.to_csv(index=False).encode("utf-8"),
                   file_name="ranked_tickets.csv", mime="text/csv")

#deatil view
st.subheader("Why each ticket scored the way it did")
for r in shown:
    label = f"{PRIORITY_ICON[r.priority]} {r.priority} · {r.ticket.id} · {r.ticket.title}  (score {r.score})"
    with st.expander(label):
        if r.ticket.description:
            st.write(r.ticket.description)
        st.caption(r.sla)
        for reason in r.reasons or ["No scoring signals found."]:
            st.markdown(f"- {reason}")
        if st.button("Remove ticket", key=f"del_{r.ticket.id}"):
            st.session_state.tickets = [t for t in st.session_state.tickets if t.id != r.ticket.id]
            st.rerun()
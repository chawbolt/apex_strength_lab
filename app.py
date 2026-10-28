import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from coach_engine import process_athlete_data, generate_demo_dataset, generate_pdf_report

st.set_page_config(page_title="Apex Strength Lab", page_icon="🏋️‍♂️", layout="wide")

st.markdown("""
<style>
    div[data-testid="stMetric"] {
        background-color: #161B26;
        border: 1px solid #283044;
        padding: 16px 20px;
        border-radius: 12px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.2);
    }
    .coach-brief {
        padding: 16px 20px;
        border-radius: 10px;
        margin-bottom: 20px;
        font-size: 0.98rem;
        line-height: 1.5;
    }
</style>
""", unsafe_allow_html=True)

# --- GOOGLE SHEETS CONNECTION WITH FALLBACK ---
gsheets_connected = False
conn = None

try:
    from streamlit_gsheets import GSheetsConnection
    conn = st.connection("gsheets", type=GSheetsConnection)
    cloud_df = conn.read(ttl=0)
    if cloud_df is not None and not cloud_df.empty:
        gsheets_connected = True
except Exception:
    gsheets_connected = False

# Initialize Session State if Google Sheets is not yet connected
if "workout_db" not in st.session_state:
    if gsheets_connected:
        st.session_state.workout_db = cloud_df
    else:
        demo = generate_demo_dataset()
        demo.insert(0, "Athlete", "Alex Mercer")
        st.session_state.workout_db = demo

db = st.session_state.workout_db.copy()
if "Athlete" not in db.columns:
    db.insert(0, "Athlete", "Alex Mercer")

# --- SIDEBAR: ATHLETE ROSTER & DATA SOURCE ---
st.sidebar.markdown("## ⚡ Apex Strength Lab")
if gsheets_connected:
    st.sidebar.success("🟢 Connected to Google Sheets")
else:
    st.sidebar.info("🟡 Running Local / Session Memory")

existing_athletes = sorted(db['Athlete'].dropna().unique().tolist())
if not existing_athletes:
    existing_athletes = ["Alex Mercer"]

st.sidebar.subheader("Athlete Selection")
selected_athlete = st.sidebar.selectbox("Select Athlete", existing_athletes)

new_athlete_name = st.sidebar.text_input("➕ Add New Athlete")
if st.sidebar.button("Create Athlete Profile") and new_athlete_name:
    if new_athlete_name not in existing_athletes:
        # Create an initial placeholder set for the new athlete
        new_row = pd.DataFrame([{
            "Athlete": new_athlete_name,
            "Date": pd.Timestamp.today().strftime("%Y-%m-%d"),
            "Exercise": "Squat",
            "Weight": 225.0,
            "Reps": 5,
            "RPE": 7.0
        }])
        st.session_state.workout_db = pd.concat([st.session_state.workout_db, new_row], ignore_index=True)
        if gsheets_connected and conn is not None:
            conn.update(data=st.session_state.workout_db)
        st.rerun()

# Filter data for currently selected athlete
athlete_data = db[db['Athlete'] == selected_athlete].copy()
if athlete_data.empty:
    st.warning(f"No workout data logged yet for {selected_athlete}.")
    st.stop()

available_lifts = sorted(athlete_data['Exercise'].dropna().unique().tolist())
exercise_focus = st.sidebar.selectbox("Analyze Movement", available_lifts + ["All Lifts"])

# --- PROCESS ANALYTICS ---
analytics, sbd_totals, filtered_sets = process_athlete_data(athlete_data, selected_lift=exercise_focus)
latest = analytics.iloc[-1]
week_ago = analytics.iloc[-8] if len(analytics) >= 8 else analytics.iloc[0]

e1rm_delta = round(latest['Rolling_e1RM'] - week_ago['Rolling_e1RM'], 1)
acute_pct_diff = round(((latest['Acute_Load'] - latest['Chronic_Load']) / max(1, latest['Chronic_Load'])) * 100, 1)

# --- PDF EXPORT BUTTON ---
st.sidebar.markdown("---")
st.sidebar.subheader("📄 Client Check-In Report")
pdf_buffer = generate_pdf_report(selected_athlete, exercise_focus, latest, sbd_totals, latest['Status'])
st.sidebar.download_button(
    label="📥 Export PDF Report",
    data=pdf_buffer,
    file_name=f"{selected_athlete.replace(' ', '_')}_{exercise_focus}_Report.pdf",
    mime="application/pdf",
    use_container_width=True,
    type="primary"
)

# --- HEADER & AI COACH BRIEF ---
st.title(f"🏋️‍♂️ {selected_athlete} — Performance & Readiness")

acwr_val = latest['ACWR']
if acwr_val > 1.45:
    brief_bg, brief_border, icon = "rgba(239, 68, 68, 0.12)", "#EF4444", "🚨"
    brief_msg = f"<b>Overreaching Warning ({acwr_val:.2f} ACWR):</b> {selected_athlete}'s 7-day volume is <b>+{acute_pct_diff}%</b> above baseline. Elevated fatigue risk—reduce back-off volume by 25% this week."
elif acwr_val < 0.80:
    brief_bg, brief_border, icon = "rgba(59, 130, 246, 0.12)", "#3B82F6", "🔋"
    brief_msg = f"<b>High Readiness / Fresh ({acwr_val:.2f} ACWR):</b> Fatigue has cleared below baseline. {selected_athlete} is ready for heavy singles or a volume wave."
else:
    brief_bg, brief_border, icon = "rgba(16, 185, 129, 0.12)", "#10B981", "✅"
    brief_msg = f"<b>Optimal Progression ({acwr_val:.2f} ACWR):</b> Volume absorption is clean. {exercise_focus} e1RM has shifted <b>{e1rm_delta:+.1f} lbs</b> over the last 7 days."

st.markdown(
    f'<div class="coach-brief" style="background:{brief_bg}; border-left: 5px solid {brief_border};">'
    f'{icon} {brief_msg}</div>',
    unsafe_allow_html=True
)

# --- METRIC CARDS ---
c1, c2, c3, c4 = st.columns(4)
with c1:
    st.metric(f"{exercise_focus} Peak e1RM", f"{latest['Rolling_e1RM']:,.1f} lbs", delta=f"{e1rm_delta:+.1f} lbs (7d)")
with c2:
    st.metric("Projected SBD Total", f"{sbd_totals['Total']:,.0f} lbs", delta=f"S:{sbd_totals['Squat']:.0f} | B:{sbd_totals['Bench Press']:.0f} | D:{sbd_totals['Deadlift']:.0f}", delta_color="off")
with c3:
    st.metric("7-Day Acute Load", f"{latest['Acute_Load']:,.0f} lbs/d", delta=f"{acute_pct_diff:+.1f}% vs Baseline", delta_color="inverse" if acwr_val > 1.45 else "normal")
with c4:
    st.metric("Fatigue Ratio (ACWR)", f"{acwr_val:.2f}", delta=latest['Status'], delta_color="inverse" if acwr_val > 1.45 else "normal")

# --- TABS: ANALYTICS + INTERACTIVE DATA EDITOR ---
tab1, tab2, tab3 = st.tabs(["📈 Strength & Fatigue Visuals", "✏️ Log & Edit Workouts (Live Sheet)", "📋 Daily Aggregations"])

with tab1:
    lift_days = analytics[analytics['Did_Lift']].copy()
    fig_str = go.Figure()
    fig_str.add_trace(go.Bar(
        x=lift_days['Date'], y=lift_days['Total_Volume'], name='Tonnage (lbs)',
        marker_color='rgba(99, 110, 250, 0.28)', yaxis='y2'
    ))
    fig_str.add_trace(go.Scatter(
        x=lift_days['Date'], y=lift_days['Peak_e1RM'], mode='lines+markers',
        name=f'{exercise_focus} e1RM', line=dict(color='#10B981', width=3.5)
    ))
    fig_str.update_layout(
        title=f"{exercise_focus} — e1RM vs. Session Tonnage", template="plotly_dark",
        hovermode="x unified", height=420, margin=dict(l=20, r=20, t=50, b=20),
        yaxis=dict(title="e1RM (lbs)"), yaxis2=dict(title="Volume (lbs)", overlaying="y", side="right")
    )
    st.plotly_chart(fig_str, use_container_width=True)

with tab2:
    st.subheader(f"Editing Training Logs for {selected_athlete}")
    st.caption("Edit numbers directly in cells, click rows to delete, or scroll down and click '+' to log new sets.")
    
    # Editable DataFrame

    editable_cols = ["Date", "Exercise", "Weight", "Reps", "RPE"]
    athlete_logs = athlete_data[editable_cols].sort_values("Date", ascending=False).reset_index(drop=True)
    athlete_logs['Date'] = pd.to_datetime(athlete_logs['Date']).dt.date
    
    edited_logs = st.data_editor(
        athlete_logs,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "Date": st.column_config.DateColumn("Workout Date", required=True),
            "Exercise": st.column_config.SelectboxColumn("Exercise", options=["Squat", "Bench Press", "Deadlift", "Overhead Press", "Barbell Row"], required=True),
            "Weight": st.column_config.NumberColumn("Weight (lbs)", min_value=0.0, step=2.5, format="%.1f lbs", required=True),
            "Reps": st.column_config.NumberColumn("Reps", min_value=1, max_value=30, step=1, required=True),
            "RPE": st.column_config.NumberColumn("RPE", min_value=5.0, max_value=10.0, step=0.5, format="%.1f")
        }
    )
    
    if st.button("💾 Save Changes & Recalculate", type="primary"):
        # Reconstruct full DB with updated athlete records
        edited_logs["Athlete"] = selected_athlete
        edited_logs["Date"] = pd.to_datetime(edited_logs["Date"]).dt.strftime("%Y-%m-%d")
        
        other_athletes = db[db['Athlete'] != selected_athlete]
        updated_db = pd.concat([other_athletes, edited_logs], ignore_index=True)
        st.session_state.workout_db = updated_db
        
        if gsheets_connected and conn is not None:
            conn.update(data=updated_db)
            st.success("✅ Changes synced to Google Sheet!")
        else:
            st.success("✅ Changes saved to current session!")
        st.rerun()

with tab3:
    st.dataframe(analytics[analytics['Did_Lift']].tail(12)[['Date', 'Peak_e1RM', 'Top_Weight', 'Total_Sets', 'Total_Volume', 'Avg_RPE', 'ACWR', 'Status']], use_container_width=True, hide_index=True)
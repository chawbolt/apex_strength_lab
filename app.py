import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from coach_engine import process_athlete_data, generate_demo_dataset, generate_pdf_report

st.set_page_config(page_title="Apex Strength Lab", page_icon="🏋️‍♂️", layout="wide")

# --- CUSTOM CSS FOR COMMERCIAL SAAS FEEL ---
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

# --- SIDEBAR CONTROLS ---
st.sidebar.markdown("## ⚡ Apex Strength Lab")
st.sidebar.caption("Quantitative Periodization & Fatigue Suite")

athlete_name = st.sidebar.text_input("Athlete Name", "Alex Mercer")
data_source = st.sidebar.radio("Workout Data Source", ["Demo Athlete (6-Week SBD Block)", "Upload Custom CSV"])

demo_df = generate_demo_dataset()

if data_source == "Upload Custom CSV":
    st.sidebar.download_button(
        label="📥 Download Sample CSV Template",
        data=demo_df.to_csv(index=False).encode('utf-8'),
        file_name="sample_athlete_log.csv",
        mime="text/csv",
        use_container_width=True
    )
    uploaded_file = st.sidebar.file_uploader("Upload CSV (Date, Exercise, Weight, Reps, RPE)", type=["csv"])
    if uploaded_file is not None:
        raw_df = pd.read_csv(uploaded_file)
    else:
        st.info("👈 Download the Sample CSV Template from the sidebar or switch to 'Demo Athlete' to explore.")
        st.stop()
else:
    raw_df = demo_df

available_lifts = sorted(raw_df['Exercise'].dropna().unique().tolist())
exercise_focus = st.sidebar.selectbox("Analyze Movement", available_lifts + ["All Lifts"])

# --- RUN ANALYTICS ---
analytics, sbd_totals, filtered_sets = process_athlete_data(raw_df, selected_lift=exercise_focus)
latest = analytics.iloc[-1]
week_ago = analytics.iloc[-8] if len(analytics) >= 8 else analytics.iloc[0]

e1rm_delta = round(latest['Rolling_e1RM'] - week_ago['Rolling_e1RM'], 1)
acute_pct_diff = round(((latest['Acute_Load'] - latest['Chronic_Load']) / max(1, latest['Chronic_Load'])) * 100, 1)

# --- SIDEBAR EXPORT ---
st.sidebar.markdown("---")
st.sidebar.subheader("📄 Client Check-In Report")
pdf_buffer = generate_pdf_report(athlete_name, exercise_focus, latest, sbd_totals, latest['Status'])
st.sidebar.download_button(
    label="📥 Export Branded PDF Briefing",
    data=pdf_buffer,
    file_name=f"{athlete_name.replace(' ', '_')}_{exercise_focus}_Report.pdf",
    mime="application/pdf",
    use_container_width=True,
    type="primary"
)

# --- HEADER & AI COACH BRIEF ---
st.title(f"🏋️‍♂️ {athlete_name} — Performance & Readiness")

acwr_val = latest['ACWR']
if acwr_val > 1.45:
    brief_bg, brief_border, icon = "rgba(239, 68, 68, 0.12)", "#EF4444", "🚨"
    brief_msg = f"<b>Overreaching Warning ({acwr_val:.2f} ACWR):</b> {athlete_name}'s 7-day workload is <b>+{acute_pct_diff}%</b> above their 28-day baseline. Injury and CNS fatigue risk is elevated—consider cutting back-off volume by 25-30% this week."
elif acwr_val < 0.80:
    brief_bg, brief_border, icon = "rgba(59, 130, 246, 0.12)", "#3B82F6", "🔋"
    brief_msg = f"<b>High Readiness / Deloaded ({acwr_val:.2f} ACWR):</b> Acute fatigue has dropped well below chronic capacity. {athlete_name} is recovered and primed for heavy singles or a new volume block."
else:
    brief_bg, brief_border, icon = "rgba(16, 185, 129, 0.12)", "#10B981", "✅"
    brief_msg = f"<b>Optimal Sweet Spot ({acwr_val:.2f} ACWR):</b> {athlete_name} is adapting cleanly. {exercise_focus} e1RM has moved <b>{e1rm_delta:+.1f} lbs</b> over the last 7 days while fatigue remains controlled."

st.markdown(
    f'<div class="coach-brief" style="background:{brief_bg}; border-left: 5px solid {brief_border};">'
    f'{icon} {brief_msg}</div>',
    unsafe_allow_html=True
)

# --- TOP KPI METRIC ROW ---
c1, c2, c3, c4 = st.columns(4)
with c1:
    st.metric(f"{exercise_focus} Peak e1RM", f"{latest['Rolling_e1RM']:,.1f} lbs", delta=f"{e1rm_delta:+.1f} lbs (7d)")
with c2:
    st.metric("Projected SBD Total", f"{sbd_totals['Total']:,.0f} lbs", delta=f"S:{sbd_totals['Squat']:.0f} | B:{sbd_totals['Bench Press']:.0f} | D:{sbd_totals['Deadlift']:.0f}", delta_color="off")
with c3:
    st.metric("7-Day Acute Load", f"{latest['Acute_Load']:,.0f} lbs/d", delta=f"{acute_pct_diff:+.1f}% vs 28d Base", delta_color="inverse" if acwr_val > 1.45 else "normal")
with c4:
    st.metric("Fatigue Ratio (ACWR)", f"{acwr_val:.2f}", delta=latest['Status'], delta_color="inverse" if acwr_val > 1.45 else "normal")

# --- TABS FOR CLEAN NAVIGATION ---
tab1, tab2, tab3 = st.tabs(["📈 Strength & Tonnage Progression", "⚡ Workload & Fatigue (ACWR)", "📋 Clean Session Logs"])

with tab1:
    lift_days = analytics[analytics['Did_Lift']].copy()
    
    fig_str = go.Figure()
    # Daily Tonnage Bars on secondary axis
    fig_str.add_trace(go.Bar(
        x=lift_days['Date'],
        y=lift_days['Total_Volume'],
        name='Session Tonnage (lbs)',
        marker_color='rgba(99, 110, 250, 0.28)',
        yaxis='y2',
        hovertemplate='<b>%{x|%b %d}</b><br>Session Volume: %{y:,.0f} lbs<extra></extra>'
    ))
    # e1RM Line on primary axis
    fig_str.add_trace(go.Scatter(
        x=lift_days['Date'],
        y=lift_days['Peak_e1RM'],
        mode='lines+markers',
        name=f'{exercise_focus} e1RM (lbs)',
        line=dict(color='#10B981', width=3.5),
        marker=dict(size=8, color='#10B981', line=dict(width=1.5, color='#0F172A')),
        hovertemplate='<b>%{x|%b %d}</b><br>Estimated 1RM: %{y:.1f} lbs<extra></extra>'
    ))
    
    fig_str.update_layout(
        title=f"{exercise_focus} — Estimated 1RM vs. Session Volume Load",
        template="plotly_dark",
        hovermode="x unified",
        height=440,
        margin=dict(l=20, r=20, t=50, b=20),
        yaxis=dict(title="Estimated 1RM (lbs)", showgrid=True, gridcolor="rgba(255,255,255,0.06)"),
        yaxis2=dict(title="Session Volume (lbs)", overlaying="y", side="right", showgrid=False),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    st.plotly_chart(fig_str, use_container_width=True)

with tab2:
    fig_acwr = go.Figure()
    fig_acwr.add_hrect(y0=0.8, y1=1.35, fillcolor="#10B981", opacity=0.12, line_width=0, annotation_text="Optimal Sweet Spot (0.80 - 1.35)")
    fig_acwr.add_hrect(y0=1.45, y1=max(2.1, analytics['ACWR'].max() + 0.15), fillcolor="#EF4444", opacity=0.14, line_width=0, annotation_text="Overreaching Risk (> 1.45)")

    fig_acwr.add_trace(go.Scatter(
        x=analytics['Date'],
        y=analytics['ACWR'],
        mode='lines',
        name='ACWR Ratio',
        line=dict(color='#38BDF8', width=3, shape='spline'),
        fill='tozeroy',
        fillcolor='rgba(56, 189, 248, 0.08)',
        hovertemplate='<b>%{x|%b %d, %Y}</b><br>ACWR: %{y:.2f}<extra></extra>'
    ))

    fig_acwr.update_layout(
        title="Acute-to-Chronic Workload Ratio (7-Day Stress vs. 28-Day Fitness)",
        template="plotly_dark",
        hovermode="x unified",
        height=440,
        margin=dict(l=20, r=20, t=50, b=20),
        yaxis=dict(title="ACWR Ratio", range=[0.4, max(2.1, analytics['ACWR'].max() + 0.2)]),
        xaxis=dict(title="")
    )
    st.plotly_chart(fig_acwr, use_container_width=True)

with tab3:
    st.markdown("##### Training Sessions Only (Rest Days Filtered Out for Readability)")
    session_table = analytics[analytics['Did_Lift']].sort_values('Date', ascending=False).copy()
    session_table['Avg_RPE'] = session_table['Avg_RPE'].round(1)
    
    st.dataframe(
        session_table[['Date', 'Peak_e1RM', 'Top_Weight', 'Total_Sets', 'Total_Volume', 'Avg_RPE', 'ACWR', 'Status']],
        use_container_width=True,
        hide_index=True,
        column_config={
            "Date": st.column_config.DateColumn("Session Date", format="MMM DD, YYYY"),
            "Peak_e1RM": st.column_config.NumberColumn("Est. 1RM", format="%.1f lbs"),
            "Top_Weight": st.column_config.NumberColumn("Top Weight", format="%.1f lbs"),
            "Total_Sets": st.column_config.NumberColumn("Working Sets", format="%d sets"),
            "Total_Volume": st.column_config.ProgressColumn("Session Tonnage", format="%d lbs", min_value=0, max_value=int(session_table['Total_Volume'].max() * 1.1)),
            "Avg_RPE": st.column_config.NumberColumn("Avg RPE", format="RPE %.1f"),
            "ACWR": st.column_config.NumberColumn("Fatigue Ratio", format="%.2f"),
            "Status": st.column_config.TextColumn("Readiness Status")
        }
    )
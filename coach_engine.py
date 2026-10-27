import io
import pandas as pd
import numpy as np
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

def calculate_e1rm(weight, reps, rpe=None):
    """Calculates RPE-adjusted estimated 1-Rep Max."""
    if pd.isna(weight) or pd.isna(reps) or reps <= 0:
        return 0.0
    
    effective_reps = float(reps)
    if pd.notna(rpe) and 5.0 <= float(rpe) <= 10.0:
        effective_reps += (10.0 - float(rpe))
        
    if effective_reps >= 37:
        return float(weight)
    return round(float(weight) * (36.0 / (37.0 - effective_reps)), 1)

def generate_demo_dataset():
    """Generates a realistic 6-week SBD (Squat, Bench, Deadlift) training block."""
    dates = pd.date_range(end=pd.Timestamp.today().normalize(), periods=42, freq='D')
    rows = []
    
    lifts = {
        "Squat": {"base": 335, "inc": 1.6, "freq": [0, 3]},       # Mon / Thu
        "Bench Press": {"base": 235, "inc": 1.1, "freq": [1, 4]}, # Tue / Fri
        "Deadlift": {"base": 415, "inc": 2.0, "freq": [2, 5]}     # Wed / Sat
    }
    
    for i, d in enumerate(dates):
        day_of_week = i % 7
        overload_spike = 20 if 28 <= i <= 36 else 0
        
        for lift_name, cfg in lifts.items():
            if day_of_week in cfg["freq"]:
                top_wt = round((cfg["base"] + (i * cfg["inc"]) + overload_spike) / 2.5) * 2.5
                # Top working set
                rows.append({"Date": d.strftime("%Y-%m-%d"), "Exercise": lift_name, "Weight": top_wt, "Reps": 4, "RPE": 8.5})
                # Back-off sets
                backoff = round((top_wt * 0.88) / 2.5) * 2.5
                for _ in range(3):
                    rows.append({"Date": d.strftime("%Y-%m-%d"), "Exercise": lift_name, "Weight": backoff, "Reps": 6, "RPE": 8.0})
                    
    return pd.DataFrame(rows)

def process_athlete_data(df, selected_lift="All Lifts"):
    """Processes raw set logs into clean daily workload and strength progression metrics."""
    df = df.copy()
    df['Date'] = pd.to_datetime(df['Date']).dt.normalize()
    df['Volume'] = df['Weight'] * df['Reps']
    df['e1RM'] = df.apply(lambda r: calculate_e1rm(r['Weight'], r['Reps'], r.get('RPE', None)), axis=1)
    df['Relative_Intensity'] = ((df['Weight'] / df['e1RM'].replace(0, np.nan)) * 100).round(1)
    
    # Calculate SBD Total across the whole dataset
    sbd_totals = {}
    for lift in ["Squat", "Bench Press", "Deadlift"]:
        sub = df[df['Exercise'].str.contains(lift, case=False, na=False)]
        sbd_totals[lift] = sub['e1RM'].max() if not sub.empty else 0.0
    sbd_totals["Total"] = round(sum(sbd_totals.values()), 1)

    # Filter for specific lift if selected
    filtered_df = df if selected_lift == "All Lifts" else df[df['Exercise'] == selected_lift].copy()
    if filtered_df.empty:
        filtered_df = df

    daily = filtered_df.groupby('Date').agg(
        Total_Volume=('Volume', 'sum'),
        Total_Sets=('Reps', 'count'),
        Peak_e1RM=('e1RM', 'max'),
        Avg_RPE=('RPE', 'mean'),
        Top_Weight=('Weight', 'max')
    ).reset_index()

    full_range = pd.date_range(start=daily['Date'].min(), end=daily['Date'].max(), freq='D')
    daily = (
        daily.set_index('Date')
        .reindex(full_range)
        .fillna({'Total_Volume': 0, 'Total_Sets': 0, 'Peak_e1RM': 0, 'Avg_RPE': 0, 'Top_Weight': 0})
        .rename_axis('Date')
        .reset_index()
    )

    daily['Did_Lift'] = daily['Total_Sets'] > 0
    daily['Rolling_e1RM'] = daily['Peak_e1RM'].replace(0, np.nan).ffill().fillna(0).round(1)

    # Rolling 7-day Acute vs 28-day Chronic loads
    daily['Acute_Load'] = daily['Total_Volume'].rolling(window=7, min_periods=1).mean().round(0)
    daily['Chronic_Load'] = daily['Total_Volume'].rolling(window=28, min_periods=7).mean().round(0)
    daily['ACWR'] = (daily['Acute_Load'] / daily['Chronic_Load'].replace(0, np.nan)).fillna(1.0).round(2)

    def flag_risk(ratio):
        if ratio > 1.45:
            return "High Fatigue (Overreaching)"
        elif ratio < 0.80:
            return "Deload / High Readiness"
        return "Optimal Sweet Spot"

    daily['Status'] = daily['ACWR'].apply(flag_risk)
    return daily, sbd_totals, filtered_df

def generate_pdf_report(athlete_name, exercise_focus, latest_metrics, sbd_totals, status_text):
    """Generates a polished 1-page client PDF summary."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    story = []
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], fontSize=18, textColor=colors.HexColor('#0F172A'), spaceAfter=4)
    sub_style = ParagraphStyle('SubStyle', parent=styles['Normal'], fontSize=10, textColor=colors.HexColor('#64748B'), spaceAfter=14)
    body_style = ParagraphStyle('BodyStyle', parent=styles['Normal'], fontSize=10, textColor=colors.HexColor('#334155'), leading=15)
    
    story.append(Paragraph("APEX STRENGTH LAB — ATHLETE BLOCK BRIEFING", title_style))
    story.append(Paragraph(f"Athlete: <b>{athlete_name}</b> &nbsp;|&nbsp; Focus: <b>{exercise_focus}</b> &nbsp;|&nbsp; Generated: <b>{pd.Timestamp.today().strftime('%b %d, %Y')}</b>", sub_style))
    
    status_color = colors.HexColor('#10B981') if "Optimal" in status_text else (colors.HexColor('#EF4444') if "High" in status_text else colors.HexColor('#3B82F6'))
    banner_data = [[Paragraph(f"<b>CURRENT BLOCK STATUS: {status_text.upper()} (ACWR: {latest_metrics['ACWR']:.2f})</b>", ParagraphStyle('Banner', textColor=colors.white, fontSize=10, alignment=1))]]
    banner_table = Table(banner_data, colWidths=[530])
    banner_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), status_color),
        ('BOTTOMPADDING', (0,0), (-1,-1), 8),
        ('TOPPADDING', (0,0), (-1,-1), 8),
    ]))
    story.append(banner_table)
    story.append(Spacer(1, 14))
    
    table_data = [
        ["Performance Metric", "Current Reading", "Coaching Interpretation"],
        ["Projected SBD Total", f"{sbd_totals['Total']:,.1f} lbs", f"S: {sbd_totals['Squat']:.0f} | B: {sbd_totals['Bench Press']:.0f} | D: {sbd_totals['Deadlift']:.0f}"],
        [f"{exercise_focus} Peak e1RM", f"{latest_metrics['Rolling_e1RM']:,.1f} lbs", "RPE-adjusted 1-Rep Max trajectory"],
        ["7-Day Acute Workload", f"{latest_metrics['Acute_Load']:,.0f} lbs/day", "Rolling 7-day daily tonnage stress"],
        ["28-Day Chronic Baseline", f"{latest_metrics['Chronic_Load']:,.0f} lbs/day", "28-day work capacity foundation"],
        ["Fatigue Ratio (ACWR)", f"{latest_metrics['ACWR']:.2f}", "0.80 - 1.35 optimal progressive overload zone"]
    ]
    
    t = Table(table_data, colWidths=[150, 120, 260])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1E293B')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 7),
        ('TOPPADDING', (0,0), (-1,-1), 7),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#F8FAFC')]),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#CBD5E1')),
    ]))
    story.append(t)
    story.append(Spacer(1, 18))
    
    story.append(Paragraph("<b>Automated Periodization Recommendation:</b>", styles['Heading3']))
    if "High" in status_text:
        notes = "Acute workload has spiked above chronic baseline. Recommend reducing back-off volume by 25-30% and capping RPE at 7.5 over the next 5-7 days."
    elif "Deload" in status_text:
        notes = "Fatigue is below baseline. Athlete is fresh and cleared for intensity progression or 1RM testing."
    else:
        notes = "Athlete is adapting cleanly within the target fatigue zone. Maintain current progressive overload rate."
    story.append(Paragraph(notes, body_style))
    
    doc.build(story)
    buffer.seek(0)
    return buffer
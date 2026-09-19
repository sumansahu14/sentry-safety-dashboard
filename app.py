"""
SENTRY — Factory Safety Monitoring Dashboard
Streamlit prototype implementing:
  1. Multi-camera monitoring
  2. Customizable PPE compliance (per zone/camera)
  3. Continuous real-time monitoring (simulated live feed)
  4. Voice and audio alerts (visual indicator — TTS/siren hook point marked)
  5. Environmental pattern analysis (24h scan)
  6. Feedback loop — signage suppression
  7. Entry-point check
  8. Dashboard — summary cards, trend charts, exportable reports

Run with:  streamlit run app.py
"""

import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import random
import io

# ---------------------------------------------------------------------------
# PAGE CONFIG + STYLE
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="SENTRY — Factory Safety Monitoring",
    page_icon="🛡️",
    layout="wide",
)

st.markdown("""
<style>
    .stApp { background-color: #101314; color: #e7eaea; }
    section[data-testid="stSidebar"] { background-color: #181c1e; }
    div[data-testid="stMetric"] {
        background-color: #181c1e;
        border: 1px solid #2a3033;
        padding: 14px 16px;
        border-radius: 2px;
    }
    div[data-testid="stMetricLabel"] { color: #8b9497; }
    .cam-card {
        background-color: #181c1e;
        border: 1px solid #2a3033;
        padding: 10px 14px;
        border-radius: 2px;
        margin-bottom: 8px;
    }
    .cam-card.hazard { border-left: 4px solid #e5484d; }
    .cam-card.ppe { border-left: 4px solid #f2a93b; }
    .cam-card.ok { border-left: 4px solid #3ecf8e; }
    .cam-title { font-weight: 600; font-size: 15px; }
    .cam-sub { color: #8b9497; font-size: 12px; }
    .tag { display:inline-block; padding:2px 7px; font-size:11px; border-radius:2px; margin-top:5px;}
    .tag-hazard { background:#4a1e20; color:#e5484d; }
    .tag-ppe { background:#5c4620; color:#f2a93b; }
    .tag-ok { background:#1c3e30; color:#3ecf8e; }
    .status-line { color:#8b9497; font-size:12.5px; }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# MOCK DATA SETUP (replace with real DB / detection pipeline output)
# ---------------------------------------------------------------------------

if "cameras" not in st.session_state:
    st.session_state.cameras = pd.DataFrame([
        {"camera_id": "CAM-01", "name": "Entry Gate", "workstation": "Assembly Floor B", "zone": "Checkpoint",
         "status": "online"},
        {"camera_id": "CAM-02", "name": "Loading Dock", "workstation": "Warehouse", "zone": "Zone 1",
         "status": "online"},
        {"camera_id": "CAM-03", "name": "Cafeteria", "workstation": "Common Area", "zone": "Zone 0",
         "status": "online"},
        {"camera_id": "CAM-04", "name": "Welding Bay 2", "workstation": "Assembly Floor B", "zone": "Zone 3",
         "status": "online"},
        {"camera_id": "CAM-05", "name": "Assembly Line 1", "workstation": "Assembly Floor B", "zone": "Zone 1",
         "status": "online"},
        {"camera_id": "CAM-06", "name": "Assembly Line 2", "workstation": "Assembly Floor B", "zone": "Zone 2",
         "status": "online"},
        {"camera_id": "CAM-07", "name": "Warehouse Aisle 3", "workstation": "Warehouse", "zone": "Zone 2",
         "status": "online"},
        {"camera_id": "CAM-08", "name": "Loading Dock B", "workstation": "Warehouse", "zone": "Zone 3",
         "status": "reconnecting"},
        {"camera_id": "CAM-09", "name": "Maintenance Room", "workstation": "Assembly Floor B", "zone": "Zone 4",
         "status": "online"},
    ])

GEAR_TYPES = ["Helmet", "Vest", "Gloves", "Footwear", "Goggles", "Respirator"]

# Default PPE rules per zone — this dict is what makes the system "customizable"
if "zone_rules" not in st.session_state:
    st.session_state.zone_rules = {
        "Checkpoint": {"Helmet": True, "Vest": True, "Gloves": False, "Footwear": True, "Goggles": False, "Respirator": False},
        "Zone 0":     {g: False for g in GEAR_TYPES},  # Cafeteria — no PPE required
        "Zone 1":     {"Helmet": True, "Vest": True, "Gloves": False, "Footwear": True, "Goggles": False, "Respirator": False},
        "Zone 2":     {"Helmet": True, "Vest": True, "Gloves": False, "Footwear": True, "Goggles": False, "Respirator": False},
        "Zone 3":     {"Helmet": True, "Vest": True, "Gloves": True, "Footwear": True, "Goggles": True, "Respirator": False},
        "Zone 4":     {"Helmet": False, "Vest": False, "Gloves": True, "Footwear": True, "Goggles": False, "Respirator": False},
    }

if "events" not in st.session_state:
    now = datetime.now()
    sample_events = [
        ("CAM-04", "Smoke detected", "hazard", "High", now - timedelta(minutes=2)),
        ("CAM-01", "Helmet missing", "ppe", "Medium", now - timedelta(minutes=5)),
        ("CAM-09", "Gloves missing", "ppe", "Low", now - timedelta(minutes=15)),
        ("CAM-07", "Signage confirmed — slip warning suppressed", "info", "Low", now - timedelta(minutes=40)),
        ("CAM-06", "Vest missing", "ppe", "Medium", now - timedelta(minutes=52)),
        ("CAM-05", "High vibration — Machine 4", "hazard", "High", now - timedelta(minutes=75)),
        ("CAM-02", "Footwear missing", "ppe", "Low", now - timedelta(minutes=95)),
    ]
    st.session_state.events = pd.DataFrame(
        sample_events, columns=["camera_id", "event", "category", "severity", "timestamp"]
    )

if "env_report" not in st.session_state:
    st.session_state.env_report = pd.DataFrame([
        {"zone": "Assembly Floor B — near Machine 4", "hazard": "Vibration ↑", "status": "Open", "suggest_signage": True},
        {"zone": "Warehouse Aisle 2", "hazard": "Possible leak", "status": "Open", "suggest_signage": True},
        {"zone": "Warehouse Aisle 3", "hazard": "Slip risk", "status": "Resolved — signage detected", "suggest_signage": False},
        {"zone": "Welding Bay 2 floor", "hazard": "Slip risk", "status": "Open", "suggest_signage": True},
    ])

# Hourly violation trend (mock)
if "trend" not in st.session_state:
    hours = list(range(6, 15))
    st.session_state.trend = pd.DataFrame({
        "hour": [f"{h:02d}:00" for h in hours],
        "PPE violations": [4, 8, 12, 6, 3, 5, 10, 7, 6],
        "Hazard events": [0, 0, 1, 0, 0, 0, 0, 1, 0],
    })

# ---------------------------------------------------------------------------
# SIDEBAR — NAVIGATION + SYSTEM STATUS
# ---------------------------------------------------------------------------
st.sidebar.markdown("## 🛡️ SENTRY")
st.sidebar.caption("Factory Safety Monitoring")
st.sidebar.markdown("---")

page = st.sidebar.radio(
    "Navigate",
    ["Live Monitoring", "Compliance Settings", "Environmental Report", "Reports & Analytics"],
    label_visibility="collapsed",
)

st.sidebar.markdown("---")
st.sidebar.markdown(
    '<span class="status-line">🟢 Running local — no cloud connection</span>',
    unsafe_allow_html=True,
)
online_count = (st.session_state.cameras["status"] == "online").sum()
total_count = len(st.session_state.cameras)
st.sidebar.markdown(
    f'<span class="status-line">📷 {online_count} of {total_count} cameras online</span>',
    unsafe_allow_html=True,
)
active_hazards = (st.session_state.events["category"] == "hazard").sum()
st.sidebar.markdown(
    f'<span class="status-line">🚨 {active_hazards} active hazard alert(s)</span>',
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# PAGE 1 — LIVE MONITORING  (multi-camera grid + continuous monitoring + entry check)
# ---------------------------------------------------------------------------
if page == "Live Monitoring":
    st.title("Live Monitoring")
    st.caption("Multi-camera grid · continuous real-time detection · entry-point check")

    col_grid, col_feed = st.columns([2.1, 1])

    with col_grid:
        st.subheader("Camera grid")
        cams = st.session_state.cameras
        cols = st.columns(3)

        # Determine current alert state per camera from latest event
        latest_by_cam = (
            st.session_state.events.sort_values("timestamp", ascending=False)
            .drop_duplicates("camera_id")
            .set_index("camera_id")
        )

        for i, row in cams.iterrows():
            cam_id = row["camera_id"]
            col = cols[i % 3]
            state = "ok"
            tag_text = "COMPLIANT"
            if cam_id in latest_by_cam.index:
                ev = latest_by_cam.loc[cam_id]
                # only show as active alert if within last 10 minutes
                if (datetime.now() - ev["timestamp"]) < timedelta(minutes=10):
                    state = ev["category"]
                    tag_text = ev["event"].upper()
            if row["status"] == "reconnecting":
                state = "reconnecting"
                tag_text = "RECONNECTING"

            rules = st.session_state.zone_rules.get(row["zone"], {})
            required_gear = [g for g, req in rules.items() if req]
            gear_str = ", ".join(required_gear) if required_gear else "No PPE required"

            css_class = "ok" if state in ("ok", "reconnecting") else state
            tag_class = {"hazard": "tag-hazard", "ppe": "tag-ppe"}.get(state, "tag-ok")

            with col:
                st.markdown(f"""
                <div class="cam-card {css_class}">
                    <div class="cam-title">{row['name']}</div>
                    <div class="cam-sub">{cam_id} · {row['workstation']} · {row['zone']}</div>
                    <div class="tag {tag_class}">{tag_text}</div>
                    <div class="cam-sub" style="margin-top:6px;">Required: {gear_str}</div>
                </div>
                """, unsafe_allow_html=True)

        st.markdown("---")
        st.subheader("Entry-point check")
        ec1, ec2 = st.columns([1, 2])
        with ec1:
            if st.button("🚪 Simulate worker entry scan"):
                missing = random.choice(["Helmet", "Vest", None, None])
                st.session_state["entry_result"] = missing
        with ec2:
            result = st.session_state.get("entry_result", None)
            if result:
                st.error(f"🔊 Voice alert: \"Please wear your {result} before entering.\"")
            elif "entry_result" in st.session_state:
                st.success("🔊 Voice alert: \"Access approved. Full PPE detected.\"")
            else:
                st.caption("No scan run yet.")

    with col_feed:
        st.subheader("Live event feed")
        for _, ev in st.session_state.events.sort_values("timestamp", ascending=False).iterrows():
            icon = {"hazard": "🔴", "ppe": "🟠", "info": "🟢"}[ev["category"]]
            audio_note = "🔊 siren triggered" if ev["category"] == "hazard" else (
                "🔊 voice warning issued" if ev["category"] == "ppe" else ""
            )
            st.markdown(f"""
            **{icon} {ev['event']}**
            <br><span class="status-line">{ev['camera_id']} · {ev['timestamp'].strftime('%H:%M:%S')} · Severity: {ev['severity']}</span>
            <br><span class="status-line">{audio_note}</span>
            <hr style="margin:8px 0; border-color:#2a3033;">
            """, unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# PAGE 2 — COMPLIANCE SETTINGS  (customizable PPE per zone/camera)
# ---------------------------------------------------------------------------
elif page == "Compliance Settings":
    st.title("Compliance Settings")
    st.caption("Set required PPE per zone — hazard detection (fire/smoke/fall) is always on and cannot be disabled here.")

    zone_list = list(st.session_state.zone_rules.keys())
    selected_zone = st.selectbox("Select zone", zone_list)

    st.markdown(f"#### Required gear for **{selected_zone}**")
    cols = st.columns(len(GEAR_TYPES))
    new_rules = {}
    for i, gear in enumerate(GEAR_TYPES):
        with cols[i]:
            new_rules[gear] = st.checkbox(
                gear, value=st.session_state.zone_rules[selected_zone][gear], key=f"rule_{selected_zone}_{gear}"
            )

    if st.button("💾 Save rule set for this zone"):
        st.session_state.zone_rules[selected_zone] = new_rules
        st.success(f"Updated PPE rules for {selected_zone}.")

    st.markdown("---")
    st.subheader("All zone rules — overview")
    rules_df = pd.DataFrame(st.session_state.zone_rules).T
    st.dataframe(rules_df, use_container_width=True)

    st.info("🔒 Hazard detection (fire, smoke, fall, machine vibration) applies to every camera at all times and is not configurable — by design.")

# ---------------------------------------------------------------------------
# PAGE 3 — ENVIRONMENTAL REPORT  (24h scan + feedback loop / signage suppression)
# ---------------------------------------------------------------------------
elif page == "Environmental Report":
    st.title("Environmental Pattern Analysis")
    st.caption("24-hour footage scan for slippery zones, vibration, and leakage — with signage feedback loop")

    df = st.session_state.env_report

    for i, row in df.iterrows():
        resolved = "Resolved" in row["status"]
        color = "#3ecf8e" if resolved else "#f2a93b"
        icon = "✅" if resolved else "⚠️"
        st.markdown(f"""
        <div class="cam-card" style="border-left:4px solid {color};">
            <div class="cam-title">{icon} {row['zone']}</div>
            <div class="cam-sub">Detected hazard: {row['hazard']}</div>
            <div class="cam-sub">Status: {row['status']}</div>
        </div>
        """, unsafe_allow_html=True)
        if row["suggest_signage"] and not resolved:
            c1, c2 = st.columns([3, 1])
            with c1:
                st.caption(f"Suggested action: place a warning sign at **{row['zone']}**")
            with c2:
                if st.button("Mark signage installed", key=f"sign_{i}"):
                    st.session_state.env_report.at[i, "status"] = "Resolved — signage detected"
                    st.session_state.env_report.at[i, "suggest_signage"] = False
                    st.rerun()

    st.markdown("---")
    st.caption("Once a warning sign is detected on-camera in a zone, that specific hazard stops being re-flagged there — closing the loop between recommendation and corrective action.")

# ---------------------------------------------------------------------------
# PAGE 4 — REPORTS & ANALYTICS  (summary cards, trend charts, exportable reports)!
# ---------------------------------------------------------------------------
elif page == "Reports & Analytics":
    st.title("Reports & Analytics")

    shift = st.selectbox("Filter by shift", ["All day", "Morning (06:00–14:00)", "Night (14:00–22:00)"])

    # Summary cards
    total_violations = (st.session_state.events["category"] == "ppe").sum()
    active_hazard_alerts = (st.session_state.events["category"] == "hazard").sum()
    compliance_pct = 100 - int(total_violations / max(len(st.session_state.cameras), 1) * 15)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Violations today", int(total_violations), "-4 vs yesterday")
    c2.metric("Active hazard alerts", int(active_hazard_alerts))
    c3.metric("Overall compliance", f"{compliance_pct}%", "+3% this week")
    c4.metric("Avg. response time", "4.1s", "local inference")

    st.markdown("---")
    st.subheader("Violations by hour")
    st.bar_chart(st.session_state.trend.set_index("hour"))

    st.subheader("Violations by zone")
    by_zone = (
        st.session_state.events.merge(st.session_state.cameras, on="camera_id")
        .groupby("zone").size().reset_index(name="count")
    )
    st.bar_chart(by_zone.set_index("zone"))

    st.markdown("---")
    st.subheader("Export incident report")
    export_df = st.session_state.events.merge(st.session_state.cameras, on="camera_id")
    csv_buffer = io.StringIO()
    export_df.to_csv(csv_buffer, index=False)
    dl1, dl2 = st.columns([1, 1])
    with dl1:
        st.download_button(
            "⬇️ Download CSV report",
            data=csv_buffer.getvalue(),
            file_name=f"sentry_incident_report_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv",
        )
    with dl2:
        st.button("⬇️ Download PDF report", disabled=True, help="Wire up ReportLab/WeasyPrint here to render this same DataFrame as PDF.")

    st.markdown("---")
    st.subheader("Full event log")
    st.dataframe(export_df.sort_values("timestamp", ascending=False), use_container_width=True)

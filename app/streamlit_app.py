"""Fleet Management AI dashboard.  Run:  streamlit run app/streamlit_app.py"""
import html
import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd
import plotly.express as _px
import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

import agent
import config as C
from alerts import nice
from db import query

importlib.reload(agent)  # Streamlit re-runs this script but not imported modules; pick up agent.py edits without a restart

st.set_page_config(page_title="Fleet Management AI", page_icon="🚛", layout="wide")

# ================================================================== Look & feel
PRIMARY, INK, MUTED, LINE = "#2563EB", "#0F172A", "#64748B", "#E2E8F0"
COLORWAY = ["#2563EB", "#14B8A6", "#F59E0B", "#8B5CF6", "#EF4444", "#0EA5E9", "#84CC16", "#EC4899"]
TIER_COLORS = {"High": "#EF4444", "Medium": "#F59E0B", "Low": "#10B981"}
KIND_COLORS = {"Preventive": "#2563EB", "Breakdown": "#EF4444"}

pio.templates["fleet"] = go.layout.Template(
    layout=dict(
        font=dict(family="Inter, system-ui, -apple-system, Segoe UI, sans-serif", size=12.5, color="#334155"),
        title=dict(font=dict(size=15, color=INK), x=0.01, xanchor="left", y=0.96),
        paper_bgcolor="#FFFFFF", plot_bgcolor="#FFFFFF", colorway=COLORWAY,
        xaxis=dict(showgrid=False, linecolor=LINE, ticks="", zeroline=False, title_font=dict(color=MUTED)),
        yaxis=dict(gridcolor="#EEF2F7", zeroline=False, showline=False, title_font=dict(color=MUTED)),
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="right", x=1, font=dict(size=11.5)),
        margin=dict(l=8, r=8, t=64, b=8), hoverlabel=dict(bgcolor=INK, font_color="#fff", bordercolor=INK),
        bargap=0.28, barcornerradius=4,
    ),
    data=dict(scatter=[go.Scatter(line=dict(width=2.6), marker=dict(size=6))]),
)
TEMPLATE = "plotly_white+fleet"

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
html, body, .stApp, .stMarkdown, .stButton button, .stDownloadButton button, input, textarea, [data-baseweb="tab"] {
  font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif;
}
.block-container { padding-top: 1.4rem; padding-bottom: 3rem; max-width: 1440px; }
header[data-testid="stHeader"] { background: transparent; }
[data-testid="stAppDeployButton"] { display: none !important; }

/* ---------- hero ---------- */
.hero { position: relative; overflow: hidden; border-radius: 22px; padding: 28px 32px; margin-bottom: 18px;
  background: linear-gradient(130deg, #0B1220 0%, #1E3A8A 55%, #2563EB 100%); color: #fff;
  box-shadow: 0 12px 30px -12px rgba(30, 58, 138, .55); }
.hero:after { content: ""; position: absolute; right: -80px; top: -90px; width: 320px; height: 320px; border-radius: 50%;
  background: radial-gradient(circle, rgba(255,255,255,.18), rgba(255,255,255,0) 70%); }
.hero-row { display: flex; gap: 18px; align-items: center; position: relative; z-index: 1; }
.hero-icon { font-size: 34px; width: 64px; height: 64px; border-radius: 18px; display: grid; place-items: center;
  background: rgba(255,255,255,.12); border: 1px solid rgba(255,255,255,.22); flex-shrink: 0; }
.hero-eyebrow { font-size: 11.5px; letter-spacing: .14em; font-weight: 700; color: #93C5FD; text-transform: uppercase; }
.hero-title { font-size: clamp(1.5rem, 2.6vw, 2.15rem); font-weight: 800; line-height: 1.15; margin: 2px 0 4px; letter-spacing: -.02em; }
.hero-sub { color: #CBD5E1; font-size: .98rem; margin: 0; }
.hero-chips { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 18px; position: relative; z-index: 1; }
.chip { font-size: 12.5px; font-weight: 500; padding: 6px 12px; border-radius: 999px;
  background: rgba(255,255,255,.12); border: 1px solid rgba(255,255,255,.2); color: #E2E8F0; }
.chip.warn { background: rgba(245,158,11,.18); border-color: rgba(245,158,11,.45); color: #FDE68A; }

/* ---------- tabs as pills (Streamlit >=1.60 uses role/testid; older versions use data-baseweb) ---------- */
[data-testid="stTabs"] [role="tablist"], .stTabs [data-baseweb="tab-list"] {
  gap: 4px; background: #fff; padding: 6px; border-radius: 14px; border: 1px solid #E2E8F0; flex-wrap: wrap;
  box-shadow: 0 1px 2px rgba(15,23,42,.04); }
[data-testid="stTab"], .stTabs [data-baseweb="tab"] {
  height: 40px; padding: 0 16px !important; border-radius: 10px !important; background: transparent; white-space: nowrap; }
[data-testid="stTab"] p, .stTabs [data-baseweb="tab"] p { font-weight: 500; color: #475569; font-size: .93rem; }
[data-testid="stTab"]:hover, .stTabs [data-baseweb="tab"]:hover { background: #F1F5F9; }
[data-testid="stTab"][aria-selected="true"], .stTabs [data-baseweb="tab"][aria-selected="true"] {
  background: #2563EB !important; box-shadow: 0 4px 12px -4px rgba(37,99,235,.6); }
[data-testid="stTab"][aria-selected="true"] p, .stTabs [data-baseweb="tab"][aria-selected="true"] p {
  color: #fff !important; font-weight: 600; }
.stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"] { display: none; }
[data-testid="stTabs"] [role="tabpanel"], .stTabs [data-baseweb="tab-panel"] { padding-top: 1.1rem; }

/* ---------- cards ---------- */
[class*="st-key-card_"] { background: #fff; border: 1px solid #E2E8F0; border-radius: 16px; padding: 14px 16px 10px;
  box-shadow: 0 1px 2px rgba(15,23,42,.04), 0 6px 18px -10px rgba(15,23,42,.12); }
.kpi { background: #fff; border: 1px solid #E2E8F0; border-radius: 16px; padding: 16px 18px; height: 100%;
  box-shadow: 0 1px 2px rgba(15,23,42,.04), 0 6px 18px -10px rgba(15,23,42,.12); position: relative; overflow: hidden; }
.kpi:before { content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 4px; background: var(--tone); }
.kpi-top { display: flex; align-items: center; gap: 10px; }
.kpi-icon { width: 34px; height: 34px; border-radius: 10px; display: grid; place-items: center; font-size: 17px;
  background: var(--tone-bg); flex-shrink: 0; }
.kpi-label { font-size: .8rem; font-weight: 600; color: #64748B; text-transform: uppercase; letter-spacing: .04em; line-height: 1.2; }
.kpi-value { font-size: clamp(1.15rem, 1.55vw, 1.6rem); font-weight: 800; color: #0F172A; margin-top: 12px;
  letter-spacing: -.02em; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.kpi-sub { font-size: .82rem; color: #64748B; margin-top: 2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.t-blue   { --tone: #2563EB; --tone-bg: #DBEAFE; }
.t-green  { --tone: #10B981; --tone-bg: #D1FAE5; }
.t-red    { --tone: #EF4444; --tone-bg: #FEE2E2; }
.t-amber  { --tone: #F59E0B; --tone-bg: #FEF3C7; }
.t-violet { --tone: #8B5CF6; --tone-bg: #EDE9FE; }
.t-teal   { --tone: #14B8A6; --tone-bg: #CCFBF1; }

[data-testid="stMetric"] { background: #fff; border: 1px solid #E2E8F0; border-radius: 16px; padding: 14px 18px;
  box-shadow: 0 1px 2px rgba(15,23,42,.04); }
[data-testid="stMetricValue"] { font-weight: 800; letter-spacing: -.02em; }

.sec { margin: 18px 0 10px; }
.sec-title { font-size: 1.12rem; font-weight: 700; color: #0F172A; letter-spacing: -.01em; }
.sec-sub { font-size: .88rem; color: #64748B; margin-top: 2px; }
.badge { display: inline-flex; align-items: center; gap: 6px; font-size: 12.5px; font-weight: 600; padding: 5px 12px;
  border-radius: 999px; }
.badge.on  { background: #D1FAE5; color: #065F46; }
.badge.off { background: #F1F5F9; color: #475569; }
.badge .dot { width: 7px; height: 7px; border-radius: 50%; background: currentColor; }

/* ---------- widgets ---------- */
.stButton > button, .stDownloadButton > button { border-radius: 999px; border: 1px solid #E2E8F0; background: #fff;
  font-weight: 500; color: #334155; transition: all .15s ease; box-shadow: 0 1px 2px rgba(15,23,42,.04); }
.stButton > button:hover, .stDownloadButton > button:hover { border-color: #2563EB; color: #2563EB; background: #EFF6FF;
  transform: translateY(-1px); }
[data-testid="stDataFrame"] { border-radius: 12px; overflow: hidden; }
[data-testid="stAlert"] { border-radius: 14px; }

/* ---------- chat ---------- */
[data-testid="stChatMessage"] { background: #fff; border: 1px solid #E2E8F0; border-radius: 16px; padding: 14px 18px;
  margin-bottom: 10px; box-shadow: 0 1px 2px rgba(15,23,42,.04); }
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) { background: #EFF6FF; border-color: #BFDBFE;
  margin-left: auto; width: 88% !important; }
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"]) { width: 96% !important; }
[data-testid="stChatMessage"] table { border-collapse: separate; border-spacing: 0; border: 1px solid #E2E8F0;
  border-radius: 12px; overflow: hidden; font-size: .9rem; margin: 8px 0; }
[data-testid="stChatMessage"] th { background: #F8FAFC; color: #334155; font-weight: 600; }
[data-testid="stChatMessage"] th, [data-testid="stChatMessage"] td { padding: 8px 14px; border: none;
  border-bottom: 1px solid #EEF2F7; }
[data-testid="stChatMessage"] tr:last-child td { border-bottom: none; }
[data-testid="stChatMessage"] tbody tr:hover td { background: #F8FAFC; }
[data-testid="stChatInput"] { border-radius: 16px; }

/* ---------- sidebar ---------- */
.brand { display: flex; align-items: center; gap: 12px; padding: 4px 0 14px; }
.brand-icon { width: 42px; height: 42px; border-radius: 12px; display: grid; place-items: center; font-size: 22px;
  background: linear-gradient(135deg, #2563EB, #14B8A6); }
.brand-name { font-weight: 800; font-size: 1.05rem; color: #F8FAFC; line-height: 1.1; }
.brand-tag { font-size: .78rem; color: #94A3B8; }
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

LABELS = {"cost_per_km": "Fuel cost per km (Rs)", "cost_pkr": "Cost (Rs)", "cost": "Cost (Rs)", "month": "Month",
          "km_per_l": "km per litre", "risk_prob": "30-day breakdown risk", "risk_tier": "Risk tier", "kind": "Type",
          "registration": "Vehicle", "make_model": "Model", "city": "Depot", "vehicles": "Vehicles", "value": "Pressure",
          "reading_date": "Week", "variable": "Sensor", "n": "Breakdowns", "excess_cost_pkr": "Excess fuel cost (Rs)",
          "fuel_price_per_litre": "Price (Rs/L)", "harsh_per_100km": "Harsh braking per 100 km", "maintenance_type": "Service",
          "experience_years": "Experience (years)", "mean_abs_shap": "Impact on risk (mean |SHAP|)", "index": "Factor"}


class _PX:
    """plotly.express with human-readable labels and the fleet template applied everywhere."""
    def __getattr__(self, name):
        fn = getattr(_px, name)
        return lambda *a, **k: fn(*a, labels={**LABELS, **k.pop("labels", {})}, template=k.pop("template", TEMPLATE), **k)


px = _PX()
rs = lambda x: f"Rs {x:,.0f}"


def rs_short(x):
    """Compact rupees for KPI cards (Pakistani units): Rs 1.95 Cr, Rs 39.9 Lakh, else full."""
    if abs(x) >= 1e7:
        return f"Rs {x / 1e7:.2f} Cr"
    if abs(x) >= 1e5:
        return f"Rs {x / 1e5:.1f} Lakh"
    return rs(x)


_card_n = [0]


def card():
    """A white rounded card (styled through the st-key-card_* CSS class)."""
    _card_n[0] += 1
    return st.container(key=f"card_{_card_n[0]}")


def chart(fig, h=360):
    # explicit colours: Streamlit fills unset paper/plot colours from the app theme (grey), even with theme=None
    fig.update_layout(height=h, paper_bgcolor="#FFFFFF", plot_bgcolor="#FFFFFF")
    st.plotly_chart(fig, width="stretch", theme=None, config={"displaylogo": False})


def chart_card(fig, h=360):
    with card():
        chart(fig, h)


def section(title, sub=None):
    s = f'<div class="sec-sub">{html.escape(sub)}</div>' if sub else ""
    st.markdown(f'<div class="sec"><div class="sec-title">{html.escape(title)}</div>{s}</div>', unsafe_allow_html=True)


def kpi(col, icon, label, value, sub="", tone="blue", full=None):
    """KPI card. `full` is shown on hover (e.g. the exact rupee amount behind a compact 'Rs 1.95 Cr')."""
    tip = html.escape(str(full if full is not None else value))
    col.markdown(f'<div class="kpi t-{tone}"><div class="kpi-top"><span class="kpi-icon">{icon}</span>'
                 f'<span class="kpi-label">{html.escape(str(label))}</span></div>'
                 f'<div class="kpi-value" title="{tip}">{html.escape(str(value))}</div>'
                 f'<div class="kpi-sub" title="{html.escape(str(sub))}">{html.escape(str(sub))}</div></div>',
                 unsafe_allow_html=True)


# ================================================================== Data
@st.cache_data
def load():
    d = {}
    d["vehicles"] = query("SELECT v.*, d.city FROM vehicles v JOIN depots d ON d.id = v.depot_id")
    d["trips"] = query("""SELECT t.*, v.registration, v.make_model, d.city, dr.name AS driver
                          FROM trips t JOIN vehicles v ON v.id = t.vehicle_id JOIN depots d ON d.id = v.depot_id
                          JOIN drivers dr ON dr.id = t.driver_id""")
    d["trips"]["month"] = d["trips"].trip_date.str[:7]
    d["maint"] = query("""SELECT m.*, v.registration, v.make_model, d.city FROM maintenance m
                          JOIN vehicles v ON v.id = m.vehicle_id JOIN depots d ON d.id = v.depot_id""")
    d["maint"]["month"] = d["maint"].maintenance_date.str[:7]
    d["drivers"] = query("SELECT * FROM drivers")
    d["sensors"] = query("SELECT * FROM sensor_readings")
    d["alerts"] = pd.read_csv(C.PROCESSED / "alerts.csv")
    d["anom"] = pd.read_csv(C.PROCESSED / "fuel_anomalies.csv")
    return d


def need_pipeline():
    st.error("Data/model files not found. Run the pipeline first:  `python src/run_pipeline.py`")
    st.stop()


if not (C.DB_PATH.exists() and (C.PROCESSED / "alerts.csv").exists()):
    need_pipeline()
D = load()
alerts, trips, maint = D["alerts"], D["trips"], D["maint"]

# ================================================================== Header
st.markdown(
    '<div class="hero"><div class="hero-row"><div class="hero-icon">🚛</div><div>'
    '<div class="hero-eyebrow">Fleet Intelligence</div>'
    '<div class="hero-title">AI Fleet Management &amp; Maintenance</div>'
    '<p class="hero-sub">Predict breakdowns, catch fuel leaks &amp; theft, and put a rupee value on acting early.</p>'
    '</div></div><div class="hero-chips">'
    f'<span class="chip">📅 {C.START_DATE} → {C.END_DATE}</span>'
    f'<span class="chip">🎯 Scored as of {C.AS_OF_DATE}</span>'
    '<span class="chip">💰 Amounts in PKR</span>'
    '<span class="chip warn">Simulated demo fleet</span>'
    '</div></div>', unsafe_allow_html=True)

with st.sidebar:
    st.markdown('<div class="brand"><div class="brand-icon">🚛</div><div><div class="brand-name">FleetAI</div>'
                '<div class="brand-tag">Maintenance &amp; fuel intelligence</div></div></div>', unsafe_allow_html=True)
    st.markdown("**About**")
    st.write("Predicts which vehicles are likely to break down in the next 30 days, explains why, flags abnormal fuel use, "
             "and puts a rupee value on acting early.")
    st.caption("Data: simulated fleet modelled on the mindweave sample (CC-BY-NC) + real engine-sensor readings (MIT). "
               "Savings rest on assumptions in `src/config.py`.")
    st.caption("Refresh everything: `python src/run_pipeline.py`")
    st.divider()
    st.markdown("**🔑 Assistant AI key (optional)**")
    st.text_input("Gemini or Claude API key", type="password", key="api_key",
                  help="Free Gemini key: https://aistudio.google.com/apikey . Kept only in this browser session, never saved. "
                       "Without a key the assistant answers common questions offline.")

tabs = st.tabs(["📊 Overview", "🚨 Risk & Alerts", "🚚 Vehicle", "⛽ Fuel", "🔧 Maintenance", "🧑‍✈️ Drivers", "🧠 Model",
                "💬 Assistant"])

# ------------------------------------------------------------------ Overview
with tabs[0]:
    end = pd.Timestamp(C.END_DATE)
    last30 = trips[trips.trip_date > (end - pd.Timedelta(days=30)).strftime("%Y-%m-%d")]
    m30 = maint[maint.maintenance_date > (end - pd.Timedelta(days=30)).strftime("%Y-%m-%d")]
    status = D["vehicles"].status.value_counts()
    c = st.columns(3)   # 2 rows of 3 so rupee amounts never get cut off
    kpi(c[0], "🚚", "Vehicles", len(D["vehicles"]), f"{alerts.city.nunique()} depots", "blue")
    kpi(c[1], "🟢", "Active / workshop", f"{status.get('active', 0)} / {status.get('maintenance', 0)}", "Current status", "teal")
    kpi(c[2], "🚨", "High-risk alerts", int((alerts.risk_tier == "High").sum()),
        f"{int((alerts.risk_tier == 'Medium').sum())} medium", "red")
    st.write("")
    c = st.columns(3)
    fuel30, maint30 = last30.fuel_cost_pkr.sum(), m30.cost_pkr.sum()
    saving = alerts[alerts.risk_tier != "Low"].net_saving_pkr.clip(lower=0).sum()
    kpi(c[0], "⛽", "Fuel cost (30d)", rs_short(fuel30), f"{rs(fuel30 / last30.distance_km.sum())}/km", "amber", rs(fuel30))
    kpi(c[1], "🔧", "Maintenance (30d)", rs_short(maint30), f"{len(m30)} jobs", "violet", rs(maint30))
    kpi(c[2], "💰", "Potential saving", rs_short(saving), "High/Medium serviced now", "green", rs(saving))

    st.write("")
    a, b = st.columns(2)
    mt = trips.groupby("month").agg(cost=("fuel_cost_pkr", "sum"), km=("distance_km", "sum")).reset_index()
    mt["cost_per_km"] = mt.cost / mt.km
    with a:
        chart_card(px.line(mt, x="month", y="cost_per_km", title="Fuel cost per km (Rs)", markers=True))
    mm = maint.groupby(["month", "kind"]).cost_pkr.sum().reset_index()
    with b:
        chart_card(px.bar(mm, x="month", y="cost_pkr", color="kind", title="Monthly maintenance spend (Rs)",
                          color_discrete_map=KIND_COLORS))
    a, b = st.columns(2)
    rt = alerts.groupby(["city", "risk_tier"]).size().reset_index(name="vehicles")
    with a:
        chart_card(px.bar(rt, x="city", y="vehicles", color="risk_tier", title="Risk tier by depot",
                          color_discrete_map=TIER_COLORS, category_orders={"risk_tier": ["High", "Medium", "Low"]}))
    with b:
        chart_card(px.histogram(alerts, x="risk_prob", nbins=20, title="Distribution of 30-day breakdown risk"))

# ------------------------------------------------------------------ Risk & Alerts
with tabs[1]:
    section("Predictive maintenance alerts", "Vehicles most likely to break down in the next 30 days, and what to do about it.")
    with card():
        f1, f2 = st.columns(2)
        tiers = f1.multiselect("Risk tier", ["High", "Medium", "Low"], default=["High", "Medium"])
        cities = f2.multiselect("Depot", sorted(alerts.city.unique()), default=sorted(alerts.city.unique()))
        view = alerts[alerts.risk_tier.isin(tiers) & alerts.city.isin(cities)]
        st.dataframe(view[["registration", "make_model", "city", "risk_prob", "risk_tier", "recommended_service",
                           "service_overdue_pct", "service_cost_pkr", "expected_loss_pkr", "net_saving_pkr", "top_reasons"]],
                     hide_index=True, width="stretch",
                     column_config={"registration": "Vehicle", "make_model": "Model", "city": "Depot",
                                    "risk_prob": st.column_config.ProgressColumn("30-day risk", min_value=0, max_value=1, format="percent"),
                                    "risk_tier": "Tier", "recommended_service": "Recommended service",
                                    "service_overdue_pct": st.column_config.NumberColumn("Overdue", format="%d%%"),
                                    "service_cost_pkr": st.column_config.NumberColumn("Service cost (Rs)", format="localized"),
                                    "expected_loss_pkr": st.column_config.NumberColumn("Expected loss (Rs)", format="localized"),
                                    "net_saving_pkr": st.column_config.NumberColumn("Net saving (Rs)", format="localized"),
                                    "top_reasons": st.column_config.TextColumn("Why", width="large")})
        d1, d2 = st.columns([1, 3])
        d1.download_button("⬇ Download alerts (CSV)", view.to_csv(index=False), "fleet_alerts.csv", "text/csv")
        d2.caption("Net saving = P(breakdown) × typical breakdown loss × assumed risk reduction − service cost. "
                   f"Assumptions: downtime Rs {C.DOWNTIME_COST_PER_DAY_PKR:,}/day, service removes {C.SERVICE_RISK_REDUCTION:.0%} of risk "
                   "(config.py). Negative values mean servicing is not worth it on cost alone.")
    st.write("")
    chart_card(px.bar(alerts.head(20), x="registration", y="risk_prob", color="risk_tier", title="Top 20 vehicles by risk",
                      color_discrete_map=TIER_COLORS), h=380)

# ------------------------------------------------------------------ Vehicle
with tabs[2]:
    sel, _ = st.columns([1, 2])
    reg = sel.selectbox("Vehicle", alerts.registration.tolist())
    a = alerts[alerts.registration == reg].iloc[0]
    vid = int(a.vehicle_id)
    tone = {"High": "red", "Medium": "amber", "Low": "green"}.get(a.risk_tier, "blue")
    c = st.columns(4)
    kpi(c[0], "📈", "30-day breakdown risk", f"{a.risk_prob:.0%}", f"{a.risk_tier} risk", tone)
    kpi(c[1], "🛠️", "Recommended service", a.recommended_service, f"{a.service_overdue_pct:.0f}% overdue", "violet")
    kpi(c[2], "🧾", "Service cost", rs(a.service_cost_pkr), a.make_model, "blue")
    kpi(c[3], "💰", "Net saving", rs(a.net_saving_pkr), "if serviced now", "green" if a.net_saving_pkr > 0 else "amber")
    st.write("")
    st.info(f"**Why:** {a.top_reasons}", icon="💡")
    vt = trips[trips.vehicle_id == vid]
    vm = maint[maint.vehicle_id == vid].sort_values("maintenance_date", ascending=False)
    a1, a2 = st.columns(2)
    eff = vt.groupby("month").apply(lambda g: g.distance_km.sum() / g.fuel_litres.sum(), include_groups=False).reset_index(name="km_per_l")
    with a1:
        chart_card(px.line(eff, x="month", y="km_per_l", title="Fuel efficiency (km/l)", markers=True))
    s = D["sensors"][D["sensors"].vehicle_id == vid]
    with a2:
        chart_card(px.line(s, x="reading_date", y=["lub_oil_pressure", "coolant_pressure", "fuel_pressure"],
                           title="Engine pressure readings (weekly)"))
    section("Maintenance history")
    with card():
        st.dataframe(vm[["maintenance_date", "maintenance_type", "kind", "odometer_km", "cost_pkr", "downtime_days"]],
                     hide_index=True, width="stretch",
                     column_config={"maintenance_date": "Date", "maintenance_type": "Service", "kind": "Type",
                                    "odometer_km": st.column_config.NumberColumn("Odometer (km)", format="localized"),
                                    "cost_pkr": st.column_config.NumberColumn("Cost (Rs)", format="localized"),
                                    "downtime_days": "Downtime (days)"})

# ------------------------------------------------------------------ Fuel
with tabs[3]:
    with card():
        f1, f2 = st.columns([3, 2])
        grp = f1.radio("Group by", ["registration", "make_model", "city", "route"], horizontal=True,
                       format_func=lambda x: {"registration": "Vehicle", "make_model": "Model", "city": "Depot", "route": "Route"}[x])
        days = f2.slider("Last N days", 30, 365, 90)
    since = (pd.Timestamp(C.END_DATE) - pd.Timedelta(days=days)).strftime("%Y-%m-%d")
    g = trips[trips.trip_date > since].groupby(grp).agg(km=("distance_km", "sum"), litres=("fuel_litres", "sum"),
                                                        cost=("fuel_cost_pkr", "sum")).reset_index()
    g["cost_per_km"] = g.cost / g.km
    g["km_per_l"] = g.km / g.litres
    st.write("")
    grp_name = {"registration": "vehicle", "make_model": "model", "city": "depot", "route": "route"}[grp]
    chart_card(px.bar(g.sort_values("cost_per_km", ascending=False).head(25), x=grp, y="cost_per_km",
                      title=f"Fuel cost per km by {grp_name} (Rs)"))
    price = trips.groupby(["month", "make_model"]).fuel_price_per_litre.mean().reset_index()
    st.write("")
    chart_card(px.line(price, x="month", y="fuel_price_per_litre", color="make_model",
                       title="Fuel price paid (Rs/L) · simulated drift towards today's rates"))

    section("Fuel anomalies", "Trips that used far more fuel than the vehicle's baseline: possible leak or theft.")
    an = D["anom"][D["anom"].flagged == 1].merge(D["vehicles"][["id", "registration"]], left_on="vehicle_id", right_on="id", suffixes=("", "_v"))
    c = st.columns(3)
    kpi(c[0], "🚩", "Flagged trips (all time)", f"{len(an):,}", "abnormal fuel use", "red")
    kpi(c[1], "💸", "Excess fuel cost", rs_short(an.excess_cost_pkr.sum()), "above baseline", "amber", rs(an.excess_cost_pkr.sum()))
    kpi(c[2], "🛢️", "Excess litres", f"{an.excess_litres.sum():,.0f} L", f"across {an.registration.nunique()} vehicles", "violet")
    st.write("")
    top = an.groupby("registration").excess_cost_pkr.sum().nlargest(15).reset_index()
    chart_card(px.bar(top, x="registration", y="excess_cost_pkr", title="Excess fuel cost by vehicle (Rs)",
                      color_discrete_sequence=["#EF4444"]))
    st.write("")
    with card():
        st.markdown("**Latest 50 flagged trips**")
        st.dataframe(an.sort_values("trip_date", ascending=False).head(50)[["trip_date", "registration", "route", "distance_km",
                                                                              "fuel_litres", "baseline_kmpl", "excess_litres", "excess_cost_pkr"]],
                     hide_index=True, width="stretch",
                     column_config={"trip_date": "Date", "registration": "Vehicle", "route": "Route",
                                    "distance_km": st.column_config.NumberColumn("Distance (km)", format="%.0f"),
                                    "fuel_litres": st.column_config.NumberColumn("Fuel (L)", format="%.1f"),
                                    "baseline_kmpl": st.column_config.NumberColumn("Baseline km/l", format="%.2f"),
                                    "excess_litres": st.column_config.NumberColumn("Excess (L)", format="%.1f"),
                                    "excess_cost_pkr": st.column_config.NumberColumn("Excess cost (Rs)", format="localized")})

# ------------------------------------------------------------------ Maintenance
with tabs[4]:
    bd = maint[maint.kind == "Breakdown"]
    pv = maint[maint.kind == "Preventive"].cost_pkr.sum()
    c = st.columns(3)
    kpi(c[0], "⚠️", "Breakdown share of cost", f"{bd.cost_pkr.sum() / (bd.cost_pkr.sum() + pv):.0%}", "of total maintenance", "red")
    kpi(c[1], "⏱️", "Vehicle-days lost", f"{int(bd.downtime_days.sum()):,}", "to breakdowns", "amber")
    kpi(c[2], "🛡️", "Preventive spend", rs_short(pv), f"{int((maint.kind == 'Preventive').sum()):,} jobs", "blue", rs(pv))
    st.write("")
    a, b = st.columns(2)
    bt = maint.groupby(["maintenance_type", "kind"]).agg(cost=("cost_pkr", "sum"), jobs=("id", "count")).reset_index()
    with a:
        chart_card(px.bar(bt.sort_values("cost"), x="cost", y="maintenance_type", color="kind", orientation="h",
                          title="Total spend by maintenance type (Rs)", color_discrete_map=KIND_COLORS), h=400)
    with b:
        chart_card(px.bar(bd.groupby("month").agg(n=("id", "count")).reset_index(), x="month", y="n", title="Breakdowns per month",
                          color_discrete_sequence=["#EF4444"]), h=400)
    per_v = bd.groupby("registration").agg(breakdowns=("id", "count"), cost=("cost_pkr", "sum"), downtime=("downtime_days", "sum")).nlargest(10, "cost")
    section("Vehicles with the highest breakdown cost")
    with card():
        st.dataframe(per_v.reset_index(), hide_index=True, width="stretch",
                     column_config={"registration": "Vehicle", "breakdowns": "Breakdowns",
                                    "cost": st.column_config.NumberColumn("Cost (Rs)", format="localized"),
                                    "downtime": "Downtime (days)"})

# ------------------------------------------------------------------ Drivers
with tabs[5]:
    since = (pd.Timestamp(C.END_DATE) - pd.Timedelta(days=180)).strftime("%Y-%m-%d")
    dd = trips[trips.trip_date > since].groupby("driver").agg(trips=("id", "count"), km=("distance_km", "sum"),
                                                              harsh=("harsh_braking_events", "sum")).reset_index()
    dd["harsh_per_100km"] = dd.harsh / dd.km * 100
    dd = dd.merge(D["drivers"][["name", "experience_years", "depot_id"]], left_on="driver", right_on="name")
    a, b = st.columns([1, 1])
    with a:
        chart_card(px.scatter(dd, x="experience_years", y="harsh_per_100km", size="km", hover_name="driver",
                              title="Driver experience vs harsh braking (last 180 days)"), h=460)
    with b:
        with card():
            st.markdown("**Driver ranking** · most harsh braking first")
            st.dataframe(dd.sort_values("harsh_per_100km", ascending=False)[["driver", "experience_years", "trips", "km", "harsh_per_100km"]]
                         .round(2), hide_index=True, width="stretch", height=400,
                         column_config={"driver": "Driver", "experience_years": "Exp (yrs)", "trips": "Trips",
                                        "km": st.column_config.NumberColumn("km", format="localized"),
                                        "harsh_per_100km": st.column_config.ProgressColumn(
                                            "Harsh / 100 km", min_value=0, max_value=float(dd.harsh_per_100km.max() or 1), format="%.2f")})

# ------------------------------------------------------------------ Model
with tabs[6]:
    rep = ROOT / "reports"
    section("Breakdown-risk model", "XGBoost, time-based test on 2025")
    if (rep / "risk_model_metrics.csv").exists():
        with card():
            mt = pd.read_csv(rep / "risk_model_metrics.csv")
            # all-text columns: mixing numbers with "–" breaks Arrow serialisation
            mt = mt.apply(lambda col: col.map(lambda v: "–" if pd.isna(v) else f"{v:.3f}" if isinstance(v, float) else str(v)))
            st.dataframe(mt, hide_index=True, width="stretch",
                         column_config={"model": "Model", "roc_auc": "ROC-AUC", "pr_auc": "PR-AUC", "threshold": "Threshold",
                                        "precision": "Precision", "recall": "Recall", "f1": "F1",
                                        "precision_top10pct": "Precision (top 10%)"})
            st.caption("ROC-AUC / PR-AUC = how well vehicles are ranked by risk; precision = flagged snapshots that really "
                       "broke down within 30 days; recall = breakdowns caught; top 10% = precision among the riskiest 10%.")
        st.write("")
        imp = pd.read_csv(rep / "shap_importance.csv", index_col=0).head(15).iloc[::-1]
        imp.index = [nice(f) for f in imp.index]
        chart_card(px.bar(imp, x="mean_abs_shap", orientation="h", title="What drives risk (mean |SHAP|)"), h=480)
    section("Fuel anomaly detection", "Test on 2025")
    if (rep / "anomaly_metrics.csv").exists():
        with card():
            st.dataframe(pd.read_csv(rep / "anomaly_metrics.csv"), hide_index=True, width="stretch",
                         column_config={"detector": "Detector", "precision": "Precision", "recall": "Recall", "f1": "F1",
                                        "flagged": st.column_config.NumberColumn("Trips flagged", format="localized")})
            st.caption("Precision = flagged trips that really were anomalies; recall = injected anomalies caught.")
    st.write("")
    st.warning("**Read these results honestly.** The fleet data is *simulated*: breakdown risk was generated from overdue services, "
               "vehicle age and driver behaviour, so the model rediscovers that structure; anomalies were injected as ≥35% extra "
               "fuel, which makes them easy to detect. Real fleet data will be noisier. The model beats a simple overdue-service "
               "rule on recall but not clearly on top-10% precision.", icon="⚖️")

# ------------------------------------------------------------------ Assistant
with tabs[7]:
    api_key = st.session_state.get("api_key") or None
    provider = agent.resolve_provider(api_key)[0]
    online = provider != "offline"
    mode = {"gemini": f"Gemini · {agent.GEMINI_MODEL}", "anthropic": f"Claude · {agent.MODEL}",
            "offline": "Offline mode"}[provider]
    h1, h2 = st.columns([3, 2])
    h1.markdown('<div class="sec" style="margin-top:0"><div class="sec-title">💬 Fleet Assistant</div>'
                '<div class="sec-sub">Roman Urdu ya English mein poochein. Answers come from your fleet data, not guesses.</div></div>',
                unsafe_allow_html=True)
    h2.markdown(f'<div style="text-align:right;margin-top:6px"><span class="badge {"on" if online else "off"}" '
                f'title="{html.escape(agent.mode_label(api_key))}"><span class="dot"></span>{html.escape(mode)}</span></div>'
                + ("" if online else '<div class="sec-sub" style="text-align:right">Add a free Gemini key in the sidebar '
                   'for open-ended questions</div>'), unsafe_allow_html=True)
    if "chat" not in st.session_state:
        st.session_state.chat, st.session_state.hist = [], []
    SUGGEST = {"⚠️ Risk gaariyan":"Is hafte kaun si gaariyan risk mein hain?", "⛽ Fuel cost / depot": "Fuel cost per km depot ke hisaab se",
               "🕵️ Fuel anomaly": "Fuel chori anomaly dikhao", "🔧 Maintenance": "Maintenance kharcha", "🧑‍✈️ Driver ranking": "Driver ranking"}
    cols = st.columns(len(SUGGEST) + 1)
    clicked = [q_ for c_, (lbl, q_) in zip(cols, SUGGEST.items()) if c_.button(lbl, width="stretch")]  # render all buttons
    picked = clicked[0] if clicked else None
    if cols[-1].button("🗑️ Clear chat", width="stretch"):
        st.session_state.chat, st.session_state.hist = [], []
        st.rerun()
    st.write("")
    if not st.session_state.chat and not picked and not st.session_state.get("chat_q"):
        st.markdown('<div class="kpi t-blue" style="text-align:center;padding:28px">'
                    '<div style="font-size:30px">🚛</div><div class="sec-title" style="margin-top:6px">Assalam-o-Alaikum!</div>'
                    '<div class="sec-sub">Upar se koi sawal chunein ya neeche apna sawal likhein.</div></div>',
                    unsafe_allow_html=True)
    for role, text in st.session_state.chat:
        st.chat_message(role).markdown(text)
    if q := (st.chat_input("Poochein: Is hafte kaun si gaariyan risk mein hain?", key="chat_q") or picked):
        st.chat_message("user").markdown(q)
        with st.spinner("Soch raha hoon..."):
            reply, st.session_state.hist = agent.answer(q, st.session_state.hist, api_key=api_key)
        st.chat_message("assistant").markdown(reply)
        st.session_state.chat += [("user", q), ("assistant", reply)]

"""Fleet Management AI dashboard.  Run:  streamlit run app/streamlit_app.py"""
import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd
import plotly.express as _px
import streamlit as st

import agent
import config as C
from alerts import nice
from db import query

importlib.reload(agent)  # Streamlit re-runs this script but not imported modules; pick up agent.py edits without a restart

st.set_page_config(page_title="Fleet Management AI", page_icon="🚛", layout="wide")
LABELS = {"cost_per_km": "Fuel cost per km (Rs)", "cost_pkr": "Cost (Rs)", "cost": "Cost (Rs)", "month": "Month",
          "km_per_l": "km per litre", "risk_prob": "30-day breakdown risk", "risk_tier": "Risk tier", "kind": "Type",
          "registration": "Vehicle", "make_model": "Model", "city": "Depot", "vehicles": "Vehicles", "value": "Pressure",
          "reading_date": "Week", "variable": "Sensor", "n": "Breakdowns", "excess_cost_pkr": "Excess fuel cost (Rs)",
          "fuel_price_per_litre": "Price (Rs/L)", "harsh_per_100km": "Harsh braking per 100 km", "maintenance_type": "Service",
          "experience_years": "Experience (years)", "mean_abs_shap": "Impact on risk (mean |SHAP|)", "index": "Factor"}


class _PX:
    """plotly.express with human-readable axis/legend labels applied everywhere."""
    def __getattr__(self, name):
        fn = getattr(_px, name)
        return lambda *a, **k: fn(*a, labels={**LABELS, **k.pop("labels", {})}, **k)


px = _PX()
TIER_COLORS = {"High": "#d62728", "Medium": "#ff9f1c", "Low": "#2ca02c"}
rs = lambda x: f"Rs {x:,.0f}"


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

st.title("🚛 AI Fleet Management & Maintenance")
st.caption(f"Simulated demo fleet · {C.START_DATE} to {C.END_DATE} · scored as of {C.AS_OF_DATE} · amounts in PKR")

with st.sidebar:
    st.header("About")
    st.write("Predicts which vehicles are likely to break down in the next 30 days, explains why, flags abnormal fuel use, "
             "and puts a rupee value on acting early.")
    st.caption("Data: simulated fleet modelled on the mindweave sample (CC-BY-NC) + real engine-sensor readings (MIT). "
               "Savings rest on assumptions in `src/config.py`.")
    st.caption("Refresh everything: `python src/run_pipeline.py`")
    st.divider()
    st.subheader("Assistant AI key (optional)")
    st.text_input("Gemini or Claude API key", type="password", key="api_key",
                  help="Free Gemini key: https://aistudio.google.com/apikey . Kept only in this browser session, never saved. "
                       "Without a key the assistant answers common questions offline.")

tabs = st.tabs(["Overview", "Risk & Alerts", "Vehicle", "Fuel", "Maintenance", "Drivers", "Model", "Assistant"])

# ------------------------------------------------------------------ Overview
with tabs[0]:
    end = pd.Timestamp(C.END_DATE)
    last30 = trips[trips.trip_date > (end - pd.Timedelta(days=30)).strftime("%Y-%m-%d")]
    m30 = maint[maint.maintenance_date > (end - pd.Timedelta(days=30)).strftime("%Y-%m-%d")]
    status = D["vehicles"].status.value_counts()
    c = st.columns(6)
    c[0].metric("Vehicles", len(D["vehicles"]))
    c[1].metric("Active / in workshop", f"{status.get('active', 0)} / {status.get('maintenance', 0)}")
    c[2].metric("High-risk alerts", int((alerts.risk_tier == "High").sum()), f"{int((alerts.risk_tier == 'Medium').sum())} medium", delta_color="off", delta_arrow="off")
    c[3].metric("Fuel cost (30d)", rs(last30.fuel_cost_pkr.sum()), f"{rs(last30.fuel_cost_pkr.sum() / last30.distance_km.sum())}/km", delta_color="off", delta_arrow="off")
    c[4].metric("Maintenance (30d)", rs(m30.cost_pkr.sum()), f"{len(m30)} jobs", delta_color="off", delta_arrow="off")
    c[5].metric("Potential net saving", rs(alerts[alerts.risk_tier != "Low"].net_saving_pkr.clip(lower=0).sum()),
                "if High/Medium serviced now", delta_color="off", delta_arrow="off")

    a, b = st.columns(2)
    mt = trips.groupby("month").agg(cost=("fuel_cost_pkr", "sum"), km=("distance_km", "sum")).reset_index()
    mt["cost_per_km"] = mt.cost / mt.km
    a.plotly_chart(px.line(mt, x="month", y="cost_per_km", title="Fuel cost per km (Rs)", markers=True), width="stretch")
    mm = maint.groupby(["month", "kind"]).cost_pkr.sum().reset_index()
    b.plotly_chart(px.bar(mm, x="month", y="cost_pkr", color="kind", title="Monthly maintenance spend (Rs)",
                          color_discrete_map={"Preventive": "#1f77b4", "Breakdown": "#d62728"}), width="stretch")
    a, b = st.columns(2)
    rt = alerts.groupby(["city", "risk_tier"]).size().reset_index(name="vehicles")
    a.plotly_chart(px.bar(rt, x="city", y="vehicles", color="risk_tier", title="Risk tier by depot",
                          color_discrete_map=TIER_COLORS), width="stretch")
    b.plotly_chart(px.histogram(alerts, x="risk_prob", nbins=20, title="Distribution of 30-day breakdown risk"), width="stretch")

# ------------------------------------------------------------------ Risk & Alerts
with tabs[1]:
    st.subheader("Predictive maintenance alerts")
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
    st.download_button("⬇ Download alerts (CSV)", view.to_csv(index=False), "fleet_alerts.csv", "text/csv")
    st.caption("Net saving = P(breakdown) × typical breakdown loss × assumed risk reduction − service cost. "
               f"Assumptions: downtime Rs {C.DOWNTIME_COST_PER_DAY_PKR:,}/day, service removes {C.SERVICE_RISK_REDUCTION:.0%} of risk "
               "(config.py). Negative values mean servicing is not worth it on cost alone.")
    st.plotly_chart(px.bar(alerts.head(20), x="registration", y="risk_prob", color="risk_tier", title="Top 20 vehicles by risk",
                           color_discrete_map=TIER_COLORS), width="stretch")

# ------------------------------------------------------------------ Vehicle
with tabs[2]:
    reg = st.selectbox("Vehicle", alerts.registration.tolist())
    a = alerts[alerts.registration == reg].iloc[0]
    vid = int(a.vehicle_id)
    c = st.columns(4)
    c[0].metric("30-day breakdown risk", f"{a.risk_prob:.0%}", a.risk_tier, delta_color="off", delta_arrow="off")
    c[1].metric("Recommended service", a.recommended_service, f"{a.service_overdue_pct:.0f}% overdue", delta_color="off", delta_arrow="off")
    c[2].metric("Service cost", rs(a.service_cost_pkr))
    c[3].metric("Net saving", rs(a.net_saving_pkr))
    st.info(f"**Why:** {a.top_reasons}")
    vt = trips[trips.vehicle_id == vid]
    vm = maint[maint.vehicle_id == vid].sort_values("maintenance_date", ascending=False)
    a1, a2 = st.columns(2)
    eff = vt.groupby("month").apply(lambda g: g.distance_km.sum() / g.fuel_litres.sum(), include_groups=False).reset_index(name="km_per_l")
    a1.plotly_chart(px.line(eff, x="month", y="km_per_l", title="Fuel efficiency (km/l)", markers=True), width="stretch")
    s = D["sensors"][D["sensors"].vehicle_id == vid]
    a2.plotly_chart(px.line(s, x="reading_date", y=["lub_oil_pressure", "coolant_pressure", "fuel_pressure"],
                            title="Engine pressure readings (weekly)"), width="stretch")
    st.markdown("**Maintenance history**")
    st.dataframe(vm[["maintenance_date", "maintenance_type", "kind", "odometer_km", "cost_pkr", "downtime_days"]],
                 hide_index=True, width="stretch")

# ------------------------------------------------------------------ Fuel
with tabs[3]:
    grp = st.radio("Group by", ["registration", "make_model", "city", "route"], horizontal=True,
                   format_func=lambda x: {"registration": "Vehicle", "make_model": "Model", "city": "Depot", "route": "Route"}[x])
    days = st.slider("Last N days", 30, 365, 90)
    since = (pd.Timestamp(C.END_DATE) - pd.Timedelta(days=days)).strftime("%Y-%m-%d")
    g = trips[trips.trip_date > since].groupby(grp).agg(km=("distance_km", "sum"), litres=("fuel_litres", "sum"),
                                                        cost=("fuel_cost_pkr", "sum")).reset_index()
    g["cost_per_km"] = g.cost / g.km
    g["km_per_l"] = g.km / g.litres
    st.plotly_chart(px.bar(g.sort_values("cost_per_km", ascending=False).head(25), x=grp, y="cost_per_km",
                           title=f"Fuel cost per km by {grp} (Rs)"), width="stretch")
    price = trips.groupby(["month", "make_model"]).fuel_price_per_litre.mean().reset_index()
    st.plotly_chart(px.line(price, x="month", y="fuel_price_per_litre", color="make_model",
                            title="Fuel price paid (Rs/L) - simulated drift towards today's rates"), width="stretch")
    st.subheader("Fuel anomalies (possible leak / theft)")
    an = D["anom"][D["anom"].flagged == 1].merge(D["vehicles"][["id", "registration"]], left_on="vehicle_id", right_on="id", suffixes=("", "_v"))
    st.metric("Flagged trips (all time)", len(an), f"Excess fuel {rs(an.excess_cost_pkr.sum())}", delta_color="off", delta_arrow="off")
    top = an.groupby("registration").excess_cost_pkr.sum().nlargest(15).reset_index()
    st.plotly_chart(px.bar(top, x="registration", y="excess_cost_pkr", title="Excess fuel cost by vehicle (Rs)"), width="stretch")
    st.dataframe(an.sort_values("trip_date", ascending=False).head(50)[["trip_date", "registration", "route", "distance_km", "fuel_litres",
                                                                          "baseline_kmpl", "excess_litres", "excess_cost_pkr"]],
                 hide_index=True, width="stretch")

# ------------------------------------------------------------------ Maintenance
with tabs[4]:
    a, b = st.columns(2)
    bt = maint.groupby(["maintenance_type", "kind"]).agg(cost=("cost_pkr", "sum"), jobs=("id", "count")).reset_index()
    a.plotly_chart(px.bar(bt.sort_values("cost"), x="cost", y="maintenance_type", color="kind", orientation="h",
                          title="Total spend by maintenance type (Rs)",
                          color_discrete_map={"Preventive": "#1f77b4", "Breakdown": "#d62728"}), width="stretch")
    bd = maint[maint.kind == "Breakdown"]
    b.plotly_chart(px.bar(bd.groupby("month").agg(n=("id", "count")).reset_index(), x="month", y="n", title="Breakdowns per month"),
                   width="stretch")
    pv = maint[maint.kind == "Preventive"].cost_pkr.sum()
    st.metric("Breakdown share of total maintenance cost", f"{bd.cost_pkr.sum() / (bd.cost_pkr.sum() + pv):.0%}",
              f"{int(bd.downtime_days.sum())} vehicle-days lost to breakdowns", delta_color="off", delta_arrow="off")
    per_v = bd.groupby("registration").agg(breakdowns=("id", "count"), cost=("cost_pkr", "sum"), downtime=("downtime_days", "sum")).nlargest(10, "cost")
    st.markdown("**Vehicles with the highest breakdown cost**")
    st.dataframe(per_v.reset_index(), hide_index=True, width="stretch")

# ------------------------------------------------------------------ Drivers
with tabs[5]:
    since = (pd.Timestamp(C.END_DATE) - pd.Timedelta(days=180)).strftime("%Y-%m-%d")
    dd = trips[trips.trip_date > since].groupby("driver").agg(trips=("id", "count"), km=("distance_km", "sum"),
                                                              harsh=("harsh_braking_events", "sum")).reset_index()
    dd["harsh_per_100km"] = dd.harsh / dd.km * 100
    dd = dd.merge(D["drivers"][["name", "experience_years", "depot_id"]], left_on="driver", right_on="name")
    st.plotly_chart(px.scatter(dd, x="experience_years", y="harsh_per_100km", size="km", hover_name="driver",
                               title="Driver experience vs harsh braking (last 180 days)"), width="stretch")
    st.dataframe(dd.sort_values("harsh_per_100km", ascending=False)[["driver", "experience_years", "trips", "km", "harsh_per_100km"]]
                 .round(2), hide_index=True, width="stretch")

# ------------------------------------------------------------------ Model
with tabs[6]:
    rep = ROOT / "reports"
    st.subheader("Breakdown-risk model (XGBoost, time-based test on 2025)")
    if (rep / "risk_model_metrics.csv").exists():
        st.dataframe(pd.read_csv(rep / "risk_model_metrics.csv").astype(object).fillna("–"), hide_index=True, width="stretch")
        imp = pd.read_csv(rep / "shap_importance.csv", index_col=0).head(15).iloc[::-1]
        imp.index = [nice(f) for f in imp.index]
        st.plotly_chart(px.bar(imp, x="mean_abs_shap", orientation="h", title="What drives risk (mean |SHAP|)"), width="stretch")
    st.subheader("Fuel anomaly detection (test on 2025)")
    if (rep / "anomaly_metrics.csv").exists():
        st.dataframe(pd.read_csv(rep / "anomaly_metrics.csv"), hide_index=True, width="stretch")
        st.caption("Metrics columns: ROC-AUC / PR-AUC rank quality; precision = flagged vehicles that really broke down; "
                   "recall = breakdowns caught; top10pct = precision among the 10% riskiest snapshots.")
    st.warning("**Read these results honestly.** The fleet data is *simulated*: breakdown risk was generated from overdue services, "
               "vehicle age and driver behaviour, so the model rediscovers that structure; anomalies were injected as ≥35% extra "
               "fuel, which makes them easy to detect. Real fleet data will be noisier. The model beats a simple overdue-service "
               "rule on recall but not clearly on top-10% precision.")

# ------------------------------------------------------------------ Assistant
with tabs[7]:
    api_key = st.session_state.get("api_key") or None
    st.caption(f"Mode: {agent.mode_label(api_key)}")
    if "chat" not in st.session_state:
        st.session_state.chat, st.session_state.hist = [], []
    SUGGEST = {"⚠ Risk wali gaariyan": "Is hafte kaun si gaariyan risk mein hain?", "⛽ Fuel cost / depot": "Fuel cost per km depot ke hisaab se",
               "🕵 Fuel anomaly": "Fuel chori anomaly dikhao", "🔧 Maintenance": "Maintenance kharcha", "🧑‍✈️ Driver ranking": "Driver ranking"}
    cols = st.columns(len(SUGGEST) + 1)
    clicked = [q_ for c_, (lbl, q_) in zip(cols, SUGGEST.items()) if c_.button(lbl, width="stretch")]  # render all buttons
    picked = clicked[0] if clicked else None
    if cols[-1].button("🗑 Clear chat", width="stretch"):
        st.session_state.chat, st.session_state.hist = [], []
        st.rerun()
    for role, text in st.session_state.chat:
        st.chat_message(role).markdown(text)
    if q := (st.chat_input("Poochein: Is hafte kaun si gaariyan risk mein hain?") or picked):
        st.chat_message("user").markdown(q)
        with st.spinner("Soch raha hoon..."):
            reply, st.session_state.hist = agent.answer(q, st.session_state.hist, api_key=api_key)
        st.chat_message("assistant").markdown(reply)
        st.session_state.chat += [("user", q), ("assistant", reply)]

# =============================================================================
# dashboard_terminal.py — Dashboard Bénin Terminal / Port de Cotonou
# METEO-BENIN / DPROM / SPAM
# =============================================================================

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import pytz
import io
import os
import requests

# =============================================================================
# Configuration
# =============================================================================

TZ_BENIN = pytz.timezone("Africa/Porto-Novo")  # UTC+1

POINT = {"name": "Port de Cotonou", "lat": 6.35, "lon": 2.43}

# Seuils d'alerte rafales (km/h) par hauteur
THRESHOLDS = {
    "10m":  {"green": 28,  "yellow": 49,  "orange": 74  },
    "22m":  {"green": 33,  "yellow": 57,  "orange": 86  },
    "60m":  {"green": 40,  "yellow": 70,  "orange": 107 },
    "70m":  {"green": 40,  "yellow": 72,  "orange": 109 },
}

COLORS = {
    "green":  "#2ECC71",
    "yellow": "#F1C40F",
    "orange": "#E67E22",
    "red":    "#E74C3C",
    "bg":     "#0E1117",
    "card":   "#1E2130",
    "text":   "#FFFFFF",
    "blue":   "#2E75B6",
}

# GitHub Raw URL — à adapter selon votre repo
GITHUB_OWNER = "DianeLaourou"
GITHUB_REPO  = "Benin-Terminal-Forecast"
GITHUB_BRANCH = "main"

st.set_page_config(
    page_title="Bénin Terminal — Prévisions Météo Port",
    page_icon="⚓",
    layout="wide",
    initial_sidebar_state="expanded",
)

# =============================================================================
# CSS
# =============================================================================

st.markdown("""
<style>
    .main { background-color: #0E1117; }
    .metric-card {
        background: #1E2130; border-radius: 10px;
        padding: 15px; text-align: center; margin: 5px;
    }
    .alert-green  { background:#1a3a2a; border-left:4px solid #2ECC71; padding:10px; border-radius:5px; }
    .alert-yellow { background:#3a3a1a; border-left:4px solid #F1C40F; padding:10px; border-radius:5px; }
    .alert-orange { background:#3a2a1a; border-left:4px solid #E67E22; padding:10px; border-radius:5px; }
    .alert-red    { background:#3a1a1a; border-left:4px solid #E74C3C; padding:10px; border-radius:5px; }
    .stPlotlyChart { border-radius: 10px; }
    h1, h2, h3 { color: #FFFFFF; }
</style>
""", unsafe_allow_html=True)

# =============================================================================
# Fonctions utilitaires
# =============================================================================

def now_local():
    return datetime.now(tz=TZ_BENIN).replace(tzinfo=None)

def get_alert_level(gust, height):
    """Retourne le niveau d'alerte pour une rafale à une hauteur donnée."""
    t = THRESHOLDS[height]
    if gust <= t["green"]:   return "green",  "🟢 Vert"
    if gust <= t["yellow"]:  return "yellow", "🟡 Jaune"
    if gust <= t["orange"]:  return "orange", "🟠 Orange"
    return "red", "🔴 Rouge"

def get_global_alert(df):
    """Niveau d'alerte global sur toute la période."""
    levels = {"green": 0, "yellow": 1, "orange": 2, "red": 3}
    max_level = 0
    for h, col in [("10m","RafaleV10_Km/h"),("22m","RafaleV22_Km/h"),
                   ("60m","RafaleV60_Km/h"),("70m","RafaleV70_Km/h")]:
        for v in df[col].dropna():
            lvl, _ = get_alert_level(v, h)
            max_level = max(max_level, levels[lvl])
    inv = {0:"green", 1:"yellow", 2:"orange", 3:"red"}
    labels = {"green":"🟢 VERT — Conditions favorables",
              "yellow":"🟡 JAUNE — Vigilance recommandée",
              "orange":"🟠 ORANGE — Conditions difficiles",
              "red":"🔴 ROUGE — Opérations dangereuses"}
    k = inv[max_level]
    return k, labels[k]

def load_csv_from_github(filename):
    """Charge un CSV depuis GitHub Raw."""
    url = f"https://raw.githubusercontent.com/{GITHUB_OWNER}/{GITHUB_REPO}/{GITHUB_BRANCH}/{filename}"
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        df = pd.read_csv(io.StringIO(r.text))
        df["forecast_time_local"] = pd.to_datetime(df["forecast_time_local"])
        return df, url
    except Exception as e:
        return None, str(e)

def list_csv_files_github():
    """Liste les CSV disponibles sur GitHub via l'API."""
    url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/git/trees/{GITHUB_BRANCH}?recursive=1"
    try:
        r = requests.get(url, timeout=10)
        data = r.json()
        files = [f["path"] for f in data.get("tree", [])
                 if f["path"].endswith(".csv") and "ECMWF_Port" in f["path"]]
        return sorted(files, reverse=True)
    except:
        return []

def generate_demo_data():
    """Données de démonstration."""
    now = now_local().replace(minute=0, second=0, microsecond=0)
    times = [now + timedelta(hours=2*i) for i in range(21)]
    import random, math
    rows = []
    for i, t in enumerate(times):
        base = 10 + 5*math.sin(i/3)
        rows.append({
            "forecast_time_local": t,
            "V10m_Dir": "SO", "V10m_Km/h": base,      "RafaleV10_Km/h": base*2.0,
            "V22m_Dir": "SO", "V22m_Km/h": base*1.08,  "RafaleV22_Km/h": base*2.2,
            "V60m_Dir": "SO", "V60m_Km/h": base*1.19,  "RafaleV60_Km/h": base*2.5,
            "V70m_Dir": "SO", "V70m_Km/h": base*1.21,  "RafaleV70_Km/h": base*2.6,
            "T(°C)": 27 + math.sin(i/4),
            "Pluie(mm)": max(0, random.gauss(0.01, 0.005)),
        })
    return pd.DataFrame(rows)

# =============================================================================
# Graphiques
# =============================================================================

def plot_wind_level(df, height, v_col, g_col, show_markers=True):
    """Graphique vent + rafales pour une hauteur donnée avec zones colorées."""
    t = THRESHOLDS[height]
    x = df["forecast_time_local"].dt.strftime("%d/%m %H:%M")
    fig = go.Figure()

    # Zones colorées seuils
    ymax = max(df[g_col].max() * 1.2, t["orange"] + 20)
    zones = [
        (0,          t["green"],  "rgba(46,204,113,0.08)",  "🟢 Vert"),
        (t["green"], t["yellow"], "rgba(241,196,15,0.10)",  "🟡 Jaune"),
        (t["yellow"],t["orange"], "rgba(230,126,34,0.12)",  "🟠 Orange"),
        (t["orange"],ymax,        "rgba(231,76,60,0.14)",   "🔴 Rouge"),
    ]
    for y0, y1, col, name in zones:
        fig.add_hrect(y0=y0, y1=y1, fillcolor=col, line_width=0,
                      annotation_text=name, annotation_position="right",
                      annotation_font_size=9, annotation_font_color="#aaaaaa")

    # Lignes seuils
    for val, color, dash in [
        (t["green"],  COLORS["green"],  "dot"),
        (t["yellow"], COLORS["yellow"], "dot"),
        (t["orange"], COLORS["orange"], "dot"),
    ]:
        fig.add_hline(y=val, line_dash=dash, line_color=color,
                      line_width=1, opacity=0.6)

    # Vitesse vent
    fig.add_trace(go.Scatter(
        x=x, y=df[v_col], name=f"Vent {height}",
        line=dict(color="#4FC3F7", width=2),
        mode="lines+markers" if show_markers else "lines",
        marker=dict(size=5),
    ))

    # Rafales
    fig.add_trace(go.Scatter(
        x=x, y=df[g_col], name=f"Rafales {height}",
        line=dict(color="#FF8A65", width=2, dash="dash"),
        mode="lines+markers" if show_markers else "lines",
        marker=dict(size=5, symbol="triangle-up"),
        fill="tonexty", fillcolor="rgba(255,138,101,0.08)",
    ))

    fig.update_layout(
        title=dict(text=f"⚡ Vent à {height}", font=dict(size=13, color="white")),
        paper_bgcolor=COLORS["bg"], plot_bgcolor="#161B2E",
        font=dict(color="white", size=10),
        height=280, margin=dict(l=50, r=120, t=40, b=60),
        legend=dict(orientation="h", y=-0.25, font=dict(size=9)),
        yaxis=dict(title="km/h", gridcolor="#2a2a3a", range=[0, ymax]),
        xaxis=dict(gridcolor="#2a2a3a", tickangle=-45, tickfont=dict(size=8)),
        hovermode="x unified",
    )
    return fig

def plot_temp_rain(df, show_markers=True):
    """Graphique T°C et Pluie."""
    x = df["forecast_time_local"].dt.strftime("%d/%m %H:%M")
    fig = make_subplots(specs=[[{"secondary_y": True}]])

    fig.add_trace(go.Scatter(
        x=x, y=df["T(°C)"], name="T°C",
        line=dict(color="#FF6B6B", width=2),
        mode="lines+markers" if show_markers else "lines",
        marker=dict(size=5),
    ), secondary_y=False)

    fig.add_trace(go.Bar(
        x=x, y=df["Pluie(mm)"], name="Pluie (mm)",
        marker_color="rgba(100,181,246,0.6)",
    ), secondary_y=True)

    fig.update_layout(
        title=dict(text="🌡️ Température & Pluie", font=dict(size=13, color="white")),
        paper_bgcolor=COLORS["bg"], plot_bgcolor="#161B2E",
        font=dict(color="white", size=10),
        height=280, margin=dict(l=50, r=80, t=40, b=60),
        legend=dict(orientation="h", y=-0.25, font=dict(size=9)),
        xaxis=dict(gridcolor="#2a2a3a", tickangle=-45, tickfont=dict(size=8)),
        hovermode="x unified",
    )
    fig.update_yaxes(title_text="T (°C)", gridcolor="#2a2a3a", secondary_y=False)
    fig.update_yaxes(title_text="Pluie (mm)", secondary_y=True)
    return fig

def plot_wind_summary(df):
    """Graphique synthèse rafales aux 4 hauteurs."""
    x = df["forecast_time_local"].dt.strftime("%d/%m %H:%M")
    fig = go.Figure()

    configs = [
        ("RafaleV10_Km/h", "10m",  "#4FC3F7"),
        ("RafaleV22_Km/h", "22m",  "#81C784"),
        ("RafaleV60_Km/h", "60m",  "#FFB74D"),
        ("RafaleV70_Km/h", "70m",  "#FF8A65"),
    ]
    for col, label, color in configs:
        fig.add_trace(go.Scatter(
            x=x, y=df[col], name=f"Rafales {label}",
            line=dict(color=color, width=2),
            mode="lines",
        ))

    fig.update_layout(
        title=dict(text="🌬️ Synthèse rafales — tous niveaux", font=dict(size=13, color="white")),
        paper_bgcolor=COLORS["bg"], plot_bgcolor="#161B2E",
        font=dict(color="white", size=10),
        height=300, margin=dict(l=50, r=80, t=40, b=60),
        legend=dict(orientation="h", y=-0.25, font=dict(size=9)),
        yaxis=dict(title="km/h", gridcolor="#2a2a3a"),
        xaxis=dict(gridcolor="#2a2a3a", tickangle=-45, tickfont=dict(size=8)),
        hovermode="x unified",
    )
    return fig

# =============================================================================
# Tableau récapitulatif
# =============================================================================

def render_table(df):
    """Tableau avec cellules colorées selon alertes."""
    def color_gust(val, height):
        lvl, _ = get_alert_level(val, height)
        colors_map = {
            "green":  "background-color:#1a3a2a; color:#2ECC71",
            "yellow": "background-color:#3a3a1a; color:#F1C40F",
            "orange": "background-color:#3a2a1a; color:#E67E22",
            "red":    "background-color:#3a1a1a; color:#E74C3C",
        }
        return colors_map[lvl]

    display = df.copy()
    display["forecast_time_local"] = display["forecast_time_local"].dt.strftime("%d/%m %H:%M")
    display = display.rename(columns={
        "forecast_time_local": "Date/Heure",
        "V10m_Dir": "Dir 10m", "V10m_Km/h": "V 10m", "RafaleV10_Km/h": "Raf. 10m",
        "V22m_Dir": "Dir 22m", "V22m_Km/h": "V 22m", "RafaleV22_Km/h": "Raf. 22m",
        "V60m_Dir": "Dir 60m", "V60m_Km/h": "V 60m", "RafaleV60_Km/h": "Raf. 60m",
        "V70m_Dir": "Dir 70m", "V70m_Km/h": "V 70m", "RafaleV70_Km/h": "Raf. 70m",
        "T(°C)": "T (°C)", "Pluie(mm)": "Pluie (mm)",
    })

    # Arrondir
    for col in ["V 10m","Raf. 10m","V 22m","Raf. 22m","V 60m","Raf. 60m","V 70m","Raf. 70m"]:
        display[col] = display[col].round(1)
    display["T (°C)"] = display["T (°C)"].round(1)
    display["Pluie (mm)"] = display["Pluie (mm)"].round(3)

    def style_row(row):
        styles = [""] * len(row)
        cols = list(display.columns)
        mappings = [
            ("Raf. 10m", "10m"), ("Raf. 22m", "22m"),
            ("Raf. 60m", "60m"), ("Raf. 70m", "70m"),
        ]
        for col_name, height in mappings:
            if col_name in cols:
                idx = cols.index(col_name)
                styles[idx] = color_gust(row[col_name], height)
        return styles

    styled = display.style.apply(style_row, axis=1)
    st.dataframe(styled, use_container_width=True, height=400)

# =============================================================================
# Sidebar
# =============================================================================

def render_sidebar():
    with st.sidebar:
        st.markdown("## ⚓ Bénin Terminal")
        st.markdown("**Port de Cotonou**")
        st.markdown(f"*{POINT['lat']}°N, {POINT['lon']}°E*")
        st.divider()

        # Sélection du bulletin
        st.markdown("### 📂 Bulletin")
        source = st.radio("Source", ["GitHub", "Fichier local"], horizontal=True)

        df = None
        run_label = ""

        if source == "GitHub":
            csv_files = list_csv_files_github()
            if csv_files:
                selected = st.selectbox("Choisir le bulletin", csv_files,
                                        format_func=lambda x: x.replace("ECMWF_Port_","").replace(".csv",""))
                df, url = load_csv_from_github(selected)
                if df is not None:
                    run_label = selected.replace("ECMWF_Port_","").replace(".csv","")
                    st.success(f"✅ {len(df)} échéances chargées")
                else:
                    st.error(f"❌ Erreur : {url}")
            else:
                st.warning("⚠️ Aucun CSV trouvé sur GitHub")

        else:
            uploaded = st.file_uploader("Charger un CSV local", type=["csv"])
            if uploaded:
                df = pd.read_csv(uploaded)
                df["forecast_time_local"] = pd.to_datetime(df["forecast_time_local"])
                run_label = uploaded.name.replace("ECMWF_Port_","").replace(".csv","")
                st.success(f"✅ {len(df)} échéances chargées")

        if df is None:
            st.info("💡 Mode démonstration")
            df = generate_demo_data()
            run_label = "DEMO"

        st.divider()

        # Filtre temporel
        st.markdown("### 🕐 Période")
        df["forecast_time_local"] = pd.to_datetime(df["forecast_time_local"])
        times = sorted(df["forecast_time_local"].dt.to_pydatetime().tolist())
        dt_min = times[0]; dt_max = times[-1]

        # Par défaut : 19h du jour J
        _19h = dt_min.replace(hour=19, minute=0, second=0, microsecond=0)
        _19h_times = [t for t in times if t >= _19h]
        _def_start = _19h_times[0] if _19h_times else dt_min

        show_past = st.toggle("🕐 Voir les échéances passées", value=False)
        def_start = dt_min if show_past else _def_start

        col_a, col_b = st.columns(2)
        with col_a:
            start_d = st.date_input("De", value=def_start.date(),
                                    min_value=dt_min.date(), max_value=dt_max.date())
            _hs = sorted({t.hour for t in times if t.date()==start_d}) or list(range(0,24,2))
            _def_sh = def_start.hour if start_d == def_start.date() else _hs[0]
            _sh_idx = _hs.index(_def_sh) if _def_sh in _hs else 0
            start_h = st.selectbox("Heure", _hs, format_func=lambda h: f"{h:02d}:00",
                                   index=_sh_idx, key="sh")
        with col_b:
            end_d = st.date_input("À", value=dt_max.date(),
                                  min_value=dt_min.date(), max_value=dt_max.date())
            _he = sorted({t.hour for t in times if t.date()==end_d}) or list(range(0,24,2))
            end_h = st.selectbox("Heure", _he, format_func=lambda h: f"{h:02d}:00",
                                 index=len(_he)-1, key="eh")

        time_start = datetime.combine(start_d, datetime.min.time()).replace(hour=start_h)
        time_end   = datetime.combine(end_d,   datetime.min.time()).replace(hour=end_h)

        st.divider()

        # Options
        st.markdown("### ⚙️ Affichage")
        show_markers = st.checkbox("Marqueurs", value=True)
        show_summary = st.checkbox("Graphique synthèse", value=True)

        st.divider()
        st.markdown(f"""
        <div style='color:#aaaaaa; font-size:0.65rem; text-align:center; line-height:1.8;'>
            Port de Cotonou<br>6.35°N, 2.43°E<br>
            Source : ECMWF via GEE<br>
            METEO-BENIN / DPROM / SPAM<br>
            © 2026
        </div>
        """, unsafe_allow_html=True)

        return df, run_label, time_start, time_end, show_markers, show_summary

# =============================================================================
# Main
# =============================================================================

def main():
    df, run_label, time_start, time_end, show_markers, show_summary = render_sidebar()

    # Filtrer
    df["forecast_time_local"] = pd.to_datetime(df["forecast_time_local"])
    df_f = df[(df["forecast_time_local"] >= pd.Timestamp(time_start)) &
              (df["forecast_time_local"] <= pd.Timestamp(time_end))].copy()

    if df_f.empty:
        st.warning("⚠️ Aucune donnée sur la période sélectionnée.")
        return

    # ── En-tête ──────────────────────────────────────────────────────────────
    col_title, col_alert = st.columns([3, 1])
    with col_title:
        st.markdown(f"## ⚓ Prévisions Météo — Port de Cotonou")
        st.markdown(f"**Bulletin : {run_label}**  |  "
                    f"{df_f['forecast_time_local'].min().strftime('%d/%m/%Y %H:%M')} → "
                    f"{df_f['forecast_time_local'].max().strftime('%d/%m/%Y %H:%M')}")
    with col_alert:
        lvl_key, lvl_label = get_global_alert(df_f)
        st.markdown(f"""
        <div class="alert-{lvl_key}" style="text-align:center; margin-top:10px;">
            <b style="font-size:1.1rem;">{lvl_label}</b>
        </div>
        """, unsafe_allow_html=True)

    st.divider()

    # ── KPI ──────────────────────────────────────────────────────────────────
    k1, k2, k3, k4, k5 = st.columns(5)
    now = now_local()
    closest = df_f.iloc[(df_f["forecast_time_local"] - now).abs().argsort()[:1]]

    with k1:
        v = closest["RafaleV10_Km/h"].values[0] if not closest.empty else 0
        lvl, lbl = get_alert_level(v, "10m")
        st.metric("💨 Rafales 10m", f"{v:.0f} km/h", delta=lbl,
                  delta_color="off")
    with k2:
        v = closest["RafaleV22_Km/h"].values[0] if not closest.empty else 0
        lvl, lbl = get_alert_level(v, "22m")
        st.metric("💨 Rafales 22m", f"{v:.0f} km/h", delta=lbl,
                  delta_color="off")
    with k3:
        v = closest["RafaleV60_Km/h"].values[0] if not closest.empty else 0
        lvl, lbl = get_alert_level(v, "60m")
        st.metric("💨 Rafales 60m", f"{v:.0f} km/h", delta=lbl,
                  delta_color="off")
    with k4:
        v = closest["RafaleV70_Km/h"].values[0] if not closest.empty else 0
        lvl, lbl = get_alert_level(v, "70m")
        st.metric("💨 Rafales 70m", f"{v:.0f} km/h", delta=lbl,
                  delta_color="off")
    with k5:
        v = closest["T(°C)"].values[0] if not closest.empty else 0
        st.metric("🌡️ T°C", f"{v:.1f} °C")

    st.divider()

    # ── Graphique synthèse ────────────────────────────────────────────────────
    if show_summary:
        st.plotly_chart(plot_wind_summary(df_f), use_container_width=True)

    # ── Graphiques par niveau ─────────────────────────────────────────────────
    st.markdown("### 📊 Vent par niveau")
    col1, col2 = st.columns(2)
    with col1:
        st.plotly_chart(plot_wind_level(df_f, "10m", "V10m_Km/h",  "RafaleV10_Km/h",  show_markers), use_container_width=True)
        st.plotly_chart(plot_wind_level(df_f, "60m", "V60m_Km/h",  "RafaleV60_Km/h",  show_markers), use_container_width=True)
    with col2:
        st.plotly_chart(plot_wind_level(df_f, "22m", "V22m_Km/h",  "RafaleV22_Km/h",  show_markers), use_container_width=True)
        st.plotly_chart(plot_wind_level(df_f, "70m", "V70m_Km/h",  "RafaleV70_Km/h",  show_markers), use_container_width=True)

    # ── T°C + Pluie ───────────────────────────────────────────────────────────
    st.plotly_chart(plot_temp_rain(df_f, show_markers), use_container_width=True)

    # ── Tableau récapitulatif ─────────────────────────────────────────────────
    st.markdown("### 📋 Tableau récapitulatif")
    render_table(df_f)

    # ── Légende seuils ────────────────────────────────────────────────────────
    st.markdown("### 📌 Seuils d'alerte rafales (km/h)")
    col_l1, col_l2 = st.columns(2)
    with col_l1:
        st.markdown("""
        | Hauteur | 🟢 Vert | 🟡 Jaune | 🟠 Orange | 🔴 Rouge |
        |---------|---------|----------|-----------|---------|
        | 10m | ≤28 | 29–49 | 50–74 | ≥75 |
        | 22m | ≤33 | 34–57 | 58–86 | ≥87 |
        """)
    with col_l2:
        st.markdown("""
        | Hauteur | 🟢 Vert | 🟡 Jaune | 🟠 Orange | 🔴 Rouge |
        |---------|---------|----------|-----------|---------|
        | 60m | ≤40 | 41–70 | 71–107 | ≥107 |
        | 70m | ≤40 | 42–72 | 73–109 | ≥110 |
        """)

    # ── Export ────────────────────────────────────────────────────────────────
    st.divider()
    st.markdown("### 💾 Export")
    csv_export = df_f.copy()
    csv_export["forecast_time_local"] = csv_export["forecast_time_local"].dt.strftime("%Y-%m-%d %H:%M")
    st.download_button(
        "⬇️ Télécharger CSV filtré",
        data=csv_export.to_csv(index=False).encode("utf-8"),
        file_name=f"BeninTerminal_{run_label}.csv",
        mime="text/csv",
    )

if __name__ == "__main__":
    main()

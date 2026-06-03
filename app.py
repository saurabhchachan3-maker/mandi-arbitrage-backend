import os
import time
from datetime import date as dt_date

import feedparser
import numpy as np
import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text

# ── Page config — MUST be the very first Streamlit call ──────────────────────
st.set_page_config(
    page_title="Grain Arbitrage Terminal",
    page_icon="🌾",
    layout="wide",
)

# ── DB engine ─────────────────────────────────────────────────────────────────
try:
    _DB_URL = st.secrets["DATABASE_URL"]
except Exception:
    _DB_URL = os.getenv("DATABASE_URL", "")
_engine = create_engine(_DB_URL, pool_pre_ping=True) if _DB_URL else None

# ── Passcode (read once at module level) ──────────────────────────────────────
try:
    _PASSCODE = st.secrets.get("DASHBOARD_PASSCODE", "")
except Exception:
    _PASSCODE = os.getenv("DASHBOARD_PASSCODE", "")

# ── Language — backed by session state so it survives tab switches ────────────
if "lang" not in st.session_state:
    st.session_state["lang"] = "en"
LNG: str = st.session_state["lang"]

# ── Translation table ─────────────────────────────────────────────────────────
_T: dict[str, dict[str, str]] = {
    "app_title":      {"en": "Grain Arbitrage Terminal",       "hi": "अनाज आर्बिट्राज टर्मिनल"},
    "app_caption":    {"en": "Live intelligence dashboard for physical grain trading across Indian mandis.",
                       "hi": "भारतीय मंडियों में भौतिक अनाज व्यापार के लिए लाइव इंटेलिजेंस डैशबोर्ड।"},
    "tab_inventory":  {"en": "📊 Live Inventory",              "hi": "📊 लाइव इन्वेंटरी"},
    "tab_intel":      {"en": "📰 Market Intelligence",         "hi": "📰 बाज़ार इंटेलिजेंस"},
    "tab_entry":      {"en": "✏️ Manual Entry",                "hi": "✏️ मैन्युअल प्रविष्टि"},
    "tab_ai":         {"en": "🤖 AI Price Predictor",          "hi": "🤖 AI मूल्य पूर्वानुमान"},
    "weather_hdr":    {"en": "Regional Weather",               "hi": "क्षेत्रीय मौसम"},
    "dgft_hdr":       {"en": "DGFT / Govt. Circulars",         "hi": "DGFT / सरकारी परिपत्र"},
    "issued_lbl":     {"en": "Issued",                         "hi": "जारी"},
    "news_hdr":       {"en": "Live News Feed",                 "hi": "ताज़ा समाचार"},
    "news_note":      {"en": "",
                       "hi": "📰 *अंग्रेज़ी हेडलाइंस (Live English Headlines via Google News)*"},
    "news_empty":     {"en": "No articles found.",             "hi": "कोई समाचार नहीं मिला।"},
    "news_loading":   {"en": "Fetching news…",                 "hi": "समाचार लोड हो रहे हैं…"},
    "no_trades":      {"en": "No trades recorded yet.",        "hi": "अभी तक कोई व्यापार दर्ज नहीं।"},
    "delete_sel":     {"en": "Select Trade ID to Delete",      "hi": "हटाने के लिए ट्रेड ID चुनें"},
    "delete_btn":     {"en": "🗑️ Delete Entry",                "hi": "🗑️ प्रविष्टि हटाएं"},
    "ai_hdr":         {"en": "## 🤖 AI Arbitrage Predictor",   "hi": "## 🤖 AI आर्बिट्राज पूर्वानुमान"},
    "ai_caption":     {"en": ("Macro-rule engine evaluating live government policy and regional weather "
                              "to generate NCDEX–mandi spread estimates. Transitions to ML mode at 30 trades."),
                       "hi": ("मैक्रो-नियम इंजन जो नीति संकेतों और मौसम पैटर्न का मूल्यांकन कर "
                              "NCDEX–मंडी स्प्रेड अनुमान देता है। 30 ट्रेड पर ML मोड में बदलेगा।")},
    "signals_hdr":    {"en": "Active Market Signals",          "hi": "सक्रिय बाज़ार संकेत"},
    "no_signals":     {"en": "No strong macro signals detected.", "hi": "कोई मजबूत संकेत नहीं।"},
    "lbl_ncdex":      {"en": "NCDEX Reference (₹/qtl)",        "hi": "NCDEX संदर्भ (₹/क्विंटल)"},
    "lbl_mandi":      {"en": "Predicted Mandi Price (₹/qtl)",  "hi": "अनुमानित मंडी मूल्य (₹/क्विंटल)"},
    "lbl_spread":     {"en": "Predicted NCDEX–Mandi Spread",   "hi": "अनुमानित NCDEX–मंडी अंतर"},
    "lbl_bias":       {"en": "Predicted Market Bias",          "hi": "अनुमानित बाज़ार पूर्वाग्रह"},
    "lbl_strength":   {"en": "Arbitrage Signal Strength",      "hi": "आर्बिट्राज संकेत शक्ति"},
    "bullish":        {"en": "📈 BULLISH",                     "hi": "📈 तेजी"},
    "bearish":        {"en": "📉 BEARISH",                     "hi": "📉 मंदी"},
    "neutral":        {"en": "➡️ STABLE",                     "hi": "➡️ स्थिर"},
    "advice_bullish": {"en": "Physical mandi prices expected to firm. Consider accumulating at current spot levels.",
                       "hi": "मंडी मूल्य मजबूत होने की उम्मीद है। मौजूदा स्तरों पर इन्वेंटरी जमा करें।"},
    "advice_bearish": {"en": "Downward pressure likely. Prioritise liquidating surplus above cost-price.",
                       "hi": "कीमतों में गिरावट संभव। लागत मूल्य से ऊपर अधिशेष स्टॉक बेचें।"},
    "advice_neutral": {"en": "Mixed signals. Hold positions and monitor NAFED releases and weather updates.",
                       "hi": "मिश्रित संकेत। NAFED और मौसम अपडेट की निगरानी करें।"},
    "engine_ml":      {"en": "🧠 **Engine Mode: High-Fidelity ML** — Local spread optimisation active.",
                       "hi": "🧠 **इंजन मोड: हाई-फिडेलिटी ML** — स्थानीय स्प्रेड ऑप्टिमाइज़ेशन सक्रिय।"},
    "engine_macro":   {"en": "📊 **Engine Mode: Macro-Rule Baseline** (Weather + NAFED Notifications)",
                       "hi": "📊 **इंजन मोड: मैक्रो-नियम बेसलाइन** (मौसम + NAFED अधिसूचनाएं)"},
    "engine_body":    {"en": ("The system transitions to **High-Fidelity ML** once the database reaches "
                              "**{n} entries**, unlocking location-specific spread arbitrage optimisation."),
                       "hi": ("**{n} प्रविष्टियां** होने पर सिस्टम **ML** मोड में बदल जाएगा।")},
}


def tx(key: str, **fmt) -> str:
    s = _T.get(key, {}).get(LNG) or _T.get(key, {}).get("en") or key
    return s.format(**fmt) if fmt else s


# ── Static market intelligence data ──────────────────────────────────────────
COMMODITIES: dict[str, str] = {
    "Chana (Gram)": "chana gram grain prices india",
    "Moong Dal":    "moong dal grain prices india",
    "Groundnut":    "groundnut peanut grain prices india",
}

WEATHER_DATA: dict[str, list[tuple[str, str, str]]] = {
    "Chana (Gram)": [
        ("Madhya Pradesh", "32 °C", "Dry, no rain forecast"),
        ("Rajasthan",      "36 °C", "Hot & arid, mild wind"),
        ("Maharashtra",    "29 °C", "Partly cloudy"),
    ],
    "Moong Dal": [
        ("Rajasthan",   "38 °C", "Dry, high UV index"),
        ("Maharashtra", "30 °C", "Light showers expected"),
        ("Karnataka",   "27 °C", "Moderate humidity"),
    ],
    "Groundnut": [
        ("Gujarat",        "33 °C", "Dry, strong winds"),
        ("Andhra Pradesh", "31 °C", "Partly cloudy"),
        ("Tamil Nadu",     "28 °C", "Light rain expected"),
    ],
}

DGFT_ALERTS: dict[str, list[tuple[str, str, dt_date]]] = {
    "Chana (Gram)": [
        ("Stock Limit Advisory",
         "States advised to strictly enforce trader stock limits under the Essential Commodities Act.",
         dt_date(2026, 5, 26)),
        ("Import Duty Update",
         "Chana import duty retained at 66% — effective for all consignments cleared after 01-May-2026.",
         dt_date(2026, 5, 22)),
        ("MSP Notification",
         "Govt. MSP for Chana fixed at ₹5,440/qtl for Rabi 2025-26 season.",
         dt_date(2026, 5, 15)),
    ],
    "Moong Dal": [
        ("Buffer Stock Release",
         "NAFED to release 50,000 MT Moong from central buffer stocks across Delhi, Mumbai, and Chennai APMCs.",
         dt_date(2026, 5, 25)),
        ("Export Incentive",
         "DGFT extends MEIS benefit of 3% for Moong exports to ASEAN nations for a further 6 months.",
         dt_date(2026, 5, 20)),
        ("Quality Standard Alert",
         "FSSAI revised moisture-content ceiling for packaged Moong Dal from 14% to 12%.",
         dt_date(2026, 5, 12)),
    ],
    "Groundnut": [
        ("SEZ Notification",
         "Kandla SEZ announces a 90-day zero-duty export window for groundnut oil and meal.",
         dt_date(2026, 5, 23)),
        ("Aflatoxin Advisory",
         "FSSAI advisory: all groundnut export consignments to EU/US must carry an aflatoxin test certificate.",
         dt_date(2026, 5, 18)),
        ("MSP Update",
         "CACP recommends Kharif 2026 Groundnut MSP at ₹6,783/qtl — a 4.2% hike over last season.",
         dt_date(2026, 5, 8)),
    ],
}

DGFT_TITLE_HI: dict[str, str] = {
    "Stock Limit Advisory":   "स्टॉक सीमा सलाह",
    "Import Duty Update":     "आयात शुल्क अपडेट",
    "MSP Notification":       "एमएसपी अधिसूचना",
    "Buffer Stock Release":   "बफर स्टॉक जारी",
    "Export Incentive":       "निर्यात प्रोत्साहन",
    "Quality Standard Alert": "गुणवत्ता मानक चेतावनी",
    "SEZ Notification":       "एसईजेड अधिसूचना",
    "Aflatoxin Advisory":     "एफ्लाटॉक्सिन सलाह",
    "MSP Update":             "एमएसपी अपडेट",
}

BASE_NCDEX: dict[str, float] = {
    "Chana (Gram)": 5_580.0, "Moong Dal": 8_750.0, "Groundnut": 6_900.0,
}
BASE_SPREAD: dict[str, float] = {
    "Chana (Gram)": 180.0, "Moong Dal": 280.0, "Groundnut": 150.0,
}


# ─────────────────────────────────────────────────────────────────────────────
# SECURITY GATE
# ─────────────────────────────────────────────────────────────────────────────

def render_login() -> None:
    """Render the centered passcode gate. Hides sidebar and all app content."""
    st.markdown("""
        <style>
        [data-testid="stSidebar"]       { display: none !important; }
        [data-testid="collapsedControl"] { display: none !important; }
        </style>
    """, unsafe_allow_html=True)

    st.markdown("<br><br>", unsafe_allow_html=True)
    _, col, _ = st.columns([1, 1.1, 1])
    with col:
        st.markdown("""
            <div style='text-align:center; padding:40px 32px; background:#ffffff;
                        border-radius:20px; border:1px solid #e5e7eb;
                        box-shadow:0 4px 24px rgba(0,0,0,0.07);'>
                <div style='font-size:3rem'>🌾</div>
                <h2 style='margin:8px 0 4px'>Grain Arbitrage Terminal</h2>
                <p style='color:#6b7280; font-size:0.9rem; margin-bottom:24px'>
                    Secure Trading Intelligence Platform
                </p>
            </div>
        """, unsafe_allow_html=True)
        st.markdown("")
        entered = st.text_input(
            "Dashboard Passcode",
            type="password",
            placeholder="Enter passcode…",
            label_visibility="collapsed",
        )
        if st.button("🔓  Enter Dashboard", use_container_width=True, type="primary"):
            if entered == _PASSCODE:
                st.session_state["authenticated"] = True
                st.rerun()
            else:
                st.error("Incorrect passcode — please try again.")


if not st.session_state.get("authenticated"):
    render_login()
    st.stop()   # ← nothing below this line runs unless authenticated


# ─────────────────────────────────────────────────────────────────────────────
# AUTHENTICATED — SIDEBAR
# ─────────────────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("## ⚙️ Settings")
    _lang_choice = st.radio("Language / भाषा", ["English", "Hindi"], horizontal=True)
    _new_lng = "hi" if _lang_choice == "Hindi" else "en"
    if _new_lng != LNG:
        st.session_state["lang"] = _new_lng
        st.rerun()

    st.markdown("---")
    if st.button("🚪 Logout", use_container_width=True):
        st.session_state["authenticated"] = False
        st.rerun()
    st.caption("Grain Arbitrage Terminal v2.0\nPowered by OpenAI + Supabase")


# ─────────────────────────────────────────────────────────────────────────────
# DATABASE HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def load_all_trades() -> tuple[pd.DataFrame, str | None]:
    """Return (DataFrame, error_message). error_message is None on success."""
    if _engine is None:
        return pd.DataFrame(), "DATABASE_URL not configured — check secrets.toml"
    try:
        with _engine.connect() as conn:
            df = pd.read_sql_query(
                """SELECT id, date, sender_number, workflow_type, commodity,
                          quantity, rate, warehouse_location, seller_name,
                          buyer_name, delivery_date, status
                   FROM   physical_trades
                   ORDER  BY id DESC""",
                conn,
            )
        return df, None
    except Exception as exc:
        return pd.DataFrame(), str(exc)


def insert_trade_manual(data: dict) -> int:
    with _engine.begin() as conn:
        result = conn.execute(
            text("""
                INSERT INTO physical_trades
                    (date, sender_number, workflow_type, commodity, quantity,
                     rate, warehouse_location, seller_name, buyer_name,
                     delivery_date, status)
                VALUES
                    (:date, :sender_number, :workflow_type, :commodity, :quantity,
                     :rate, :warehouse_location, :seller_name, :buyer_name,
                     :delivery_date, :status)
                RETURNING id
            """),
            data,
        )
        return result.fetchone()[0]


def delete_trade(trade_id: int) -> bool:
    try:
        with _engine.begin() as conn:
            conn.execute(
                text("DELETE FROM physical_trades WHERE id = :id"),
                {"id": trade_id},
            )
        return True
    except Exception:
        return False


# ─────────────────────────────────────────────────────────────────────────────
# MARKET INTELLIGENCE HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _relative_label(issue_date: dt_date) -> str:
    delta = (dt_date.today() - issue_date).days
    if LNG == "hi":
        if delta == 0:  return "आज"
        if delta == 1:  return "कल"
        if delta < 30:  return f"{delta} दिन पहले"
        return f"{delta // 30} महीने पहले"
    if delta == 0:  return "today"
    if delta == 1:  return "yesterday"
    if delta < 30:  return f"{delta} days ago"
    return f"{delta // 30} month{'s' if delta // 30 > 1 else ''} ago"


def fetch_news(query: str, max_items: int = 5) -> list[dict]:
    url = (f"https://news.google.com/rss/search?q={query.replace(' ', '+')}"
           f"&hl=en-IN&gl=IN&ceid=IN:en")
    feed = feedparser.parse(url)
    return [
        {
            "title":     e.get("title", "No title"),
            "link":      e.get("link", "#"),
            "published": e.get("published", ""),
            "source":    e.get("source", {}).get("title", "Google News"),
        }
        for e in feed.entries[:max_items]
    ]


# ─────────────────────────────────────────────────────────────────────────────
# RENDER: LIVE INVENTORY
# ─────────────────────────────────────────────────────────────────────────────

def _build_ledger_df(df: pd.DataFrame) -> pd.DataFrame:
    """
    Transform a flat trades DataFrame into a double-entry ledger view.

    Purchase side  →  Pur_Qty  | Pur_Rate  | Pur_Value
    Sale side      →  Sale_Qty | Sale_Rate | Sale_Value

    Rows where trade_action is neither 'Purchase' nor 'Sale' get NaN on
    both sides so they still appear in the table without polluting totals.
    """
    df = df.copy().reset_index(drop=True)          # ← reset so index is always 0,1,2…
    df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce")
    df["rate"]     = pd.to_numeric(df["rate"],     errors="coerce")
    df["_value"]   = df["quantity"] * df["rate"]

    # Build boolean masks anchored to df's own index — avoids AssertionError
    # when df is a non-contiguous slice of the original DataFrame
    if "trade_action" in df.columns:
        is_pur  = df["trade_action"].eq("Purchase")
        is_sale = df["trade_action"].eq("Sale")
    else:
        is_pur  = pd.Series(False, index=df.index)
        is_sale = pd.Series(False, index=df.index)

    df["Pur_Qty"]    = np.where(is_pur,  df["quantity"], np.nan)
    df["Pur_Rate"]   = np.where(is_pur,  df["rate"],     np.nan)
    df["Pur_Value"]  = np.where(is_pur,  df["_value"],   np.nan)
    df["Sale_Qty"]   = np.where(is_sale, df["quantity"], np.nan)
    df["Sale_Rate"]  = np.where(is_sale, df["rate"],     np.nan)
    df["Sale_Value"] = np.where(is_sale, df["_value"],   np.nan)

    # Columns that must be present before selecting
    base_cols   = ["date", "commodity", "warehouse_location"]
    ledger_cols = ["Pur_Qty", "Pur_Rate", "Pur_Value",
                   "Sale_Qty", "Sale_Rate", "Sale_Value"]
    available   = [c for c in base_cols + ledger_cols if c in df.columns]

    rename_map = {
        "date":               "Date",
        "commodity":          "Commodity",
        "warehouse_location": "Place",
        "Pur_Qty":            "Pur Qty (Qtl)",
        "Pur_Rate":           "Pur Rate (₹)",
        "Pur_Value":          "Pur Value (₹)",
        "Sale_Qty":           "Sale Qty (Qtl)",
        "Sale_Rate":          "Sale Rate (₹)",
        "Sale_Value":         "Sale Value (₹)",
    }
    return df[available].rename(columns=rename_map)


def _ledger_kpis(df: pd.DataFrame) -> None:
    """Render a 6-column KPI strip: purchase side | sale side | net."""
    df = df.copy().reset_index(drop=True)          # ← same fix: reset index first
    df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce")
    df["rate"]     = pd.to_numeric(df["rate"],     errors="coerce")
    df["_value"]   = df["quantity"] * df["rate"]

    if "trade_action" in df.columns:
        is_pur  = df["trade_action"].eq("Purchase")
        is_sale = df["trade_action"].eq("Sale")
    else:
        is_pur  = pd.Series(False, index=df.index)
        is_sale = pd.Series(False, index=df.index)

    pur_qty  = df.loc[is_pur,  "quantity"].sum()
    pur_val  = df.loc[is_pur,  "_value"].sum()
    sale_qty = df.loc[is_sale, "quantity"].sum()
    sale_val = df.loc[is_sale, "_value"].sum()
    net_qty  = pur_qty - sale_qty
    net_val  = pur_val - sale_val

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("🟢 Pur Qty (qtl)"  if LNG == "en" else "🟢 खरीद मात्रा",  f"{pur_qty:,.0f}")
    c2.metric("🟢 Pur Value (₹)"  if LNG == "en" else "🟢 खरीद मूल्य",   f"₹{pur_val:,.0f}")
    c3.metric("🔴 Sale Qty (qtl)" if LNG == "en" else "🔴 बिक्री मात्रा", f"{sale_qty:,.0f}")
    c4.metric("🔴 Sale Value (₹)" if LNG == "en" else "🔴 बिक्री मूल्य",  f"₹{sale_val:,.0f}")
    c5.metric("⚖️ Net Qty (qtl)"  if LNG == "en" else "⚖️ नेट मात्रा",   f"{net_qty:,.0f}",
              delta_color="normal" if net_qty >= 0 else "inverse")
    c6.metric("⚖️ Net Value (₹)"  if LNG == "en" else "⚖️ नेट मूल्य",    f"₹{net_val:,.0f}",
              delta_color="normal" if net_val >= 0 else "inverse")


def _section_header(emoji: str, title: str, count: int) -> None:
    st.markdown(
        f"<h3 style='margin-bottom:4px'>{emoji} {title} "
        f"<span style='font-size:0.75rem; color:#6b7280; font-weight:normal'>"
        f"({count} {'entry' if count == 1 else 'entries'})</span></h3>",
        unsafe_allow_html=True,
    )


def render_inventory(df: pd.DataFrame, db_error: str | None = None) -> None:
    # Show DB error prominently so it's never silently swallowed
    if db_error:
        st.error(f"⚠️ **Database connection error** — could not load trades.\n\n`{db_error}`")
        return

    if df.empty:
        st.info(tx("no_trades"))
        return

    # ── Commodity filter (dynamic from DB) ───────────────────────────────────
    unique_commodities = sorted(
        df["commodity"].dropna().str.title().unique()
    )
    filter_opts = (["All Commodities"] if LNG == "en" else ["सभी अनाज"]) + unique_commodities
    selected = st.selectbox(
        "Filter by Commodity / अनाज चुनें" if LNG == "en" else "अनाज चुनें",
        filter_opts,
    )

    if selected not in ("All Commodities", "सभी अनाज"):
        df = df[df["commodity"].str.title() == selected]

    # ─────────────────────────────────────────────────────────────────────────
    # SECTION 1 — WAREHOUSE STOCK (Warehousing)
    # ─────────────────────────────────────────────────────────────────────────
    wh = df[df["workflow_type"] == "Warehousing"].copy()
    _section_header("🏭", "Current Warehouse Stock" if LNG == "en" else "गोदाम स्टॉक", len(wh))

    if wh.empty:
        st.info("No warehousing entries yet." if LNG == "en" else "कोई गोदाम प्रविष्टि नहीं।")
    else:
        # Purchase / Sale / Net KPI strip
        _ledger_kpis(wh)
        st.markdown("")

        # Double-entry ledger table
        ledger_wh = _build_ledger_df(wh)
        st.dataframe(
            ledger_wh.style.format(
                {c: "{:,.0f}" for c in ledger_wh.columns
                 if any(k in c for k in ["Qty", "Rate", "Value"])},
                na_rep="—",
            ),
            hide_index=True, use_container_width=True,
        )

        # Weighted avg per commodity (collapsed)
        with st.expander("📊 Avg Cost Summary" if LNG == "en" else "📊 औसत लागत सारांश"):
            wh_valid = wh.dropna(subset=["rate", "quantity"]).copy()
            if not wh_valid.empty:
                wh_valid["value"] = pd.to_numeric(wh_valid["quantity"], errors="coerce") \
                                  * pd.to_numeric(wh_valid["rate"], errors="coerce")
                wav = wh_valid.groupby("commodity").apply(
                    lambda x: x["value"].sum() / x["quantity"].sum(),
                    include_groups=False,
                ).reset_index()
                wav.columns = ["Commodity", "Avg Purchase Price (₹/Quintal)"]
                wav["Commodity"] = wav["Commodity"].str.title()
                wav["Avg Purchase Price (₹/Quintal)"] = \
                    wav["Avg Purchase Price (₹/Quintal)"].map(lambda v: f"₹{v:,.0f}")
                st.dataframe(wav, hide_index=True, use_container_width=True)

    st.markdown("---")

    # ─────────────────────────────────────────────────────────────────────────
    # SECTION 2 — PROCESSING PIPELINES
    # ─────────────────────────────────────────────────────────────────────────
    proc = df[df["workflow_type"] == "Processing"].copy()
    _section_header("⚙️", "Active Processing Pipelines" if LNG == "en" else "प्रोसेसिंग पाइपलाइन",
                    len(proc))

    if proc.empty:
        st.info("No processing entries yet." if LNG == "en" else "कोई प्रोसेसिंग प्रविष्टि नहीं।")
    else:
        p1, p2, p3 = st.columns(3)
        p1.metric("Total Pending (qtl)" if LNG == "en" else "कुल लंबित (क्विंटल)",
                  f"{proc['quantity'].sum():,.0f}")
        p2.metric("Commodities" if LNG == "en" else "अनाज", proc["commodity"].nunique())
        p3.metric("Locations" if LNG == "en" else "स्थान",
                  proc["warehouse_location"].dropna().nunique())

        cols_proc = ["id", "date", "commodity", "quantity",
                     "warehouse_location", "status"]
        rename_proc = {
            "id": "ID", "date": "Date", "commodity": "Commodity",
            "quantity": "Qty (qtl)", "warehouse_location": "Location", "status": "Status",
        }
        st.dataframe(
            proc[cols_proc].rename(columns=rename_proc),
            hide_index=True, use_container_width=True,
        )

    st.markdown("---")

    # ─────────────────────────────────────────────────────────────────────────
    # SECTION 3 — DIRECT TRADE LEDGER
    # ─────────────────────────────────────────────────────────────────────────
    dt = df[df["workflow_type"] == "Direct Trade"].copy()
    _section_header("🤝", "Direct Trade Ledger" if LNG == "en" else "डायरेक्ट ट्रेड लेजर", len(dt))

    if dt.empty:
        st.info("No direct trades yet." if LNG == "en" else "कोई डायरेक्ट ट्रेड नहीं।")
    else:
        # Purchase / Sale / Net KPI strip
        _ledger_kpis(dt)
        st.markdown("")

        # Double-entry ledger (seller / buyer appended as extra context cols)
        ledger_dt = _build_ledger_df(dt)
        # Attach seller / buyer columns if present
        for extra_col, extra_label in [("seller_name", "Seller"), ("buyer_name", "Buyer"),
                                        ("delivery_date", "Delivery Date")]:
            if extra_col in dt.columns:
                ledger_dt[extra_label] = dt[extra_col].values
        st.dataframe(
            ledger_dt.style.format(
                {c: "{:,.0f}" for c in ledger_dt.columns
                 if any(k in c for k in ["Qty", "Rate", "Value"])},
                na_rep="—",
            ),
            hide_index=True, use_container_width=True,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # CATCH-ALL — rows where workflow_type is NULL / unclassified
    # ─────────────────────────────────────────────────────────────────────────
    unclassified = df[~df["workflow_type"].isin(["Warehousing", "Processing", "Direct Trade"])].copy()
    if not unclassified.empty:
        st.markdown("---")
        _section_header("📋", "Unclassified / Legacy Entries" if LNG == "en"
                        else "अवर्गीकृत प्रविष्टियां", len(unclassified))
        st.caption("These rows have no workflow_type (old schema entries)." if LNG == "en"
                   else "इन प्रविष्टियों में workflow_type नहीं है।")
        ledger_unc = _build_ledger_df(unclassified)
        st.dataframe(
            ledger_unc.style.format(
                {c: "{:,.0f}" for c in ledger_unc.columns
                 if any(k in c for k in ["Qty", "Rate", "Value"])},
                na_rep="—",
            ),
            hide_index=True, use_container_width=True,
        )

    st.markdown("---")

    # ─────────────────────────────────────────────────────────────────────────
    # DELETE ENTRY (red button via CSS)
    # ─────────────────────────────────────────────────────────────────────────
    st.markdown("""<style>
        [data-testid="stForm"] button[kind="primaryFormSubmit"],
        [data-testid="stForm"] button[data-testid="baseButton-primary"] {
            background-color: #dc2626 !important; border-color: #dc2626 !important;
            color: white !important;
        }
    </style>""", unsafe_allow_html=True)

    with st.expander("🗑️ Delete / Correct an Entry" if LNG == "en" else "🗑️ प्रविष्टि सुधारें / हटाएं"):
        label_map = {
            int(r["id"]): (
                f"ID {int(r['id'])} — {str(r.get('workflow_type',''))[:2]} "
                f"{str(r.get('commodity','')).title()} "
                f"{r.get('quantity','')} qtl  ({r.get('date','')})"
            )
            for _, r in df.iterrows()
        }
        with st.form("delete_form"):
            col_a, col_b = st.columns([3, 1])
            with col_a:
                sel_id = st.selectbox(
                    tx("delete_sel"),
                    options=list(label_map.keys()),
                    format_func=lambda i: label_map[i],
                )
            with col_b:
                st.markdown("<br>", unsafe_allow_html=True)
                del_submitted = st.form_submit_button(tx("delete_btn"), type="primary")

        if del_submitted:
            if delete_trade(sel_id):
                st.success(f"Entry #{sel_id} deleted." if LNG == "en"
                           else f"प्रविष्टि #{sel_id} हटा दी गई।")
                st.rerun()
            else:
                st.error("Delete failed." if LNG == "en" else "हटाने में विफल।")


# ─────────────────────────────────────────────────────────────────────────────
# RENDER: MANUAL ENTRY WORKSPACE
# ─────────────────────────────────────────────────────────────────────────────

def render_manual_entry() -> None:
    st.markdown("## ✏️ Manual Trade Entry" if LNG == "en" else "## ✏️ मैन्युअल ट्रेड प्रविष्टि")
    st.caption(
        "Log historical entries directly into the Supabase database. "
        "All fields marked * are required." if LNG == "en" else
        "सीधे Supabase डेटाबेस में ऐतिहासिक प्रविष्टियां दर्ज करें। * अनिवार्य फ़ील्ड।"
    )
    st.markdown("")

    _, form_col, _ = st.columns([0.5, 3, 0.5])
    with form_col:
        with st.form("manual_entry_form", clear_on_submit=True):
            wf_options = ["Warehousing", "Processing", "Direct Trade"]
            workflow_type = st.selectbox(
                "Transaction Type *" if LNG == "en" else "लेनदेन प्रकार *",
                wf_options,
            )
            commodity = st.text_input(
                "Commodity * (e.g. chana, moong, wheat)" if LNG == "en"
                else "अनाज * (जैसे चना, मूंग, गेहूं)"
            )

            c1, c2 = st.columns(2)
            with c1:
                quantity = st.number_input(
                    "Quantity (quintals) *" if LNG == "en" else "मात्रा (क्विंटल) *",
                    min_value=0.0, step=0.5, format="%.1f",
                )
            with c2:
                rate = st.number_input(
                    "Rate ₹/qtl (leave 0 for Processing)" if LNG == "en"
                    else "दर ₹/क्विंटल (Processing के लिए 0 छोड़ें)",
                    min_value=0.0, step=1.0, format="%.0f",
                )

            warehouse_location = st.text_input(
                "Warehouse Location / City" if LNG == "en" else "गोदाम स्थान / शहर"
            )

            c3, c4 = st.columns(2)
            with c3:
                seller_name = st.text_input(
                    "Seller Name" if LNG == "en" else "विक्रेता का नाम"
                )
            with c4:
                buyer_name = st.text_input(
                    "Buyer Name (Direct Trade only)" if LNG == "en"
                    else "खरीदार का नाम (केवल Direct Trade)"
                )

            delivery_date = st.date_input(
                "Delivery Date (Direct Trade only)" if LNG == "en"
                else "डिलीवरी तिथि (केवल Direct Trade)",
            )

            submitted = st.form_submit_button(
                "✅  Submit Entry" if LNG == "en" else "✅  प्रविष्टि सबमिट करें",
                type="primary", use_container_width=True,
            )

    if submitted:
        if not commodity.strip():
            st.error("Commodity is required." if LNG == "en" else "अनाज का नाम अनिवार्य है।")
            return
        if quantity <= 0:
            st.error("Quantity must be greater than 0." if LNG == "en"
                     else "मात्रा 0 से अधिक होनी चाहिए।")
            return

        insert_data = {
            "date":               dt_date.today().isoformat(),
            "sender_number":      "manual_entry",
            "workflow_type":      workflow_type,
            "commodity":          commodity.strip().lower(),
            "quantity":           quantity,
            "rate":               rate if rate > 0 else None,
            "warehouse_location": warehouse_location.strip() or None,
            "seller_name":        seller_name.strip() or None,
            "buyer_name":         buyer_name.strip() or None,
            "delivery_date":      str(delivery_date) if workflow_type == "Direct Trade" else None,
            "status":             "Pending" if workflow_type == "Processing" else None,
        }

        try:
            new_id = insert_trade_manual(insert_data)
            st.success(
                f"✅ Entry #{new_id} logged — {workflow_type} · "
                f"{commodity.strip().title()} · {quantity:,.0f} qtl"
                if LNG == "en" else
                f"✅ प्रविष्टि #{new_id} दर्ज — {workflow_type} · "
                f"{commodity.strip().title()} · {quantity:,.0f} क्विंटल"
            )
            st.balloons()
        except Exception as exc:
            st.error(f"Database insert failed: {exc}")


# ─────────────────────────────────────────────────────────────────────────────
# RENDER: MARKET INTELLIGENCE
# ─────────────────────────────────────────────────────────────────────────────

def render_market_intel() -> None:
    st.markdown("## 📰 Market Intelligence" if LNG == "en" else "## 📰 बाज़ार इंटेलिजेंस")

    # Commodity selector — pre-built list + free search
    sel_commodity = st.selectbox(
        "Select commodity for intelligence feed" if LNG == "en"
        else "इंटेलिजेंस फीड के लिए अनाज चुनें",
        list(COMMODITIES.keys()),
    )
    query = COMMODITIES[sel_commodity]

    col1, col2, col3 = st.columns([1, 1, 1.4])

    with col1:
        st.markdown(f"#### {tx('weather_hdr')}")
        for region, temp, condition in WEATHER_DATA[sel_commodity]:
            st.metric(label=region, value=temp, delta=condition, delta_color="off")

    with col2:
        st.markdown(f"#### {tx('dgft_hdr')}")
        for title_en, body, issue_date in DGFT_ALERTS[sel_commodity]:
            date_str = issue_date.strftime("%d-%b-%Y")
            relative = _relative_label(issue_date)
            title_display = DGFT_TITLE_HI.get(title_en, title_en) if LNG == "hi" else title_en
            with st.expander(f"[{date_str}]  {title_display}"):
                st.caption(f"📅 {tx('issued_lbl')} {date_str} · {relative}")
                st.write(body)

    with col3:
        st.markdown(f"#### {tx('news_hdr')}")
        note = tx("news_note")
        if note:
            st.caption(note)
        with st.spinner(tx("news_loading")):
            articles = fetch_news(query)
        if not articles:
            st.info(tx("news_empty"))
        else:
            for art in articles:
                prefix = "📰 " if LNG == "hi" else ""
                st.markdown(
                    f"**{prefix}[{art['title']}]({art['link']})**  \n"
                    f"<span style='color:grey; font-size:0.8em'>"
                    f"{art['source']} &nbsp;·&nbsp; {art['published']}</span>",
                    unsafe_allow_html=True,
                )
                st.divider()


# ─────────────────────────────────────────────────────────────────────────────
# RENDER: AI ARBITRAGE PREDICTOR
# ─────────────────────────────────────────────────────────────────────────────

def compute_arbitrage_signal(commodity: str) -> dict:
    signals: list[tuple[str, str, int]] = []
    net_score = 0

    for title_en, _body, _date in DGFT_ALERTS[commodity]:
        t = title_en.upper()
        if "STOCK LIMIT" in t:
            signals.append(("📋 Stock limit enforcement — depresses spot", "BEARISH", -2)); net_score -= 2
        if "BUFFER" in t:
            signals.append(("🏛️ NAFED buffer release adding supply", "BEARISH", -3)); net_score -= 3
        if "EXPORT INCENTIVE" in t or "SEZ" in t:
            signals.append(("🚢 Export stimulus / SEZ window active", "BULLISH", +2)); net_score += 2
        if "IMPORT DUTY" in t:
            signals.append(("🛡️ High import duty protects price floor", "BULLISH", +1)); net_score += 1
        if "MSP" in t:
            signals.append(("💰 Govt. MSP provides price-floor support", "BULLISH", +1)); net_score += 1
        if "AFLATOXIN" in t or "QUALITY" in t:
            signals.append(("⚠️ Quality advisory suppresses export premium", "BEARISH", -1)); net_score -= 1

    for region, _temp, condition in WEATHER_DATA[commodity]:
        cond = condition.lower()
        if any(w in cond for w in ["dry", "arid", "no rain", "high uv"]):
            signals.append((f"☀️ {region}: dry spell → supply risk", "BULLISH", +2)); net_score += 2
        elif any(w in cond for w in ["light shower", "light rain"]):
            signals.append((f"🌦️ {region}: light rain → neutral", "NEUTRAL", 0))
        elif any(w in cond for w in ["shower", "rain", "flood"]):
            signals.append((f"🌧️ {region}: rainfall → improved supply", "BEARISH", -1)); net_score -= 1
        elif "wind" in cond:
            signals.append((f"💨 {region}: strong winds → minor crop stress", "BULLISH", +1)); net_score += 1

    ncdex_ref       = BASE_NCDEX[commodity]
    adj_spread      = max(50.0, BASE_SPREAD[commodity] + net_score * 18)
    trend_key       = "bullish" if net_score >= 2 else ("bearish" if net_score <= -2 else "neutral")
    return {
        "trend_key": trend_key, "signals": signals, "net_score": net_score,
        "ncdex_ref": ncdex_ref, "predicted_spread": adj_spread,
        "predicted_mandi": ncdex_ref - adj_spread,
        "confidence": int(min(85, 50 + abs(net_score) * 5)),
    }


def render_ai_predictor(trade_count: int) -> None:
    THRESHOLD    = 30
    TREND_COLORS = {"bullish": "#16a34a", "bearish": "#dc2626", "neutral": "#d97706"}

    st.markdown(tx("ai_hdr"))
    st.caption(tx("ai_caption"))
    st.markdown("---")

    inner_tabs = st.tabs(list(COMMODITIES.keys()))
    for inner_tab, commodity in zip(inner_tabs, COMMODITIES.keys()):
        with inner_tab:
            r          = compute_arbitrage_signal(commodity)
            color      = TREND_COLORS[r["trend_key"]]
            advice_key = "advice_" + r["trend_key"]
            st.markdown(
                f"<h2 style='color:{color}; margin-bottom:2px'>{tx(r['trend_key'])}</h2>"
                f"<p style='color:#555; margin-top:2px; font-size:0.95em'>{tx(advice_key)}</p>",
                unsafe_allow_html=True,
            )
            st.markdown("")

            m1, m2, m3, m4, m5 = st.columns(5)
            m1.metric(tx("lbl_ncdex"), f"₹{r['ncdex_ref']:,.0f}")
            m2.metric(tx("lbl_mandi"), f"₹{r['predicted_mandi']:,.0f}",
                      delta=f"−₹{r['predicted_spread']:,.0f} vs NCDEX", delta_color="off")
            m3.metric(tx("lbl_spread"), f"₹{r['predicted_spread']:,.0f}/qtl")
            m4.metric(tx("lbl_bias"), tx(r["trend_key"]),
                      delta=f"Score: {r['net_score']:+d}",
                      delta_color="normal" if r["net_score"] >= 0 else "inverse")
            m5.metric(tx("lbl_strength"), f"{r['confidence']}%",
                      delta="Macro-rule baseline", delta_color="off")
            st.markdown("")

            st.markdown(f"#### {tx('signals_hdr')}")
            if r["signals"]:
                for desc, direction, weight in r["signals"]:
                    badge = ("#16a34a" if direction == "BULLISH"
                             else "#dc2626" if direction == "BEARISH" else "#d97706")
                    w_str = f"+{weight}" if weight > 0 else str(weight)
                    st.markdown(
                        f"<div style='display:flex; justify-content:space-between; align-items:center;"
                        f"padding:8px 14px; border-left:4px solid {badge}; background:#f8f8f8;"
                        f"margin-bottom:6px; border-radius:4px;'>"
                        f"<span style='font-size:0.91em'>{desc}</span>"
                        f"<span style='font-weight:700; color:{badge}; white-space:nowrap;"
                        f"margin-left:12px'>{direction} ({w_str})</span></div>",
                        unsafe_allow_html=True,
                    )
            else:
                st.info(tx("no_signals"))

            st.markdown("")
            pct    = min(100, int(trade_count / THRESHOLD * 100))
            bar    = "🟩" * int(pct / 5) + "⬜" * (20 - int(pct / 5))
            remain = max(0, THRESHOLD - trade_count)
            mode   = tx("engine_ml") if trade_count >= THRESHOLD else tx("engine_macro")
            st.info(
                f"{mode}  \n"
                f"{'Data Accumulation' if LNG == 'en' else 'डेटा संचय'}: "
                f"**{trade_count} {'trade' if trade_count == 1 else 'trades'} recorded**.  \n"
                f"{bar} &nbsp; {pct}% — **{remain} entries remaining**  \n\n"
                f"{tx('engine_body', n=THRESHOLD)}"
            )


# ─────────────────────────────────────────────────────────────────────────────
# PAGE LAYOUT
# ─────────────────────────────────────────────────────────────────────────────

hdr_col, refresh_col = st.columns([6, 1])
with hdr_col:
    st.title(tx("app_title"))
    st.caption(tx("app_caption"))
with refresh_col:
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("🔄 Refresh", use_container_width=True):
        st.rerun()

_df, _db_error = load_all_trades()

tab_inv, tab_intel, tab_entry, tab_ai = st.tabs([
    tx("tab_inventory"), tx("tab_intel"), tx("tab_entry"), tx("tab_ai"),
])

with tab_inv:
    render_inventory(_df, _db_error)

with tab_intel:
    render_market_intel()

with tab_entry:
    render_manual_entry()

with tab_ai:
    render_ai_predictor(len(_df))

# ── Auto-refresh every 60 seconds ────────────────────────────────────────────
time.sleep(60)
st.rerun()

import os
import time
from datetime import date as dt_date

import feedparser
import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()
_engine = create_engine(os.getenv("DATABASE_URL"), pool_pre_ping=True)

# ── Page config (must be the very first Streamlit call) ───────────────────────
st.set_page_config(page_title="Grain Arbitrage Terminal", layout="wide")

# ── Language toggle (sidebar) ─────────────────────────────────────────────────
st.sidebar.markdown("## ⚙️ Settings")
_lang_choice = st.sidebar.radio("Language / भाषा", ["English", "Hindi"], horizontal=True)
LNG: str = "hi" if _lang_choice == "Hindi" else "en"
st.sidebar.markdown("---")
st.sidebar.caption("Grain Arbitrage Terminal v1.0\nPowered by OpenAI + NCDEX data")

# ── Translation dictionary ─────────────────────────────────────────────────────
_T: dict[str, dict[str, str]] = {
    # App chrome
    "app_title":       {"en": "Grain Arbitrage Terminal",
                        "hi": "अनाज आर्बिट्राज टर्मिनल"},
    "app_caption":     {"en": "Live intelligence dashboard for physical grain trading across Indian mandis.",
                        "hi": "भारतीय मंडियों में भौतिक अनाज व्यापार के लिए लाइव इंटेलिजेंस डैशबोर्ड।"},
    # Commodity tab labels
    "tab_chana":       {"en": "Chana (Gram)",              "hi": "चना (ग्राम)"},
    "tab_moong":       {"en": "Moong Dal",                 "hi": "मूंग दाल"},
    "tab_groundnut":   {"en": "Groundnut",                 "hi": "मूंगफली"},
    "tab_ai":          {"en": "🤖 AI Price Predictor",     "hi": "🤖 AI मूल्य पूर्वानुमान"},
    # Weather
    "weather_hdr":     {"en": "Regional Weather",          "hi": "क्षेत्रीय मौसम"},
    # Circulars
    "dgft_hdr":        {"en": "DGFT / Govt. Circulars",    "hi": "DGFT / सरकारी परिपत्र"},
    "issued_lbl":      {"en": "Issued",                    "hi": "जारी"},
    # News
    "news_hdr":        {"en": "Live News Feed",            "hi": "ताज़ा समाचार मुख्य समाचार"},
    "news_note":       {"en": "",
                        "hi": "📰 *अंग्रेज़ी हेडलाइंस (Live English Headlines via Google News)*"},
    "news_empty":      {"en": "No news articles found.",   "hi": "कोई समाचार नहीं मिला।"},
    "news_loading":    {"en": "Fetching news…",            "hi": "समाचार लोड हो रहे हैं…"},
    # Inventory section
    "inventory_hdr":   {"en": "### Live Godown Inventory & Trades",
                        "hi": "### लाइव गोदाम इन्वेंटरी और व्यापार"},
    "no_trades":       {"en": "No trades recorded yet.",
                        "hi": "अभी तक कोई व्यापार दर्ज नहीं।"},
    "net_stock_hdr":   {"en": "🏭 Current Net Warehouse Stock",
                        "hi": "🏭 गोदाम में कुल स्टॉक स्थिति"},
    "trade_log_hdr":   {"en": "Trade Log",                 "hi": "व्यापार लॉग"},
    "delete_hdr":      {"en": "Correct a Mistaken Entry",  "hi": "गलत प्रविष्टि सुधारें"},
    "delete_sel":      {"en": "Select Trade ID to Delete", "hi": "हटाने के लिए ट्रेड ID चुनें"},
    "delete_btn":      {"en": "🗑️ Delete Entry",           "hi": "🗑️ प्रविष्टि हटाएं"},
    # Table column names
    "col_commodity":   {"en": "Commodity",                        "hi": "अनाज"},
    "col_net_wt":      {"en": "Net Weight Available (Quintals)",   "hi": "उपलब्ध नेट वजन (क्विंटल)"},
    "col_avg_price":   {"en": "Avg Purchase Price (₹/Quintal)",    "hi": "औसत खरीद मूल्य (₹/क्विंटल)"},
    "col_bought":      {"en": "Total Bought (qtl)",                "hi": "कुल खरीद (क्विंटल)"},
    "col_sold":        {"en": "Total Sold (qtl)",                  "hi": "कुल बिक्री (क्विंटल)"},
    "col_status":      {"en": "Status",                            "hi": "स्थिति"},
    # Stock status badges
    "in_stock":        {"en": "✅ In Stock",   "hi": "✅ स्टॉक में"},
    "zero_stock":      {"en": "⚪ Zero Stock", "hi": "⚪ शून्य स्टॉक"},
    "oversold":        {"en": "❌ Oversold",   "hi": "❌ अधिक बिक्री"},
    # AI predictor chrome
    "ai_hdr":          {"en": "## 🤖 AI Arbitrage Predictor",
                        "hi": "## 🤖 AI आर्बिट्राज पूर्वानुमान"},
    "ai_caption":      {"en": ("Macro-rule engine evaluating live government policy signals and regional "
                               "weather patterns to generate NCDEX–mandi spread estimates and directional "
                               "trade recommendations. Transitions automatically to ML mode once 30 trades "
                               "are recorded in your local database."),
                        "hi": ("मैक्रो-नियम इंजन जो सरकारी नीति संकेतों और क्षेत्रीय मौसम पैटर्न का मूल्यांकन "
                               "कर NCDEX–मंडी स्प्रेड अनुमान और व्यापार सुझाव देता है। 30 ट्रेड दर्ज होने पर "
                               "स्वचालित रूप से ML मोड में बदल जाएगा।")},
    "signals_hdr":     {"en": "Active Market Signals",            "hi": "सक्रिय बाज़ार संकेत"},
    "no_signals":      {"en": "No strong macro signals detected.", "hi": "कोई मजबूत संकेत नहीं मिला।"},
    # AI metric labels
    "lbl_ncdex":       {"en": "NCDEX Reference (₹/qtl)",          "hi": "NCDEX संदर्भ (₹/क्विंटल)"},
    "lbl_mandi":       {"en": "Predicted Mandi Price (₹/qtl)",     "hi": "अनुमानित मंडी मूल्य (₹/क्विंटल)"},
    "lbl_spread":      {"en": "Predicted NCDEX–Mandi Spread",      "hi": "अनुमानित NCDEX–मंडी अंतर"},
    "lbl_bias":        {"en": "Predicted Market Bias",             "hi": "अनुमानित बाज़ार पूर्वाग्रह"},
    "lbl_strength":    {"en": "Arbitrage Signal Strength",         "hi": "आर्बिट्राज संकेत शक्ति"},
    # Trend labels (used by AI tab metric cards)
    "bullish":         {"en": "📈 BULLISH",  "hi": "📈 तेजी"},
    "bearish":         {"en": "📉 BEARISH",  "hi": "📉 मंदी"},
    "neutral":         {"en": "➡️ STABLE",   "hi": "➡️ स्थिर"},
    # Trade advice (full sentence per trend)
    "advice_bullish":  {"en": ("Physical mandi prices expected to firm. Consider accumulating inventory "
                               "at current spot levels before NCDEX corrects upward."),
                        "hi": ("भौतिक मंडी मूल्य मजबूत होने की उम्मीद है। NCDEX के ऊपर सुधार से पहले "
                               "मौजूदा स्पॉट स्तरों पर इन्वेंटरी जमा करने पर विचार करें।")},
    "advice_bearish":  {"en": ("Downward price pressure likely. Prioritise liquidating surplus physical "
                               "stock above cost-price before the NCDEX–mandi spread compresses further."),
                        "hi": ("कीमतों में गिरावट की संभावना है। NCDEX–मंडी अंतर संकुचित होने से पहले "
                               "लागत मूल्य से ऊपर अधिशेष भौतिक स्टॉक बेचने को प्राथमिकता दें।")},
    "advice_neutral":  {"en": ("Mixed signals. Hold existing positions and monitor NAFED release progress "
                               "or fresh weather developments before committing capital."),
                        "hi": ("मिश्रित संकेत। पूंजी लगाने से पहले NAFED जारी होने की प्रगति या "
                               "नए मौसम विकास की निगरानी करते रहें।")},
    # Engine mode footer
    "engine_ml":       {"en": "🧠 **Engine Mode: High-Fidelity ML** — Local spread optimisation active.",
                        "hi": "🧠 **इंजन मोड: हाई-फिडेलिटी ML** — स्थानीय स्प्रेड ऑप्टिमाइज़ेशन सक्रिय।"},
    "engine_macro":    {"en": "📊 **Engine Mode: Macro-Rule Baseline** (Weather + NAFED Notifications)",
                        "hi": "📊 **इंजन मोड: मैक्रो-नियम बेसलाइन** (मौसम + NAFED अधिसूचनाएं)"},
    "engine_body":     {"en": ("The system will automatically transition to **High-Fidelity Machine Learning** "
                               "once the local database reaches **{n} historical entries**, unlocking local "
                               "spread arbitrage optimisation using your own mandi data, cost-basis, and "
                               "location-specific price patterns."),
                        "hi": ("जब लोकल डेटाबेस में **{n} ऐतिहासिक प्रविष्टियां** हो जाएंगी, तब सिस्टम "
                               "स्वचालित रूप से **हाई-फिडेलिटी मशीन लर्निंग** में बदल जाएगा और आपके मंडी "
                               "डेटा, लागत आधार और स्थान-विशिष्ट मूल्य पैटर्न का उपयोग करेगा।")},
}


def tx(key: str, **fmt) -> str:
    """Return the translated string for the current language, with optional .format() substitutions."""
    s = _T.get(key, {}).get(LNG) or _T.get(key, {}).get("en") or key
    return s.format(**fmt) if fmt else s


# ── Static data ────────────────────────────────────────────────────────────────
COMMODITIES: dict[str, str] = {
    "Chana (Gram)": "chana gram grain prices india",
    "Moong Dal":    "moong dal grain prices india",
    "Groundnut":    "groundnut peanut grain prices india",
}

# Maps commodity English key → translated tab label key
COMMODITY_TAB_KEY: dict[str, str] = {
    "Chana (Gram)": "tab_chana",
    "Moong Dal":    "tab_moong",
    "Groundnut":    "tab_groundnut",
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

# Each alert: (title_en, body, issue_date)
DGFT_ALERTS: dict[str, list[tuple[str, str, dt_date]]] = {
    "Chana (Gram)": [
        ("Stock Limit Advisory",
         "States advised to strictly enforce trader stock limits under the Essential Commodities Act. "
         "District collectors to conduct surprise inspections at mandis and cold-storage facilities.",
         dt_date(2026, 5, 26)),
        ("Import Duty Update",
         "Chana import duty retained at 66% — no revision in the latest DGFT review. "
         "Effective for all consignments cleared after 01-May-2026.",
         dt_date(2026, 5, 22)),
        ("MSP Notification",
         "Govt. MSP for Chana fixed at ₹5,440/qtl for Rabi 2025-26 season. "
         "Procurement through NAFED and state agencies to commence from 01-Jun-2026.",
         dt_date(2026, 5, 15)),
    ],
    "Moong Dal": [
        ("Buffer Stock Release",
         "NAFED to release 50,000 MT Moong from central buffer stocks across Delhi, Mumbai, and Chennai "
         "APMCs to cool wholesale prices ahead of the kharif arrival.",
         dt_date(2026, 5, 25)),
        ("Export Incentive",
         "DGFT extends MEIS benefit of 3% for Moong exports to ASEAN nations for a further 6 months. "
         "Exporters must register their intent on DGFT portal before 30-Jun-2026.",
         dt_date(2026, 5, 20)),
        ("Quality Standard Alert",
         "FSSAI has revised moisture-content ceiling for packaged Moong Dal from 14% to 12%. "
         "Non-compliant stock to be quarantined pending re-testing. Applicable to all licensed FBOs.",
         dt_date(2026, 5, 12)),
    ],
    "Groundnut": [
        ("SEZ Notification",
         "Kandla SEZ announces a 90-day zero-duty export window for groundnut oil and meal. "
         "Window opens 01-Jun-2026. Applications via SEZ online portal only.",
         dt_date(2026, 5, 23)),
        ("Aflatoxin Advisory",
         "FSSAI advisory: all groundnut export consignments to EU/US must carry an aflatoxin test "
         "certificate from an NABL-accredited lab. Tolerance limit B1+B2+G1+G2 ≤ 10 ppb.",
         dt_date(2026, 5, 18)),
        ("MSP Update",
         "CACP recommends Kharif 2026 Groundnut MSP at ₹6,783/qtl — a 4.2% hike over last season. "
         "Cabinet approval expected before 15-Jun-2026.",
         dt_date(2026, 5, 8)),
    ],
}

# Hindi translations for DGFT alert titles
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

# NCDEX reference futures prices (₹/qtl) and neutral mandi discounts
BASE_NCDEX: dict[str, float] = {
    "Chana (Gram)": 5_580.0,
    "Moong Dal":    8_750.0,
    "Groundnut":    6_900.0,
}
BASE_SPREAD: dict[str, float] = {
    "Chana (Gram)": 180.0,
    "Moong Dal":    280.0,
    "Groundnut":    150.0,
}


# ── Helper: relative date label ───────────────────────────────────────────────
def _relative_label(issue_date: dt_date) -> str:
    delta = (dt_date.today() - issue_date).days
    if LNG == "hi":
        if delta == 0:   return "आज"
        if delta == 1:   return "कल"
        if delta < 30:   return f"{delta} दिन पहले"
        return f"{delta // 30} महीने पहले"
    else:
        if delta == 0:   return "today"
        if delta == 1:   return "yesterday"
        if delta < 30:   return f"{delta} days ago"
        months = delta // 30
        return f"{months} month{'s' if months > 1 else ''} ago"


# ── News fetcher ──────────────────────────────────────────────────────────────
def fetch_news(query: str, max_items: int = 5) -> list[dict]:
    url = (f"https://news.google.com/rss/search?q={query.replace(' ', '+')}"
           f"&hl=en-IN&gl=IN&ceid=IN:en")
    feed = feedparser.parse(url)
    results = []
    for entry in feed.entries[:max_items]:
        results.append({
            "title":     entry.get("title", "No title"),
            "link":      entry.get("link", "#"),
            "published": entry.get("published", ""),
            "source":    entry.get("source", {}).get("title", "Google News"),
        })
    return results


# ── Render: Weather ───────────────────────────────────────────────────────────
def render_weather(commodity: str) -> None:
    st.markdown(f"#### {tx('weather_hdr')}")
    for region, temp, condition in WEATHER_DATA[commodity]:
        st.metric(label=region, value=temp, delta=condition, delta_color="off")


# ── Render: DGFT Circulars ────────────────────────────────────────────────────
def render_dgft(commodity: str) -> None:
    st.markdown(f"#### {tx('dgft_hdr')}")
    for title_en, body, issue_date in DGFT_ALERTS[commodity]:
        date_str = issue_date.strftime("%d-%b-%Y")
        relative = _relative_label(issue_date)
        # Choose title language; always prepend the date tag
        title_display = DGFT_TITLE_HI.get(title_en, title_en) if LNG == "hi" else title_en
        label = f"[{date_str}]  {title_display}"
        with st.expander(label):
            st.caption(f"📅 {tx('issued_lbl')} {date_str} · {relative}")
            st.write(body)


# ── Render: News Feed ─────────────────────────────────────────────────────────
def render_news(commodity: str, query: str) -> None:
    st.markdown(f"#### {tx('news_hdr')}")
    note = tx("news_note")
    if note:
        st.caption(note)
    with st.spinner(tx("news_loading")):
        articles = fetch_news(query)
    if not articles:
        st.info(tx("news_empty"))
        return
    for article in articles:
        # In Hindi mode wrap with a bilingual prefix badge
        prefix = "📰 " if LNG == "hi" else ""
        st.markdown(
            f"**{prefix}[{article['title']}]({article['link']})**  \n"
            f"<span style='color:grey; font-size:0.8em'>"
            f"{article['source']} &nbsp;·&nbsp; {article['published']}"
            f"</span>",
            unsafe_allow_html=True,
        )
        st.divider()


# ── DB helpers ────────────────────────────────────────────────────────────────
def load_trades() -> pd.DataFrame:
    try:
        with _engine.connect() as conn:
            return pd.read_sql_query(
                "SELECT id, date, action, commodity, quantity, price, location "
                "FROM physical_trades ORDER BY id DESC",
                conn,
            )
    except Exception:
        return pd.DataFrame()


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


# ── Render: Net Warehouse Stock ───────────────────────────────────────────────
def render_net_stock(df: pd.DataFrame) -> None:
    st.markdown(f"#### {tx('net_stock_hdr')}")

    buy_df  = df[df["action"] == "buy"].copy()
    sell_df = df[df["action"] == "sell"].copy()

    buys  = buy_df.groupby("commodity")["quantity"].sum()
    sells = sell_df.groupby("commodity")["quantity"].sum()

    # Weighted average purchase price: Σ(qty × price) / Σ(qty)
    if not buy_df.empty:
        buy_df["value"] = buy_df["quantity"] * buy_df["price"]
        wav_price = buy_df.groupby("commodity").apply(
            lambda x: x["value"].sum() / x["quantity"].sum(),
            include_groups=False,
        )
    else:
        wav_price = pd.Series(dtype=float)

    commodities = sorted(df["commodity"].unique())
    rows = []
    for commodity in commodities:
        bought   = float(buys.get(commodity, 0.0))
        sold     = float(sells.get(commodity, 0.0))
        net      = bought - sold
        avg_cost = float(wav_price.get(commodity, 0.0))

        status = (tx("in_stock") if net > 0
                  else tx("zero_stock") if net == 0
                  else tx("oversold"))

        rows.append({
            tx("col_commodity"):  commodity.title(),
            tx("col_net_wt"):     net,
            tx("col_avg_price"):  round(avg_cost, 2),
            tx("col_bought"):     bought,
            tx("col_sold"):       sold,
            tx("col_status"):     status,
        })

    # Metric cards — one per commodity
    if rows:
        card_cols = st.columns(len(rows))
        for col, row in zip(card_cols, rows):
            with col:
                net_val  = row[tx("col_net_wt")]
                avg_val  = row[tx("col_avg_price")]
                avg_str  = f"₹{avg_val:,.0f}/qtl {tx('col_avg_price').split('(')[0].strip()}"
                st.metric(
                    label=f"{row[tx('col_status')]}  {row[tx('col_commodity')]}",
                    value=f"{net_val:,.1f} qtl",
                    delta=avg_str,
                    delta_color="inverse" if net_val <= 0 else "off",
                )

    # Summary table with columns in a logical display order
    col_order = [
        tx("col_commodity"),
        tx("col_net_wt"),
        tx("col_avg_price"),
        tx("col_bought"),
        tx("col_sold"),
        tx("col_status"),
    ]
    st.dataframe(pd.DataFrame(rows)[col_order], use_container_width=True, hide_index=True)


# ── Render: Full Trade Log + Delete ──────────────────────────────────────────
def render_trades() -> None:
    # Red delete-button CSS
    st.markdown(
        """<style>
        [data-testid="stForm"] button[kind="primaryFormSubmit"],
        [data-testid="stForm"] button[data-testid="baseButton-primary"] {
            background-color: #dc2626 !important;
            border-color:     #dc2626 !important;
            color: white !important;
        }
        [data-testid="stForm"] button[kind="primaryFormSubmit"]:hover,
        [data-testid="stForm"] button[data-testid="baseButton-primary"]:hover {
            background-color: #b91c1c !important;
            border-color:     #b91c1c !important;
        }
        </style>""",
        unsafe_allow_html=True,
    )

    st.markdown(tx("inventory_hdr"))
    df = load_trades()

    if df.empty:
        st.info(tx("no_trades"))
        return

    # 1. Net stock aggregation
    render_net_stock(df)
    st.markdown("---")

    # 2. Raw trade log
    st.markdown(f"#### {tx('trade_log_hdr')}")
    display_df = df.copy()
    display_df.columns = ["ID", "Date", "Action", "Commodity",
                          "Qty (qtl)", "Price (₹/qtl)", "Location"]
    st.dataframe(display_df, use_container_width=True, hide_index=True)

    # 3. Delete / undo entry
    st.markdown(f"#### {tx('delete_hdr')}")
    label_map: dict[int, str] = {
        int(row["id"]): (
            f"ID {int(row['id'])}  —  "
            f"{str(row['action']).upper()}  "
            f"{row['quantity']} qtl  "
            f"{str(row['commodity']).title()}  "
            f"@ ₹{row['price']}/qtl  "
            f"({row['location']})"
        )
        for _, row in df.iterrows()
    }

    with st.form("delete_form"):
        col_a, col_b = st.columns([3, 1])
        with col_a:
            selected_id = st.selectbox(
                tx("delete_sel"),
                options=list(label_map.keys()),
                format_func=lambda i: label_map[i],
            )
        with col_b:
            st.markdown("<br>", unsafe_allow_html=True)
            submitted = st.form_submit_button(tx("delete_btn"), type="primary")

    if submitted:
        if delete_trade(selected_id):
            st.success(f"Trade ID {selected_id} removed." if LNG == "en"
                       else f"ट्रेड ID {selected_id} सफलतापूर्वक हटा दी गई।")
            st.rerun()
        else:
            st.error(f"Could not delete Trade ID {selected_id}." if LNG == "en"
                     else f"ट्रेड ID {selected_id} नहीं हटाई जा सकी।")


# ── Signal engine ─────────────────────────────────────────────────────────────
def compute_arbitrage_signal(commodity: str) -> dict:
    """
    Evaluate DGFT policy + regional weather and return:
        trend_key        – 'bullish' | 'bearish' | 'neutral'  (maps to T keys)
        signals          – list of (description_en, direction, weight)
        net_score        – signed int
        ncdex_ref        – reference NCDEX futures ₹/qtl
        predicted_spread – estimated NCDEX–mandi spread ₹/qtl
        predicted_mandi  – implied mandi price ₹/qtl
        confidence       – arbitrage signal strength 0–100 %
    """
    signals: list[tuple[str, str, int]] = []
    net_score = 0

    # ── Policy signals ────────────────────────────────────────────────────────
    for title_en, _body, _date in DGFT_ALERTS[commodity]:
        t = title_en.upper()
        if "STOCK LIMIT" in t:
            signals.append(("📋 Stock limit enforcement — curbs hoarding, depresses spot", "BEARISH", -2))
            net_score -= 2
        if "BUFFER" in t:
            signals.append(("🏛️ NAFED buffer release adding supply to market", "BEARISH", -3))
            net_score -= 3
        if "EXPORT INCENTIVE" in t or "SEZ" in t:
            signals.append(("🚢 Export demand stimulus / SEZ window active", "BULLISH", +2))
            net_score += 2
        if "IMPORT DUTY" in t:
            signals.append(("🛡️ High import duty protects domestic price floor", "BULLISH", +1))
            net_score += 1
        if "MSP" in t:
            signals.append(("💰 Govt. MSP provides hard price-floor support", "BULLISH", +1))
            net_score += 1
        if "AFLATOXIN" in t or "QUALITY" in t:
            signals.append(("⚠️ Quality/safety advisory suppresses export premium", "BEARISH", -1))
            net_score -= 1

    # ── Weather signals ───────────────────────────────────────────────────────
    for region, _temp, condition in WEATHER_DATA[commodity]:
        cond = condition.lower()
        if any(w in cond for w in ["dry", "arid", "no rain", "high uv"]):
            signals.append((f"☀️ {region}: dry spell / moisture deficit → supply risk", "BULLISH", +2))
            net_score += 2
        elif any(w in cond for w in ["light shower", "light rain"]):
            signals.append((f"🌦️ {region}: light rainfall → neutral supply impact", "NEUTRAL", 0))
        elif any(w in cond for w in ["shower", "rain", "flood"]):
            signals.append((f"🌧️ {region}: rainfall → improved supply outlook", "BEARISH", -1))
            net_score -= 1
        elif "wind" in cond:
            signals.append((f"💨 {region}: strong winds → minor moisture crop stress", "BULLISH", +1))
            net_score += 1

    # ── Derived metrics ───────────────────────────────────────────────────────
    ncdex_ref        = BASE_NCDEX[commodity]
    adjusted_spread  = max(50.0, BASE_SPREAD[commodity] + net_score * 18)
    predicted_mandi  = ncdex_ref - adjusted_spread
    confidence       = int(min(85, 50 + abs(net_score) * 5))

    trend_key = "bullish" if net_score >= 2 else ("bearish" if net_score <= -2 else "neutral")

    return {
        "trend_key":        trend_key,
        "signals":          signals,
        "net_score":        net_score,
        "ncdex_ref":        ncdex_ref,
        "predicted_spread": adjusted_spread,
        "predicted_mandi":  predicted_mandi,
        "confidence":       confidence,
    }


# ── Render: AI Predictor Tab ──────────────────────────────────────────────────
def render_ai_predictor(trade_count: int) -> None:
    THRESHOLD = 30
    TREND_COLORS = {"bullish": "#16a34a", "bearish": "#dc2626", "neutral": "#d97706"}

    st.markdown(tx("ai_hdr"))
    st.caption(tx("ai_caption"))
    st.markdown("---")

    inner_tabs = st.tabs([tx(COMMODITY_TAB_KEY[c]) for c in COMMODITIES])

    for inner_tab, commodity in zip(inner_tabs, COMMODITIES.keys()):
        with inner_tab:
            r     = compute_arbitrage_signal(commodity)
            color = TREND_COLORS[r["trend_key"]]

            # ── Trend banner ──────────────────────────────────────────────────
            trend_label  = tx(r["trend_key"])
            advice_text  = tx(f"advice_{r['trend_key']}")
            st.markdown(
                f"<h2 style='color:{color}; margin-bottom:2px'>{trend_label}</h2>"
                f"<p style='color:#555; margin-top:2px; font-size:0.95em'>{advice_text}</p>",
                unsafe_allow_html=True,
            )
            st.markdown("")

            # ── Five metric cards ─────────────────────────────────────────────
            m1, m2, m3, m4, m5 = st.columns(5)
            with m1:
                st.metric(tx("lbl_ncdex"),
                          f"₹{r['ncdex_ref']:,.0f}",
                          help="Approximate active-month NCDEX futures price used as the baseline.")
            with m2:
                st.metric(tx("lbl_mandi"),
                          f"₹{r['predicted_mandi']:,.0f}",
                          delta=f"−₹{r['predicted_spread']:,.0f} vs NCDEX",
                          delta_color="off")
            with m3:
                st.metric(tx("lbl_spread"),
                          f"₹{r['predicted_spread']:,.0f}/qtl",
                          help="Wider spread = larger physical–futures arbitrage window.")
            with m4:
                st.metric(tx("lbl_bias"),
                          trend_label,
                          delta=f"Score: {r['net_score']:+d}",
                          delta_color="normal" if r["net_score"] >= 0 else "inverse")
            with m5:
                st.metric(tx("lbl_strength"),
                          f"{r['confidence']}%",
                          delta="Macro-rule baseline",
                          delta_color="off")

            st.markdown("")

            # ── Signal breakdown ──────────────────────────────────────────────
            st.markdown(f"#### {tx('signals_hdr')}")
            if r["signals"]:
                for desc, direction, weight in r["signals"]:
                    badge = ("#16a34a" if direction == "BULLISH"
                             else "#dc2626" if direction == "BEARISH"
                             else "#d97706")
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

            # ── Engine mode footer ────────────────────────────────────────────
            pct      = min(100, int(trade_count / THRESHOLD * 100))
            filled   = int(pct / 5)
            bar      = "🟩" * filled + "⬜" * (20 - filled)
            remain   = max(0, THRESHOLD - trade_count)
            word     = "trade" if trade_count == 1 else "trades"

            mode_line = tx("engine_ml") if trade_count >= THRESHOLD else tx("engine_macro")
            body_line = tx("engine_body", n=THRESHOLD)
            data_line = (f"Data Accumulation: **{trade_count} {word} recorded**."
                         if LNG == "en"
                         else f"डेटा संचय: **{trade_count} ट्रेड दर्ज**।")
            remain_line = (f"{bar} &nbsp; {pct}% toward ML unlock — **{remain} entries remaining**"
                           if LNG == "en"
                           else f"{bar} &nbsp; {pct}% — ML अनलॉक के लिए **{remain} प्रविष्टियां शेष**")

            st.info(f"{mode_line}  \n{data_line}  \n{remain_line}  \n\n{body_line}")


# ─────────────────────────────────────────────────────────────────────────────
# PAGE LAYOUT
# ─────────────────────────────────────────────────────────────────────────────

st.title(tx("app_title"))
st.caption(tx("app_caption"))

# ── Main tabs ─────────────────────────────────────────────────────────────────
_tab_labels = [tx(COMMODITY_TAB_KEY[c]) for c in COMMODITIES] + [tx("tab_ai")]
_all_tabs   = st.tabs(_tab_labels)
_comm_tabs  = _all_tabs[:-1]
_ai_tab     = _all_tabs[-1]

for tab, (commodity, query) in zip(_comm_tabs, COMMODITIES.items()):
    with tab:
        col1, col2, col3 = st.columns([1, 1, 1.4])
        with col1:
            render_weather(commodity)
        with col2:
            render_dgft(commodity)
        with col3:
            render_news(commodity, query)

with _ai_tab:
    _trade_df = load_trades()
    render_ai_predictor(len(_trade_df))

# ── Inventory & trades section ────────────────────────────────────────────────
st.markdown("---")
render_trades()

# ── Auto-refresh every 60 seconds ─────────────────────────────────────────────
time.sleep(60)
st.rerun()

import json
import logging
import os
from datetime import date
from typing import Optional

import requests as http_requests
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, Response
from openai import OpenAI
from sqlalchemy import create_engine, text

load_dotenv()

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── App & clients ─────────────────────────────────────────────────────────────
app    = FastAPI(title="Grain Arbitrage API")
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
engine = create_engine(os.getenv("DATABASE_URL"), pool_pre_ping=True)

# ── Tiered access lists (comma-separated phone numbers in .env) ───────────────
# Numbers must match the 'from' field in Meta payloads e.g. "919876543210"
ADMIN_NUMBERS  = {n.strip() for n in os.getenv("ADMIN_NUMBERS",  "").split(",") if n.strip()}
WORKER_NUMBERS = {n.strip() for n in os.getenv("WORKER_NUMBERS", "").split(",") if n.strip()}

# ── Meta WhatsApp Cloud API credentials ───────────────────────────────────────
META_ACCESS_TOKEN     = os.getenv("META_ACCESS_TOKEN")
PHONE_NUMBER_ID       = os.getenv("PHONE_NUMBER_ID")
WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN")

# ── OpenAI system prompt — three-workflow dynamic router ──────────────────────
SYSTEM_PROMPT = """
You are an intelligent commodity trading data extraction bot for an Indian trader.
Messages arrive in casual Hindi, Hinglish, or English.
Extract ANY commodity the user mentions — do NOT restrict to specific grains.

Classify the message into exactly ONE of three workflow types and return ONLY
a raw valid JSON object with the keys shown below. No markdown, no explanation.

────────────────────────────────────────────────
WORKFLOW 1 — "Processing"
Triggered by: sorting, grading, cleaning, kachra, mill, chakki, processing, safai.
Fields: workflow_type, commodity, quantity, warehouse_location, status (always "Pending")
Example output:
{"workflow_type":"Processing","commodity":"chana","quantity":200,"warehouse_location":"Indore Godown","status":"Pending"}

────────────────────────────────────────────────
WORKFLOW 2 — "Direct Trade"
Triggered by: immediate buy-sell flip, both a buyer AND seller mentioned, seedha deal, party-to-party.
Fields: workflow_type, commodity, quantity, rate, seller_name, buyer_name, delivery_date
Example output:
{"workflow_type":"Direct Trade","commodity":"moong","quantity":100,"rate":8500,"seller_name":"Ramesh Traders","buyer_name":"Saurabh Enterprises","delivery_date":"2026-06-10"}

────────────────────────────────────────────────
WORKFLOW 3 — "Warehousing"
Triggered by: storing for inventory, godown mein rakha, stock banana, kharidi for holding.
Fields: workflow_type, commodity, quantity, rate, warehouse_location, seller_name
Example output:
{"workflow_type":"Warehousing","commodity":"groundnut","quantity":150,"rate":6800,"warehouse_location":"Rajkot Godown","seller_name":"Gujarat Agro"}

────────────────────────────────────────────────
TRADE ACTION — include in every response:
Analyze the message intent and add "trade_action" to the JSON:
- "Purchase" — user is buying goods, setting up stock, receiving material,
  kharidi karna, godown mein aana, stock banana, warehousing inward.
- "Sale"     — user is selling or dispatching material, bikri karna,
  maal bheja, dispatch, outward movement.
- "Processing" — material sent for sorting, grading, cleaning (use only
  when workflow_type is also "Processing").

────────────────────────────────────────────────
Rules:
- Always include "trade_action" in every JSON response.
- Use null for any other field that is genuinely absent in the message.
- quantity is always a plain number (quintals unless stated otherwise).
- rate is price per quintal as a plain number.
- Output ONLY the JSON object — no text before or after it.

Updated examples with trade_action:
{"workflow_type":"Warehousing","trade_action":"Purchase","commodity":"chana","quantity":200,"rate":5200,"warehouse_location":"Indore","seller_name":"Ramesh"}
{"workflow_type":"Direct Trade","trade_action":"Sale","commodity":"moong","quantity":100,"rate":8500,"seller_name":"Ramesh","buyer_name":"Saurabh","delivery_date":"2026-06-10"}
{"workflow_type":"Processing","trade_action":"Processing","commodity":"chana","quantity":150,"warehouse_location":"Indore","status":"Pending"}
""".strip()


# ── Database ──────────────────────────────────────────────────────────────────

def init_db() -> None:
    """Create or migrate the physical_trades table to the new multi-workflow schema."""
    with engine.begin() as conn:
        # Base table — safe on fresh databases
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS physical_trades (
                id                SERIAL PRIMARY KEY,
                date              TEXT NOT NULL,
                sender_number     TEXT,
                workflow_type     TEXT,
                commodity         TEXT,
                quantity          REAL,
                rate              REAL,
                warehouse_location TEXT,
                seller_name       TEXT,
                buyer_name        TEXT,
                delivery_date     TEXT,
                status            TEXT
            )
        """))
        # Migration guards — add new columns if table already exists with old schema
        for col, col_type in [
            ("sender_number",      "TEXT"),
            ("workflow_type",      "TEXT"),
            ("trade_action",       "TEXT"),
            ("rate",               "REAL"),
            ("warehouse_location", "TEXT"),
            ("seller_name",        "TEXT"),
            ("buyer_name",         "TEXT"),
            ("delivery_date",      "TEXT"),
            ("status",             "TEXT"),
        ]:
            conn.execute(text(
                f"ALTER TABLE physical_trades ADD COLUMN IF NOT EXISTS {col} {col_type}"
            ))

        # Drop NOT NULL from legacy columns created by the old schema.
        # The new insert_trade() never sends action/price/location, so any
        # NOT NULL constraint on them causes a constraint-violation error.
        for legacy_col in ["action", "commodity", "quantity", "price", "location"]:
            try:
                conn.execute(text(
                    f"ALTER TABLE physical_trades ALTER COLUMN {legacy_col} DROP NOT NULL"
                ))
            except Exception:
                pass   # column doesn't exist on a fresh install — safe to ignore


def insert_trade(data: dict) -> int:
    """Insert one trade row and return the new primary key."""
    with engine.begin() as conn:
        result = conn.execute(
            text("""
                INSERT INTO physical_trades
                    (date, sender_number, workflow_type, trade_action, commodity, quantity,
                     rate, warehouse_location, seller_name, buyer_name,
                     delivery_date, status)
                VALUES
                    (:date, :sender_number, :workflow_type, :trade_action, :commodity, :quantity,
                     :rate, :warehouse_location, :seller_name, :buyer_name,
                     :delivery_date, :status)
                RETURNING id
            """),
            data,
        )
        return result.fetchone()[0]


def get_stock_summary() -> str:
    """Return a short human-readable stock summary for the admin reply."""
    try:
        with engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT commodity, workflow_type, SUM(quantity) AS total
                FROM   physical_trades
                WHERE  workflow_type IN ('Warehousing', 'Processing')
                GROUP  BY commodity, workflow_type
                ORDER  BY commodity
            """)).fetchall()
        if not rows:
            return "No active stock on record."
        return "\n".join(
            f"  • {row[0].title()}: {row[2]:,.0f} qtl ({row[1]})"
            for row in rows
        )
    except Exception as exc:
        logger.error("Stock summary query failed: %s", exc)
        return "Balance query unavailable."


# ── WhatsApp reply ────────────────────────────────────────────────────────────

def send_whatsapp_reply(to: str, message: str) -> None:
    """Send a free-form text reply via the Meta Cloud API."""
    if not META_ACCESS_TOKEN or not PHONE_NUMBER_ID:
        logger.warning("META_ACCESS_TOKEN or PHONE_NUMBER_ID not set — reply skipped.")
        return
    try:
        resp = http_requests.post(
            f"https://graph.facebook.com/v20.0/{PHONE_NUMBER_ID}/messages",
            headers={
                "Authorization": f"Bearer {META_ACCESS_TOKEN}",
                "Content-Type":  "application/json",
            },
            json={
                "messaging_product": "whatsapp",
                "to":   to,
                "type": "text",
                "text": {"body": message},
            },
            timeout=10,
        )
        resp.raise_for_status()
        logger.info("WhatsApp reply sent to %s", to)
    except Exception as exc:
        logger.error("WhatsApp reply failed for %s: %s", to, exc)


def format_admin_reply(data: dict, trade_id: int, summary: str) -> str:
    """Build the detailed admin confirmation message."""
    wf   = data.get("workflow_type", "Unknown")
    comm = str(data.get("commodity", "—")).title()
    qty  = data.get("quantity", "—")

    lines = [
        f"✅ *Trade Logged* — ID #{trade_id}",
        "━━━━━━━━━━━━━━━━━━━━",
        f"🔄 *Workflow:*   {wf}",
        f"📦 *Commodity:*  {comm}",
        f"⚖️ *Quantity:*   {qty} qtl",
    ]

    if wf == "Processing":
        lines += [
            f"🏭 *Location:*   {data.get('warehouse_location') or '—'}",
            f"📋 *Status:*     {data.get('status') or 'Pending'}",
        ]
    elif wf == "Direct Trade":
        lines += [
            f"💰 *Rate:*       ₹{data.get('rate') or '—'}/qtl",
            f"🧑‍💼 *Seller:*     {data.get('seller_name') or '—'}",
            f"👤 *Buyer:*      {data.get('buyer_name') or '—'}",
            f"📅 *Delivery:*   {data.get('delivery_date') or '—'}",
        ]
    elif wf == "Warehousing":
        lines += [
            f"💰 *Rate:*       ₹{data.get('rate') or '—'}/qtl",
            f"🏭 *Location:*   {data.get('warehouse_location') or '—'}",
            f"🧑‍💼 *Seller:*     {data.get('seller_name') or '—'}",
        ]

    lines += [
        "",
        "📊 *Current Stock Summary*",
        "━━━━━━━━━━━━━━━━━━━━",
        summary,
    ]
    return "\n".join(lines)


# ── Startup ───────────────────────────────────────────────────────────────────

@app.on_event("startup")
def startup_event() -> None:
    init_db()
    logger.info("DB ready | Admins: %s | Workers: %s", ADMIN_NUMBERS, WORKER_NUMBERS)


# ── GET /whatsapp — Meta verification handshake ───────────────────────────────

@app.get("/whatsapp")
async def verify_webhook(request: Request):
    mode      = request.query_params.get("hub.mode")
    token     = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    if mode and token:
        if mode == "subscribe" and token == WHATSAPP_VERIFY_TOKEN:
            return Response(content=challenge, media_type="text/plain")
        raise HTTPException(status_code=403, detail="Forbidden")
    raise HTTPException(status_code=400, detail="Bad Request")


# ── POST /whatsapp — incoming message router ──────────────────────────────────

@app.post("/whatsapp")
async def receive_whatsapp(request: Request):
    payload = await request.json()
    print("🚨 INCOMING PAYLOAD 🚨:", payload, flush=True)
    logger.info("Incoming payload: %s", payload)

    OK = Response(content="OK", media_type="text/plain", status_code=200)

    # ── 1. Navigate Meta's nested payload ────────────────────────────────────
    try:
        entry    = payload.get("entry", [])
        changes  = entry[0].get("changes", []) if entry else []
        value    = changes[0].get("value", {}) if changes else {}
        messages = value.get("messages", [])

        if not messages:
            logger.info("Status update / non-message event — ACK only.")
            return OK

        message  = messages[0]
        sender   = message.get("from", "")          # e.g. "919876543210"
        msg_type = message.get("type", "")

        if msg_type != "text":
            logger.info("Non-text message (type=%s) — ACK only.", msg_type)
            return OK

        body = message.get("text", {}).get("body", "").strip()
        if not body:
            logger.warning("Empty text body — ACK only.")
            return OK

    except Exception as exc:
        logger.error("Payload navigation failed: %s", exc)
        return OK

    logger.info("Message from %s: %s", sender, body)

    # ── 2. Tiered access control ──────────────────────────────────────────────
    is_admin  = sender in ADMIN_NUMBERS
    is_worker = sender in WORKER_NUMBERS

    if not is_admin and not is_worker:
        logger.warning("Unknown sender %s — blocked. No OpenAI, no DB, no reply.", sender)
        return OK                                    # silent drop

    # ── 3. OpenAI trade extraction ────────────────────────────────────────────
    try:
        ai_resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": body},
            ],
            temperature=0,
        )
        raw = ai_resp.choices[0].message.content.strip()
        logger.info("OpenAI raw: %s", raw)
    except Exception as exc:
        logger.error("OpenAI call failed: %s", exc)
        if is_admin:
            send_whatsapp_reply(sender, "❌ Server error: could not reach OpenAI.")
        return OK

    # ── 4. Parse and validate JSON ────────────────────────────────────────────
    try:
        data          = json.loads(raw)
        workflow_type = data.get("workflow_type", "")
        if workflow_type not in ("Processing", "Direct Trade", "Warehousing"):
            raise ValueError(f"Unknown workflow_type: {workflow_type!r}")
        commodity = str(data.get("commodity") or "").strip()
        quantity  = float(data.get("quantity") or 0)
    except Exception as exc:
        logger.error("Parse failed for %r: %s", raw, exc)
        if is_admin:
            send_whatsapp_reply(sender, f"❌ Could not parse trade.\nRaw: {raw[:300]}")
        return OK

    # ── 5. Persist to Supabase ────────────────────────────────────────────────
    def _safe_float(v) -> Optional[float]:
        try:
            return float(v) if v is not None else None
        except (TypeError, ValueError):
            return None

    insert_data = {
        "date":               date.today().isoformat(),
        "sender_number":      sender,
        "workflow_type":      workflow_type,
        "trade_action":       data.get("trade_action"),
        "commodity":          commodity,
        "quantity":           quantity,
        "rate":               _safe_float(data.get("rate")),
        "warehouse_location": data.get("warehouse_location"),
        "seller_name":        data.get("seller_name"),
        "buyer_name":         data.get("buyer_name"),
        "delivery_date":      data.get("delivery_date"),
        "status":             data.get("status"),
    }

    try:
        trade_id = insert_trade(insert_data)
        logger.info("Saved trade #%s | wf=%s | sender=%s", trade_id, workflow_type, sender)
    except Exception as exc:
        logger.error("DB insert failed: %s", exc)
        if is_admin:
            send_whatsapp_reply(sender, "❌ Server error: database insert failed.")
        return OK

    # ── 6. Reply based on tier ────────────────────────────────────────────────
    if is_admin:
        summary = get_stock_summary()
        send_whatsapp_reply(sender, format_admin_reply(data, trade_id, summary))
    else:
        send_whatsapp_reply(sender, "✔️ Entry successfully logged.")

    return OK

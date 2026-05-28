import json
import logging
import os
from datetime import date

from dotenv import load_dotenv
from fastapi import FastAPI, Form, HTTPException, Request, Response
from fastapi.responses import PlainTextResponse
from openai import OpenAI
from sqlalchemy import create_engine, text

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Grain Arbitrage API")
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

DATABASE_URL        = os.getenv("DATABASE_URL")
WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN")
engine = create_engine(DATABASE_URL, pool_pre_ping=True)

SYSTEM_PROMPT = (
    "You are a data extraction bot for an Indian grain trader. "
    "The user will send messages in casual Hindi or Hinglish about physical grain trades. "
    "Extract: action (must be exactly \"buy\" or \"sell\"), commodity (e.g., chana, moong, groundnut), "
    "quantity_quintals, price_per_quintal, and location. "
    "Output ONLY a raw valid JSON object matching these keys. "
    "Do not write any conversational text or formatting outside the JSON."
)


def init_db() -> None:
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS physical_trades (
                id        SERIAL PRIMARY KEY,
                date      TEXT   NOT NULL,
                action    TEXT   NOT NULL,
                commodity TEXT   NOT NULL,
                quantity  REAL   NOT NULL,
                price     REAL   NOT NULL,
                location  TEXT   NOT NULL
            )
        """))


def insert_trade(action: str, commodity: str, quantity: float, price: float, location: str) -> int:
    with engine.begin() as conn:
        result = conn.execute(
            text(
                "INSERT INTO physical_trades (date, action, commodity, quantity, price, location) "
                "VALUES (:date, :action, :commodity, :quantity, :price, :location) "
                "RETURNING id"
            ),
            {
                "date":      date.today().isoformat(),
                "action":    action,
                "commodity": commodity,
                "quantity":  quantity,
                "price":     price,
                "location":  location,
            },
        )
        return result.fetchone()[0]


@app.on_event("startup")
def startup_event() -> None:
    init_db()
    logger.info("Database initialised — connected to PostgreSQL via DATABASE_URL")


@app.get("/whatsapp")
async def verify_webhook(request: Request):
    mode      = request.query_params.get("hub.mode")
    token     = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    if mode and token:
        if mode == "subscribe" and token == os.getenv("WHATSAPP_VERIFY_TOKEN"):
            return Response(content=challenge, media_type="text/plain")
        raise HTTPException(status_code=403, detail="Forbidden")
    raise HTTPException(status_code=400, detail="Bad Request")


@app.post("/whatsapp", response_class=PlainTextResponse)
async def whatsapp_webhook(Body: str = Form(...)) -> str:
    logger.info("Received WhatsApp message: %s", Body)

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": Body},
            ],
            temperature=0,
        )
        raw = response.choices[0].message.content.strip()
        logger.info("OpenAI response: %s", raw)
    except Exception as exc:
        logger.error("OpenAI API call failed: %s", exc)
        return "Error: could not reach OpenAI."

    try:
        data = json.loads(raw)
        action = str(data["action"]).lower()
        if action not in ("buy", "sell"):
            raise ValueError(f"Invalid action value: {action!r}")
        commodity = str(data["commodity"])
        quantity = float(data["quantity_quintals"])
        price = float(data["price_per_quintal"])
        location = str(data["location"])
    except (json.JSONDecodeError, KeyError, ValueError, TypeError) as exc:
        logger.error("Failed to parse trade from OpenAI response %r: %s", raw, exc)
        return "Error: could not extract trade details from message."

    try:
        trade_id = insert_trade(action, commodity, quantity, price, location)
        logger.info("Inserted trade id=%s", trade_id)
    except Exception as exc:
        logger.error("Database insert failed: %s", exc)
        return "Error: could not save trade to database."

    return (
        f"Trade recorded (id={trade_id}): {action.upper()} {quantity} qtl of {commodity} "
        f"@ ₹{price}/qtl in {location}."
    )

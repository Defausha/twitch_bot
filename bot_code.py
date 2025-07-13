import os
import asyncio
import sqlite3
from datetime import datetime
from typing import List
from fastapi import FastAPI, HTTPException, Header, Depends, Request
from pydantic import BaseModel
from dotenv import load_dotenv
from twitchio.ext import commands
import logging
import sys

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler("ban_log.txt", encoding="utf-8"),
        logging.StreamHandler()
    ],
    level=logging.INFO
)

DB_PATH = "bot_data.db"

# DB инициализация
LOCK_FILE = "bot.lock"

if os.path.exists(LOCK_FILE):
    logging.critical("🔒 'bot.lock' detected — another instance may already be running. Shutting down.")
    raise SystemExit("Lock file exists. Bot is already running.")

import atexit

def remove_lock():
    if os.path.exists(LOCK_FILE):
        os.remove(LOCK_FILE)
        logging.info("Lock released.")

atexit.register(remove_lock)

with open(LOCK_FILE, "w") as f:
    f.write(str(os.getpid()))

def init_db():
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS warnings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    time TEXT NOT NULL
                )
            ''')
            conn.commit()
        logging.debug("Database initialized successfully.")
    except Exception as e:
        logging.critical(f"Failed to initialize database: {e}")

init_db()

load_dotenv()
TWITCH_TOKEN = os.getenv("TWITCH_OAUTH_TOKEN", "").strip()
TWITCH_CHANNEL = os.getenv("TWITCH_CHANNEL", "").strip()
API_TOKEN = os.getenv("API_TOKEN", "").strip()
TWITCH_PREFIX = os.getenv("TWITCH_PREFIX", "!")

if not TWITCH_TOKEN:
    logging.critical("TWITCH_OAUTH_TOKEN is missing.")
    raise ValueError("TWITCH_OAUTH_TOKEN missing")
if not TWITCH_CHANNEL:
    logging.critical("TWITCH_CHANNEL is missing.")
    raise ValueError("TWITCH_CHANNEL missing")
if not API_TOKEN:
    logging.critical("API_TOKEN is missing.")
    raise ValueError("API_TOKEN missing")

bot = commands.Bot(token=TWITCH_TOKEN, prefix=TWITCH_PREFIX, initial_channels=[TWITCH_CHANNEL])
app = FastAPI()
pending_bans = {}

class Warning(BaseModel):
    user: str
    reason: str
    time: str

class NewWarning(BaseModel):
    user: str
    reason: str

def log_ban_action(user, moderator, action):
    logging.info(f"{moderator} — {action} for user {user}")

@bot.event()
async def event_ready():
    logging.info(f"[Twitch] Бот запущен как {bot.nick}")

@bot.event()
async def event_join(channel, user):
    if user.name.lower() in ["nightbot", "streamelements"]:
        return
    await channel.send(
        f"🌟 Welcome, {user.name}, traveler of distant lands! "
        f"To avoid curses and chaos, whisper !rules to reveal the sacred laws of our realm."
    )

@app.middleware("http")
async def log_api_requests(request: Request, call_next):
    ip = request.client.host
    path = request.url.path
    token = request.headers.get("x-token", "<no token>")
    logging.info(f"[API] Request to {path} from IP {ip}, token={token}")
    response = await call_next(request)
    return response

def verify_token(x_token: str = Header(...)):
    if x_token != API_TOKEN:
        logging.warning(f"Invalid API token attempt: {x_token}")
        raise HTTPException(status_code=403, detail="Неверный токен")

@bot.command(name="warncount")
async def warn_count(ctx):
    log_ban_action("-", ctx.author.name, "warncount request")
    if "moderator" not in ctx.author.badges and "broadcaster" not in ctx.author.badges:
        return
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM warnings")
            total = cursor.fetchone()[0]
        await ctx.send(f"📊 Total warnings in the database: {total}")
    except Exception as e:
        logging.error(f"Failed to fetch warning count: {e}")
        await ctx.send("⚠️ Unable to retrieve warning count at the moment.")

@bot.command(name="serverstatus")
async def server_status(ctx):
    if "moderator" not in ctx.author.badges and "broadcaster" not in ctx.author.badges:
        return
    await ctx.send("✅ Bot and API are operating normally")

@bot.command(name="warnlist")
async def warn_list(ctx):
    log_ban_action("-", ctx.author.name, f"warnlist request: {ctx.message.content.strip()}")
    if not ctx.author.is_mod:
        return
    parts = ctx.message.content.strip().split()
    if len(parts) < 2:
        await ctx.send("⚠️ Please specify a username: !warnlist <name>")
        return
    target_user = parts[1].lower()
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT reason, time FROM warnings WHERE user = ? ORDER BY time DESC LIMIT 2", (target_user,))
            rows = cursor.fetchall()
            cursor.execute("SELECT COUNT(*) FROM warnings WHERE user = ?", (target_user,))
            total_count = cursor.fetchone()[0]
    except Exception as e:
        logging.error(f"Failed to fetch warnings for {target_user}: {e}")
        await ctx.send(f"⚠️ Could not retrieve warnings for {target_user}.")
        return

    if not rows:
        await ctx.send(f"🪽 {target_user} walks with a clean soul. No warnings found.")
        return
    for reason, time in rows:
        msg = f"⚠️ {target_user} — {reason} ({time})"
        if len(msg) > 450:
            msg = msg[:447] + "..."
        await ctx.send(msg)
    if total_count >= 3 and target_user not in pending_bans:
        await ctx.send(f"⚔️ {target_user} has earned their third strike. Use !confirmban {target_user} to exile them from the realm (2-minute window).")
        pending_bans[target_user] = {
            "initiator": ctx.author.name,
            "channel": ctx.channel
        }
        log_ban_action(target_user, ctx.author.name, "запрос на бан")
        async def remove_after_timeout():
            await asyncio.sleep(120)
            if target_user in pending_bans:
                del pending_bans[target_user]
                await ctx.send(f"⏳ The ban rite for {target_user} has expired. It shall be invoked again after 10 minutes.")
                log_ban_action(target_user, ctx.author.name, "ban request expired without confirmation")
                await asyncio.sleep(600)
                await ctx.send(f"🔁 You may now use !warnlist {target_user} again to reinitiate the ban request.")
        asyncio.create_task(remove_after_timeout())

@app.get("/api/warnings/{user}", response_model=List[Warning])
def get_user_warnings(user: str, token: None = Depends(verify_token)):
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT user, reason, time FROM warnings WHERE user = ?", (user,))
            rows = cursor.fetchall()
    except Exception as e:
        logging.error(f"Failed to retrieve warnings for API user '{user}': {e}")
        raise HTTPException(status_code=500, detail="Database error while retrieving warnings.")

    if not rows:
        raise HTTPException(status_code=404, detail="No warnings found for this user.")
    return [{"user": u, "reason": r, "time": t} for u, r, t in rows]

@app.post("/api/warnings", status_code=201)
def add_warning(w: NewWarning, token: None = Depends(verify_token)):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO warnings (user, reason, time) VALUES (?, ?, ?)", (w.user, w.reason, now))
            new_id = cursor.lastrowid
            conn.commit()
        return {"message": "Warning has been recorded.", "id": new_id}
    except Exception as e:
        logging.error(f"Failed to add warning for user '{w.user}': {e}")
        raise HTTPException(status_code=500, detail="Failed to add warning.")

@app.delete("/api/warnings/{user}", status_code=200)
def delete_user_warnings(user: str, token: None = Depends(verify_token)):
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM warnings WHERE user = ?", (user,))
            changes = conn.total_changes
            conn.commit()
    except Exception as e:
        logging.error(f"Failed to delete warnings for user '{user}': {e}")
        raise HTTPException(status_code=500, detail="Database error while deleting warnings.")

    if changes == 0:
        raise HTTPException(status_code=404, detail="No warnings were removed — nothing found.")
    return {"message": f"{changes} warnings have been removed."}

async def run_single_bot():
    loop = asyncio.get_event_loop()
    loop.create_task(bot.start())
    import uvicorn
    config = uvicorn.Config(app, host="0.0.0.0", port=8000, loop="asyncio", log_level="info")
    server = uvicorn.Server(config)
    await server.serve()

@bot.command(name="hello")
async def hello(ctx):
    if ctx.author.name.lower() in ["nightbot", "streamelements"]:
        return
    await ctx.send(f"👋 Welcome to the chat, {ctx.author.name}!")

@bot.command(name="rules")
async def show_rules(ctx):
    rules_list = [
        "📜 The Laws of the Realm:",
        "1️⃣ Speak with kindness and courtesy, lest the spirits grow restless.",
        "2️⃣ Refrain from spamming — echoes are heard, but not welcomed.",
        "3️⃣ Stay true to the quest — stray talk clouds the path.",
        "4️⃣ Share no spoilers — let each traveler discover their fate.",
        "5️⃣ Heed the words of the Seer (moderators) and the Streamkeeper.",
        "6️⃣ Keep your sword sheathed — respect is the shield of the wise."
    ]
    for rule in rules_list:
        await ctx.send(rule)

if __name__ == "__main__":
    import threading
    import uvicorn

    def start_api():
        uvicorn.run("bot_code:app", host="0.0.0.0", port=8000, log_level="info")

    # Запускаем API в отдельном потоке
    api_thread = threading.Thread(target=start_api, daemon=True)
    api_thread.start()

    # Запускаем TwitchIO-бота в основном потоке
    bot.run()

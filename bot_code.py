import asyncio
import os
import json
from datetime import datetime, timedelta
from twitchio.ext import commands
from dotenv import load_dotenv

# --- Загрузка переменных из .env ---
load_dotenv()
TOKEN = os.getenv("TWITCH_OAUTH_TOKEN", "")
CHANNEL = os.getenv("TWITCH_CHANNEL", "")
PREFIX = os.getenv("TWITCH_PREFIX", "!")
MAX_RESTARTS = int(os.getenv("MAX_RESTARTS", 5))

# --- Проверка наличия обязательных параметров ---
if not TOKEN or not CHANNEL:
    print("❌ Не указан токен или канал в .env.")
    exit(1)

# --- Пути к файлам ---
WARNINGS_FILE = "warnings.json"
SETTINGS_FILE = "bot_settings.json"
WELCOMED_FILE = "welcomed.json"

# --- Убедимся, что JSON-файлы существуют ---
def ensure_file(filepath, default_data):
    if not os.path.exists(filepath):
        try:
            with open(filepath, "w") as f:
                json.dump(default_data, f, indent=4)
            print(f"[INFO] Создан файл: {filepath}")
        except Exception as e:
            print(f"❌ Не удалось создать файл {filepath}: {e}")

ensure_file(WARNINGS_FILE, {})
ensure_file(WELCOMED_FILE, {})
ensure_file(SETTINGS_FILE, {"autoclear_days": 30, "notify_autoclear": True})

# --- Логгирование ---
def log_event(message, file="bot_events.log"):
    try:
        with open(file, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now()} - {message}\n")
    except Exception as e:
        print(f"Ошибка при логировании: {e}")

def log_error(message):
    log_event(message, file="bot_errors.log")

# --- Работа с файлами JSON ---
class JsonStorage:
    def __init__(self, filepath, default):
        self.filepath = filepath
        self.default = default
        self.data = self.load()

    def load(self):
        try:
            if os.path.exists(self.filepath):
                with open(self.filepath, "r") as f:
                    return json.load(f)
        except Exception as e:
            log_error(f"Ошибка загрузки {self.filepath}: {e}")
        return self.default.copy()

    def save(self):
        try:
            with open(self.filepath, "w") as f:
                json.dump(self.data, f, indent=4)
        except Exception as e:
            log_error(f"Ошибка сохранения {self.filepath}: {e}")

    def get(self):
        return self.data

    def set(self, new_data):
        self.data = new_data
        self.save()

def save_json(data, filepath):
    try:
        with open(filepath, "w") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        log_error(f"Ошибка сохранения {filepath}: {e}")

# --- Загрузка данных ---
warnings_store = JsonStorage(WARNINGS_FILE, {})
settings_store = JsonStorage(SETTINGS_FILE, {"autoclear_days": 30, "notify_autoclear": True})
welcomed_store = JsonStorage(WELCOMED_FILE, {})
warnings = warnings_store.get()
settings = settings_store.get()
welcomed = welcomed_store.get()

# --- Сохранение welcomed с автоочисткой ---
def save_welcomed():
    now = datetime.now()
    to_remove = []
    for user, time in welcomed.items():
        try:
            parsed_time = datetime.strptime(time, "%Y-%m-%d %H:%M:%S")
            if (now - parsed_time).days > 90:
                to_remove.append(user)
        except Exception as e:
            log_error(f"Ошибка даты welcomed {user}: {e}")
            to_remove.append(user)
    for user in to_remove:
        del welcomed[user]
    welcomed_store.set(welcomed)

# --- Автоочистка предупреждений ---
async def auto_clear_warnings(bot):
    while True:
        await asyncio.sleep(86400)
        now = datetime.now()
        days = settings.get("autoclear_days", 30)

        for user in list(warnings.keys()):
            try:
                warnings[user] = [
                    w for w in warnings[user]
                    if (now - datetime.strptime(w['time'], "%Y-%m-%d %H:%M:%S")) < timedelta(days=days)
                ]
                if not warnings[user]:
                    del warnings[user]
            except Exception as e:
                log_error(f"Ошибка автоочистки {user}: {e}")

        warnings_store.set(warnings)
        log_event("🔄 Автоочистка завершена.")
        print("🔄 Автоочистка завершена.")

        if settings.get("notify_autoclear") and CHANNEL:
            try:
                channel = bot.get_channel(CHANNEL)
                if channel:
                    await channel.send("🔄 Автоочистка завершена.")
            except Exception as e:
                log_error(f"Ошибка отправки уведомления: {e}")

# --- Запуск бота ---
async def run_single_bot():
    bot = commands.Bot(token=TOKEN, prefix=PREFIX, initial_channels=[CHANNEL])

    @bot.event # type: ignore
    async def event_ready():
        print(f"✅ Бот готов как {bot.nick}")
        print(f"🎮 Канал: {CHANNEL}")
        print(f"🔣 Префикс команд: {PREFIX}")
        asyncio.create_task(auto_clear_warnings(bot))

    @bot.event # type: ignore
    async def event_message(message):
        if message.echo:
            print(f"[DEBUG] Пропущено echo-сообщение от {message.author.name}")
            return
        if message.author.name.lower() == bot.nick.lower():
            print(f"[DEBUG] Пропущено сообщение от самого бота: {message.author.name}")
            return

        print(f"[DEBUG] Принято сообщение от {message.author.name}: {message.content}")
        await bot.handle_commands(message)

        username = message.author.name.lower()
        now = datetime.now()
        last_seen_str = welcomed.get(username)

        try:
            if not last_seen_str:
                await message.channel.send(f"Welcome, @{username}! It's nice to meet you! Have a snack 🍩")
            else:
                last_seen = datetime.strptime(last_seen_str, "%Y-%m-%d %H:%M:%S")
                days_since = (now - last_seen).days
                if days_since > 30:
                    await message.channel.send(f"@{username}, it's really you?! Long time no see, friend! Welcome back!")
                elif days_since > 7:
                    await message.channel.send(f"Oh hi! It's been awhile, @{username}! Thanks for coming")
                else:
                    await message.channel.send(f"Hi there @{username}! Thanks for coming")
        except Exception as e:
            log_error(f"Ошибка приветствия {username}: {e}")
            await message.channel.send(f"Hi @{username}!")

        welcomed[username] = now.strftime("%Y-%m-%d %H:%M:%S")
        save_welcomed()

    # --- Команды ---
    @bot.command(name="ping")
    async def ping(ctx):
        await ctx.send("🏓 Pong!")

    @bot.command(name="rules")
    async def rules(ctx):
        rules_parts = [
            """1. Please enjoy the stream with courtesy
Be respectful and use polite language toward both the streamer and other viewers.""",
            """2. Avoid spam or excessive repeated messages
Please refrain from posting the same comment repeatedly or sending meaningless messages in quick succession.""",
            """3. Keep off-topic discussions to a minimum
Excessive comments unrelated to the stream may disturb others, so please be considerate.""",
            """4. No spoilers, please
Avoid sharing spoilers about games, movies, or anime, as it may ruin the experience for others.""",
            """5. Follow the instructions of moderators and the streamer
To ensure smooth stream management, please follow any directions given by the streamer or moderators.""",
            """6. Maintain polite behavior
Always treat others with respect and speak kindly."""
        ]
        for part in rules_parts:
            await ctx.send(part)
            await asyncio.sleep(1)

    @bot.command(name="socials")
    async def socials(ctx):
        await ctx.send("🔗 Наши соцсети: Twitter — https://x.com/DefaulT20307939 | Discord — https://discord.gg/ae4XJ7Nu")

    def parse_username(content):
        parts = content.split()
        return parts[1].lstrip("@") if len(parts) > 1 else None

    @bot.command(name="warn")
    async def warn(ctx):
        try:
            if not ctx.author.is_mod:
                return
            user = parse_username(ctx.message.content)
            parts = ctx.message.content.split(maxsplit=2)
            if not user or len(parts) < 3:
                await ctx.send("⚠️ Используй: !warn <user> причина")
                return
            reason = parts[2]
            time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            warnings.setdefault(user, []).append({"reason": reason, "time": time_str})
            warnings_store.set(warnings)
            await ctx.send(f"⚠️ Пользователю @{user} выдано предупреждение: {reason}")
            log_event(f"{ctx.author.name} → warn @{user}: {reason}")
        except Exception as e:
            log_error(f"Ошибка команды warn: {e}")

    @bot.command(name="warnings")
    async def show_warnings(ctx):
        try:
            user = parse_username(ctx.message.content)
            if not user:
                await ctx.send("ℹ️ Используй: !warnings <user>")
                return
            user_warnings = warnings.get(user)
            if not user_warnings:
                await ctx.send(f"✅ У @{user} нет предупреждений.")
            else:
                msg = f"⚠️ Предупреждения для @{user}:"
                messages = []
                for i, w in enumerate(user_warnings, 1):
                    entry = f"{i}. {w['reason']} ({w['time']})"
                    if len(msg + '\n' + entry) > 450:
                        messages.append(msg)
                        msg = entry
                    else:
                        msg += f"\n{entry}"
                messages.append(msg)
                for part in messages:
                    await ctx.send(part)
                    await asyncio.sleep(1)
        except Exception as e:
            log_error(f"Ошибка команды warnings: {e}")

    @bot.command(name="clearwarnings")
    async def clear_warnings(ctx):
        try:
            if not ctx.author.is_mod:
                return
            user = parse_username(ctx.message.content)
            if not user:
                await ctx.send("🧹 Используй: !clearwarnings <user>")
                return
            if user in warnings:
                del warnings[user]
                warnings_store.set(warnings)
                await ctx.send(f"🧹 Предупреждения для @{user} удалены.")
                log_event(f"{ctx.author.name} → clearwarnings @{user}")
            else:
                await ctx.send(f"✅ У @{user} и так нет предупреждений.")
        except Exception as e:
            log_error(f"Ошибка команды clearwarnings: {e}")

    @bot.command(name="help")
    async def help_command(ctx):
        try:
            if not ctx.author.is_mod:
                return
            help_lines = [
                "📘 Список команд:",
                "!ping — Проверка ответа",
                "!rules — Правила чата",
                "!socials — Ссылки на соцсети",
                "!warn @user причина — Выдать предупреждение (модератор)",
                "!warnings @user — Показать предупреждения",
                "!clearwarnings @user — Удалить предупреждения (модератор)",
                "!help — Список всех команд"
            ]
            current_msg = ""
            for line in help_lines:
                if len(current_msg) + len(line) + 1 > 450:
                    await ctx.send(current_msg)
                    current_msg = ""
                current_msg += line + "\n"
            if current_msg:
                await ctx.send(current_msg)
        except Exception as e:
            log_error(f"Ошибка команды help: {e}")

    await bot.start()

# --- Запуск с автоперезапуском ---
async def run_bot_with_restarts():
    attempts = 0
    while attempts < MAX_RESTARTS:
        try:
            await run_single_bot()
        except Exception as e:
            print(f"⚠️ Ошибка: {e}. Перезапуск через 5 секунд.")
            log_error(f"Перезапуск после ошибки: {e}")
            attempts += 1
            await asyncio.sleep(5)
        else:
            break
    if attempts >= MAX_RESTARTS:
        final_msg = "❌ Бот завершил работу после максимального количества попыток."
        print(final_msg)
        log_error(final_msg)

# --- Точка входа ---
if __name__ == "__main__":
    print("[DEBUG] Запуск Twitch-бота...")
    asyncio.run(run_bot_with_restarts())

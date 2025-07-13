# # 🧙‍♂️ Twitch Fantasy Bot + REST API

This is a fantasy-styled Twitch moderation bot with REST API support for warnings and bans.

---

## 🔧 Technologies Used

* Python 3.10+
* TwitchIO (chat bot)
* FastAPI (REST API)
* SQLite (persistent storage)
* dotenv (config)

---

## ⚙️ Bot Commands

| Command              | Description                                                          |
| -------------------- | -------------------------------------------------------------------- |
| `!hello`             | Sends a warm welcome to the user.                                    |
| `!rules`             | Shows rules in a fantasy roleplay style.                             |
| `!warncount`         | Displays total warnings in the database. *(moderators only)*         |
| `!warnlist <user>`   | Shows 2 recent warnings. Prompts for ban on 3rd. *(moderators only)* |
| `!confirmban <user>` | Confirms permanent ban after 3 warnings. *(moderators only)*         |
| `!serverstatus`      | Displays current bot and API status. *(moderators only)*             |
| `!apiinfo`           | Shows API documentation link. *(moderators only)*                    |

---

## 🔒 Ban Logic

* On 3 warnings, bot requests ban confirmation.
* If not confirmed in 2 minutes, request expires.
* Ban request repeats in 10 minutes if unresolved.

---

## 📡 REST API (secured with token)

| Method   | Endpoint               | Description                    |
| -------- | ---------------------- | ------------------------------ |
| `GET`    | `/api/warnings/{user}` | Get all warnings for a user    |
| `POST`   | `/api/warnings`        | Add a new warning              |
| `DELETE` | `/api/warnings/{user}` | Remove all warnings for a user |

> Requires `x-token` header with valid `API_TOKEN`.

Swagger UI available at:

```
http://localhost:8000/docs
```

---

## 📁 Log Files

| File          | Purpose                                          |
| ------------- | ------------------------------------------------ |
| `ban_log.txt` | Tracks warnings, ban requests, and confirmations |
| `api_log.txt` | Records all REST API access events               |

---

## 🚀 Running the Bot (on Windows)

### 1. Create `.env` file

```
TWITCH_OAUTH_TOKEN=your_token_here
TWITCH_CHANNEL=your_channel
TWITCH_PREFIX=!
API_TOKEN=your_api_token
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Start the bot

```bash
python bot.py
```

---

## 🏹 The Realm is Watching

This bot was built for immersive community moderation with a dash of fantasy lore. Long live the realm!

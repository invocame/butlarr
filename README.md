# Butlarr

## Requirements

- Docker and Docker Compose installed on your machine
- A Telegram bot (see below for how to create one)
- Sonarr and/or Radarr already running and reachable from the machine where Butlarr will run

---

## 1. Create a Telegram bot

1. Open Telegram and search for **@BotFather**
2. Send the command `/newbot`
3. Follow the instructions: choose a name and a username for your bot
4. BotFather will reply with a **token** — save it, you'll need it shortly

---

## 2. Find your Telegram ID

Butlarr uses a whitelist of IDs to decide who can interact with it. Only IDs in the list will receive a response — everyone else is silently ignored.

To find your ID:

1. Search for **@userinfobot** on Telegram
2. Send any message to it
3. It will reply with your **User ID** (a positive integer, e.g. `123456789`)

> **Want to use the bot inside a group?**
> Add the bot to the group, then send a message in the group to **@userinfobot** — it will return the **Chat ID** of the group (a negative number, e.g. `-100987654321`). Add that to your whitelist.

---

## 3. Configure config.yaml

Copy the template to the root of the project:

```bash
cp templates/config.yaml config.yaml
```

Open `config.yaml` with any editor and fill in the fields:

```yaml
telegram:
  token: "YOUR_TOKEN_FROM_BOTFATHER"

# Telegram IDs allowed to use the bot (users and/or groups)
whitelist:
  - 123456789          # your user ID
  - 987654321          # another user's ID
  - -100112233445566   # a Telegram group ID (negative number)

apis:
  movie:
    api_host: "http://192.168.1.100:7878"   # Radarr address
    api_key: "YOUR_RADARR_API_KEY"
  series:
    api_host: "http://192.168.1.100:8989"   # Sonarr address
    api_key: "YOUR_SONARR_API_KEY"

services:
  - type: "Radarr"
    commands: ["movie", "m"]
    api: "movie"
  - type: "Sonarr"
    commands: ["series", "s"]
    api: "series"
```

> **Where do I find the Radarr/Sonarr API key?**
> Open the web interface → Settings → General → the API Key is at the top of the page.

---

## 4. Start the bot

With `config.yaml` filled in and saved in the project root, start everything with:

```bash
docker compose up -d
```

To follow the logs in real time:

```bash
docker compose logs -f
```

To stop the bot:

```bash
docker compose down
```

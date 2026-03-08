from . import CONFIG

TELEGRAM_TOKEN = CONFIG["telegram"]["token"]

# Flat set of allowed Telegram IDs (user IDs are positive integers,
# group/supergroup chat IDs are negative integers).
WHITELIST: set[int] = set(CONFIG.get("whitelist", []))

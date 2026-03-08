from functools import wraps
from loguru import logger

from ..config.secrets import WHITELIST


def _get_ids(update):
    """Return (user_id, chat_id) from either a message or callback query."""
    if update.message:
        return update.message.from_user.id, update.message.chat_id
    if update.callback_query:
        return update.callback_query.from_user.id, update.callback_query.message.chat_id
    return None, None


def is_allowed(update) -> bool:
    user_id, chat_id = _get_ids(update)
    allowed = user_id in WHITELIST or chat_id in WHITELIST
    if not allowed:
        logger.debug(
            f"Ignoring update from user_id={user_id} chat_id={chat_id} — not in whitelist"
        )
    return allowed


def authorized(_func=None, *, min_auth_level=None):
    """
    Decorator that silently ignores any interaction from users/chats
    not present in the whitelist defined in config.yaml (or env vars).

    The `min_auth_level` parameter is accepted for back-compatibility
    but has no effect — whitelist presence is the only check.
    """
    def decorator(func):
        @wraps(func)
        async def wrapped_func(*args, **kwargs):
            # args[0] = self (service instance), args[1] = update
            update = args[1] if len(args) >= 2 else kwargs.get("update")
            if not is_allowed(update):
                # Silently ignore — answer callback queries to avoid the
                # "loading" spinner hanging in the Telegram client.
                if update and update.callback_query:
                    try:
                        await update.callback_query.answer()
                    except Exception:
                        pass
                return None
            return await func(*args, **kwargs)

        return wrapped_func

    # Support both @authorized and @authorized(min_auth_level=...)
    if _func is not None:
        return decorator(_func)
    return decorator

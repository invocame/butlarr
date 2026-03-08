from loguru import logger
from telegram import Update
from telegram.ext import Application

from .config.secrets import TELEGRAM_TOKEN
from .config.services import SERVICES
from .tg_handler import get_clbk_handler, get_common_handlers


def main():
    logger.info("Creating bot...")
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    logger.info("Registering start & help commands...")
    for h in get_common_handlers(SERVICES):
        application.add_handler(h)

    logger.info("Registering services...")
    for s in SERVICES:
        s.register(application)

    logger.info("Registering callback handler...")
    application.add_handler(get_clbk_handler(SERVICES))

    logger.info("Start polling for messages...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

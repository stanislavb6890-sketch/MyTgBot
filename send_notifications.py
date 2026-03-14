#!/usr/bin/env python3
"""Скрипт для отправки уведомлений об истекающих подписках

Запускать по крону, например:
*/15 * * * * /path/to/venv/bin/python /path/to/vpn-bot/send_notifications.py

Или раз в час:
0 * * * * /path/to/venv/bin/python /path/to/vpn-bot/send_notifications.py
"""
import asyncio
import os
import sys
import logging

# Добавляем путь
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aiogram import Bot
from config import BOT_TOKEN
from bot.utils.notifications import check_expiring_subscriptions, init_notification_db
from bot.utils.database import init_db

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def main():
    logger.info("🔔 Запуск проверки уведомлений...")
    
    # Инициализация БД
    init_db()
    init_notification_db()
    
    # Запуск бота для отправки сообщений
    bot = Bot(token=BOT_TOKEN)
    
    try:
        sent = await check_expiring_subscriptions(bot)
        logger.info(f"✅ Отправлено уведомлений: {sent}")
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())

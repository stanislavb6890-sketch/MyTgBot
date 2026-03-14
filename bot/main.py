"""Главный файл бота - Long Polling режим"""
import asyncio
import logging
import sys
import os

# Добавляем путь для импортов
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aiogram import Bot, Dispatcher
from aiohttp import web
from config import BOT_TOKEN
from bot.utils.database import init_db
from bot.handlers import (
    start_router, tariff_router, profile_router, 
    trial_router, payment_router
)
from bot.handlers.payment import yoomoney_webhook

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def on_startup(bot: Bot):
    """Запуск при старте"""
    logger.info("🚀 Бот запускается...")
    
    # Инициализация БД
    init_db()
    logger.info("✅ База данных инициализирована")


async def on_shutdown(bot: Bot):
    """Выключение"""
    logger.info("🛑 Бот выключается...")


async def main():
    """Основная функция - Long Polling"""
    # Инициализация бота
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    
    # Подключение роутеров
    dp.include_router(start_router)
    dp.include_router(tariff_router)
    dp.include_router(profile_router)
    dp.include_router(trial_router)
    dp.include_router(payment_router)
    
    # Запускаем on_startup
    await on_startup(bot)
    
    logger.info("🤖 Бот работает в режиме Long Polling")
    logger.info("Напиши /start боту в Telegram!")
    
    # Удаляем webhook если был
    await bot.delete_webhook()
    
    # Запускаем polling
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

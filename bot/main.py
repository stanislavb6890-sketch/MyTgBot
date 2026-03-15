"""Главный файл бота - Long Polling + Web App"""
import asyncio
import logging
import sys
import os
from aiohttp import web

# Добавляем путь для импортов
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aiogram import Bot, Dispatcher
from config import BOT_TOKEN, WEBHOOK_URL
from bot.utils.database import init_db
from bot.handlers import (
    start_router, tariff_router, profile_router, 
    trial_router, payment_router
)
from bot.handlers.admin import admin_router
from bot.handlers.payment import yoomoney_webhook
from bot.api import setup_api_routes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Web App route
async def webapp_handler(request):
    """Обслуживание Web App"""
    app_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'webapp', 'index.html')
    with open(app_path, 'r', encoding='utf-8') as f:
        return web.Response(text=f.read(), content_type='text/html')


async def on_startup(bot: Bot):
    """Запуск при старте"""
    logger.info("🚀 Бот запускается...")
    
    # Инициализация БД
    init_db()
    logger.info("✅ База данных инициализирована")


async def on_shutdown(bot: Bot):
    """Выключение"""
    logger.info("🛑 Бот выключается...")


async def web_server():
    """Веб-сервер для Web App"""
    app = web.Application()
    
    # Подключаем API
    setup_api_routes(app)
    
    app.router.add_get('/miniapp', webapp_handler)
    app.router.add_get('/app', webapp_handler)  # совместимость
    app.router.add_post('/webhook/yoomoney', yoomoney_webhook)
    
    runner = web.AppRunner(app)
    await runner.setup()
    
    site = web.TCPSite(runner, '0.0.0.0', 8080)
    await site.start()
    
    logger.info("🌐 Веб-сервер запущен на порту 8080")


async def main():
    """Основная функция"""
    # Инициализация бота
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    
    # Подключение роутеров
    dp.include_router(start_router)
    dp.include_router(tariff_router)
    dp.include_router(profile_router)
    dp.include_router(trial_router)
    dp.include_router(payment_router)
    dp.include_router(admin_router)
    
    # Запускаем on_startup
    await on_startup(bot)
    
    # Запускаем веб-сервер и polling параллельно
    await asyncio.gather(
        web_server(),
        dp.start_polling(bot)
    )


if __name__ == "__main__":
    asyncio.run(main())

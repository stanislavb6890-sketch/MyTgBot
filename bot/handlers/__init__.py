"""Экспорт всех обработчиков"""
from bot.handlers.start import router as start_router
from bot.handlers.tariff import router as tariff_router
from bot.handlers.profile import router as profile_router
from bot.handlers.trial import router as trial_router
from bot.handlers.payment import router as payment_router
from bot.handlers.admin import admin_router

__all__ = [
    "start_router",
    "tariff_router", 
    "profile_router",
    "trial_router",
    "payment_router",
    "admin_router",
]

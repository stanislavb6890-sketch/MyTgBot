"""Конфигурация бота"""
import os
from dotenv import load_dotenv

load_dotenv()

# Telegram
BOT_TOKEN = os.getenv("BOT_TOKEN")

# RemnaWave
REMNAWAVE_URL = os.getenv("REMNAWAVE_URL")
REMNAWAVE_TOKEN = os.getenv("REMNAWAVE_TOKEN")

# Webhook
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
YOOMONEY_SECRET = os.getenv("YOOMONEY_SECRET")

# Admin
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

# ЮMoney
YOOMONEY_WALLET = "4100118105213472"  # Номер кошелька

# Тарифы
TARIFF_BASE_PRICE_PER_DAY = 5  # рублей

TARIFFS = {
    "duration": {
        14: {"days": 14, "discount": 0, "name": "14 дней", "price": 79},
        30: {"days": 30, "discount": 0, "name": "1 месяц", "price": 129},
        90: {"days": 90, "discount": 0.15, "name": "3 месяца", "price": 349},
        180: {"days": 180, "discount": 0.20, "name": "6 месяцев", "price": 619},
        365: {"days": 365, "discount": 0.30, "name": "1 год", "price": 999},
    },
    "devices": {
        # Цена за месяц: +30₽/мес за каждое доп. устройство
        1: {"price": 0, "name": "1 устройство"},
        2: {"price": 60, "name": "2 устройства"},      # +30₽/мес × 2 мес
        3: {"price": 120, "name": "3 устройства"},    # +30₽/мес × 4 мес
        4: {"price": 180, "name": "4 устройства"},    # +30₽/мес × 6 мес
        5: {"price": 240, "name": "5 устройств"},     # +30₽/мес × 8 мес
        6: {"price": 300, "name": "6 устройств"},     # +30₽/мес × 10 мес
        7: {"price": 360, "name": "7 устройств"},     # +30₽/мес × 12 мес
    },
    "servers": {
        1: {"price": 0, "name": "1 сервер"},
        2: {"price": 45, "name": "2 сервера"},
        3: {"price": 90, "name": "3 сервера"},
        4: {"price": 135, "name": "4 сервера"},
        5: {"price": 180, "name": "5 серверов"},
    },
    "traffic": {
        # 50 GB включено, безлимит +100₽ фиксировано (не зависит от периода)
        "50gb": {"limit": 50 * 1024 * 1024 * 1024, "price": 0, "name": "50 GB"},
        "unlimited": {"limit": 0, "price": 100, "name": "Безлимит"},
    },
    "reset": {
        # Трафик не сбрасывается
        "none": {"price": 0, "name": "Без сброса"},
    },
}

# Тестовый период
TRIAL_DAYS = 3
TRIAL_TRAFFIC = 10 * 1024 * 1024 * 1024  # 10 GB  # 5 GB
TRIAL_DEVICES = 1
TRIAL_SERVERS = 1

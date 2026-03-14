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
        30: {"days": 30, "discount": 0, "name": "1 месяц", "price": 150},
        90: {"days": 90, "discount": 0.15, "name": "3 месяца", "price": 383},
        180: {"days": 180, "discount": 0.20, "name": "6 месяцев", "price": 720},
        365: {"days": 365, "discount": 0.30, "name": "1 год", "price": 1260},
    },
    "devices": {
        1: {"price": 0, "name": "1 устройство"},
        2: {"price": 25, "name": "2 устройства"},
        3: {"price": 50, "name": "3 устройства"},
        4: {"price": 75, "name": "4 устройства"},
        5: {"price": 100, "name": "5 устройств"},
        6: {"price": 125, "name": "6 устройств"},
        7: {"price": 150, "name": "7 устройств"},
    },
    "servers": {
        1: {"price": 0, "name": "1 сервер"},
        2: {"price": 45, "name": "2 сервера"},
        3: {"price": 90, "name": "3 сервера"},
        4: {"price": 135, "name": "4 сервера"},
        5: {"price": 180, "name": "5 серверов"},
    },
    "traffic": {
        "10gb": {"limit": 10 * 1024 * 1024 * 1024, "price": 0, "name": "10 GB"},
        "20gb": {"limit": 20 * 1024 * 1024 * 1024, "price": 40, "name": "20 GB"},
        "30gb": {"limit": 30 * 1024 * 1024 * 1024, "price": 55, "name": "30 GB"},
        "unlimited": {"limit": 0, "price": 200, "name": "Безлимит"},
    },
    "reset": {
        "none": {"price": 0, "name": "Без сброса"},
        "weekly": {"days": 7, "price": 30, "name": "Раз в неделю"},
        "monthly": {"days": 30, "price": 15, "name": "Раз в месяц"},
    },
}

# Тестовый период
TRIAL_DAYS = 3
TRIAL_TRAFFIC = 10 * 1024 * 1024 * 1024  # 10 GB  # 5 GB
TRIAL_DEVICES = 1
TRIAL_SERVERS = 1

"""База данных SQLite"""
import sqlite3
import asyncio
from datetime import datetime, timedelta
from typing import Optional
import random
import string

DB_PATH = "vpn_bot.db"


def init_db():
    """Инициализация БД"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Пользователи бота
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER UNIQUE NOT NULL,
            username TEXT,
            first_name TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_active BOOLEAN DEFAULT 1
        )
    """)

    # Подписки (VPN)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            remnawave_uuid TEXT UNIQUE NOT NULL,
            short_uuid TEXT,
            username TEXT NOT NULL,
            status TEXT DEFAULT 'active',
            duration_days INTEGER NOT NULL,
            traffic_limit_bytes INTEGER NOT NULL,
            traffic_used_bytes INTEGER DEFAULT 0,
            devices_limit INTEGER NOT NULL,
            servers_count INTEGER NOT NULL,
            reset_type TEXT DEFAULT 'none',
            is_trial BOOLEAN DEFAULT 0,
            is_paid BOOLEAN DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP NOT NULL,
            activated_at TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    # Выбранные серверы для подписки
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS subscription_servers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subscription_id INTEGER NOT NULL,
            node_uuid TEXT NOT NULL,
            node_name TEXT NOT NULL,
            country_code TEXT,
            FOREIGN KEY (subscription_id) REFERENCES subscriptions(id)
        )
    """)

    # Платежи
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subscription_id INTEGER,
            user_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            currency TEXT DEFAULT 'RUB',
            status TEXT DEFAULT 'pending',
            yoomoney_notification_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            paid_at TIMESTAMP,
            FOREIGN KEY (subscription_id) REFERENCES subscriptions(id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    conn.commit()
    conn.close()


def get_db_connection():
    return sqlite3.connect(DB_PATH)


# === Users ===

def get_or_create_user(telegram_id: int, username: str = None, first_name: str = None):
    """Получить или создать пользователя"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
    user = cursor.fetchone()

    if not user:
        cursor.execute(
            "INSERT INTO users (telegram_id, username, first_name) VALUES (?, ?, ?)",
            (telegram_id, username, first_name)
        )
        conn.commit()
        user_id = cursor.lastrowid
    else:
        user_id = user[0]

    conn.close()
    return user_id


def get_user_by_telegram(telegram_id: int):
    """Получить пользователя по Telegram ID"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
    user = cursor.fetchone()
    conn.close()
    return user


def user_has_trial(telegram_id: int) -> bool:
    """Проверить, получал ли пользователь тестовую подписку"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT has_trial FROM users WHERE telegram_id = ?", (telegram_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] == 1 if result else False


# === Subscriptions ===

def create_subscription(
    user_id: int,
    remnawave_uuid: str,
    short_uuid: str,
    username: str,
    duration_days: int,
    traffic_limit_bytes: int,
    devices_limit: int,
    servers_count: int,
    reset_type: str = "none",
    is_trial: bool = False,
    is_paid: bool = False,
    price: float = 0
) -> int:
    """Создать подписку"""
    conn = get_db_connection()
    cursor = conn.cursor()

    expires_at = datetime.now() + timedelta(days=duration_days)

    cursor.execute("""
        INSERT INTO subscriptions 
        (user_id, remnawave_uuid, short_uuid, username, duration_days, traffic_limit_bytes,
         devices_limit, servers_count, reset_type, is_trial, is_paid, expires_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (user_id, remnawave_uuid, short_uuid, username, duration_days, traffic_limit_bytes,
          devices_limit, servers_count, reset_type, is_trial, is_paid, expires_at))

    subscription_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return subscription_id


def add_subscription_server(subscription_id: int, node_uuid: str, node_name: str, country_code: str = None):
    """Добавить сервер к подписке"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO subscription_servers (subscription_id, node_uuid, node_name, country_code)
        VALUES (?, ?, ?, ?)
    """, (subscription_id, node_uuid, node_name, country_code))
    conn.commit()
    conn.close()


def get_user_subscriptions(user_id: int):
    """Получить все подписки пользователя"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT s.id, s.user_id, s.remnawave_uuid, s.short_uuid, s.username, s.status,
               s.duration_days, s.traffic_limit_bytes, s.traffic_used_bytes,
               s.devices_limit, s.servers_count, s.reset_type, s.is_trial, s.is_paid,
               s.created_at, s.expires_at, s.activated_at,
               COALESCE(s.price, s.duration_days * 5) as price,
               GROUP_CONCAT(ss.node_name, ', ') as servers
        FROM subscriptions s
        LEFT JOIN subscription_servers ss ON s.id = ss.subscription_id
        WHERE s.user_id = ?
        GROUP BY s.id
        ORDER BY s.created_at DESC
    """, (user_id,))
    subs = cursor.fetchall()
    conn.close()
    return subs


def get_subscription_by_uuid(remnawave_uuid: str):
    """Получить подписку по UUID RemnaWave"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM subscriptions WHERE remnawave_uuid = ?", (remnawave_uuid,))
    sub = cursor.fetchone()
    conn.close()
    return sub


def activate_subscription(subscription_id: int):
    """Активировать подписку (после оплаты)"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE subscriptions 
        SET is_paid = 1, activated_at = CURRENT_TIMESTAMP 
        WHERE id = ?
    """, (subscription_id,))
    conn.commit()
    conn.close()


def disable_subscription(remnawave_uuid: str):
    """Отключить подписку"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE subscriptions SET status = 'disabled' WHERE remnawave_uuid = ?
    """, (remnawave_uuid,))
    conn.commit()
    conn.close()


# === Payments ===

def create_payment(user_id: int, amount: float, subscription_id: int = None) -> int:
    """Создать платёж"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO payments (user_id, amount, subscription_id, status)
        VALUES (?, ?, ?, 'pending')
    """, (user_id, amount, subscription_id))
    payment_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return payment_id


def confirm_payment(payment_id: int, notification_id: str):
    """Подтвердить платёж"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE payments 
        SET status = 'paid', paid_at = CURRENT_TIMESTAMP, yoomoney_notification_id = ?
        WHERE id = ?
    """, (notification_id, payment_id))
    conn.commit()
    conn.close()


# === Утилиты ===

def get_db():
    """Получить соединение с БД (алиас для совместимости)"""
    return get_db_connection()


def generate_username(telegram_id: int) -> str:
    """Генерация имени пользователя"""
    return f"user{telegram_id}"


if __name__ == "__main__":
    init_db()
    print("✅ База данных инициализирована!")

"""Уведомления об окончании подписки"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import List

from aiogram import Bot
from bot.utils.database import get_db

logger = logging.getLogger(__name__)

# За сколько дней до истечения отправлять уведомления
NOTIFICATION_DAYS = [1, 3, 7]


async def check_expiring_subscriptions(bot: Bot) -> int:
    """Проверить истекающие подписки и отправить уведомления"""
    conn = get_db()
    cursor = conn.cursor()
    
    sent_count = 0
    now = datetime.now()
    
    for days in NOTIFICATION_DAYS:
        # Находим подписки, истекающие через указанное количество дней
        target_date = now + timedelta(days=days)
        target_date_start = target_date.replace(hour=0, minute=0, second=0)
        target_date_end = target_date.replace(hour=23, minute=59, second=59)
        
        cursor.execute("""
            SELECT s.id, s.user_id, s.expires_at, s.username, u.telegram_id, u.first_name
            FROM subscriptions s
            JOIN users u ON s.user_id = u.id
            WHERE s.status = 'active' 
            AND s.expires_at >= ?
            AND s.expires_at <= ?
        """, (target_date_start.isoformat(), target_date_end.isoformat()))
        
        subscriptions = cursor.fetchall()
        
        for sub in subscriptions:
            sub_id, user_id, expires_at, username, telegram_id, first_name = sub
            
            # Проверяем, не отправляли ли уже уведомление
            cursor.execute("""
                SELECT id FROM notification_log 
                WHERE user_id = ? AND days_before = ? AND sent_date = date('now')
            """, (user_id, days))
            
            if cursor.fetchone():
                logger.info(f"Уведомление для user_id={user_id} за {days} дней уже отправлено")
                continue
            
            # Отправляем уведомление
            try:
                message = get_notification_message(days, first_name or username or "пользователь")
                await bot.send_message(telegram_id, message)
                
                # Логируем отправку
                cursor.execute("""
                    INSERT INTO notification_log (user_id, days_before, sent_at)
                    VALUES (?, ?, datetime('now'))
                """, (user_id, days))
                conn.commit()
                
                sent_count += 1
                logger.info(f"✅ Отправлено уведомление user_id={user_id} за {days} дней до истечения")
                
            except Exception as e:
                logger.error(f"❌ Ошибка отправки user_id={user_id}: {e}")
    
    conn.close()
    return sent_count


def get_notification_message(days: int, name: str) -> str:
    """Получить текст уведомления"""
    if days == 1:
        return f"""⏰ Привет, {name}!

Твоя подписка истекает уже завтра! 

Не забудь продлить, чтобы не остаться без интернета. Если нужна помощь — просто напиши боту."""
    elif days == 3:
        return f"""📅 Привет, {name}!

Твоя подписка истекает через 3 дня.

У тебя есть время продлить её со скидкой. Если что — пиши, помогу!"""
    else:  # 7 days
        return f"""📆 Привет, {name}!

Напоминаю: подписка истекает через неделю.

Если планируешь продлить — самое время. Возникли вопросы? Я на связи!"""


def init_notification_db():
    """Создать таблицу для логирования уведомлений"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notification_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            days_before INTEGER NOT NULL,
            sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    conn.commit()
    conn.close()
    logger.info("✅ Таблица notification_log создана")

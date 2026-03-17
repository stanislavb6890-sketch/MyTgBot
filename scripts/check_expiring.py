#!/usr/bin/env python3
"""Проверка истекающих подписок и отправка уведомлений"""

import asyncio
import sys
sys.path.insert(0, '/root/.openclaw/workspace/vpn-bot')

from datetime import datetime, timedelta
from bot.utils.database import get_db_connection

async def check_expiring_subscriptions():
    """Проверяет подписки, которые истекают через 3 дня"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Находим подписки, которые истекают через 3 дня
    expires_soon = datetime.now() + timedelta(days=3)
    
    cursor.execute("""
        SELECT s.id, s.user_id, s.expires_at, u.telegram_id
        FROM subscriptions s
        JOIN users u ON s.user_id = u.id
        WHERE s.status = 'active' 
        AND s.expires_at <= ?
        AND s.expires_at > ?
    """, (expires_soon.isoformat(), datetime.now().isoformat()))
    
    expiring = cursor.fetchall()
    
    if expiring:
        # Импортируем утилиту для отправки уведомлений
        from bot.utils.notifications import send_telegram_message
        
        for sub in expiring:
            sub_id, user_id, expires_at, telegram_id = sub
            
            try:
                await send_telegram_message(
                    telegram_id,
                    f"⏰ <b>Напоминание</b>\n\n"
                    f"Ваша подписка истекает {expires_at[:10]}\n"
                    f"Не забудьте продлить!",
                    parse_mode="HTML"
                )
                print(f"✅ Уведомление отправлено пользователю {telegram_id}")
            except Exception as e:
                print(f"❌ Ошибка отправки {telegram_id}: {e}")
    
    conn.close()
    print(f"Проверка завершена. Найдено {len(expiring)} истекающих подписок")

if __name__ == "__main__":
    asyncio.run(check_expiring_subscriptions())

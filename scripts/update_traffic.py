#!/usr/bin/env python3
"""
Cron скрипт для обновления трафика из RemnaWave
Запускать каждые 30 минут
"""
import asyncio
import sys
import os

# Добавляем путь к проекту
sys.path.insert(0, '/root/.openclaw/workspace/vpn-bot')
os.chdir('/root/.openclaw/workspace/vpn-bot')

from remnawave import RemnawaveSDK
from config import REMNAWAVE_URL, REMNAWAVE_TOKEN
from bot.utils.database import get_db


async def update_traffic():
    """Обновить трафик для всех активных подписок"""
    print("🔄 Начинаю обновление трафика...")
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Получаем все активные подписки с remnawave_uuid
    cursor.execute("""
        SELECT s.id, s.remnawave_uuid, s.traffic_limit_bytes
        FROM subscriptions s
        WHERE s.status = 'active' AND s.remnawave_uuid IS NOT NULL
    """)
    
    subscriptions = cursor.fetchall()
    print(f"📊 Найдено {len(subscriptions)} активных подписок")
    
    sdk = RemnawaveSDK(base_url=REMNAWAVE_URL, token=REMNAWAVE_TOKEN)
    
    updated = 0
    for sub_id, uuid, limit_bytes in subscriptions:
        try:
            # Получаем пользователя из RemnaWave
            user = await sdk.users.get_user_by_uuid(uuid)
            
            if user and hasattr(user, 'user_traffic') and user.user_traffic:
                # Получаем bytes_used
                bytes_used = user.user_traffic.used_traffic_bytes or 0
                
                # Обновляем в БД
                cursor.execute(
                    "UPDATE subscriptions SET traffic_used_bytes = ? WHERE id = ?",
                    (bytes_used, sub_id)
                )
                updated += 1
                print(f"✅ Подписка {sub_id}: {bytes_used / (1024**3):.2f} GB")
                
        except Exception as e:
            print(f"❌ Ошибка для подписки {sub_id}: {e}")
    
    conn.commit()
    conn.close()
    
    print(f"✅ Обновлено {updated} подписок")


if __name__ == "__main__":
    asyncio.run(update_traffic())

"""Уведомления в Telegram"""
import asyncio
import logging

logger = logging.getLogger(__name__)


def get_bot_token():
    """Получить токен бота из config"""
    try:
        from config import BOT_TOKEN
        return BOT_TOKEN
    except:
        return None


async def send_telegram_message(chat_id: int, text: str, parse_mode: str = "Markdown"):
    """Отправить сообщение в Telegram"""
    token = get_bot_token()
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN не настроен")
        return False
    
    import aiohttp
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as response:
                if response.status == 200:
                    logger.info(f"Уведомление отправлено пользователю {chat_id}")
                    return True
                else:
                    logger.error(f"Ошибка отправки: {response.status}")
                    return False
    except Exception as e:
        logger.error(f"Исключение при отправке: {e}")
        return False


async def notify_payment_success(telegram_id: int, subscription_data: dict, remaining_balance: float):
    """Уведомление об успешной оплате подписки"""
    sub = subscription_data
    
    text = f"""✅ *Подписка оплачена!*

📋 *Детали:*
• ID: #{sub.get('id', 'N/A')}
• Статус: Активирована
• Истекает: {sub.get('expires_at', 'N/A')[:10]}
• Трафик: {sub.get('traffic_limit', 0)} GB
• Устройства: {sub.get('devices', 1)}

💰 *Баланс:* {remaining_balance} ₽

📱 Скопируйте ссылку в разделе 'Подписки' для настройки VPN"""
    
    return await send_telegram_message(telegram_id, text)


async def notify_trial_activated(telegram_id: int):
    """Уведомление об активации триала"""
    text = """🎉 *Тестовый период активирован!*

📋 *Детали:*
• Срок: 3 дня
• Трафик: 5 GB
• Устройства: 1

📱 Получите ссылку в разделе 'Подписки' для настройки VPN"""
    
    return await send_telegram_message(telegram_id, text)


async def notify_balance_topup(telegram_id: int, amount: float, new_balance: float):
    """Уведомление о пополнении баланса"""
    text = f"""💰 *Баланс пополнен!*

• Сумма: +{amount} ₽
• Новый баланс: {new_balance} ₽"""
    
    return await send_telegram_message(telegram_id, text)


async def notify_new_referral(telegram_id: int, referrer_name: str, bonus: float):
    """Уведомление о новом рефале"""
    text = f"""👥 *Новый реферал!*

@{referrer_name} присоединился по вашей ссылке

🎁 *Бонус:* +{bonus} ₽"""
    
    return await send_telegram_message(telegram_id, text)


async def notify_subscription_expiring(telegram_id: int, days_left: int, sub_id: int):
    """Уведомление об истечении подписки"""
    text = f"""⏰ *Подписка истекает!*

До окончания подписки #{sub_id} осталось *{days_left} дней*

Продлите подписку, чтобы не потерять доступ к VPN"""
    
    return await send_telegram_message(telegram_id, text)


async def check_expiring_subscriptions():
    """Проверить подписки, которые истекают через N дней (для крона)"""
    import sqlite3
    from datetime import datetime, timedelta
    
    conn = sqlite3.connect('vpn_bot.db')
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    # Подписки, которые истекают через 3 дня
    check_date = datetime.now() + timedelta(days=3)
    
    c.execute("""
        SELECT s.id, s.user_id, s.expires_at, u.telegram_id
        FROM subscriptions s
        JOIN users u ON s.user_id = u.id
        WHERE s.status = 'active' 
        AND date(s.expires_at) = date(?)
    """, (check_date.strftime('%Y-%m-%d'),))
    
    expiring = c.fetchall()
    conn.close()
    
    sent = 0
    for sub in expiring:
        days_left = 3
        success = await notify_subscription_expiring(sub['telegram_id'], days_left, sub['id'])
        if success:
            sent += 1
    
    return sent


if __name__ == "__main__":
    # Тест отправки
    asyncio.run(send_telegram_message(123456789, "Тестовое уведомление!"))

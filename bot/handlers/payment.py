"""Обработка платежей и webhook"""
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiohttp import web
import hashlib
import hmac
import json
import subprocess
from bot.utils.database import confirm_payment, activate_subscription, get_subscription_by_uuid, get_db_connection
from bot.utils.remnawave import enable_vpn_user
from config import YOOMONEY_SECRET
import asyncio
import logging

router = Router()


def send_notification_async(notification_func, *args):
    """Отправить уведомление асинхронно через subprocess"""
    try:
        import json
        args_json = json.dumps(args, default=str)
        venv_python = '/root/.openclaw/workspace/vpn-bot/venv/bin/python3'
        subprocess.Popen([
            venv_python, '-c', f'''
import asyncio
import sys
sys.path.insert(0, "/root/.openclaw/workspace/vpn-bot")
import logging
logging.basicConfig(level=logging.INFO)
from bot.utils.notifications import {notification_func}
result = asyncio.run({notification_func}(*{args_json}))
print(f"Result: {{result}}")
'''
        ], cwd='/root/.openclaw/workspace/vpn-bot', 
           stdout=subprocess.PIPE, 
           stderr=subprocess.PIPE)
        print(f"📨 Уведомление отправлено: {notification_func}")
    except Exception as e:
        print(f"Ошибка отправки уведомления: {e}")

# === Webhook для ЮMoney ===
import logging
logger = logging.getLogger(__name__)

async def yoomoney_webhook(request):
    """Обработка webhook от ЮMoney"""
    logger.info("🔔 Webhook called!")
    try:
        # Пробуем получить JSON данные
        content_type = request.headers.get('Content-Type', '')
        logger.info(f"   Content-Type: {content_type}")
        
        if 'application/json' in content_type:
            data = await request.json()
        else:
            data = await request.post()
        
        # Получаем данные
        notification_type = data.get("notification_type")
        amount = data.get("amount")
        currency = data.get("currency")
        label = data.get("label")  # ID платежа в нашей системе
        notification_id = data.get("notification_id")
        
        print(f"💰 ЮMoney webhook: notification_type={notification_type}, amount={amount}, currency={currency}, label={label}")
        print(f"   Raw data: {data}")
        
        # Проверяем подпись
        if YOOMONEY_SECRET:
            # Получаем подпись из заголовка
            signature = request.headers.get('X-Yoomoney-Signature', '')
            
            # Формируем строку для подписи
            params = f"{notification_type}&{amount}&{currency}&{YOOMONEY_SECRET}&{label}"
            expected_sha = hashlib.sha256(params.encode()).hexdigest()
            
            # Проверяем подпись
            if signature and signature != expected_sha:
                logger.warning(f"❌ Неверная подпись webhook! Ожидалась: {expected_sha}, получена: {signature}")
                return web.Response(text="Invalid signature", status=403)
            
            logger.info("✅ Подпись верифицирована")
        
        # Подтверждаем платёж
        if label and amount:
            # Проверяем: пополнение баланса или оплата подписки
            if label.startswith("topup_"):
                # Пополнение баланса: topup_{user_id}_{amount}
                parts = label.split("_")
                if len(parts) == 3:
                    user_id = int(parts[1])
                    amount = float(amount)
                    
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    
                    # Начисляем баланс
                    cursor.execute("UPDATE users SET balance = balance + ? WHERE id = ?", (amount, user_id))
                    
                    # Записываем платёж в историю
                    cursor.execute("""
                        INSERT INTO payments (user_id, amount, currency, status, yoomoney_notification_id)
                        VALUES (?, ?, 'RUB', 'paid', ?)
                    """, (user_id, amount, notification_id))
                    
                    # Начисляем реферальные бонусы
                    cursor.execute("SELECT referrer_id FROM users WHERE id = ?", (user_id,))
                    referrer_row = cursor.fetchone()
                    
                    if referrer_row and referrer_row[0]:
                        referrer_id = referrer_row[0]
                        
                        # Уровень 1: 5%
                        bonus_level1 = amount * 0.05
                        cursor.execute("UPDATE users SET referral_bonus = referral_bonus + ?, balance = balance + ? WHERE id = ?", 
                                    (bonus_level1, bonus_level1, referrer_id))
                        
                        # Уровень 2: 3%
                        cursor.execute("SELECT referrer_id FROM users WHERE id = ?", (referrer_id,))
                        level2_row = cursor.fetchone()
                        if level2_row and level2_row[0]:
                            bonus_level2 = amount * 0.03
                            cursor.execute("UPDATE users SET referral_bonus = referral_bonus + ?, balance = balance + ? WHERE id = ?",
                                        (bonus_level2, bonus_level2, level2_row[0]))
                            
                            # Уровень 3: 1%
                            cursor.execute("SELECT referrer_id FROM users WHERE id = ?", (level2_row[0],))
                            level3_row = cursor.fetchone()
                            if level3_row and level3_row[0]:
                                bonus_level3 = amount * 0.01
                                cursor.execute("UPDATE users SET referral_bonus = referral_bonus + ?, balance = balance + ? WHERE id = ?",
                                            (bonus_level3, bonus_level3, level3_row[0]))
                    
                    # Получаем данные для уведомления ДО закрытия соединения
                    cursor.execute("SELECT telegram_id, balance FROM users WHERE id = ?", (user_id,))
                    user_row = cursor.fetchone()
                    
                    conn.commit()
                    conn.close()
                    
                    # Отправляем уведомление о пополнении баланса
                    if user_row:
                        telegram_id, new_balance = user_row
                        send_notification_async(
                            "notify_balance_topup", 
                            telegram_id, 
                            amount, 
                            new_balance
                        )
                    
                    print(f"✅ Баланс пополнен: user_id={user_id}, amount={amount}")
            else:
                # Оплата подписки (label = subscription_id)
                sub_id = int(label)
                amount = float(amount)
                
                conn = get_db_connection()
                cursor = conn.cursor()
                
                # Получаем данные подписки
                cursor.execute("""
                    SELECT s.user_id, s.expires_at, s.traffic_limit_bytes, s.devices_limit, u.telegram_id, u.balance
                    FROM subscriptions s
                    JOIN users u ON s.user_id = u.id
                    WHERE s.id = ?
                """, (sub_id,))
                row = cursor.fetchone()
                
                if row:
                    user_id, expires_at, traffic_bytes, devices, telegram_id, balance = row
                    
                    # Получаем remnawave_uuid для активации
                    cursor.execute("SELECT remnawave_uuid FROM subscriptions WHERE id = ?", (sub_id,))
                    remnawave_row = cursor.fetchone()
                    remnawave_uuid = remnawave_row[0] if remnawave_row else None
                    
                    # Обновляем подписку как оплаченную
                    cursor.execute("""
                        UPDATE subscriptions 
                        SET is_paid = 1, paid_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                    """, (sub_id,))
                    
                    # Записываем платёж в историю
                    cursor.execute("""
                        INSERT INTO payments (subscription_id, user_id, amount, currency, status, yoomoney_notification_id)
                        VALUES (?, ?, ?, 'RUB', 'paid', ?)
                    """, (sub_id, user_id, amount, notification_id))
                    
                    conn.commit()
                    conn.close()
                    
                    # Активируем пользователя в Remnawave
                    if remnawave_uuid:
                        try:
                            import subprocess
                            subprocess.run(
                                ['/root/.openclaw/workspace/vpn-bot/venv/bin/python3', '-c', f'''
import asyncio
from bot.utils.remnawave import enable_vpn_user
asyncio.run(enable_vpn_user("{remnawave_uuid}"))
'''],
                                capture_output=True,
                                timeout=30
                            )
                            print(f"✅ VPN пользователь активирован: {remnawave_uuid}")
                        except Exception as e:
                            print(f"❌ Ошибка активации VPN: {e}")
                    
                    traffic_gb = traffic_bytes / (1024**3) if traffic_bytes else 0
                    
                    # Отправляем уведомление об успешной оплате
                    send_notification_async(
                        "notify_payment_success",
                        telegram_id,
                        {
                            "id": sub_id,
                            "expires_at": expires_at,
                            "traffic_limit": traffic_gb,
                            "devices": devices
                        },
                        balance
                    )
                    
                    print(f"✅ Подписка оплачена: sub_id={sub_id}, amount={amount}")
                else:
                    conn.close()
                    print(f"❌ Подписка не найдена: sub_id={sub_id}")
        
        return web.Response(text="OK")
    
    except Exception as e:
        print(f"❌ Webhook error: {e}")
        return web.Response(text="ERROR")


# === Проверка оплаты ===
@router.callback_query(F.data == "check_payment")
async def check_payment(callback: CallbackQuery):
    """Проверка оплаты (кнопка в боте)"""
    telegram_id = callback.from_user.id
    
    # Пока без webhook — активируем вручную
    # В будущем подключим ЮMoney API
    
    await callback.message.edit_text(
        "⏳ Проверяю...\n\n"
        "⚠️ ВНИМАНИЕ: Это тестовый режим!\n\n"
        "Для активации подписки свяжись с @ssredok\n"
        "После оплаты нажми 'Я оплатил' и ожидай активации.",
        reply_markup=get_main_keyboard(has_subscription=True, has_trial=True)
    )
    await callback.answer()


def get_main_keyboard():
    """Импорт главной клавиатуры"""
    from bot.keyboards import get_main_keyboard as gm
    return gm()


# === Админ: статистика ===
@router.message(F.text == "/stats")
async def cmd_stats(message: Message):
    """Статистика (админ)"""
    from config import ADMIN_ID
    from bot.utils.database import get_db_connection
    
    if message.from_user.id != ADMIN_ID:
        return
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Всего пользователей
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]
    
    # Всего подписок
    cursor.execute("SELECT COUNT(*) FROM subscriptions")
    total_subs = cursor.fetchone()[0]
    
    # Активных подписок
    cursor.execute("SELECT COUNT(*) FROM subscriptions WHERE status = 'active'")
    active_subs = cursor.fetchone()[0]
    
    # Оплаченных
    cursor.execute("SELECT COUNT(*) FROM subscriptions WHERE is_paid = 1")
    paid_subs = cursor.fetchone()[0]
    
    conn.close()
    
    await message.answer(
        f"📊 СТАТИСТИКА\n\n"
        f"👥 Пользователей бота: {total_users}\n"
        f"📱 Всего подписок: {total_subs}\n"
        f"🟢 Активных: {active_subs}\n"
        f"✅ Оплаченных: {paid_subs}"
    )

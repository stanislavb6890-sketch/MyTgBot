"""Обработка платежей и webhook"""
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiohttp import web
import hashlib
import hmac
import json
from bot.utils.database import confirm_payment, activate_subscription, get_subscription_by_uuid, get_db_connection
from bot.utils.remnawave import enable_vpn_user
from config import YOOMONEY_SECRET
import asyncio

router = Router()

# === Webhook для ЮMoney ===
async def yoomoney_webhook(request):
    """Обработка webhook от ЮMoney"""
    try:
        data = await request.post()
        
        # Получаем данные
        notification_type = data.get("notification_type")
        amount = data.get("amount")
        currency = data.get("currency")
        label = data.get("label")  # ID платежа в нашей системе
        notification_id = data.get("notification_id")
        
        print(f"💰 ЮMoney webhook: {notification_type}, amount={amount}, label={label}")
        
        # Проверяем подпись
        if YOOMONEY_SECRET:
            # Формируем строку для подписи
            params = f"{notification_type}&{amount}&{currency}&{YOOMONEY_SECRET}&{label}"
            sha = hashlib.sha256(params.encode()).hexdigest()
            # TODO: Проверить подпись полностью
        
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
                    cursor.execute("UPDATE users SET balance = balance + ? WHERE id = ?", (amount, user_id))
                    conn.commit()
                    conn.close()
                    
                    print(f"✅ Баланс пополнен: user_id={user_id}, amount={amount}")
            else:
                # Оплата подписки
                payment_id = int(label)
                confirm_payment(payment_id, notification_id)
                print(f"✅ Платёж подтверждён: {payment_id}")
        
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

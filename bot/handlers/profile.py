"""Кабинет пользователя"""
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from bot.keyboards import get_main_keyboard, get_cabinet_keyboard, get_subscription_keyboard
from bot.utils.database import get_user_subscriptions, get_or_create_user, user_has_trial
from bot.utils.remnawave import enable_vpn_user, disable_vpn_user
from config import YOOMONEY_WALLET
from datetime import datetime

router = Router()


@router.callback_query(F.data == "my_subscriptions")
async def my_subscriptions(callback: CallbackQuery):
    """Кабинет пользователя"""
    telegram_id = callback.from_user.id
    first_name = callback.from_user.first_name or "друг"

    user_id = get_or_create_user(telegram_id)
    subs = get_user_subscriptions(user_id)
    has_trial_used = user_has_trial(telegram_id)

    if not subs:
        await callback.message.edit_text(
            "📱 У вас пока нет подписок.",
            reply_markup=get_main_keyboard(has_subscription=False, has_trial=has_trial_used)
        )
        await callback.answer()
        return

    # Показываем только 1 неоплаченную подписку
    unpaid_subs = [s for s in subs if not s[12]]  # is_paid = False
    
    text = f"📱 КАБИНЕТ - {first_name}\n\n"
    text += f"📊 Всего подписок: {len(subs)}\n"
    
    if unpaid_subs:
        sub = unpaid_subs[0]  # Показываем только первую неоплаченную
        
        is_active = sub[5] == "active"
        is_paid = sub[12]
        
        status_emoji = "🟢" if is_active else "🔴"
        trial_emoji = "🧪 ТЕСТ" if sub[12] else "💰 НЕ ОПЛАЧЕНО"

        traffic_limit_gb = sub[7] / (1024**3)
        traffic_used_gb = sub[8] / (1024**3)

        expires = sub[15]
        if isinstance(expires, str):
            try:
                exp_date = datetime.fromisoformat(expires.replace("Z", "+00:00"))
                expires_str = exp_date.strftime("%d.%m.%Y")
            except:
                expires_str = str(expires)
        else:
            expires_str = str(expires)

        duration = sub[6]
        price = sub[16] if len(sub) > 16 and sub[16] else duration * 5
        payment_url = f"https://yoomoney.ru/quickpay/confirm?receiver={YOOMONEY_WALLET}&quickpay-form=button&paymentType=AC&sum={price}&label={sub[0]}"

        text += f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━
❗️ НЕОПЛАЧЕННАЯ ПОДПИСКА #{sub[0]}

📅 Истекает: {expires_str}
📊 Трафик: {traffic_used_gb:.1f} / {traffic_limit_gb:.0f} GB  
📱 Устройства: {sub[9]}
🌍 Серверов: {sub[10]}
💵 К оплате: {price}₽

⏰ Если не оплатить — удалится через 24ч
"""
    else:
        # Все оплаченные - показываем первую активную
        active_subs = [s for s in subs if s[5] == "active"]
        if active_subs:
            sub = active_subs[0]
            status_emoji = "🟢"
            trial_emoji = "💰 ПОКУПКА"
            traffic_limit_gb = sub[7] / (1024**3)
            traffic_used_gb = sub[8] / (1024**3)
            expires = sub[15]
            if isinstance(expires, str):
                try:
                    exp_date = datetime.fromisoformat(expires.replace("Z", "+00:00"))
                    expires_str = exp_date.strftime("%d.%m.%Y")
                except:
                    expires_str = str(expires)
            else:
                expires_str = str(expires)
            short_uuid = sub[3]
            sub_url = f"https://sys.goodred.pro/{short_uuid}"
            
            text += f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ АКТИВНАЯ ПОДПИСКА #{sub[0]}

📅 Истекает: {expires_str}
📊 Трафик: {traffic_used_gb:.1f} / {traffic_limit_gb:.0f} GB
📱 Устройства: {sub[9]}
🌍 Серверов: {sub[10]}
🔗 {sub_url}
"""

    await callback.message.edit_text(text, reply_markup=get_cabinet_keyboard(has_unpaid=bool(unpaid_subs), payment_url=payment_url if unpaid_subs else None))
    await callback.answer()


@router.callback_query(F.data.startswith("sub_info_"))
async def subscription_info(callback: CallbackQuery):
    """Информация о подписке"""
    sub_id = int(callback.data.split("_")[2])
    telegram_id = callback.from_user.id
    has_trial_used = user_has_trial(telegram_id)

    user_id = get_or_create_user(telegram_id)
    subs = get_user_subscriptions(user_id)

    sub = next((s for s in subs if s[0] == sub_id), None)

    if not sub:
        await callback.message.edit_text("❌ Подписка не найдена", reply_markup=get_cabinet_keyboard())
        await callback.answer()
        return

    status_emoji = "🟢" if sub[5] == "active" else "🔴"
    trial_emoji = "🧪 ТЕСТ" if sub[12] else "💰 ПОКУПКА"
    traffic_limit_gb = sub[7] / (1024**3)
    traffic_used_gb = sub[8] / (1024**3)

    short_uuid = sub[3]
    sub_url = f"https://sys.goodred.pro/{short_uuid}"

    text = f"""📋 Подписка #{sub[0]}

{status_emoji} Статус: {sub[5].upper()}
{trial_emoji}
📅 Истекает: {sub[15]}
📊 Трафик: {traffic_used_gb:.1f} / {traffic_limit_gb:.0f} GB
📱 Устройства: {sub[9]}
🌍 Серверов: {sub[10]}

🔗 ССЫЛКА НА ПОДКЛЮЧЕНИЕ:
{sub_url}
"""

    await callback.message.edit_text(text, reply_markup=get_cabinet_keyboard())
    await callback.answer()


@router.callback_query(F.data.startswith("pay_sub_"))
async def pay_subscription(callback: CallbackQuery):
    """Оплата подписки"""
    sub_id = int(callback.data.split("_")[-1])
    telegram_id = callback.from_user.id
    has_trial_used = user_has_trial(telegram_id)
    
    # Получаем цену подписки (упрощённо)
    from bot.utils.database import get_user_subscriptions
    user_id = get_or_create_user(telegram_id)
    subs = get_user_subscriptions(user_id)
    
    # Находим нужную подписку
    sub = next((s for s in subs if s[0] == sub_id), None)
    
    if not sub:
        await callback.message.edit_text("❌ Подписка не найдена", reply_markup=get_cabinet_keyboard())
        await callback.answer()
        return
    
    # Цена = days * 5 (база)
    duration = sub[6]  # duration_days
    price = sub[16] if len(sub) > 16 and sub[16] else duration * 5
    
    payment_url = f"https://yoomoney.ru/quickpay/confirm?receiver={YOOMONEY_WALLET}&quickpay-form=button&paymentType=AC&sum={price}&label={sub_id}"
    
    await callback.message.edit_text(
        f"💳 ОПЛАТА ПОДПИСКИ #{sub_id}\n\n"
        f"💵 Сумма: {price}₽\n\n"
        f"Нажмите кнопку ниже для оплаты",
        reply_markup=get_cabinet_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data.startswith("sub_renew_"))
async def subscription_renew(callback: CallbackQuery):
    """Продление подписки"""
    sub_id = int(callback.data.split("_")[2])
    telegram_id = callback.from_user.id
    has_trial_used = user_has_trial(telegram_id)

    await callback.message.edit_text(
        f"🔄 Продление подписки #{sub_id}\n\n"
        "Перейди в конструктор тарифов для продления.",
        reply_markup=get_cabinet_keyboard())
    await callback.answer()


@router.message(F.text == "/my")
async def cmd_my(message: Message):
    """Команда /my - кабинет"""
    telegram_id = message.from_user.id
    first_name = message.from_user.first_name or "друг"

    user_id = get_or_create_user(telegram_id)
    subs = get_user_subscriptions(user_id)
    has_trial_used = user_has_trial(telegram_id)

    if not subs:
        await message.answer(
            "📱 У вас пока нет подписок.",
            reply_markup=get_main_keyboard(has_subscription=False, has_trial=has_trial_used)
        )
        return

    text = f"📱 КАБИНЕТ - {first_name}\n\n"
    text += f"📊 Всего подписок: {len(subs)}\n\n"

    for sub in subs:
        status_emoji = "🟢" if sub[5] == "active" else "🔴"
        trial_emoji = "🧪 ТЕСТ" if sub[12] else "💰 ПОКУПКА"

        traffic_limit_gb = sub[7] / (1024**3)
        traffic_used_gb = sub[8] / (1024**3)

        expires = sub[15]
        if isinstance(expires, str):
            try:
                exp_date = datetime.fromisoformat(expires.replace("Z", "+00:00"))
                expires_str = exp_date.strftime("%d.%m.%Y")
            except:
                expires_str = str(expires)
        else:
            expires_str = str(expires)

        short_uuid = sub[3]
        sub_url = f"https://sys.goodred.pro/{short_uuid}"

        text += f"{status_emoji} #{sub[0]} {trial_emoji} | До: {expires_str}\n"
        text += f"   📊 {traffic_used_gb:.1f}/{traffic_limit_gb:.0f} GB | 🔗 {sub_url}\n\n"

    await message.answer(text, reply_markup=get_cabinet_keyboard())


@router.callback_query(F.data == "pay_unpaid")
async def pay_unpaid(callback: CallbackQuery):
    """Оплатить неоплаченную подписку"""
    telegram_id = callback.from_user.id
    
    user_id = get_or_create_user(telegram_id)
    subs = get_user_subscriptions(user_id)
    
    # Находим неоплаченную
    unpaid = next((s for s in subs if not s[12]), None)
    
    if not unpaid:
        await callback.message.edit_text("Нет неоплаченных подписок", reply_markup=get_cabinet_keyboard())
        await callback.answer()
        return
    
    sub_id = unpaid[0]
    duration = unpaid[6]
    price = unpaid[16] if len(unpaid) > 16 and unpaid[16] else duration * 5
    
    payment_url = f"https://yoomoney.ru/quickpay/confirm?receiver={YOOMONEY_WALLET}&quickpay-form=button&paymentType=AC&sum={price}&label={sub_id}"
    
    await callback.message.answer(
        f"💳 ОПЛАТА ПОДПИСКИ #{sub_id}\n\n"
        f"💵 Сумма: {price}₽\n\n"
        f"После оплаты нажми 'Я оплатил'",
        reply_markup=get_cabinet_keyboard(has_unpaid=True)
    )
    await callback.answer()


@router.callback_query(F.data == "delete_unpaid")
async def delete_unpaid(callback: CallbackQuery):
    """Удалить неоплаченную подписку"""
    telegram_id = callback.from_user.id
    
    user_id = get_or_create_user(telegram_id)
    subs = get_user_subscriptions(user_id)
    
    # Находим неоплаченную
    unpaid = next((s for s in subs if not s[12]), None)
    
    if not unpaid:
        await callback.message.edit_text("Нет неоплаченных подписок", reply_markup=get_cabinet_keyboard())
        await callback.answer()
        return
    
    sub_id = unpaid[0]
    uuid = unpaid[2]  # remnawave_uuid
    
    # Удаляем из панели
    try:
        import asyncio
        from remnawave import RemnawaveSDK
        from config import REMNAWAVE_URL, REMNAWAVE_TOKEN
        
        async def del_user():
            sdk = RemnawaveSDK(base_url=REMNAWAVE_URL, token=REMNAWAVE_TOKEN)
            await sdk.users.delete_user(uuid=uuid)
        
        asyncio.get_event_loop().run_until_complete(del_user())
    except Exception as e:
        print(f"Error deleting user: {e}")
    
    # Удаляем из базы
    import sqlite3
    conn = sqlite3.connect('vpn_bot.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM subscriptions WHERE id = ?', (sub_id,))
    cursor.execute('DELETE FROM subscription_servers WHERE subscription_id = ?', (sub_id,))
    conn.commit()
    conn.close()
    
    await callback.message.answer(
        "✅ Подписка удалена!\n\n"
        "Можете создать новую.",
        reply_markup=get_cabinet_keyboard(has_unpaid=False)
    )
    await callback.answer()

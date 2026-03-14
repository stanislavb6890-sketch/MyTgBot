"""Тестовый период (бесплатный)"""
from aiogram import Router, F
from aiogram.types import CallbackQuery
from bot.keyboards import get_main_keyboard, get_trial_confirm_keyboard
from bot.utils.database import get_or_create_user, create_subscription, add_subscription_server
from bot.utils.remnawave import create_vpn_user, enable_vpn_user, get_all_squads, add_user_to_squads
from config import TRIAL_DAYS, TRIAL_TRAFFIC, TRIAL_DEVICES, TRIAL_SERVERS
import asyncio

router = Router()


@router.callback_query(F.data == "get_trial")
async def get_trial(callback: CallbackQuery):
    """Предложение тестового периода"""
    telegram_id = callback.from_user.id
    
    await callback.message.edit_text(
        f"🧪 ТЕСТОВЫЙ ПЕРИОД\n\n"
        f"Получи бесплатный доступ на {TRIAL_DAYS} дня:\n\n"
        f"📊 Трафик: {TRIAL_TRAFFIC // (1024**3)} GB\n"
        f"📱 Устройства: {TRIAL_DEVICES}\n"
        f"🌍 Серверы: {TRIAL_SERVERS} (на выбор)\n\n"
        f"После окончания теста можешь купить полную версию!",
        reply_markup=get_trial_confirm_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "confirm_trial")
async def confirm_trial(callback: CallbackQuery):
    """Подтверждение тестового периода"""
    telegram_id = callback.from_user.id
    
    try:
        # Получаем доступные сквады
        squads = await get_all_squads()
        
        if not squads:
            await callback.message.edit_text("❌ Нет доступных серверов!", reply_markup=get_main_keyboard(has_subscription=True, has_trial=True))
            await callback.answer()
            return
        
        # Создаём VPN пользователя (включен)
        vpn_user = await create_vpn_user(
            username=f"trial_{telegram_id}",
            traffic_limit_bytes=TRIAL_TRAFFIC,
            expire_days=TRIAL_DAYS,
            is_disabled=False  # Сразу включён для теста
        )
        
        # Сохраняем в БД
        user_id = get_or_create_user(telegram_id)
        
        # Отмечаем что получил тестовую подписку
        import sqlite3
        conn = sqlite3.connect('vpn_bot.db')
        cursor = conn.cursor()
        cursor.execute('UPDATE users SET has_trial = 1 WHERE id = ?', (user_id,))
        conn.commit()
        conn.close()
        
        sub_id = create_subscription(
            user_id=user_id,
            remnawave_uuid=vpn_user["uuid"],
            short_uuid=vpn_user["short_uuid"],
            username=vpn_user["username"],
            duration_days=TRIAL_DAYS,
            traffic_limit_bytes=TRIAL_TRAFFIC,
            devices_limit=TRIAL_DEVICES,
            servers_count=1,
            reset_type="none",
            is_trial=True,
            is_paid=True  # Тест бесплатен
        )
        
        # Добавляем первую ноду (сквад)
        first_squad = squads[0]
        
        # Добавляем пользователя в сквад
        try:
            await add_user_to_squads(vpn_user["uuid"], [str(first_squad.uuid)])
        except Exception as e:
            print(f"Error adding to squad: {e}")
        
        # Формируем ссылку
        sub_url = vpn_user.get("subscription_url", "")
        
        await callback.message.edit_text(
            f"✅ ТЕСТОВЫЙ ПЕРИОД АКТИВИРОВАН!\n\n"
            f"📅 Действителен до: {TRIAL_DAYS} дней\n"
            f"📊 Трафик: {TRIAL_TRAFFIC // (1024**3)} GB\n"
            f"📱 Устройства: {TRIAL_DEVICES}\n"
            f"🌍 Сервер: {first_squad.name}\n\n"
            f"🔗 ССЫЛКА НА ПОДКЛЮЧЕНИЕ:\n{sub_url}\n\n"
            f"После окончания теста — можешь купить полную версию!",
            reply_markup=get_main_keyboard(has_subscription=True, has_trial=True)
        )
        
    except Exception as e:
        await callback.message.edit_text(
            f"❌ Ошибка при активации теста:\n{e}",
            reply_markup=get_main_keyboard(has_subscription=True, has_trial=True)
        )
    
    await callback.answer()

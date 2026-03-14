"""Конструктор тарифов"""
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from bot.keyboards import (
    get_duration_keyboard, get_devices_keyboard, get_traffic_keyboard,
    get_reset_keyboard, get_confirm_keyboard, get_back_to_tariff_keyboard,
    get_tariff_options_keyboard, get_main_keyboard
)
from bot.utils.database import get_or_create_user, create_subscription, add_subscription_server, get_user_subscriptions
from bot.utils.remnawave import create_vpn_user, enable_vpn_user, get_all_squads, add_user_to_squads
from config import TARIFFS, YOOMONEY_WALLET
import asyncio
import json

router = Router()

# Состояния для конструктора
class TariffBuilder(StatesGroup):
    duration = State()      # Выбор срока
    devices = State()       # Выбор устройств
    traffic = State()      # Выбор трафика
    reset = State()        # Выбор сброса
    servers = State()       # Выбор серверов
    confirm = State()       # Подтверждение


# Хранилище временных данных (в реальном проекте использовать Redis)
user_data = {}


def calculate_price(duration: int, devices: int, traffic: str, reset: str, servers: int) -> float:
    """Рассчитать цену тарифа"""
    # Базовая цена из конфига (уже с учётом скидки)
    base = TARIFFS["duration"][duration]
    price = base.get("price", 150)
    
    # Устройства (первое бесплатно)
    if devices > 1:
        price += TARIFFS["devices"][devices]["price"]
    
    # Трафик
    price += TARIFFS["traffic"][traffic]["price"]
    
    # Сброс
    price += TARIFFS["reset"][reset]["price"]
    
    # Серверы (первый бесплатно)
    if servers > 1:
        price += TARIFFS["servers"][servers]["price"]
    
    return round(price, 2)


def get_tariff_summary(data: dict) -> str:
    """Получить текстовое резюме тарифа"""
    duration_info = TARIFFS["duration"].get(data.get("duration", 30), {})
    devices_info = TARIFFS["devices"].get(data.get("devices", 1), {})
    traffic_info = TARIFFS["traffic"].get(data.get("traffic", "5gb"), {})
    reset_info = TARIFFS["reset"].get(data.get("reset", "none"), {})
    
    summary = f"""🛠️ КОНСТРУКТОР ТАРИФА

📅 Срок: {duration_info.get("name", "30 дней")}
📱 Устройства: {devices_info.get("name", "1 устройство")}
📊 Трафик: {traffic_info.get("name", "5 GB")}
🔄 Сброс: {reset_info.get("name", "Без сброса")}
🌍 Серверы: {data.get("servers_count", 0)}

💵 ИТОГО: {data.get("price", 0)}₽"""
    
    return summary


@router.callback_query(F.data == "create_tariff")
async def start_tariff_builder(callback: CallbackQuery, state: FSMContext):
    """Начать создание тарифа"""
    telegram_id = callback.from_user.id
    
    # Проверяем, есть ли подписки
    user_id = get_or_create_user(telegram_id)
    subs = get_user_subscriptions(user_id)
    has_subscription = len(subs) > 0
    
    if has_subscription:
        # Показываем варианты
        await callback.message.edit_text(
            "🛠️ ЧТО ДЕЛАЕМ?\n\n"
            "⏰ Продлить — добавить время к текущей\n"
            "➕ Создать новую — новая подписка\n"
            "✏️ Изменить — поменять параметры",
            reply_markup=get_tariff_options_keyboard()
        )
    else:
        # Нет подписки - сразу создаём
        user_data[telegram_id] = {
            "action": "new",
            "duration": 30,
            "devices": 1,
            "traffic": "10gb",
            "reset": "none",
            "servers": [],
            "servers_count": 0,
        }
        
        await state.set_state(TariffBuilder.duration)
        
        await callback.message.edit_text(
            "📅 Выбери срок действия:",
            reply_markup=get_duration_keyboard()
        )
    
    await callback.answer()


@router.callback_query(F.data == "tariff_new")
async def tariff_new(callback: CallbackQuery, state: FSMContext):
    """Создать новую подписку"""
    telegram_id = callback.from_user.id
    
    # Проверяем есть ли неоплаченные подписки
    user_id = get_or_create_user(telegram_id)
    subs = get_user_subscriptions(user_id)
    has_unpaid = any(not sub[12] for sub in subs)  # is_paid = False
    
    if has_unpaid:
        await callback.message.edit_text(
            "❌ У вас есть неоплаченные подписки!\n\n"
            "Сначала оплатите существующие или дождитесь истечения срока.",
            reply_markup=get_main_keyboard(has_subscription=True, has_trial=False)
        )
        await callback.answer()
        return
    
    user_data[telegram_id] = {
        "action": "new",
        "duration": 30,
        "devices": 1,
        "traffic": "10gb",
        "reset": "none",
        "servers": [],
        "servers_count": 0,
    }
    
    await state.set_state(TariffBuilder.duration)
    
    await callback.message.edit_text(
        "📅 Выбери срок действия:",
        reply_markup=get_duration_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "tariff_extend")
async def tariff_extend(callback: CallbackQuery):
    """Продлить подписку"""
    telegram_id = callback.from_user.id
    
    await callback.message.edit_text(
        "⏰ ПРОДЛЕНИЕ ПОДПИСКИ\n\n"
        "Выбери, на сколько продлить:",
        reply_markup=get_duration_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "tariff_modify")
async def tariff_modify(callback: CallbackQuery):
    """Изменить тариф"""
    telegram_id = callback.from_user.id
    
    await callback.message.edit_text(
        "✏️ ИЗМЕНЕНИЕ ТАРИФА\n\n"
        "Выбери новые параметры:\n\n"
        "Сначала выбери срок:",
        reply_markup=get_duration_keyboard()
    )
    await callback.answer()


# === Выбор срока ===
@router.callback_query(F.data.startswith("duration_"))
async def select_duration(callback: CallbackQuery, state: FSMContext):
    telegram_id = callback.from_user.id
    
    # Проверяем, есть ли данные
    if telegram_id not in user_data:
        await callback.message.edit_text(
            "⏳ Начни заново: /start",
            reply_markup=get_main_keyboard(has_subscription=True, has_trial=True)
        )
        await callback.answer()
        return
    
    duration = int(callback.data.split("_")[1])
    
    user_data[telegram_id]["duration"] = duration
    
    await state.set_state(TariffBuilder.devices)
    
    await callback.message.edit_text(
        "📱 Выбери количество устройств:\n"
        "(1 устройство - бесплатно)",
        reply_markup=get_devices_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "back_to_duration")
async def back_to_duration(callback: CallbackQuery, state: FSMContext):
    await state.set_state(TariffBuilder.duration)
    await callback.message.edit_text(
        "📅 Выбери срок действия:",
        reply_markup=get_duration_keyboard()
    )
    await callback.answer()


# === Выбор устройств ===
@router.callback_query(F.data.startswith("devices_"))
async def select_devices(callback: CallbackQuery, state: FSMContext):
    telegram_id = callback.from_user.id
    
    if telegram_id not in user_data:
        await callback.message.edit_text("⏳ Начни заново: /start", reply_markup=get_main_keyboard(has_subscription=True, has_trial=True))
        await callback.answer()
        return
    
    devices = int(callback.data.split("_")[1])
    
    user_data[telegram_id]["devices"] = devices
    
    await state.set_state(TariffBuilder.traffic)
    
    await callback.message.edit_text(
        "📊 Выбери трафик:\n"
        "(5 GB - бесплатно, ∞ - +200₽)",
        reply_markup=get_traffic_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "back_to_devices")
async def back_to_devices(callback: CallbackQuery, state: FSMContext):
    await state.set_state(TariffBuilder.devices)
    await callback.message.edit_text(
        "📱 Выбери количество устройств:\n"
        "(1 устройство - бесплатно)",
        reply_markup=get_devices_keyboard()
    )
    await callback.answer()


# === Выбор трафика ===
@router.callback_query(F.data.startswith("traffic_"))
async def select_traffic(callback: CallbackQuery, state: FSMContext):
    telegram_id = callback.from_user.id
    
    if telegram_id not in user_data:
        await callback.message.edit_text("⏳ Начни заново: /start", reply_markup=get_main_keyboard(has_subscription=True, has_trial=True))
        await callback.answer()
        return
    
    traffic = callback.data.split("_")[1]
    
    user_data[telegram_id]["traffic"] = traffic
    
    await state.set_state(TariffBuilder.reset)
    
    await callback.message.edit_text(
        "🔄 Выбери сброс трафика:",
        reply_markup=get_reset_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "back_to_traffic")
async def back_to_traffic(callback: CallbackQuery, state: FSMContext):
    await state.set_state(TariffBuilder.traffic)
    await callback.message.edit_text(
        "📊 Выбери трафик:\n"
        "(5 GB - бесплатно, ∞ - +200₽)",
        reply_markup=get_traffic_keyboard()
    )
    await callback.answer()


# === Выбор сброса ===
@router.callback_query(F.data.startswith("reset_"))
async def select_reset(callback: CallbackQuery, state: FSMContext):
    telegram_id = callback.from_user.id
    
    if telegram_id not in user_data:
        await callback.message.edit_text("⏳ Начни заново: /start", reply_markup=get_main_keyboard(has_subscription=True, has_trial=True))
        await callback.answer()
        return
    
    reset_type = callback.data.split("_")[1]
    
    user_data[telegram_id]["reset"] = reset_type
    
    # Переходим к выбору серверов
    await state.set_state(TariffBuilder.servers)
    
    # Получаем сквады
    try:
        squads = await get_all_squads()
        user_data[telegram_id]["available_squads"] = [
            {"uuid": str(s.uuid), "name": s.name}
            for s in squads
        ]
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка получения серверов: {e}")
        return
    
    # Показываем выбор серверов
    keyboard = get_servers_keyboard_squads(user_data[telegram_id]["available_squads"])
    
    await callback.message.edit_text(
        "🌍 Выбери серверы:\n"
        "(первый сервер - бесплатный)",
        reply_markup=keyboard
    )
    await callback.answer()


def get_servers_keyboard_squads(squads: list):
    """Клавиатура выбора серверов (сквадов)"""
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    
    keyboard = InlineKeyboardBuilder()
    
    for squad in squads:
        text = f"🌍 {squad['name']}"
        callback = f"server_{squad['uuid']}"
        keyboard.button(text=text, callback_data=callback)
    
    keyboard.button(text="✅ Готово", callback_data="servers_done")
    keyboard.button(text="🔙 Назад", callback_data="back_to_reset")
    keyboard.adjust(1, repeat=True)
    return keyboard.as_markup()


@router.callback_query(F.data == "back_to_reset")
async def back_to_reset(callback: CallbackQuery, state: FSMContext):
    await state.set_state(TariffBuilder.reset)
    await callback.message.edit_text(
        "🔄 Выбери сброс трафика:",
        reply_markup=get_reset_keyboard()
    )
    await callback.answer()


# === Выбор серверов ===
@router.callback_query(F.data.startswith("server_"))
async def select_server(callback: CallbackQuery, state: FSMContext):
    telegram_id = callback.from_user.id
    
    if telegram_id not in user_data:
        await callback.answer("⏳ Начни заново: /start")
        return
    
    node_uuid = callback.data.split("_")[1]
    
    # Добавляем или убираем сервер
    if node_uuid not in user_data[telegram_id]["servers"]:
        user_data[telegram_id]["servers"].append(node_uuid)
    
    user_data[telegram_id]["servers_count"] = len(user_data[telegram_id]["servers"])
    
    # Обновляем клавиатуру
    await callback.answer(f"Выбрано серверов: {user_data[telegram_id]['servers_count']}")


@router.callback_query(F.data == "servers_done")
async def servers_done(callback: CallbackQuery, state: FSMContext):
    telegram_id = callback.from_user.id
    
    if telegram_id not in user_data:
        await callback.message.edit_text("⏳ Начни заново: /start", reply_markup=get_main_keyboard(has_subscription=True, has_trial=True))
        await callback.answer()
        return
    
    data = user_data[telegram_id]
    
    if data["servers_count"] < 1:
        await callback.answer("Выбери хотя бы 1 сервер!", show_alert=True)
        return
    
    # Рассчитываем цену
    data["price"] = calculate_price(
        data["duration"],
        data["devices"],
        data["traffic"],
        data["reset"],
        data["servers_count"]
    )
    
    await state.set_state(TariffBuilder.confirm)
    
    summary = get_tariff_summary(data)
    
    await callback.message.edit_text(
        summary + "\n\nПереходим к оплате...",
        reply_markup=get_confirm_keyboard()
    )
    await callback.answer()


# === Подтверждение ===
@router.callback_query(F.data == "confirm_payment")
async def confirm_payment(callback: CallbackQuery, state: FSMContext):
    telegram_id = callback.from_user.id
    
    if telegram_id not in user_data:
        await callback.message.edit_text("⏳ Начни заново: /start", reply_markup=get_main_keyboard(has_subscription=True, has_trial=True))
        await callback.answer()
        return
    
    data = user_data[telegram_id]
    
    # Здесь будет создание платежа через ЮMoney
    # Пока просто создаём пользователя в RemnaWave (выключенным)
    
    try:
        user_id = get_or_create_user(telegram_id)
        
        # Получаем номер покупки
        import sqlite3
        conn = sqlite3.connect('vpn_bot.db')
        cursor = conn.cursor()
        cursor.execute('SELECT purchase_count FROM users WHERE id = ?', (user_id,))
        result = cursor.fetchone()
        purchase_count = result[0] if result else 0
        
        # Генерируем username: user_telegram_id или user_telegram_id_001
        if purchase_count == 0:
            username = f"user_{telegram_id}"
        else:
            username = f"user_{telegram_id}_{purchase_count:03d}"
        
        # Увеличиваем счётчик
        cursor.execute('UPDATE users SET purchase_count = purchase_count + 1 WHERE id = ?', (user_id,))
        conn.commit()
        conn.close()
        
        # Параметры
        traffic_limit = TARIFFS["traffic"][data["traffic"]]["limit"]
        if data["traffic"] == "unlimited":  # Безлимит
            traffic_limit = 0  # 0 = unlimited
        
        # Создаём VPN пользователя (выключен)
        vpn_user = await create_vpn_user(
            username=username,
            traffic_limit_bytes=traffic_limit,
            expire_days=TARIFFS["duration"][data["duration"]]["days"],
            is_disabled=True  # Выключен до оплаты
        )
        
        # Сохраняем в БД
        sub_id = create_subscription(
            user_id=user_id,
            remnawave_uuid=vpn_user["uuid"],
            short_uuid=vpn_user["short_uuid"],
            username=vpn_user["username"],
            duration_days=TARIFFS["duration"][data["duration"]]["days"],
            traffic_limit_bytes=traffic_limit,
            devices_limit=data["devices"],
            servers_count=data["servers_count"],
            reset_type=data["reset"],
            is_paid=False,
            price=data["price"]
        )
        
        # Сохраняем выбранные серверы
        for server_uuid in data["servers"]:
            node_info = next((n for n in data.get("available_squads", []) if n["uuid"] == server_uuid), None)
            if node_info:
                add_subscription_server(sub_id, server_uuid, node_info["name"], node_info.get("country_code"))
        
        # Сохраняем ID подписки
        user_data[telegram_id]["subscription_id"] = sub_id
        user_data[telegram_id]["vpn_uuid"] = vpn_user["uuid"]
        
        # Создаём ссылку на оплату (по документации ЮMoney)
        # quickpay-form=button - форма кнопки
        payment_url = f"https://yoomoney.ru/quickpay/confirm?receiver={YOOMONEY_WALLET}&quickpay-form=button&paymentType=AC&sum={data['price']}&label={sub_id}"
        
        await callback.message.edit_text(
            f"💳 ОПЛАТА ПОДПИСКИ\n\n"
            f"💵 Сумма: {data['price']}₽\n\n"
            f"Нажми кнопку ниже для оплаты",
            reply_markup=get_payment_keyboard(payment_url)
        )
        
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка: {e}")
    
    await callback.answer()


def get_payment_keyboard(payment_url: str):
    """Кнопка оплаты"""
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="💳 Перейти к оплате", url=payment_url)
    keyboard.button(text="✅ Я оплатил", callback_data="check_payment")
    keyboard.button(text="❌ Отмена", callback_data="cancel_payment")
    return keyboard.as_markup()


# === Отмена ===
@router.callback_query(F.data == "cancel_payment")
async def cancel_payment(callback: CallbackQuery, state: FSMContext):
    telegram_id = callback.from_user.id
    
    # Удаляем данные
    if telegram_id in user_data:
        del user_data[telegram_id]
    
    await state.clear()
    
    await callback.message.edit_text(
        "❌ Оплата отменена.\n\n"
        "Для создания нового тарифа нажми /start",
    )
    await callback.answer()

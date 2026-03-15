"""Клавиатуры бота"""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, KeyboardButton, ReplyKeyboardMarkup, WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder
from config import TARIFFS, WEBHOOK_URL


def get_main_keyboard(has_subscription: bool = False, has_trial: bool = False):
    """Главная клавиатура"""
    keyboard = InlineKeyboardBuilder()
    
    # Web App кнопка
    keyboard.button(text="🌐 Открыть App", web_app=WebAppInfo(url="https://test.cloaknet.site/miniapp"))
    
    # Кабинет - только если есть подписка и мы не в кабинете
    if has_subscription:
        keyboard.button(text="📱 Кабинет", callback_data="my_subscriptions")
    
    # Создать тариф - всегда показываем
    keyboard.button(text="🛠️ Создать тариф", callback_data="create_tariff")
    
    # Тестовый период - только если ещё не получал
    if not has_trial:
        keyboard.button(text="💳 Тестовый период", callback_data="get_trial")
    
    keyboard.adjust(1, 2)
    return keyboard.as_markup()


def get_cabinet_keyboard(has_unpaid: bool = False, payment_url: str = None):
    """Клавиатура для кабинета"""
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="🏠 Главное меню", callback_data="back_to_main")
    
    # Блокируем создание тарифа если есть неоплаченные
    if has_unpaid and payment_url:
        keyboard.button(text="💳 ОПЛАТИТЬ", url=payment_url)
        keyboard.button(text="❌ Удалить", callback_data="delete_unpaid")
    elif has_unpaid:
        keyboard.button(text="💳 Оплатить", callback_data="pay_unpaid")
        keyboard.button(text="❌ Удалить", callback_data="delete_unpaid")
    else:
        keyboard.button(text="🛠️ Создать тариф", callback_data="create_tariff")
    
    keyboard.adjust(1)
    return keyboard.as_markup()


def get_subscription_keyboard(subscription_id: int, is_paid: bool = False, is_active: bool = False):
    """Клавиатура для конкретной подписки"""
    keyboard = InlineKeyboardBuilder()
    
    if not is_paid:
        # Неоплаченная - показываем кнопку оплаты
        keyboard.button(text="💳 Оплатить", callback_data=f"pay_sub_{subscription_id}")
    
    if is_active:
        keyboard.button(text="📋 Инфо", callback_data=f"sub_info_{subscription_id}")
        keyboard.button(text="🔄 Продлить", callback_data=f"sub_renew_{subscription_id}")
    
    keyboard.button(text="🔙 Назад", callback_data="my_subscriptions")
    keyboard.adjust(1)
    return keyboard.as_markup()


def get_tariff_options_keyboard():
    """Клавиатура выбора: продлить, создать, изменить"""
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="⏰ Продлить", callback_data="tariff_extend")
    keyboard.button(text="➕ Создать новую", callback_data="tariff_new")
    keyboard.button(text="✏️ Изменить тариф", callback_data="tariff_modify")
    keyboard.button(text="🔙 Назад", callback_data="back_to_main")
    keyboard.adjust(1)
    return keyboard.as_markup()


def get_duration_keyboard():
    """Выбор срока"""
    keyboard = InlineKeyboardBuilder()
    for key, data in TARIFFS["duration"].items():
        text = f"{data['name']}"
        callback = f"duration_{key}"
        keyboard.button(text=text, callback_data=callback)
    keyboard.button(text="🔙 Назад", callback_data="back_to_main")
    keyboard.adjust(2, 2, 1)
    return keyboard.as_markup()


def get_devices_keyboard():
    """Выбор количества устройств"""
    keyboard = InlineKeyboardBuilder()
    for key, data in TARIFFS["devices"].items():
        text = f"{data['name']}"
        callback = f"devices_{key}"
        keyboard.button(text=text, callback_data=callback)
    keyboard.button(text="🔙 Назад", callback_data="back_to_duration")
    keyboard.adjust(3, 2, 2)
    return keyboard.as_markup()


def get_traffic_keyboard():
    """Выбор трафика"""
    keyboard = InlineKeyboardBuilder()
    for key, data in TARIFFS["traffic"].items():
        text = f"{data['name']}"
        callback = f"traffic_{key}"
        keyboard.button(text=text, callback_data=callback)
    keyboard.button(text="🔙 Назад", callback_data="back_to_devices")
    keyboard.adjust(2)
    return keyboard.as_markup()


def get_reset_keyboard():
    """Выбор сброса трафика"""
    keyboard = InlineKeyboardBuilder()
    for key, data in TARIFFS["reset"].items():
        text = f"{data['name']}"
        callback = f"reset_{key}"
        keyboard.button(text=text, callback_data=callback)
    keyboard.button(text="🔙 Назад", callback_data="back_to_traffic")
    keyboard.adjust(3)
    return keyboard.as_markup()


def get_servers_keyboard(nodes: list):
    """Выбор серверов (из доступных нод)"""
    keyboard = InlineKeyboardBuilder()
    
    # Группируем по странам
    country_emoji = {
        "GB": "🇬🇧", "NL": "🇳🇱", "FI": "🇫🇮", "RU": "🇷🇺", "DE": "🇩🇪",
        "US": "🇺🇸", "UA": "🇺🇦", "KZ": "🇰🇿", "BY": "🇧🇾"
    }
    
    for node in nodes:
        emoji = country_emoji.get(node.country_code, "🌍")
        text = f"{emoji} {node.name}"
        callback = f"server_{node.uuid}"
        keyboard.button(text=text, callback_data=callback)
    
    keyboard.button(text="✅ Готово", callback_data="servers_done")
    keyboard.button(text="🔙 Назад", callback_data="back_to_reset")
    keyboard.adjust(1, repeat=True)
    return keyboard.as_markup()


def get_confirm_keyboard():
    """Подтверждение оплаты"""
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="💳 Оплатить", callback_data="confirm_payment")
    keyboard.button(text="🔙 Изменить", callback_data="back_to_servers")
    return keyboard.as_markup()


def get_payment_keyboard(payment_url: str):
    """Кнопка оплаты"""
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="💳 Перейти к оплате", url=payment_url)
    keyboard.button(text="✅ Я оплатил", callback_data="check_payment")
    keyboard.button(text="❌ Отмена", callback_data="cancel_payment")
    return keyboard.as_markup()


def get_profile_keyboard(subscription_id: int):
    """Клавиатура профиля подписки"""
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="📋 Информация", callback_data=f"sub_info_{subscription_id}")
    keyboard.button(text="🔄 Продлить", callback_data=f"sub_renew_{subscription_id}")
    keyboard.button(text="🔙 К подпискам", callback_data="my_subscriptions")
    return keyboard.as_markup()


def get_back_to_tariff_keyboard():
    """Назад к редактированию тарифа"""
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="🔙 Изменить тариф", callback_data="create_tariff")
    return keyboard.as_markup()


def get_trial_confirm_keyboard():
    """Подтверждение тестового периода"""
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="✅ Получить тест", callback_data="confirm_trial")
    keyboard.button(text="🔙 Назад", callback_data="back_to_main")
    return keyboard.as_markup()

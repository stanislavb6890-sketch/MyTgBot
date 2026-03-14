"""Обработчик /start и регистрация"""
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from bot.keyboards import get_main_keyboard
from bot.utils.database import get_or_create_user, get_user_subscriptions, user_has_trial
from config import ADMIN_ID

router = Router()


@router.message(F.text == "/start")
async def cmd_start(message: Message):
    """Обработка /start"""
    telegram_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name or "друг"
    
    # Создаём/получаем пользователя
    user_id = get_or_create_user(telegram_id, username, first_name)
    
    # Проверяем подписки
    subs = get_user_subscriptions(user_id)
    has_subscription = len(subs) > 0
    has_trial_used = user_has_trial(telegram_id)
    
    if not has_subscription:
        # Первая регистрация - нет подписки
        text = f"👋 Привет, {first_name}!\n\n"
        text += "Вы ещё не оформляли у нас подписку.\n\n"
        text += "Хотите попробовать?"
    else:
        # Есть подписка
        text = f"👋 С возвращением, {first_name}!\n\n"
        text += "У вас есть доступ к кабинету."
    
    # Удаляем последние сообщения бота (не пользователя)
    try:
        chat_id = message.chat.id
        bot = message.bot
        history = await bot.get_chat_history(chat_id, limit=20)
        for msg in history:
            # Удаляем только сообщения бота
            if msg.from_user and msg.from_user.is_bot:
                try:
                    await bot.delete_message(chat_id, msg.message_id)
                except:
                    pass
    except Exception as e:
        print(f"Error deleting: {e}")
    
    # Отправляем новое
    await message.answer(text, reply_markup=get_main_keyboard(has_subscription, has_trial_used))


@router.callback_query(F.data == "back_to_main")
async def back_to_main(callback: CallbackQuery):
    """Возврат в главное меню"""
    telegram_id = callback.from_user.id
    username = callback.from_user.username
    first_name = callback.from_user.first_name or "друг"
    
    user_id = get_or_create_user(telegram_id, username, first_name)
    subs = get_user_subscriptions(user_id)
    has_subscription = len(subs) > 0
    has_trial_used = user_has_trial(telegram_id)
    
    if not has_subscription:
        text = f"👋 Привет, {first_name}!\n\n"
        text += "Вы ещё не оформляли у нас подписку.\n\n"
        text += "Хотите попробовать?"
    else:
        text = f"👋 С возвращением, {first_name}!\n\n"
        text += "У вас есть доступ к кабинету."
    
    await callback.message.edit_text(text, reply_markup=get_main_keyboard(has_subscription, has_trial_used))
    await callback.answer()


@router.message(F.text == "/admin")
async def cmd_admin(message: Message):
    """Админ-команда"""
    if message.from_user.id == ADMIN_ID:
        await message.answer("🔧 Панель администратора\n\n"
                           "/stats - Статистика\n"
                           "/users - Все пользователи")
    else:
        await message.answer("⛔ Доступ запрещён")


@router.message(F.text == "/help")
async def cmd_help(message: Message):
    """Справка"""
    await message.answer(
        "📖 Справка по боту\n\n"
        "🛠️ Создать тариф - сконструируй свой VPN\n"
        "📱 Кабинет - посмотреть подписки\n"
        "💳 Тестовый период - получить бесплатный тест на 3 дня\n\n"
        "По всем вопросам: @admin"
    )

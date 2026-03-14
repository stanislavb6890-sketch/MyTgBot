"""Админ-панель"""
import logging
from datetime import datetime
from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from config import ADMIN_ID
from bot.utils.database import get_db

logger = logging.getLogger(__name__)

admin_router = Router()


# Проверка админа
def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID


class AdminStates(StatesGroup):
    waiting_for_user_id = State()


# === Команды админа ===

@admin_router.message(Command("admin"))
async def admin_panel(message: types.Message):
    """Главная админ-панель"""
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Доступ запрещён")
        return
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
        [types.InlineKeyboardButton(text="👥 Пользователи", callback_data="admin_users")],
        [types.InlineKeyboardButton(text="💳 Платежи", callback_data="admin_payments")],
        [types.InlineKeyboardButton(text="🔗 Подписки", callback_data="admin_subs")],
        [types.InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast")],
    ])
    
    await message.answer("🔧 <b>Админ-панель</b>\n\nВыберите раздел:", reply_markup=keyboard)


# === Быстрые команды ===

@admin_router.message(Command("stats"))
async def cmd_stats(message: types.Message):
    """Статистика"""
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Доступ запрещён")
        return
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM subscriptions WHERE status = 'active'")
    active_subs = cursor.fetchone()[0]
    
    cursor.execute("SELECT SUM(amount) FROM payments WHERE status = 'paid'")
    total_revenue = cursor.fetchone()[0] or 0
    
    conn.close()
    
    await message.answer(f"""📊 <b>Статистика</b>

👥 Пользователей: {total_users}
🔗 Активных подписок: {active_subs}
💰 Доход: {total_revenue:.2f} ₽""")


@admin_router.message(Command("users"))
async def cmd_users(message: types.Message):
    """Список пользователей"""
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Доступ запрещён")
        return
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT telegram_id, username, first_name, created_at, has_trial, purchase_count
        FROM users
        ORDER BY created_at DESC
        LIMIT 20
    """)
    users = cursor.fetchall()
    conn.close()
    
    if not users:
        await message.answer("👥 Пользователей пока нет")
        return
    
    text = "👥 <b>Пользователи:</b>\n\n"
    for u in users:
        tg_id, username, first_name, created, has_trial, purchases = u
        name = first_name or username or "—"
        trial_mark = " ✅" if has_trial else ""
        text += f"• {name} (TG: {tg_id}){trial_mark}\n"
        text += f"  Покупок: {purchases} | {created[:10]}\n\n"
    
    await message.answer(text)


@admin_router.message(Command("payments"))
async def cmd_payments(message: types.Message):
    """Список платежей"""
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Доступ запрещён")
        return
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT p.amount, p.status, p.created_at, u.username, u.first_name
        FROM payments p
        JOIN users u ON p.user_id = u.id
        ORDER BY p.created_at DESC
        LIMIT 15
    """)
    payments = cursor.fetchall()
    
    cursor.execute("SELECT SUM(amount) FROM payments WHERE status = 'paid'")
    total = cursor.fetchone()[0] or 0
    
    conn.close()
    
    if not payments:
        await message.answer("💳 Платежей пока нет")
        return
    
    text = f"💳 <b>Платежи</b> (всего: {total:.2f} ₽)\n\n"
    for p in payments:
        amount, status, created, username, first_name = p
        name = first_name or username or "—"
        status_emoji = "✅" if status == "paid" else "⏳"
        text += f"{status_emoji} {amount:.2f} ₽ — {name} | {created[:16]}\n"
    
    await message.answer(text)


@admin_router.message(Command("subs"))
async def cmd_subs(message: types.Message):
    """Список подписок"""
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Доступ запрещён")
        return
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT s.username, s.status, s.expires_at, s.is_trial, u.first_name, u.username
        FROM subscriptions s
        JOIN users u ON s.user_id = u.id
        ORDER BY s.created_at DESC
        LIMIT 15
    """)
    subs = cursor.fetchall()
    conn.close()
    
    if not subs:
        await message.answer("🔗 Подписок пока нет")
        return
    
    text = "🔗 <b>Подписки:</b>\n\n"
    for s in subs:
        username, status, expires, is_trial, first_name, uname = s
        name = first_name or uname or username
        status_text = "✅" if status == "active" else "❌"
        trial_text = " 🧪" if is_trial else ""
        text += f"{status_text} {name}{trial_text} — истекает {expires[:16]}\n"
    
    await message.answer(text)


# === Статистика ===

@admin_router.callback_query(F.data == "admin_stats")
async def stats_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён")
        return
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Статистика пользователей
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM users WHERE is_active = 1")
    active_users = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM users WHERE has_trial = 1")
    trial_users = cursor.fetchone()[0]
    
    # Статистика подписок
    cursor.execute("SELECT COUNT(*) FROM subscriptions WHERE status = 'active'")
    active_subs = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM subscriptions WHERE status = 'disabled'")
    disabled_subs = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM subscriptions WHERE is_trial = 1")
    trial_subs = cursor.fetchone()[0]
    
    # Статистика платежей
    cursor.execute("SELECT COUNT(*) FROM payments WHERE status = 'paid'")
    paid_payments = cursor.fetchone()[0]
    
    cursor.execute("SELECT SUM(amount) FROM payments WHERE status = 'paid'")
    total_revenue = cursor.fetchone()[0] or 0
    
    conn.close()
    
    stats_text = f"""📊 <b>Статистика бота</b>

👥 <b>Пользователи:</b>
• Всего: {total_users}
• Активных: {active_users}
• Использовали пробный: {trial_users}

🔗 <b>Подписки:</b>
• Активных: {active_subs}
• Отключено: {disabled_subs}
• Пробных: {trial_subs}

💳 <b>Платежи:</b>
• Успешных: {paid_payments}
• Общий доход: {total_revenue:.2f} ₽"""

    await callback.message.edit_text(stats_text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")]
    ]))
    await callback.answer()


# === Пользователи ===

@admin_router.callback_query(F.data == "admin_users")
async def users_callback(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён")
        return
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, telegram_id, username, first_name, created_at, has_trial, purchase_count
        FROM users
        ORDER BY created_at DESC
        LIMIT 20
    """)
    users = cursor.fetchall()
    conn.close()
    
    if not users:
        await callback.message.edit_text("👥 Пользователей пока нет", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")]
        ]))
        return
    
    text = "👥 <b>Последние пользователи:</b>\n\n"
    for u in users:
        uid, tg_id, username, first_name, created, has_trial, purchases = u
        name = first_name or username or "—"
        trial_mark = " ✅" if has_trial else ""
        text += f"• {name} (ID: {uid}, TG: {tg_id}){trial_mark}\n"
        text += f"  Покупок: {purchases} | Дата: {created[:10]}\n\n"
    
    await callback.message.edit_text(text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")]
    ]))
    await callback.answer()


# === Платежи ===

@admin_router.callback_query(F.data == "admin_payments")
async def payments_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён")
        return
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT p.id, p.amount, p.status, p.created_at, u.username, u.first_name
        FROM payments p
        JOIN users u ON p.user_id = u.id
        ORDER BY p.created_at DESC
        LIMIT 15
    """)
    payments = cursor.fetchall()
    
    cursor.execute("SELECT SUM(amount) FROM payments WHERE status = 'paid'")
    total = cursor.fetchone()[0] or 0
    
    conn.close()
    
    if not payments:
        await callback.message.edit_text("💳 Платежей пока нет", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")]
        ]))
        return
    
    text = f"💳 <b>Последние платежи</b> (всего: {total:.2f} ₽)\n\n"
    for p in payments:
        pid, amount, status, created, username, first_name = p
        name = first_name or username or "—"
        status_emoji = "✅" if status == "paid" else "⏳"
        text += f"{status_emoji} {amount:.2f} ₽ — {name}\n"
        text += f"   Дата: {created[:16]}\n\n"
    
    await callback.message.edit_text(text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")]
    ]))
    await callback.answer()


# === Подписки ===

@admin_router.callback_query(F.data == "admin_subs")
async def subs_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён")
        return
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT s.id, s.username, s.status, s.expires_at, s.is_trial, u.first_name, u.username
        FROM subscriptions s
        JOIN users u ON s.user_id = u.id
        ORDER BY s.created_at DESC
        LIMIT 15
    """)
    subs = cursor.fetchall()
    conn.close()
    
    if not subs:
        await callback.message.edit_text("🔗 Подписок пока нет", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")]
        ]))
        return
    
    text = "🔗 <b>Последние подписки:</b>\n\n"
    for s in subs:
        sid, username, status, expires, is_trial, first_name, uname = s
        name = first_name or uname or username
        status_text = "✅ Активна" if status == "active" else "❌ Отключена"
        trial_text = " 🧪" if is_trial else ""
        text += f"{status_text}{trial_text} — {name}\n"
        text += f"   Истекает: {expires[:16]}\n\n"
    
    await callback.message.edit_text(text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")]
    ]))
    await callback.answer()


# === Рассылка ===

@admin_router.callback_query(F.data == "admin_broadcast")
async def broadcast_callback(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён")
        return
    
    await callback.message.edit_text(
        "📢 <b>Рассылка</b>\n\nВведите текст сообщения для всех пользователей:",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="🔙 Отмена", callback_data="admin_back")]
        ])
    )
    await state.set_state(AdminStates.waiting_for_user_id)
    await callback.answer()


@admin_router.message(AdminStates.waiting_for_user_id)
async def broadcast_send(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Доступ запрещён")
        return
    
    broadcast_text = message.text
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT telegram_id FROM users WHERE is_active = 1")
    users = cursor.fetchall()
    conn.close()
    
    sent = 0
    failed = 0
    
    # Импортируем Bot здесь, чтобы избежать циклического импорта
    from aiogram import Bot
    from config import BOT_TOKEN
    bot = Bot(token=BOT_TOKEN)
    
    for (tg_id,) in users:
        try:
            await bot.send_message(tg_id, broadcast_text)
            sent += 1
        except Exception as e:
            logger.error(f"Не удалось отправить {tg_id}: {e}")
            failed += 1
    
    await bot.session.close()
    
    await message.answer(f"✅ Рассылка завершена!\n\nОтправлено: {sent}\nОшибок: {failed}")
    await state.clear()


# === Назад ===

@admin_router.callback_query(F.data == "admin_back")
async def back_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён")
        return
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
        [types.InlineKeyboardButton(text="👥 Пользователи", callback_data="admin_users")],
        [types.InlineKeyboardButton(text="💳 Платежи", callback_data="admin_payments")],
        [types.InlineKeyboardButton(text="🔗 Подписки", callback_data="admin_subs")],
        [types.InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast")],
    ])
    
    await callback.message.edit_text("🔧 <b>Админ-панель</b>\n\nВыберите раздел:", reply_markup=keyboard)
    await callback.answer()

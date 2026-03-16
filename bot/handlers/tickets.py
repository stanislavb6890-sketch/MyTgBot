"""Обработчики тикетов для бота"""
import logging
from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from config import ADMIN_ID
from bot.utils.database import get_db

logger = logging.getLogger(__name__)

ticket_router = Router()


# Состояния для создания тикета
class TicketStates(StatesGroup):
    waiting_subject = State()
    waiting_text = State()
    waiting_reply = State()


# === ПОЛЬЗОВАТЕЛЬ ===

@ticket_router.message(Command("support"))
@ticket_router.message(F.text == "🎫 Поддержка")
async def cmd_support(message: types.Message, state: FSMContext):
    """Начать создание тикета"""
    await message.answer(
        "🎫 <b>Создание тикета</b>\n\n"
        "Опишите вашу проблему.\n"
        "Сначала введите <b>тему</b> (кратко):",
        parse_mode="HTML"
    )
    await state.set_state(TicketStates.waiting_subject)


@ticket_router.message(TicketStates.waiting_subject)
async def ticket_subject(message: types.Message, state: FSMContext):
    """Получили тему"""
    subject = message.text.strip()
    if len(subject) < 3:
        await message.answer("Тема слишком короткая. Попробуйте ещё раз:")
        return
    
    await state.update_data(subject=subject)
    await message.answer(
        "Теперь опишите <b>подробности</b> проблемы:",
        parse_mode="HTML"
    )
    await state.set_state(TicketStates.waiting_text)


@ticket_router.message(TicketStates.waiting_text)
async def ticket_text(message: types.Message, state: FSMContext):
    """Получили описание - создаём тикет"""
    text = message.text.strip()
    if len(text) < 5:
        await message.answer("Описание слишком короткое. Попробуйте ещё раз:")
        return
    
    data = await state.get_data()
    subject = data["subject"]
    
    # Получаем user_id
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT id FROM users WHERE telegram_id = ?", (message.from_user.id,))
    row = cursor.fetchone()
    
    if not row:
        conn.close()
        await message.answer("❌ Вы не зарегистрированы в боте")
        await state.clear()
        return
    
    user_id = row[0]
    
    # Создаём тикет
    cursor.execute("""
        INSERT INTO tickets (user_id, subject, status)
        VALUES (?, ?, 'open')
    """, (user_id, subject))
    ticket_id = cursor.lastrowid
    
    # Первое сообщение
    cursor.execute("""
        INSERT INTO ticket_messages (ticket_id, user_id, text, is_admin)
        VALUES (?, ?, ?, 0)
    """, (ticket_id, user_id, text))
    
    conn.commit()
    conn.close()
    
    await state.clear()
    
    # Подтверждение
    await message.answer(
        f"✅ <b>Тикет #{ticket_id} создан!</b>\n\n"
        f"📝 Тема: {subject}\n"
        f"📄 Описание: {text[:100]}...\n\n"
        "Мы ответим вам в ближайшее время.\n"
        "Для просмотра ваших тикетов используйте /mytickets",
        parse_mode="HTML"
    )
    
    # Уведомляем админа
    try:
        from aiogram import Bot
        from config import BOT_TOKEN
        bot = Bot(token=BOT_TOKEN)
        await bot.send_message(
            ADMIN_ID,
            f"🎫 <b>Новый тикет #{ticket_id}</b>\n\n"
            f"👤 {message.from_user.first_name} (@{message.from_user.username or 'нет'})\n"
            f"📝 Тема: {subject}\n\n"
            f"📄 {text[:200]}",
            parse_mode="HTML"
        )
        await bot.session.close()
    except Exception as e:
        logger.error(f"Ошибка уведомления админа: {e}")


@ticket_router.message(Command("mytickets"))
async def cmd_my_tickets(message: types.Message):
    """Мои тикеты"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, subject, status, created_at
        FROM tickets
        WHERE user_id = (SELECT id FROM users WHERE telegram_id = ?)
        ORDER BY created_at DESC
        LIMIT 10
    """, (message.from_user.id,))
    tickets = cursor.fetchall()
    conn.close()
    
    if not tickets:
        await message.answer(
            "📬 <b>У вас нет тикетов</b>\n\n"
            "Напишите /support чтобы создать новый тикет",
            parse_mode="HTML"
        )
        return
    
    status_emoji = {"open": "🔴", "in_progress": "🟡", "closed": "✅"}
    status_text = {"open": "Открыт", "in_progress": "В работе", "closed": "Закрыт"}
    
    text = "📬 <b>Ваши тикеты:</b>\n\n"
    for tid, subject, status, created in tickets:
        emoji = status_emoji.get(status, "⚪")
        text += f"{emoji} #{tid} - {subject}\n"
        text += f"   Статус: {status_text.get(status, status)} | {created[:10]}\n\n"
    
    await message.answer(text, parse_mode="HTML")


# === АДМИН ===

@ticket_router.message(Command("tickets"))
async def cmd_admin_tickets(message: types.Message):
    """Список тикетов для админа"""
    if message.from_user.id != ADMIN_ID:
        return
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Получаем открытые тикеты
    cursor.execute("""
        SELECT t.id, t.subject, t.status, u.telegram_id, u.first_name, u.username
        FROM tickets t
        JOIN users u ON t.user_id = u.id
        WHERE t.status IN ('open', 'in_progress')
        ORDER BY t.created_at DESC
        LIMIT 15
    """)
    tickets = cursor.fetchall()
    conn.close()
    
    if not tickets:
        await message.answer("🎫 <b>Нет открытых тикетов</b>", parse_mode="HTML")
        return
    
    status_emoji = {"open": "🔴", "in_progress": "🟡"}
    
    text = "🎫 <b>Тикеты</b>\n\n"
    keyboard_buttons = []
    
    for tid, subject, status, tg_id, first_name, username in tickets:
        emoji = status_emoji.get(status, "⚪")
        name = first_name or username or "?"
        text += f"{emoji} #{tid} | {name} | {subject[:30]}\n"
        keyboard_buttons.append([
            types.InlineKeyboardButton(text=f"{emoji} #{tid} - {name}", callback_data=f"aticket_{tid}")
        ])
    
    await message.answer(text, parse_mode="HTML", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=keyboard_buttons))


@ticket_router.callback_query(F.data.startswith("aticket_"))
async def callback_ticket(callback: types.CallbackQuery):
    """Просмотр тикета админом"""
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔")
        return
    
    ticket_id = int(callback.data.split("_")[1])
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Информация о тикете
    cursor.execute("""
        SELECT t.id, t.subject, t.status, t.created_at, u.telegram_id, u.first_name, u.username
        FROM tickets t
        JOIN users u ON t.user_id = u.id
        WHERE t.id = ?
    """, (ticket_id,))
    ticket = cursor.fetchone()
    
    if not ticket:
        conn.close()
        await callback.answer("Тикет не найден")
        return
    
    tid, subject, status, created, tg_id, first_name, username = ticket
    user_name = first_name or username or "?"
    
    # Сообщения
    cursor.execute("""
        SELECT text, is_admin, created_at
        FROM ticket_messages
        WHERE ticket_id = ?
        ORDER BY created_at ASC
    """, (ticket_id,))
    messages = cursor.fetchall()
    conn.close()
    
    status_text = {"open": "Открыт", "in_progress": "В работе", "closed": "Закрыт"}
    
    text = f"🎫 <b>Тикет #{tid}</b>\n\n"
    text += f"👤 <b>{user_name}</b> (TG: {tg_id})\n"
    text += f"📝 <b>Тема:</b> {subject}\n"
    text += f"📊 <b>Статус:</b> {status_text.get(status, status)}\n"
    text += f"🕐 <b>Создан:</b> {created[:16]}\n\n"
    text += "💬 <b>Сообщения:</b>\n"
    
    for msg_text, is_admin, msg_created in messages:
        author = "👑 Поддержка" if is_admin else f"👤 {user_name}"
        text += f"\n{author} | {msg_created[11:16]}\n{msg_text[:150]}\n"
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="📝 Ответить", callback_data=f"areply_{tid}")],
        [types.InlineKeyboardButton(text="✅ Закрыть", callback_data=f"aclose_{tid}")],
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


@ticket_router.callback_query(F.data.startswith("areply_"))
async def callback_reply(callback: types.CallbackQuery, state: FSMContext):
    """Начать ответ на тикет"""
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔")
        return
    
    ticket_id = int(callback.data.split("_")[1])
    await state.update_data(ticket_id=ticket_id)
    
    await callback.message.edit_text(
        f"📝 <b>Ответ на тикет #{ticket_id}</b>\n\n"
        "Введите ваш ответ:",
        parse_mode="HTML"
    )
    await state.set_state(TicketStates.waiting_reply)
    await callback.answer()


@ticket_router.message(TicketStates.waiting_reply)
async def admin_reply(message: types.Message, state: FSMContext):
    """Ответ админа на тикет"""
    if message.from_user.id != ADMIN_ID:
        return
    
    data = await state.get_data()
    ticket_id = data.get("ticket_id")
    
    if not ticket_id:
        await message.answer("❌ Ошибка. Попробуйте /tickets")
        await state.clear()
        return
    
    reply_text = message.text.strip()
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Добавляем ответ
    cursor.execute("""
        INSERT INTO ticket_messages (ticket_id, user_id, text, is_admin)
        VALUES (?, NULL, ?, 1)
    """, (ticket_id, reply_text))
    
    # Обновляем статус
    cursor.execute("""
        UPDATE tickets SET status = 'in_progress', updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (ticket_id,))
    
    # Получаем telegram_id пользователя
    cursor.execute("""
        SELECT u.telegram_id FROM tickets t
        JOIN users u ON t.user_id = u.id
        WHERE t.id = ?
    """, (ticket_id,))
    row = cursor.fetchone()
    
    conn.commit()
    conn.close()
    
    await state.clear()
    await message.answer(f"✅ Ответ на тикет #{ticket_id} отправлен!")
    
    # Уведомляем пользователя
    if row:
        try:
            from aiogram import Bot
            from config import BOT_TOKEN
            bot = Bot(token=BOT_TOKEN)
            await bot.send_message(
                row[0],
                f"📬 <b>Ответ на тикет #{ticket_id}</b>\n\n{reply_text}",
                parse_mode="HTML"
            )
            await bot.session.close()
        except Exception as e:
            logger.error(f"Ошибка уведомления: {e}")


@ticket_router.callback_query(F.data.startswith("aclose_"))
async def callback_close(callback: types.CallbackQuery):
    """Закрыть тикет"""
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔")
        return
    
    ticket_id = int(callback.data.split("_")[1])
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        UPDATE tickets SET status = 'closed', closed_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (ticket_id,))
    
    cursor.execute("""
        SELECT u.telegram_id FROM tickets t
        JOIN users u ON t.user_id = u.id
        WHERE t.id = ?
    """, (ticket_id,))
    row = cursor.fetchone()
    
    conn.commit()
    conn.close()
    
    if row:
        try:
            from aiogram import Bot
            from config import BOT_TOKEN
            bot = Bot(token=BOT_TOKEN)
            await bot.send_message(row[0], f"✅ Ваш тикет #{ticket_id} закрыт", parse_mode="HTML")
            await bot.session.close()
        except:
            pass
    
    await callback.message.edit_text(f"✅ Тикет #{ticket_id} закрыт")
    await callback.answer()

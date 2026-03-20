"""Хендлер для привязки Telegram к веб-аккаунту"""
from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

router = Router()

class LinkStates(StatesGroup):
    waiting_for_code = State()


@router.message(Command("link"))
async def cmd_link(message: Message, state: FSMContext):
    """Привязка Telegram к веб-аккаунту"""
    from bot.utils.database import get_db
    
    telegram_id = message.from_user.id
    
    # Проверяем есть ли уже веб-аккаунт с этим telegram_id
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT email FROM web_users WHERE telegram_id = ?', (telegram_id,))
    row = c.fetchone()
    
    if row:
        conn.close()
        await message.answer(
            f"✅ Ваш Telegram уже привязан к аккаунту {row[0]}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="🌐 Открыть панель", url="https://panel.cloaknet.site")
            ]])
        )
        return
    
    conn.close()
    
    await message.answer(
        "🔗 Привязка Telegram к веб-аккаунту\n\n"
        "Введите 6-значный код который вы получили на сайте panel.cloaknet.site\n\n"
        "Если у вас нет кода — откройте панель и нажмите 'Привязать Telegram'",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🌐 Открыть панель", url="https://panel.cloaknet.site")
        ]])
    )
    await state.set_state(LinkStates.waiting_for_code)


@router.message(F.text, LinkStates.waiting_for_code)
async def process_link_code(message: Message, state: FSMContext):
    """Обработка введённого кода"""
    import urllib.request
    import json
    from bot.utils.database import get_db
    
    code = message.text.strip()
    telegram_id = message.from_user.id
    
    if not code.isdigit() or len(code) != 6:
        await message.answer("❌ Код должен быть 6 цифр. Попробуйте ещё раз /link")
        await state.clear()
        return
    
    # Вызываем API linking
    api_url = "http://127.0.0.1:8080/api/web/auth/link_telegram"
    payload = json.dumps({"code": code, "telegram_id": telegram_id}).encode()
    
    try:
        req = urllib.request.Request(
            api_url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode())
        
        if result.get("success"):
            await message.answer(
                "✅ Telegram успешно привязан к вашему веб-аккаунту!\n\n"
                "Теперь вы можете покупать подписки через панель.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text="🌐 Открыть панель", url="https://panel.cloaknet.site")
                ]])
            )
        else:
            await message.answer(f"❌ {result.get('error', 'Неверный или устаревший код')}\n\nПопробуйте получить новый код на сайте.")
    
    except Exception as e:
        await message.answer(f"❌ Ошибка связи с сервером. Попробуйте позже.\n\n/link для повтора")
    
    await state.clear()

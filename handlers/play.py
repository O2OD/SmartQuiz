import asyncio
import time
import contextlib
from aiogram import Router, Bot, types, F
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramForbiddenError
from database.engine import async_session_maker
from database.models import Quiz, Result

play_router = Router()

solo_sessions = {}
active_polls = {}

# 1. Test faol bo'lgandagi klaviatura
active_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="⏸ Pauza"), KeyboardButton(text="⏹ To'xtatish")],
        [KeyboardButton(text="🔄 Boshidan boshlash")]
    ],
    resize_keyboard=True
)

# 2. Test pauza qilingandagi klaviatura (Pauza o'rniga Davom etish chiqadi)
paused_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="▶️ Davom etish"), KeyboardButton(text="⏹ To'xtatish")],
        [KeyboardButton(text="🔄 Boshidan boshlash")]
    ],
    resize_keyboard=True
)

def format_time(seconds: int) -> str:
    m, s = divmod(seconds, 60)
    if m == 0: 
        return f"{s} soniya"
    if s == 0: 
        return f"{m} daqiqa"
    return f"{m} daqiqa {s} soniya"

async def start_shared_quiz(target, bot: Bot, quiz_id: str):
    user_id = target.from_user.id
    chat_id = target.chat.id if isinstance(target, types.Message) else target.message.chat.id

    async with async_session_maker() as session:
        db_quiz = await session.get(Quiz, quiz_id)
        if not db_quiz:
            return await bot.send_message(chat_id, "⚠️ Test topilmadi yoki o'chirilgan.", reply_markup=ReplyKeyboardRemove())
        
        db_quiz.play_count = (db_quiz.play_count or 0) + 1
        await session.commit()

    solo_sessions[user_id] = {
        "quiz_id": quiz_id,
        "current_idx": 0,
        "score": 0,
        "misses": 0,
        "total_missed": 0,
        "status": "active",
        "start_time": time.time(),
        "active_poll_id": None
    }
    
    try:
        msg = await bot.send_message(chat_id, "⏳ Tayyorlaning...")
        for i in [3, 2, 1]:
            await msg.edit_text(f"⏳ {i}...")
            await asyncio.sleep(1)
            
        with contextlib.suppress(Exception):
            await msg.delete()

        await bot.send_message(
            chat_id, 
            f"🚀 <b>{db_quiz.subject}</b> boshlandi!",
            reply_markup=active_kb,
            parse_mode="HTML"
        )
    except TelegramForbiddenError:
        solo_sessions.pop(user_id, None)
        return
    
    await ask_solo_question(user_id, bot)

async def ask_solo_question(user_id: int, bot: Bot):
    session = solo_sessions.get(user_id)
    if not session or session.get("status") != "active":
        return

    async with async_session_maker() as db_session:
        db_quiz = await db_session.get(Quiz, session["quiz_id"])
        
    if not db_quiz:
        return

    idx = session["current_idx"]
    questions = db_quiz.questions

    if idx >= len(questions):
        return await finish_solo_test(user_id, bot, session, db_quiz, questions)

    q = questions[idx]
    
    try:
        msg = await bot.send_poll(
            chat_id=user_id,
            question=f"{idx + 1}/{len(questions)}. {q['savol'][:290]}",
            options=[o[:100] for o in q['variantlar']],
            type="quiz",
            is_anonymous=False,
            correct_option_id=q['togri'],
            open_period=db_quiz.time_limit,
            reply_markup=active_kb
        )
    except TelegramForbiddenError:
        solo_sessions.pop(user_id, None)
        return

    poll_id = msg.poll.id
    session["active_poll_id"] = poll_id
    active_polls[poll_id] = {"user_id": user_id, "correct_id": q['togri']}

    asyncio.create_task(monitor_poll_timeout(user_id, poll_id, db_quiz.time_limit, bot))

async def monitor_poll_timeout(user_id: int, poll_id: str, timeout: int, bot: Bot):
    await asyncio.sleep(timeout + 1)
    
    poll_data = active_polls.pop(poll_id, None)
    if not poll_data:
        return

    session = solo_sessions.get(user_id)
    if not session or session.get("active_poll_id") != poll_id:
        return

    session["misses"] += 1
    session["total_missed"] += 1
    session["current_idx"] += 1
    session["active_poll_id"] = None

    if session["misses"] >= 2:
        session["status"] = "paused"
        try:
            # Inline tugmalarsiz, faqat pastki klaviaturani o'zgartiramiz
            await bot.send_message(
                chat_id=user_id,
                text="⏸ <b>Test avtomatik pauza qilindi.</b>\nKetma-ket 2 ta savolga javob bermadingiz.",
                reply_markup=paused_kb,
                parse_mode="HTML"
            )
        except TelegramForbiddenError:
            solo_sessions.pop(user_id, None)
    else:
        await ask_solo_question(user_id, bot)

@play_router.poll_answer()
async def handle_poll_answer(pa: types.PollAnswer, bot: Bot):
    poll_data = active_polls.pop(pa.poll_id, None)
    if not poll_data:
        return

    user_id = poll_data["user_id"]
    is_correct = pa.option_ids and pa.option_ids[0] == poll_data["correct_id"]

    session = solo_sessions.get(user_id)
    if not session:
        return

    if is_correct:
        session["score"] += 1
        
    session["misses"] = 0
    session["current_idx"] += 1
    session["active_poll_id"] = None

    await ask_solo_question(user_id, bot)

@play_router.message(F.text == "⏸ Pauza")
async def manual_pause(message: types.Message):
    user_id = message.from_user.id
    session = solo_sessions.get(user_id)
    if session and session.get("status") == "active":
        session["status"] = "paused"
        # Inline tugmalarsiz, faqat pastki klaviaturani almashtiramiz
        await message.answer("⏸ <b>Test pauza qilindi.</b>", reply_markup=paused_kb, parse_mode="HTML")

@play_router.message(F.text == "▶️ Davom etish")
async def resume_solo_test(message: types.Message, bot: Bot):
    user_id = message.from_user.id
    session = solo_sessions.get(user_id)
    if session and session.get("status") == "paused":
        session["status"] = "active"
        session["misses"] = 0
        await ask_solo_question(user_id, bot)
    else:
        await message.answer("Sizda pauza qilingan test topilmadi.")

@play_router.message(F.text == "⏹ To'xtatish")
async def manual_stop(message: types.Message, bot: Bot):
    user_id = message.from_user.id
    session = solo_sessions.get(user_id)
    if not session:
        return await message.answer("Sizda faol test yo'q.", reply_markup=ReplyKeyboardRemove())
        
    async with async_session_maker() as db_session:
        db_quiz = await db_session.get(Quiz, session["quiz_id"])
        
    await finish_solo_test(user_id, bot, session, db_quiz, db_quiz.questions, force_stop=True)

@play_router.message(F.text == "🔄 Boshidan boshlash")
async def manual_restart_msg(message: types.Message, bot: Bot):
    user_id = message.from_user.id
    session = solo_sessions.get(user_id)
    if not session:
        return await message.answer("Sizda faol test yo'q.", reply_markup=ReplyKeyboardRemove())
        
    quiz_id = session["quiz_id"]
    await start_shared_quiz(message, bot, quiz_id)

@play_router.callback_query(F.data.startswith("restart_test_"))
async def restart_test_callback(call: types.CallbackQuery, bot: Bot):
    quiz_id = call.data.split("restart_test_")[1]
    with contextlib.suppress(Exception):
        await call.message.delete()
    await start_shared_quiz(call, bot, quiz_id)

async def finish_solo_test(user_id: int, bot: Bot, session: dict, db_quiz: Quiz, questions: list, force_stop: bool = False):
    try:
        temp_msg = await bot.send_message(user_id, "⏳ Natijalar hisoblanmoqda...", reply_markup=ReplyKeyboardRemove())
        with contextlib.suppress(Exception):
            await temp_msg.delete()
    except TelegramForbiddenError:
        solo_sessions.pop(user_id, None)
        return

    raw_time = round(time.time() - session['start_time'])
    
    total_q = len(questions)
    correct = session['score']
    missed = session['total_missed']
    seen_q = session['current_idx'] if force_stop else total_q
    wrong = seen_q - correct - missed

    async with async_session_maker() as db_session:
        new_result = Result(
            user_id=user_id,
            quiz_id=db_quiz.id,
            score=correct,
            total=seen_q,
            time_spent=raw_time 
        )
        db_session.add(new_result)
        await db_session.commit()
        
    quiz_id = db_quiz.id
    del solo_sessions[user_id]
    
    bot_info = await bot.get_me()
    link = f"https://t.me/{bot_info.username}?start=test_{quiz_id}"
    share_text = f"📚 Test: {db_quiz.subject}\n📊 Savollar soni: {total_q} ta\n⏱ Vaqt: {db_quiz.time_limit} soniya\n\nQuyidagi tugma orqali bilimingizni sinab ko'ring:"
    share_url = f"https://t.me/share/url?url={link}&text={share_text}"

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Qayta topshirish", callback_data=f"restart_test_{quiz_id}")],
        [InlineKeyboardButton(text="↗️ Ulashish", url=share_url)],
        [InlineKeyboardButton(text="🏠 Asosiy menyu", callback_data="back_to_hub")]
    ])
    
    title = "🛑 Test to'xtatildi!" if force_stop else "🏁 Test yakunlandi!"
    text = (
        f"<b>{title}</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"📝 <b>Mavzu:</b> {db_quiz.subject}\n"
        f"📊 <b>Jami savollar:</b> {seen_q} ta\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"✅ <b>To'g'ri:</b> {correct} ta\n"
        f"❌ <b>Xato:</b> {wrong} ta\n"
        f"⏳ <b>Tashlab ketilgan:</b> {missed} ta\n"
        f"⏱ <b>Sarflangan vaqt:</b> {format_time(raw_time)}\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "Natijangiz saqlandi! Quyidagi amallardan birini tanlang:"
    )
        
    try:
        await bot.send_message(user_id, text, reply_markup=markup, parse_mode="HTML")
    except TelegramForbiddenError:
        pass
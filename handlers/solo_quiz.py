import asyncio
import time
import contextlib
import random
import urllib.parse
from aiogram import Router, Bot, types, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from sqlalchemy import select
from core.config import settings
from database.engine import async_session_maker
from database.models import Result, Quiz
from aiogram.types import (
    InlineKeyboardMarkup, 
    InlineKeyboardButton, 
    ReplyKeyboardMarkup, 
    KeyboardButton, 
    ReplyKeyboardRemove
)

solo_router = Router()

solo_sessions = {}
active_polls = {}

test_controls_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="⏸ Pauza"), KeyboardButton(text="⏹ To'xtatish")],
        [KeyboardButton(text="🔄 Boshidan")]
    ],
    resize_keyboard=True,
    is_persistent=True
)

def format_time(seconds: int) -> str:
    minutes, secs = divmod(seconds, 60)
    if minutes == 0:
        return f"{secs} soniya"
    if secs == 0:
        return f"{minutes} daqiqa"
    return f"{minutes} daqiqa {secs} soniya"

@solo_router.message(CommandStart())
async def cmd_start(message: types.Message, bot: Bot):
    if message.text and "solo_" in message.text:
        quiz_id = message.text.split("solo_")[1]
        await prepare_solo_test(message, quiz_id, bot)
        return

    if message.from_user.id == settings.ADMIN_ID:
        await message.answer(
            "👋 Salom Admin!\n\nYangi test yaratish uchun savollar yozilgan <b>.docx</b> faylini yuboring.\n"
            "Buyruqlar: /stats, /export, /clear",
            parse_mode="HTML"
        )
    else:
        await message.answer(
            "👋 Salom!\n\nTest ishlash uchun sizga berilgan maxsus ssilka ustiga bosing."
        )

async def prepare_solo_test(message: types.Message, quiz_id: str, bot: Bot):
    async with async_session_maker() as session:
        db_quiz = await session.get(Quiz, quiz_id)
        
    if not db_quiz:
        await message.answer("⚠️ Bu test topilmadi yoki o'chirilgan.", reply_markup=ReplyKeyboardRemove())
        return
        
    bot_info = await bot.get_me()
    quiz_name = db_quiz.name
    questions = db_quiz.questions
    vaqt = db_quiz.time_limit
    q_count = len(questions)
    
    bot_link = f"https://t.me/{bot_info.username}?start=solo_{quiz_id}"
    share_text = (
        "👆 Yuqoridagi ssilka orqali testni boshlang!\n\n"
        f"📚 Mavzu: {quiz_name}\n"
        f"🔢 Savollar soni: {q_count} ta\n"
        f"⏳ Ajratilgan vaqt: {vaqt} soniya\n"
        "👨‍💻 Admin: @PigeonPY"
    )
    share_url = f"https://t.me/share/url?url={bot_link}&text={urllib.parse.quote(share_text)}"
    
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="▶️ Boshlash", callback_data=f"start_solo_{quiz_id}")],
        [InlineKeyboardButton(text="↗️ Ulashish", url=share_url)]
    ])
    
    text = (
        f"🏷 <b>Mavzu:</b> {quiz_name}\n"
        f"📊 <b>Savollar:</b> {q_count} ta\n"
        f"⏳ <b>Vaqt:</b> Har biriga {vaqt} soniya\n\n"
        "Quyidagi tugmalar orqali testni o'zingiz ishlashingiz yoki do'stlaringizga ulashishingiz mumkin.\n\n"
        "👨‍💻 <b>Admin:</b> <a href='https://t.me/PigeonPY'>OZOD</a>"
    )
    await message.answer(text, reply_markup=markup, parse_mode="HTML", disable_web_page_preview=True)

@solo_router.callback_query(F.data.startswith("start_solo_"))
async def start_countdown(call: types.CallbackQuery, bot: Bot):
    quiz_id = call.data.split("start_solo_")[1]
    
    async with async_session_maker() as session:
        db_quiz = await session.get(Quiz, quiz_id)
        
    if not db_quiz:
        await call.answer("Test topilmadi!", show_alert=True)
        return

    solo_sessions[call.from_user.id] = {
        "quiz_id": quiz_id,
        "current_idx": 0,
        "score": 0,
        "misses": 0,
        "total_missed": 0,
        "status": "active",
        "start_time": time.time(),
        "active_poll_id": None
    }
    
    msg = await call.message.edit_text("⏳ Tayyorlaning...")
    for i in [3, 2, 1]:
        await msg.edit_text(f"⏳ {i}...")
        await asyncio.sleep(1)
        
    with contextlib.suppress(Exception):
        await msg.delete()
    
    await bot.send_message(
        call.from_user.id, 
        "🚀 <b>Boshladik!</b>\n<i>Testni boshqarish uchun pastdagi tugmalardan foydalaning.</i>",
        reply_markup=test_controls_kb,
        parse_mode="HTML"
    )
    
    await ask_solo_question(call.from_user.id, bot)

@solo_router.poll_answer(lambda pa: active_polls.get(pa.poll_id, {}).get("type") == "solo")
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

@solo_router.message(F.text == "⏸ Pauza")
async def manual_pause(message: types.Message, bot: Bot):
    user_id = message.from_user.id
    session = solo_sessions.get(user_id)
    if session and session.get("status") == "active":
        session["status"] = "paused"
            
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="▶️ Davom etish", callback_data="resume_solo")]
        ])
        await message.answer(
            "⏸ <b>Test pauza qilindi.</b>\n\nDavom etish uchun pastdagi tugmani bosing.", 
            reply_markup=markup, 
            parse_mode="HTML"
        )

@solo_router.message(F.text == "⏹ To'xtatish")
async def manual_stop(message: types.Message, bot: Bot):
    user_id = message.from_user.id
    session = solo_sessions.get(user_id)
    if not session:
        await message.answer("Sizda faol test yo'q.", reply_markup=ReplyKeyboardRemove())
        return
        
    async with async_session_maker() as db_session:
        db_quiz = await db_session.get(Quiz, session["quiz_id"])
        
    await finish_solo_test(user_id, bot, session, db_quiz, db_quiz.questions, force_stop=True)

@solo_router.message(F.text == "🔄 Boshidan")
async def manual_restart(message: types.Message, bot: Bot):
    user_id = message.from_user.id
    session = solo_sessions.get(user_id)
    if not session:
        return
        
    session["current_idx"] = 0
    session["score"] = 0
    session["misses"] = 0
    session["total_missed"] = 0
    session["status"] = "active"
    session["start_time"] = time.time()
    
    await message.answer("🔄 Test boshidan boshlandi!")
    await ask_solo_question(user_id, bot)

@solo_router.callback_query(F.data == "resume_solo")
async def resume_solo_test(call: types.CallbackQuery, bot: Bot):
    user_id = call.from_user.id
    session = solo_sessions.get(user_id)
    if session and session.get("status") == "paused":
        session["status"] = "active"
        session["misses"] = 0
        with contextlib.suppress(Exception):
            await call.message.delete()
        await ask_solo_question(user_id, bot)
    else:
        await call.answer("Aktiv test topilmadi.", show_alert=True)

async def ask_solo_question(user_id: int, bot: Bot):
    session = solo_sessions.get(user_id)
    if not session or session.get("status") != "active":
        return

    async with async_session_maker() as db_session:
        db_quiz = await db_session.get(Quiz, session["quiz_id"])
        
    if not db_quiz:
        return

    current_idx = session["current_idx"]
    questions = db_quiz.questions

    if current_idx >= len(questions):
        await finish_solo_test(user_id, bot, session, db_quiz, questions)
        return

    question = questions[current_idx]
    time_limit = db_quiz.time_limit

    original_options = question['variantlar']
    correct_text = original_options[question['togri']]
    
    shuffled_options = original_options.copy()
    random.shuffle(shuffled_options)
    new_correct_id = shuffled_options.index(correct_text)

    msg = await bot.send_poll(
        chat_id=user_id,
        question=f"{current_idx + 1}/{len(questions)}. {question['savol'][:290]}",
        options=[o[:100] for o in shuffled_options],
        type="quiz",
        is_anonymous=False,
        correct_option_id=new_correct_id,
        open_period=time_limit,
        reply_markup=test_controls_kb
    )

    poll_id = msg.poll.id
    session["active_poll_id"] = poll_id
    active_polls[poll_id] = {"type": "solo", "user_id": user_id, "correct_id": new_correct_id}

    asyncio.create_task(monitor_poll_timeout(user_id, poll_id, time_limit, bot))

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
        
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="▶️ Davom etish", callback_data="resume_solo")]
        ])
        
        await bot.send_message(
            chat_id=user_id,
            text=(
                "⏸ <b>Test avtomatik pauza qilindi.</b>\n\n"
                "Ketma-ket 2 ta savolga javob bermadingiz. Davom etish uchun pastdagi tugmani bosing."
            ),
            reply_markup=markup,
            parse_mode="HTML",
            disable_web_page_preview=True
        )
    else:
        await ask_solo_question(user_id, bot)

async def finish_solo_test(user_id: int, bot: Bot, session: dict, db_quiz: Quiz, questions: list, force_stop: bool = False):
    temp_msg = await bot.send_message(user_id, "⏳ Natijalar hisoblanmoqda...", reply_markup=ReplyKeyboardRemove())
    with contextlib.suppress(Exception):
        await temp_msg.delete()

    raw_time = round(time.time() - session['start_time'])
    time_str = format_time(raw_time)
    
    total_q = len(questions)
    correct = session['score']
    missed = session['total_missed']
    seen_q = session['current_idx'] if force_stop else total_q
    wrong = seen_q - correct - missed

    async with async_session_maker() as db_session:
        new_result = Result(
            user_id=user_id,
            quiz_name=db_quiz.name,
            score=correct,
            total=seen_q,
            time_spent=raw_time 
        )
        db_session.add(new_result)
        await db_session.commit()
        
    quiz_id_for_restart = session['quiz_id']
    del solo_sessions[user_id]
    
    kb = [
        [InlineKeyboardButton(text="🔄 Boshidan boshlash", callback_data=f"start_solo_{quiz_id_for_restart}")]
    ]
    
    markup = InlineKeyboardMarkup(inline_keyboard=kb)
    title = "🛑 Test to'xtatildi!" if force_stop else "🏁 Test yakunlandi!"
    
    text = (
        f"<b>{title}</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"📝 <b>Mavzu:</b> {db_quiz.name}\n"
        f"📊 <b>Jami savollar:</b> {seen_q} ta\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"✅ <b>To'g'ri javoblar:</b> {correct} ta\n"
        f"❌ <b>Xato javoblar:</b> {wrong} ta\n"
        f"⏳ <b>Tashlab ketilgan:</b> {missed} ta\n"
        f"⏱ <b>Sarflangan vaqt:</b> {time_str}\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "🏆 Natijangiz muvaffaqiyatli saqlandi!"
    )
        
    await bot.send_message(user_id, text, reply_markup=markup, parse_mode="HTML", disable_web_page_preview=True)
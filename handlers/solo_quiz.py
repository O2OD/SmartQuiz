import asyncio
import time
import contextlib
from aiogram import Router, Bot, types, F
from aiogram.fsm.context import FSMContext
from core.config import settings
from database.engine import async_session_maker
from database.models import Result
from aiogram.types import (
    InlineKeyboardMarkup, 
    InlineKeyboardButton, 
    ReplyKeyboardMarkup, 
    KeyboardButton, 
    ReplyKeyboardRemove
)

solo_router = Router()

db_quizzes = {}
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

async def prepare_solo_test(message: types.Message, quiz_id: str, bot: Bot):
    if quiz_id not in db_quizzes:
        await message.answer("⚠️ Bu test topilmadi yoki muddati o'tgan.", reply_markup=ReplyKeyboardRemove())
        return
        
    quiz_data = db_quizzes[quiz_id]
    
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Men tayyorman!", callback_data=f"start_solo_{quiz_id}")]
    ])
    
    text = (
        f"🎲 <b>\"{quiz_data['name']}\"</b> testiga tayyorlaning\n\n"
        f"🖊 {len(quiz_data['questions'])} ta savol\n"
        f"⏱ Har bir savol uchun {quiz_data['time']} soniya\n\n"
        f"🏁 Tayyor bo'lganingizda quyidagi tugmani bosing."
    )
    await message.answer(text, reply_markup=markup, parse_mode="HTML")

@solo_router.callback_query(F.data.startswith("start_solo_"))
async def start_countdown(call: types.CallbackQuery, bot: Bot):
    quiz_id = call.data.split("start_solo_")[1]
    
    if quiz_id not in db_quizzes:
        await call.answer("Test faol emas!", show_alert=True)
        return

    solo_sessions[call.from_user.id] = {
        "quiz_id": quiz_id,
        "current_idx": 0,
        "score": 0,
        "misses": 0,
        "total_missed": 0,
        "status": "active",
        "start_time": time.time(),
        "active_poll_id": None,
        "msg_ids": [] 
    }
    
    msg = await call.message.edit_text("⏳ Tayyorlaning...")
    for i in [3, 2, 1]:
        await msg.edit_text(f"⏳ {i}...")
        await asyncio.sleep(1)
        
    with contextlib.suppress(Exception):
        await msg.delete()
    
    info_msg = await bot.send_message(
        call.from_user.id, 
        "🚀 <b>Boshladik!</b>\n<i>Testni boshqarish uchun pastdagi tugmalardan foydalaning.</i>",
        reply_markup=test_controls_kb,
        parse_mode="HTML"
    )
    solo_sessions[call.from_user.id]["msg_ids"].append(info_msg.message_id)
    
    await ask_solo_question(call.from_user.id, bot)

@solo_router.poll_answer()
async def handle_poll_answer(pa: types.PollAnswer, bot: Bot):
    poll_data = active_polls.pop(pa.poll_id, None)
    if not poll_data or poll_data.get("type") != "solo":
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
        p_msg = await message.answer(
            "⏸ <b>Test pauza qilindi.</b>\n\nDavom etish uchun pastdagi tugmani bosing.", 
            reply_markup=markup, 
            parse_mode="HTML"
        )
        session["msg_ids"].append(p_msg.message_id)
        session["msg_ids"].append(message.message_id)

@solo_router.message(F.text == "⏹ To'xtatish")
async def manual_stop(message: types.Message, bot: Bot):
    user_id = message.from_user.id
    session = solo_sessions.get(user_id)
    if not session:
        await message.answer("Sizda faol test yo'q.", reply_markup=ReplyKeyboardRemove())
        return
        
    quiz_data = db_quizzes.get(session["quiz_id"])
    await finish_solo_test(user_id, bot, session, quiz_data, quiz_data["questions"], force_stop=True)

@solo_router.message(F.text == "🔄 Boshidan")
async def manual_restart(message: types.Message, bot: Bot):
    user_id = message.from_user.id
    session = solo_sessions.get(user_id)
    if not session:
        return
        
    for m_id in session.get("msg_ids", []):
        with contextlib.suppress(Exception):
            await bot.delete_message(user_id, m_id)
            
    session["msg_ids"] = []
    session["current_idx"] = 0
    session["score"] = 0
    session["misses"] = 0
    session["total_missed"] = 0
    session["status"] = "active"
    session["start_time"] = time.time()
    
    r_msg = await message.answer("🔄 Test boshidan boshlandi!")
    session["msg_ids"].append(r_msg.message_id)
    session["msg_ids"].append(message.message_id)
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

    quiz_data = db_quizzes.get(session["quiz_id"])
    if not quiz_data:
        return

    current_idx = session["current_idx"]
    questions = quiz_data["questions"]

    if current_idx >= len(questions):
        await finish_solo_test(user_id, bot, session, quiz_data, questions)
        return

    question = questions[current_idx]
    time_limit = quiz_data["time"]

    test_controls_kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="⏸ Pauza"), KeyboardButton(text="⏹ To'xtatish")],
            [KeyboardButton(text="🔄 Boshidan")]
        ],
        resize_keyboard=True,
        is_persistent=True
    )

    msg = await bot.send_poll(
        chat_id=user_id,
        question=f"{current_idx + 1}/{len(questions)}. {question['savol'][:290]}",
        options=[o[:100] for o in question['variantlar']],
        type="quiz",
        is_anonymous=False,
        correct_option_id=question['togri'],
        open_period=time_limit,
        reply_markup=test_controls_kb
    )

    poll_id = msg.poll.id
    session["active_poll_id"] = poll_id
    session["msg_ids"].append(msg.message_id)
    active_polls[poll_id] = {"type": "solo", "user_id": user_id, "correct_id": question["togri"]}

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
        p_msg = await bot.send_message(
            chat_id=user_id,
            text="⏸ <b>Test avtomatik pauza qilindi.</b>\n\nKetma-ket 2 ta savolga javob bermadingiz. Davom etish uchun pastdagi tugmani bosing.",
            reply_markup=markup,
            parse_mode="HTML"
        )
        session["msg_ids"].append(p_msg.message_id)
    else:
        await ask_solo_question(user_id, bot)

async def finish_solo_test(user_id: int, bot: Bot, session: dict, quiz_data: dict, questions: list, force_stop: bool = False):
    for m_id in session.get("msg_ids", []):
        with contextlib.suppress(Exception):
            await bot.delete_message(user_id, m_id)

    time_spent = round(time.time() - session['start_time'])
    total_q = len(questions)
    correct = session['score']
    missed = session['total_missed']
    wrong = (session['current_idx'] if force_stop else total_q) - correct - missed

    async with async_session_maker() as db_session:
        new_result = Result(
            user_id=user_id,
            quiz_name=quiz_data['name'],
            score=correct,
            total=total_q,
            time_spent=time_spent
        )
        db_session.add(new_result)
        await db_session.commit()
        
    quiz_id_for_restart = session['quiz_id']
    del solo_sessions[user_id]
    
    kb = [
        [InlineKeyboardButton(text="🔄 Boshidan boshlash", callback_data=f"start_solo_{quiz_id_for_restart}")]
    ]
    
    if user_id == settings.ADMIN_ID:
        kb.append([InlineKeyboardButton(text="📝 Yangi test yaratish", callback_data="admin_new_test")])
        
    kb.append([
        InlineKeyboardButton(text="🧹 Tozalash", callback_data="end_quiz_and_exit")
    ])
    
    markup = InlineKeyboardMarkup(inline_keyboard=kb)

    title = "🛑 Test to'xtatildi!" if force_stop else "🏁 Test yakunlandi!"
    
    text = (
        f"{title}\n\n"
        f"Siz <b>{session['current_idx'] if force_stop else total_q}</b> ta savol ko'rdingiz:\n\n"
        f"✅ To'g'ri – {correct}\n"
        f"❌ Xato – {wrong}\n"
        f"⏳ Tashlab ketilgan – {missed}\n"
        f"⏱ Vaqt: {time_spent} soniya\n\n"
        f"🏆 Sizning natijangiz bazaga saqlandi."
    )
        
    await bot.send_message(user_id, text, reply_markup=markup, parse_mode="HTML")

@solo_router.callback_query(F.data == "end_quiz_and_exit")
async def end_quiz_and_exit_cb(call: types.CallbackQuery, state: FSMContext):
    await state.clear()
    
    with contextlib.suppress(Exception):
        await call.message.delete()
        
    temp_msg = await call.message.answer("🧹", reply_markup=ReplyKeyboardRemove())
    with contextlib.suppress(Exception):
        await temp_msg.delete()
        
    await call.answer("Chat xotirasi tozalandi!", show_alert=False)

@solo_router.callback_query(F.data == "admin_new_test")
async def admin_new_test_cb(call: types.CallbackQuery, state: FSMContext):
    await state.clear()
    with contextlib.suppress(Exception):
        await call.message.delete()
        
    await call.message.answer(
        "📝 <b>Yangi test yaratish:</b>\n\nIltimos, test savollari yozilgan <code>.docx</code> faylini yuboring.", 
        parse_mode="HTML", 
        reply_markup=ReplyKeyboardRemove()
    )
    await call.answer()
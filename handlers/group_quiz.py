import asyncio
import time
import contextlib
from aiogram import Router, Bot, types, F
from database.engine import async_session_maker
from database.models import Result
from handlers.solo_quiz import db_quizzes, active_polls
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from core.config import settings

group_router = Router()
group_sessions = {}

async def prepare_group_test(message: types.Message, quiz_id: str, bot: Bot):
    if quiz_id not in db_quizzes:
        return
        
    quiz_data = db_quizzes[quiz_id]
    
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Guruhda testni boshlash", callback_data=f"start_group_{quiz_id}")]
    ])
    
    text = (
        f"🎲 <b>👥 Guruh uchun test: \"{quiz_data['name']}\"</b>\n\n"
        f"🖊 <b>Savollar:</b> {len(quiz_data['questions'])} ta\n"
        f"⏱ <b>Vaqt:</b> Har biriga {quiz_data['time']} soniya\n\n"
        f"📢 Hamma tayyor bo'lsa, boshlash tugmasini bosing.\n\n"
        f"👨‍💻 <b>Admin:</b> <a href=\"https://t.me/PigeonPY\">OZOD</a>"
    )
    await message.answer(text, reply_markup=markup, parse_mode="HTML", disable_web_page_preview=True)

@group_router.callback_query(F.data.startswith("start_group_"))
async def start_group_countdown(call: types.CallbackQuery, bot: Bot):
    quiz_id = call.data.split("start_group_")[1]
    chat_id = call.message.chat.id
    
    if quiz_id not in db_quizzes:
        await call.answer("⚠️ Test topilmadi yoki muddati o'tgan!", show_alert=True)
        return

    group_sessions[chat_id] = {
        "quiz_id": quiz_id,
        "current_idx": 0,
        "scores": {}, 
        "start_time": time.time(),
        "active_poll_id": None,
        "msg_ids": [call.message.message_id],
        "misses": 0,
        "starter_id": call.from_user.id,
        "current_poll_answered": False,
        "status": "active"
    }
    
    msg = await call.message.edit_text("⏳ Guruh testi tayyorlanmoqda...")
    for i in [3, 2, 1]:
        await msg.edit_text(f"⏳ Boshlanishiga: {i}...")
        await asyncio.sleep(1)
        
    with contextlib.suppress(Exception):
        await msg.delete()
        
    await ask_group_question(chat_id, bot)

@group_router.poll_answer(lambda pa: active_polls.get(pa.poll_id, {}).get("type") == "group")
async def handle_group_poll_answer(pa: types.PollAnswer, bot: Bot):
    poll_data = active_polls.get(pa.poll_id)
    if not poll_data:
        return

    chat_id = poll_data["chat_id"]
    is_correct = pa.option_ids and pa.option_ids[0] == poll_data["correct_id"]

    session = group_sessions.get(chat_id)
    if not session:
        return

    session["current_poll_answered"] = True
    session["misses"] = 0

    user_id = pa.user.id
    user_name = pa.user.full_name

    if user_id not in session["scores"]:
        session["scores"][user_id] = {"name": user_name, "correct": 0, "wrong": 0}

    if is_correct:
        session["scores"][user_id]["correct"] += 1
    else:
        session["scores"][user_id]["wrong"] += 1

async def ask_group_question(chat_id: int, bot: Bot):
    session = group_sessions.get(chat_id)
    if not session or session.get("status") != "active":
        return

    quiz_data = db_quizzes.get(session["quiz_id"])
    if not quiz_data:
        return

    current_idx = session["current_idx"]
    questions = quiz_data["questions"]

    if current_idx >= len(questions):
        await finish_group_test(chat_id, bot, session, quiz_data)
        return

    question = questions[current_idx]
    time_limit = quiz_data["time"]
    session["current_poll_answered"] = False

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛑 Testni to'xtatish", callback_data=f"stop_group_{chat_id}")]
    ])

    msg = await bot.send_poll(
        chat_id=chat_id,
        question=f"👥 {current_idx + 1}/{len(questions)}. {question['savol'][:290]}",
        options=[o[:100] for o in question['variantlar']],
        type="quiz",
        is_anonymous=False,
        correct_option_id=question['togri'],
        open_period=time_limit,
        reply_markup=markup
    )

    poll_id = msg.poll.id
    session["active_poll_id"] = poll_id
    session["msg_ids"].append(msg.message_id)
    
    active_polls[poll_id] = {
        "type": "group", 
        "chat_id": chat_id, 
        "correct_id": question["togri"]
    }

    asyncio.create_task(monitor_group_timeout(chat_id, poll_id, time_limit, bot))

async def monitor_group_timeout(chat_id: int, poll_id: str, timeout: int, bot: Bot):
    await asyncio.sleep(timeout + 1)
    
    with contextlib.suppress(Exception):
        active_polls.pop(poll_id, None)

    session = group_sessions.get(chat_id)
    if not session or session.get("active_poll_id") != poll_id or session.get("status") != "active":
        return

    if not session["current_poll_answered"]:
        session["misses"] += 1
    else:
        session["misses"] = 0

    if session["misses"] >= 2:
        session["status"] = "paused"
        
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="▶️ Davom etish", callback_data=f"resume_group_{chat_id}")]
        ])
        
        p_msg = await bot.send_message(
            chat_id=chat_id,
            text=(
                f"⏸ <b>Test avtomatik pauza qilindi!</b>\n\n"
                f"Ketma-ket 2 ta savolga guruhdan hech kim javob bermadi. Davom etish uchun pastdagi tugmani bosing.\n\n"
                f"👨‍💻 <b>Admin:</b> <a href=\"https://t.me/PigeonPY\">OZOD</a>"
            ),
            reply_markup=markup,
            parse_mode="HTML",
            disable_web_page_preview=True
        )
        session["msg_ids"].append(p_msg.message_id)
        return

    session["current_idx"] += 1
    session["active_poll_id"] = None
    
    await ask_group_question(chat_id, bot)

@group_router.callback_query(F.data.startswith("resume_group_"))
async def resume_group_test_cb(call: types.CallbackQuery, bot: Bot):
    chat_id = int(call.data.split("resume_group_")[1])
    session = group_sessions.get(chat_id)
    
    if not session or session.get("status") != "paused":
        await call.answer("Test faol emas yoki pauzada emas.", show_alert=True)
        return
        
    user_id = call.from_user.id
    if user_id != session["starter_id"] and user_id != settings.ADMIN_ID:
        member = await bot.get_chat_member(chat_id, user_id)
        if member.status not in ['administrator', 'creator']:
            await call.answer("Bunga faqat testni boshlagan odam yoki guruh admini haqli!", show_alert=True)
            return

    session["status"] = "active"
    session["misses"] = 0
    
    with contextlib.suppress(Exception):
        await call.message.delete()
        
    await call.answer("Test davom etadi!")
    await ask_group_question(chat_id, bot)

@group_router.callback_query(F.data.startswith("stop_group_"))
async def stop_group_test_cb(call: types.CallbackQuery, bot: Bot):
    chat_id = int(call.data.split("stop_group_")[1])
    session = group_sessions.get(chat_id)
    
    if not session:
        await call.answer("Test allaqachon tugagan.", show_alert=True)
        return
        
    user_id = call.from_user.id
    if user_id != session["starter_id"] and user_id != settings.ADMIN_ID:
        member = await bot.get_chat_member(chat_id, user_id)
        if member.status not in ['administrator', 'creator']:
            await call.answer("Bunga faqat testni boshlagan odam yoki guruh admini haqli!", show_alert=True)
            return

    await call.answer("Test to'xtatildi!")
    
    poll_id = session.get("active_poll_id")
    if poll_id:
        active_polls.pop(poll_id, None)
        with contextlib.suppress(Exception):
            await bot.stop_poll(chat_id, session["msg_ids"][-1])
            
    await finish_group_test(chat_id, bot, session, db_quizzes.get(session["quiz_id"]))

async def finish_group_test(chat_id: int, bot: Bot, session: dict, quiz_data: dict):
    if not quiz_data:
        return
        
    scores = session["scores"]
    sorted_scores = sorted(scores.items(), key=lambda x: x[1]["correct"], reverse=True)
    time_spent = round(time.time() - session['start_time'])
    
    current_q = session.get("current_idx", 0)
    total_q = len(quiz_data["questions"])
    
    if current_q >= total_q:
        title_text = f"🏁 <b>\"{quiz_data['name']}\"</b> testi yakunlandi!"
        seen_text = f"<i>{total_q} ta savolga javob berildi</i>"
        db_total = total_q
    else:
        title_text = f"🛑 <b>\"{quiz_data['name']}\"</b> testi to'xtatildi!"
        seen_text = f"<i>{current_q} ta savol ko'rildi</i>"
        db_total = current_q

    leaderboard_text = f"{title_text}\n\n{seen_text}\n\n"
    
    if not sorted_scores:
        leaderboard_text += "😔 Afsuski, testda hech kim ishtirok etmadi.\n"
    else:
        for idx, (user_id, data) in enumerate(sorted_scores[:11], start=1):
            medals = {1: "🥇", 2: "🥈", 3: "🥉"}
            prefix = medals.get(idx, f"{idx}.")
            correct = data["correct"]
            
            m = time_spent // 60
            s = time_spent % 60
            time_str = f"{m} daqiqa {s} soniya" if m > 0 else f"{s} soniya"
            
            leaderboard_text += f"{prefix} {data['name']} – <b>{correct}</b> ({time_str})\n"
            
            if idx == 1:
                async with async_session_maker() as db_session:
                    new_result = Result(
                        user_id=user_id,
                        quiz_name=f"👥 {quiz_data['name']} (Guruh)",
                        score=correct,
                        total=db_total,
                        time_spent=time_spent
                    )
                    db_session.add(new_result)
                    await db_session.commit()

    if current_q >= total_q:
        leaderboard_text += "\n🏆 G'oliblarni tabriklaymiz!"
        
    leaderboard_text += f"\n\n👨‍💻 <b>Admin:</b> <a href=\"https://t.me/PigeonPY\">OZOD</a>"
    
    if chat_id in group_sessions:
        del group_sessions[chat_id]
        
    await bot.send_message(chat_id, leaderboard_text, parse_mode="HTML", disable_web_page_preview=True)
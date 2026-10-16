import asyncio
import time
import contextlib
import random
from aiogram import Router, Bot, types, F
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, 
    InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
)
from aiogram.filters import CommandStart, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select, func, delete
import os

from app.database import async_session, User, Dictionary, Word

play_router = Router()

solo_sessions = {}
active_polls = {}

active_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="⏸ Pauza"), KeyboardButton(text="⏹ To'xtatish")],
        [KeyboardButton(text="🔄 Boshidan boshlash")]
    ],
    resize_keyboard=True
)

paused_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="▶️ Davom etish"), KeyboardButton(text="⏹ To'xtatish")],
        [KeyboardButton(text="🔄 Boshidan boshlash")]
    ],
    resize_keyboard=True
)

def main_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Yangi lug'at yaratish"), KeyboardButton(text="📚 Mening lug'atlarim")]
        ],
        resize_keyboard=True
    )

class BotStates(StatesGroup):
    waiting_dict_name = State()
    waiting_words = State()
    choosing_time = State()

@play_router.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    
    async with async_session() as session:
        user = await session.get(User, message.from_user.id)
        if not user:
            session.add(User(telegram_id=message.from_user.id, full_name=message.from_user.full_name))
            await session.commit()

    photo_path = "sample.jpg"
    caption = (
        "👋 <b>Lug'at yodlash botiga xush kelibsiz!</b>\n\n"
        "📋 <i>So'zlarni kiritish namunasi yuqoridagi rasmda ko'rsatilgan.</i>\n"
        "Lug'at yaratish uchun pastdagi tugmani bosing:"
    )
    
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Yangi lug'at yaratish", callback_data="start_create_dict")]
    ])

    if os.path.exists(photo_path):
        photo = FSInputFile(photo_path)
        await message.answer_photo(photo=photo, caption=caption, reply_markup=markup, parse_mode="HTML")
    else:
        await message.answer(caption, reply_markup=markup, parse_mode="HTML")
    
    await message.answer("Bosh menyu:", reply_markup=main_menu_kb())

@play_router.callback_query(F.data == "start_create_dict")
@play_router.message(F.text == "➕ Yangi lug'at yaratish")
async def create_dict_start(event: types.Message | types.CallbackQuery, state: FSMContext):
    if isinstance(event, types.CallbackQuery):
        message = event.message
        await event.answer()
    else:
        message = event

    await state.set_state(BotStates.waiting_dict_name)
    await message.answer("📝 <b>Yangi lug'at uchun nom yozing:</b>\n<i>(Masalan: English 1-kun)</i>", parse_mode="HTML")

@play_router.message(BotStates.waiting_dict_name)
async def create_dict_name(message: types.Message, state: FSMContext):
    name = message.text.strip()[:100]
    async with async_session() as session:
        new_dict = Dictionary(user_id=message.from_user.id, name=name)
        session.add(new_dict)
        await session.commit()
        dict_id = new_dict.id

    await state.update_data(dict_id=dict_id)
    await state.set_state(BotStates.waiting_words)
    await message.answer(
        f"✅ <b>{name}</b> ochildi!\n\n"
        f"Endi so'zlarni xuddi rasmda ko'rsatilgandek yuboring (har bir qatorda bittadan):\n\n"
        f"<code>apple - olma\nbook - kitob</code>",
        parse_mode="HTML"
    )

@play_router.message(BotStates.waiting_words)
async def save_words(message: types.Message, state: FSMContext):
    data = await state.get_data()
    dict_id = data.get("dict_id")
    lines = message.text.strip().splitlines()
    added = 0

    async with async_session() as session:
        for line in lines:
            line = line.strip()
            if not line:
                continue
            for sep in [" - ", "-", " — ", "—", "="]:
                if sep in line:
                    parts = line.split(sep, 1)
                    en, uz = parts[0].strip(), parts[1].strip()
                    if en and uz:
                        session.add(Word(
                            dict_id=dict_id,
                            user_id=message.from_user.id,
                            en_word=en[:250],
                            uz_word=uz[:250]
                        ))
                        added += 1
                    break
        await session.commit()

    await state.clear()
    await message.answer(
        f"🎉 Muvaffaqiyatli! Lug'atga <b>{added} ta</b> so'z qo'shildi.",
        reply_markup=main_menu_kb(),
        parse_mode="HTML"
    )

@play_router.message(F.text == "📚 Mening lug'atlarim")
async def show_dictionaries(message: types.Message):
    async with async_session() as session:
        stmt = select(Dictionary).where(Dictionary.user_id == message.from_user.id).order_by(Dictionary.id.desc())
        dicts = (await session.execute(stmt)).scalars().all()

        if not dicts:
            await message.answer("📭 Sizda hali lug'atlar yo'q.", reply_markup=main_menu_kb())
            return

        kb = []
        for d in dicts:
            cnt = await session.scalar(select(func.count(Word.id)).where(Word.dict_id == d.id))
            kb.append([InlineKeyboardButton(text=f"📘 {d.name} ({cnt} ta so'z)", callback_data=f"open_d:{d.id}")])

    await message.answer("📚 <b>Sizning lug'atlaringiz (tanlash uchun bosing):</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML")

@play_router.callback_query(F.data.startswith("open_d:"))
async def open_dictionary(callback: types.CallbackQuery):
    dict_id = int(callback.data.split(":")[1])
    async with async_session() as session:
        d = await session.get(Dictionary, dict_id)
        if not d:
            await callback.answer("Lug'at topilmadi!")
            return
        cnt = await session.scalar(select(func.count(Word.id)).where(Word.dict_id == dict_id))

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Testni boshlash", callback_data=f"prep_quiz:{dict_id}")],
        [InlineKeyboardButton(text="🔗 Ulashish", callback_data=f"share_d:{dict_id}"), InlineKeyboardButton(text="🗑 O'chirish", callback_data=f"del_d:{dict_id}")],
        [InlineKeyboardButton(text="⬅️ Ortga", callback_data="back_to_list")]
    ])

    await callback.message.edit_text(
        f"📘 Lug'at: <b>{d.name}</b>\n📊 So'zlar soni: <b>{cnt} ta</b>\n\nKerakli amalni tanlang:",
        reply_markup=kb,
        parse_mode="HTML"
    )
    await callback.answer()

@play_router.callback_query(F.data == "back_to_list")
async def back_to_list_cb(callback: types.CallbackQuery):
    async with async_session() as session:
        stmt = select(Dictionary).where(Dictionary.user_id == callback.from_user.id).order_by(Dictionary.id.desc())
        dicts = (await session.execute(stmt)).scalars().all()
        kb = []
        for d in dicts:
            cnt = await session.scalar(select(func.count(Word.id)).where(Word.dict_id == d.id))
            kb.append([InlineKeyboardButton(text=f"📘 {d.name} ({cnt} ta so'z)", callback_data=f"open_d:{d.id}")])

    await callback.message.edit_text("📚 <b>Sizning lug'atlaringiz (tanlash uchun bosing):</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML")
    await callback.answer()

@play_router.callback_query(F.data.startswith("del_d:"))
async def delete_dict_cb(callback: types.CallbackQuery):
    dict_id = int(callback.data.split(":")[1])
    async with async_session() as session:
        await session.execute(delete(Word).where(Word.dict_id == dict_id))
        await session.execute(delete(Dictionary).where(Dictionary.id == dict_id))
        await session.commit()
    await callback.answer("Lug'at o'chirildi!")
    await back_to_list_cb(callback)

@play_router.callback_query(F.data.startswith("share_d:"))
async def share_dict_cb(callback: types.CallbackQuery, bot: Bot):
    dict_id = int(callback.data.split(":")[1])
    me = await bot.get_me()
    link = f"https://t.me/{me.username}?start=share_{dict_id}"
    await callback.message.answer(
        f"🔗 <b>Ulashish ssilkasi:</b>\n\n{link}\n\n"
        f"<i>Bu ssilkani do'stlaringizga yuboring, bossa ularga ham shu lug'at qo'shiladi!</i>",
        parse_mode="HTML"
    )
    await callback.answer()

@play_router.callback_query(F.data.startswith("prep_quiz:"))
async def prep_quiz_callback(callback: types.CallbackQuery):
    dict_id = int(callback.data.split(":")[1])
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="10 sekund", callback_data=f"start_q:{dict_id}:10"),
            InlineKeyboardButton(text="15 sekund", callback_data=f"start_q:{dict_id}:15")
        ],
        [
            InlineKeyboardButton(text="20 sekund", callback_data=f"start_q:{dict_id}:20"),
            InlineKeyboardButton(text="30 sekund", callback_data=f"start_q:{dict_id}:30")
        ],
        [InlineKeyboardButton(text="⬅️ Ortga", callback_data=f"open_d:{dict_id}")]
    ])
    await callback.message.edit_text(
        "⏱ <b>Har bir savol uchun qancha vaqt (sekund) berilsin?</b>",
        reply_markup=kb,
        parse_mode="HTML"
    )
    await callback.answer()

@play_router.callback_query(F.data.startswith("start_q:"))
async def start_quiz_callback(call: types.CallbackQuery, bot: Bot):
    _, dict_id_str, sec_str = call.data.split(":")
    dict_id, time_limit = int(dict_id_str), int(sec_str)
    user_id = call.from_user.id
    chat_id = call.message.chat.id

    async with async_session() as session:
        res = await session.execute(select(Word).where(Word.dict_id == dict_id))
        words_db = res.scalars().all()

    if not words_db:
        return await call.answer("Bu lug'atda so'zlar yo'q!", show_alert=True)

    # Savollarni tayyorlash
    questions = []
    all_uz_list = [w.uz_word for w in words_db]

    for w in words_db:
        correct_ans = w.uz_word
        wrong_pool = [uz for uz in all_uz_list if uz != correct_ans]
        selected_wrongs = random.sample(wrong_pool, min(3, len(wrong_pool)))
        variants = selected_wrongs + [correct_ans]
        random.shuffle(variants)
        correct_idx = variants.index(correct_ans)

        questions.append({
            "savol": f"Inglizcha so'z: {w.en_word}",
            "variantlar": variants,
            "togri": correct_idx
        })

    random.shuffle(questions)

    solo_sessions[user_id] = {
        "dict_id": dict_id,
        "questions": questions,
        "current_idx": 0,
        "score": 0,
        "misses": 0,
        "total_missed": 0,
        "time_limit": time_limit,
        "status": "active",
        "start_time": time.time(),
        "active_poll_id": None
    }
    
    with contextlib.suppress(Exception):
        await call.message.delete()

    await bot.send_message(
        chat_id, 
        "🚀 <b>Test boshlandi!</b>",
        reply_markup=active_kb,
        parse_mode="HTML"
    )
    
    await ask_solo_question(user_id, bot)

async def ask_solo_question(user_id: int, bot: Bot):
    session = solo_sessions.get(user_id)
    if not session or session.get("status") != "active":
        return

    idx = session["current_idx"]
    questions = session["questions"]

    if idx >= len(questions):
        return await finish_solo_test(user_id, bot, session, questions)

    q = questions[idx]
    
    try:
        msg = await bot.send_poll(
            chat_id=user_id,
            question=f"{idx + 1}/{len(questions)}. {q['savol']}",
            options=[o[:100] for o in q['variantlar']],
            type="quiz",
            is_anonymous=False,
            correct_option_id=q['togri'],
            open_period=session["time_limit"],
            reply_markup=active_kb
        )
    except TelegramForbiddenError:
        solo_sessions.pop(user_id, None)
        return

    poll_id = msg.poll.id
    session["active_poll_id"] = poll_id
    active_polls[poll_id] = {"user_id": user_id, "correct_id": q['togri']}

    asyncio.create_task(monitor_poll_timeout(user_id, poll_id, session["time_limit"], bot))

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
            await bot.send_message(
                chat_id=user_id,
                text="⏸ <b>Test avtomatik pauza qilindi.</b>\nKetma-ket 2 ta savolga javob bermadingiz.",
                reply_markup=paused_kb,
                parse_mode="HTML"
            )
        except Exception:
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
        await message.answer("⏸ <b>Test pauza qilindi.</b>", reply_markup=paused_kb, parse_mode="HTML")

@play_router.message(F.text == "▶️ Davom etish")
async def resume_solo_test(message: types.Message, bot: Bot):
    user_id = message.from_user.id
    session = solo_sessions.get(user_id)
    if session and session.get("status") == "paused":
        session["status"] = "active"
        session["misses"] = 0
        await message.answer("▶️ Test davom etmoqda...", reply_markup=active_kb)
        await ask_solo_question(user_id, bot)
    else:
        await message.answer("Sizda pauza qilingan test topilmadi.")

@play_router.message(F.text == "⏹ To'xtatish")
async def manual_stop(message: types.Message, bot: Bot):
    user_id = message.from_user.id
    session = solo_sessions.get(user_id)
    if not session:
        return await message.answer("Sizda faol test yo'q.", reply_markup=main_menu_kb())
        
    await finish_solo_test(user_id, bot, session, session["questions"], force_stop=True)

@play_router.message(F.text == "🔄 Boshidan boshlash")
async def manual_restart_msg(message: types.Message, bot: Bot):
    user_id = message.from_user.id
    session = solo_sessions.get(user_id)
    if not session:
        return await message.answer("Sizda faol test yo'q.", reply_markup=main_menu_kb())
        
    dict_id = session["dict_id"]
    questions = session["questions"]
    random.shuffle(questions)
    
    session["current_idx"] = 0
    session["score"] = 0
    session["misses"] = 0
    session["total_missed"] = 0
    session["status"] = "active"
    session["start_time"] = time.time()
    
    await message.answer("🔄 Test boshidan boshlandi!", reply_markup=active_kb)
    await ask_solo_question(user_id, bot)

async def finish_solo_test(user_id: int, bot: Bot, session: dict, questions: list, force_stop: bool = False):
    with contextlib.suppress(Exception):
        await bot.send_message(user_id, "⏳ Natijalar hisoblanmoqda...", reply_markup=ReplyKeyboardRemove())

    raw_time = round(time.time() - session['start_time'])
    total_q = len(questions)
    correct = session['score']
    missed = session['total_missed']
    seen_q = session['current_idx'] if force_stop else total_q
    wrong = seen_q - correct - missed

    dict_id = session["dict_id"]
    solo_sessions.pop(user_id, None)

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Qayta topshirish", callback_data=f"prep_quiz:{dict_id}")],
        [InlineKeyboardButton(text="📚 Asosiy menyu", callback_data="back_to_main")]
    ])
    
    title = "🛑 Test to'xtatildi!" if force_stop else "🏁 Test yakunlandi!"
    text = (
        f"<b>{title}</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"📊 <b>Jami savollar:</b> {seen_q} ta\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"✅ <b>To'g'ri:</b> {correct} ta\n"
        f"❌ <b>Xato:</b> {wrong} ta\n"
        f"⏳ <b>Tashlab ketilgan:</b> {missed} ta\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "Natijangiz hisoblandi!"
    )
    
    try:
        await bot.send_message(user_id, text, reply_markup=markup, parse_mode="HTML")
        await bot.send_message(user_id, "Bosh menyu:", reply_markup=main_menu_kb())
    except Exception:
        pass

@play_router.callback_query(F.data == "back_to_main")
async def back_to_main_cb(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    with contextlib.suppress(Exception):
        await callback.message.delete()
    await callback.message.answer("Bosh menyu:", reply_markup=main_menu_kb())
    await callback.answer()
import os
import uuid
from aiogram import Router, Bot, types, F
from aiogram.filters import CommandStart, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database.engine import async_session_maker
from database.models import User, Quiz
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from services.docx import async_parse_docx

creator_router = Router()

class QuizCreate(StatesGroup):
    time = State()

@creator_router.message(CommandStart())
async def start_cmd(message: types.Message, bot: Bot, command: CommandObject):
    async with async_session_maker() as session:
        user = await session.get(User, message.from_user.id)
        if not user:
            session.add(User(
                user_id=message.from_user.id,
                full_name=message.from_user.full_name,
                username=message.from_user.username
            ))
            await session.commit()

    if command.args and command.args.startswith("test_"):
        from handlers.play import start_shared_quiz
        quiz_id = command.args.split("_")[1]
        return await start_shared_quiz(message, bot, quiz_id)

    text = (
        "👋 <b>Test yaratish platformasiga xush kelibsiz!</b>\n\n"
        "Yangi test yaratish uchun savollar yozilgan <b>.docx</b> faylini yuboring.\n\n"
        "📄 <b>Fayl formati rasmdagidek bo'lishi shart:</b>\n"
        "1. Savol raqam va nuqta bilan boshlanishi kerak.\n"
        "2. To'g'ri javob oldidan yulduzcha (<code>*</code>) qo'yiladi."
    )
    
    # Rasmni topib yuborish
    if os.path.exists("namuna.png"):
        await message.answer_photo(photo=FSInputFile("namuna.png"), caption=text, parse_mode="HTML")
    else:
        await message.answer(text, parse_mode="HTML")

@creator_router.message(F.document)
async def handle_doc(message: types.Message, bot: Bot, state: FSMContext):
    if not message.document.file_name.endswith('.docx'):
        return await message.answer("⚠️ Faqat .docx formatidagi fayl qabul qilinadi.")

    file = await bot.get_file(message.document.file_id)
    local_name = f"temp_{uuid.uuid4().hex}.docx"
    await bot.download_file(file.file_path, local_name)

    try:
        with open(local_name, 'rb') as f:
            data = f.read()
        
        questions = await async_parse_docx(data)
        
        if not questions:
            err_text = (
                "❌ <b>Fayldan savollarni o'qib bo'lmadi!</b>\n\n"
                "⚠️ <b>Eng ko'p uchraydigan xatolar:</b>\n"
                "1. Word dasturidagi <i>avtomatik raqamlashdan</i> foydalanilgan (raqamlarni qo'lda yozing).\n"
                "2. To'g'ri javob oldidan yulduzcha (<code>*</code>) qo'yilmagan.\n\n"
                "📄 <b>Iltimos, faylingizni rasmdagi namunaga moslab qayta yuboring.</b>"
            )
            if os.path.exists("namuna.png"):
                return await message.answer_photo(photo=FSInputFile("namuna.png"), caption=err_text, parse_mode="HTML")
            else:
                return await message.answer(err_text, parse_mode="HTML")

        subject = message.document.file_name.replace('.docx', '')
        await state.update_data(q=questions, sub=subject)

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="10 soniya", callback_data="time_10"),
                InlineKeyboardButton(text="15 soniya", callback_data="time_15")
            ],
            [
                InlineKeyboardButton(text="20 soniya", callback_data="time_20"),
                InlineKeyboardButton(text="30 soniya", callback_data="time_30")
            ]
        ])
        
        await message.answer(
            f"✅ <b>{len(questions)} ta savol topildi!</b>\n\n"
            "⏱ Har bir savol uchun vaqtni tanlang:",
            reply_markup=kb,
            parse_mode="HTML"
        )
        await state.set_state(QuizCreate.time)
    finally:
        if os.path.exists(local_name):
            os.remove(local_name)

@creator_router.callback_query(QuizCreate.time, F.data.startswith("time_"))
async def set_time(call: types.CallbackQuery, state: FSMContext, bot: Bot):
    limit = int(call.data.split("_")[1])
    data = await state.get_data()
    quiz_id = uuid.uuid4().hex[:8]

    async with async_session_maker() as session:
        session.add(Quiz(
            id=quiz_id,
            owner_id=call.from_user.id,
            subject=data['sub'],
            time_limit=limit,
            questions=data['q']
        ))
        await session.commit()

    await state.clear()
    
    bot_info = await bot.get_me()
    link = f"https://t.me/{bot_info.username}?start=test_{quiz_id}"
    share_url = f"https://t.me/share/url?url={link}&text=📝 {data['sub']} testiga marhamat!"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 O'zim boshlash", url=link)],
        [InlineKeyboardButton(text="↗️ Do'stlarga ulashish", url=share_url)]
    ])
    
    await call.message.edit_text(
        f"🎉 <b>Test yaratildi!</b>\n\n"
        f"📚 <b>Mavzu:</b> {data['sub']}\n"
        f"📊 <b>Savollar:</b> {len(data['q'])} ta\n"
        f"⏱ <b>Vaqt:</b> {limit} soniya",
        reply_markup=kb,
        parse_mode="HTML"
    )
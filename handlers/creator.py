import os
import uuid
from aiogram import Router, Bot, types, F
from aiogram.filters import CommandStart, Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select, delete
from database.engine import async_session_maker
from database.models import User, Quiz, Result
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile, ReplyKeyboardRemove
from services.docx import async_parse_docx

creator_router = Router()

class QuizCreate(StatesGroup):
    waiting_for_file = State()
    waiting_for_title = State()
    time = State()

def get_start_hub_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Yangi test yaratish", callback_data="action_create_test")],
        [InlineKeyboardButton(text="📂 Mening testlarim", callback_data="action_my_tests")],
        [InlineKeyboardButton(text="❓ Qo'llanma", callback_data="action_help")]
    ])

@creator_router.message(CommandStart())
async def start_cmd(message: types.Message, bot: Bot, command: CommandObject, state: FSMContext):
    await state.clear()
    
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
        quiz_id = command.args.split("test_")[1]
        async with async_session_maker() as session:
            db_quiz = await session.get(Quiz, quiz_id)
            
        if not db_quiz:
            return await message.answer("⚠️ Test topilmadi yoki o'chirilgan.")

        bot_info = await bot.get_me()
        link = f"https://t.me/{bot_info.username}?start=test_{quiz_id}"
        share_text = f"📚 Test: {db_quiz.subject}\n📊 Savollar: {len(db_quiz.questions)} ta\n⏱ Vaqt: {db_quiz.time_limit}s\n\nBilimingizni sinab ko'ring:"
        share_url = f"https://t.me/share/url?url={link}&text={share_text}"

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🚀 Testni boshlash", callback_data=f"restart_test_{quiz_id}")],
            [InlineKeyboardButton(text="↗️ Do'stlarga ulashish", url=share_url)],
            [InlineKeyboardButton(text="🏠 Asosiy menyu", callback_data="back_to_hub")]
        ])

        return await message.answer(
            f"📖 <b>Testga taklif qilindingiz!</b>\n\n"
            f"📚 <b>Mavzu:</b> {db_quiz.subject}\n"
            f"📊 <b>Savollar:</b> {len(db_quiz.questions)} ta\n"
            f"⏱ <b>Har bir savolga:</b> {db_quiz.time_limit} soniya\n\n"
            "Tayyor bo'lsangiz, boshlash tugmasini bosing:",
            reply_markup=kb,
            parse_mode="HTML"
        )

    text = (
        "👋 <b>SmartQuiz platformasiga xush kelibsiz!</b>\n\n"
        "Quyidagi bo'limlardan birini tanlang:"
    )
    await message.answer(text, reply_markup=get_start_hub_kb(), parse_mode="HTML")

@creator_router.callback_query(F.data == "back_to_hub")
async def back_to_hub_callback(call: types.CallbackQuery, state: FSMContext):
    await state.clear()
    text = "👋 <b>SmartQuiz asosiy menyusi:</b>\n\nQuyidagi bo'limlardan birini tanlang:"
    try:
        await call.message.delete()
    except Exception:
        pass
    await call.message.answer(text, reply_markup=get_start_hub_kb(), parse_mode="HTML")

@creator_router.callback_query(F.data == "action_create_test")
async def ask_for_docx_file(call: types.CallbackQuery, state: FSMContext):
    await state.set_state(QuizCreate.waiting_for_file)
    text = (
        "📄 Yangi test tuzish uchun savollar yozilgan <b>.docx</b> faylingizni yuboring.\n\n"
        "<b>Format talabi:</b>\n"
        "1. Savol raqam bilan boshlanishi kerak (masalan: <code>1. Savol?</code>)\n"
        "2. To'g'ri javob oldiga yulduzcha (<code>*</code>) qo'yiladi.\n"
        "3. Fayl yuklangach, testga o'zingiz nom berasiz (masalan: <i>Ona tili (1-50)</i>)."
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Bekor qilish", callback_data="back_to_hub")]
    ])
    
    if os.path.exists("namuna.png"):
        await call.message.delete()
        await call.message.answer_photo(photo=FSInputFile("namuna.png"), caption=text, reply_markup=kb, parse_mode="HTML")
    else:
        await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")

@creator_router.message(QuizCreate.waiting_for_file, F.document)
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
            err_text = "❌ <b>Fayldan savollarni o'qib bo'lmadi!</b>\nWord avtomatik raqamlashidan foydalanmang va to'g'ri javob oldiga <code>*</code> qo'ying."
            return await message.answer(err_text, parse_mode="HTML")

        await state.update_data(q=questions)
        await state.set_state(QuizCreate.waiting_for_title)

        await message.answer(
            f"✅ <b>{len(questions)} ta savol muvaffaqiyatli o'qildi!</b>\n\n"
            "✍️ Endi ushbu test uchun <b>nom/mavzu</b> yuboring:\n"
            "<i>(Namuna: Fizika (1-50) yoki Tarix 1-blok)</i>",
            parse_mode="HTML"
        )
    finally:
        if os.path.exists(local_name):
            os.remove(local_name)

@creator_router.message(QuizCreate.waiting_for_title)
async def handle_test_title(message: types.Message, state: FSMContext):
    title = message.text.strip()
    if len(title) > 100:
        return await message.answer("⚠️ Test nomi 100 belgidan oshmasligi kerak. Qisqaroq nom kiriting:")

    await state.update_data(sub=title)

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
        f"📝 <b>Test nomi:</b> {title}\n\n"
        "⏱ Har bir savol uchun vaqtni tanlang:",
        reply_markup=kb,
        parse_mode="HTML"
    )
    await state.set_state(QuizCreate.time)

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
    share_text = f"📚 Test: {data['sub']}\n📊 Savollar soni: {len(data['q'])} ta\n⏱ Vaqt: {limit} soniya\n\nBilimingizni sinab ko'ring:"
    share_url = f"https://t.me/share/url?url={link}&text={share_text}"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Testni boshlash", callback_data=f"restart_test_{quiz_id}")],
        [InlineKeyboardButton(text="↗️ Ulashish", url=share_url)],
        [InlineKeyboardButton(text="📂 Mening testlarim", callback_data="action_my_tests")]
    ])
    
    try:
        await call.message.delete()
    except Exception:
        pass
    
    await call.message.answer(
        f"🎉 <b>Test muvaffaqiyatli saqlandi!</b>\n\n"
        f"📚 <b>Mavzu:</b> {data['sub']}\n"
        f"📊 <b>Savollar:</b> {len(data['q'])} ta\n"
        f"⏱ <b>Vaqt:</b> {limit} soniya\n"
        f"🔗 <b>Havola:</b> <code>{link}</code>",
        reply_markup=kb,
        parse_mode="HTML"
    )

@creator_router.callback_query(F.data == "action_my_tests")
@creator_router.message(Command("mytests"))
async def show_my_tests(event: types.Message | types.CallbackQuery):
    user_id = event.from_user.id
    async with async_session_maker() as session:
        stmt = select(Quiz).where(Quiz.owner_id == user_id).order_by(Quiz.created_at.desc())
        result = await session.execute(stmt)
        quizzes = result.scalars().all()

    if not quizzes:
        text = "📭 Siz hali birorta ham test yaratmabsiz."
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ Yangi test yaratish", callback_data="action_create_test")],
            [InlineKeyboardButton(text="🏠 Asosiy menyu", callback_data="back_to_hub")]
        ])
        
        try:
            if isinstance(event, types.CallbackQuery):
                await event.message.delete()
                return await event.message.answer(text, reply_markup=kb)
            return await event.answer(text, reply_markup=kb)
        except Exception:
            return await event.answer(text, reply_markup=kb)

    buttons = []
    for q in quizzes[:10]:
        buttons.append([InlineKeyboardButton(text=f"📝 {q.subject}", callback_data=f"view_quiz_{q.id}")])
    buttons.append([InlineKeyboardButton(text="🏠 Asosiy menyu", callback_data="back_to_hub")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)

    text = f"📂 <b>Siz yaratgan testlar ({len(quizzes)} ta):</b>\n\nKerakli test ustiga bosing:"
    try:
        if isinstance(event, types.CallbackQuery):
            await event.message.delete()
            await event.message.answer(text, reply_markup=kb, parse_mode="HTML")
        else:
            await event.answer(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await event.answer(text, reply_markup=kb, parse_mode="HTML")

@creator_router.callback_query(F.data.startswith("view_quiz_"))
async def view_single_quiz(call: types.CallbackQuery, bot: Bot):
    quiz_id = call.data.split("view_quiz_")[1]
    async with async_session_maker() as session:
        db_quiz = await session.get(Quiz, quiz_id)

    if not db_quiz:
        return await call.answer("Test topilmadi yoki o'chirilgan.", show_alert=True)

    bot_info = await bot.get_me()
    link = f"https://t.me/{bot_info.username}?start=test_{quiz_id}"
    share_text = f"📚 Test: {db_quiz.subject}\n📊 Savollar: {len(db_quiz.questions)} ta\n⏱ Vaqt: {db_quiz.time_limit}s\n\nTestni boshlash:"
    share_url = f"https://t.me/share/url?url={link}&text={share_text}"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Testni ishlash", callback_data=f"restart_test_{quiz_id}")],
        [InlineKeyboardButton(text="↗️ Do'stlarga ulashish", url=share_url)],
        [InlineKeyboardButton(text="🗑 Testni o'chirish", callback_data=f"user_del_quiz_{quiz_id}")],
        [InlineKeyboardButton(text="⬅️ Ortga (Testlar ro'yxati)", callback_data="action_my_tests")]
    ])

    try:
        await call.message.delete()
    except Exception:
        pass

    await call.message.answer(
        f"📝 <b>Test ma'lumotlari:</b>\n\n"
        f"📚 <b>Mavzu:</b> {db_quiz.subject}\n"
        f"📊 <b>Savollar soni:</b> {len(db_quiz.questions)} ta\n"
        f"⏱ <b>Vaqt:</b> {db_quiz.time_limit} soniya\n"
        f"🔗 <b>Havola:</b> <code>{link}</code>",
        reply_markup=kb,
        parse_mode="HTML"
    )

@creator_router.callback_query(F.data.startswith("user_del_quiz_"))
async def user_delete_quiz(call: types.CallbackQuery):
    quiz_id = call.data.split("user_del_quiz_")[1]
    user_id = call.from_user.id

    async with async_session_maker() as session:
        db_quiz = await session.get(Quiz, quiz_id)
        if not db_quiz:
            return await call.answer("Test topilmadi.", show_alert=True)
            
        if db_quiz.owner_id != user_id:
            return await call.answer("Bu testni o'chirishga ruxsatingiz yo'q!", show_alert=True)

        await session.execute(delete(Result).where(Result.quiz_id == quiz_id))
        await session.delete(db_quiz)
        await session.commit()

    await call.answer("✅ Test bazadan butunlay o'chirildi!", show_alert=True)
    await show_my_tests(call)

@creator_router.callback_query(F.data == "action_help")
@creator_router.message(Command("help"))
async def help_cmd(event: types.Message | types.CallbackQuery):
    text = (
        "💡 <b>SmartQuiz qo'llanmasi</b>\n\n"
        "1. Microsoft Word (.docx) dasturida savollarni tayyorlang.\n"
        "2. Har bir savolni '1. ', '2. ' kabi raqam bilan boshlang.\n"
        "3. Variantlarni alohida qatorlarga yozing.\n"
        "4. To'g'ri javob oldiga yulduzcha (<code>*</code>) qo'ying.\n"
        "5. Faylni yuborgach, testga o'zingiz xohlagan nomni bering (Masalan: <b>Ona tili (1-50)</b>).\n"
        "6. Har bir savol uchun vaqt me'yorini tanlang.\n\n"
        "📂 O'zingiz yaratgan testlarni <b>Mening testlarim</b> bo'limida boshqarishingiz, qayta ulashishingiz yoki o'chirib tashlashingiz mumkin."
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 Asosiy menyu", callback_data="back_to_hub")]
    ])
    
    try:
        if isinstance(event, types.CallbackQuery):
            await event.message.delete()
            if os.path.exists("namuna.png"):
                await event.message.answer_photo(photo=FSInputFile("namuna.png"), caption=text, reply_markup=kb, parse_mode="HTML")
            else:
                await event.message.answer(text, reply_markup=kb, parse_mode="HTML")
        else:
            if os.path.exists("namuna.png"):
                await event.answer_photo(photo=FSInputFile("namuna.png"), caption=text, reply_markup=kb, parse_mode="HTML")
            else:
                await event.answer(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        pass

@creator_router.message(Command("clear"))
async def clear_cmd(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("🧹 Chat tozalandi, barcha jarayonlar bekor qilindi.", reply_markup=ReplyKeyboardRemove())
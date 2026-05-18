import os
import re
import urllib.parse
import uuid
import csv
import asyncio
from docx import Document
from aiogram import Router, Bot, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
    InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
)
from sqlalchemy import select, func
from core.config import settings
from database.engine import async_session_maker
from database.models import Result, Quiz, User

admin_router = Router()

class QuizState(StatesGroup):
    waiting_for_file = State()
    waiting_for_time = State()

time_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="10"), KeyboardButton(text="20"), KeyboardButton(text="30")],
        [KeyboardButton(text="40"), KeyboardButton(text="50"), KeyboardButton(text="60")]
    ],
    resize_keyboard=True,
    one_time_keyboard=True
)

@admin_router.message(Command("stats"), F.from_user.id == settings.ADMIN_ID)
async def get_stats(message: types.Message):
    async with async_session_maker() as session:
        quizzes_count = await session.execute(select(func.count(Quiz.id)))
        total_quizzes = quizzes_count.scalar()
        
        results_count = await session.execute(select(func.count(Result.id)))
        total_results = results_count.scalar()

    text = (
        "📊 <b>Bot Statistikasi</b>\n\n"
        f"📁 Bazadagi jami testlar: {total_quizzes} ta\n"
        f"🏃‍♂️ Jami yechilgan testlar: {total_results} ta\n\n"
        "<i>Barcha testlarni ko'rish uchun /list, Excel yuklash uchun /export bosing.</i>"
    )
    await message.answer(text, parse_mode="HTML")

@admin_router.message(Command("list"), F.from_user.id == settings.ADMIN_ID)
async def list_quizzes(message: types.Message, bot: Bot):
    temp_msg = await message.answer("⏳ Testlar bazadan yuklanmoqda...")
    
    async with async_session_maker() as session:
        result = await session.execute(select(Quiz).order_by(Quiz.created_at.desc()))
        quizzes = result.scalars().all()

    await temp_msg.delete()

    if not quizzes:
        await message.answer("⚠️ Bazada faol testlar topilmadi.")
        return

    bot_info = await bot.get_me()
    await message.answer(f"📚 <b>Jami testlar: {len(quizzes)} ta.</b>\nQuyida ularning barchasi keltirilgan:", parse_mode="HTML")
    
    for q in quizzes:
        q_count = len(q.questions)
        vaqt = q.time_limit
        quiz_name = q.name
        quiz_id = q.id
        
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
        await asyncio.sleep(0.2) 

@admin_router.message(Command("export"), F.from_user.id == settings.ADMIN_ID)
async def export_results(message: types.Message):
    temp_msg = await message.answer("⏳ Ma'lumotlar bazadan olinmoqda...")
    
    async with async_session_maker() as session:
        stmt = select(Result, User).join(User, Result.user_id == User.user_id, isouter=True)
        db_result = await session.execute(stmt)
        records = db_result.all()

    if not records:
        await temp_msg.edit_text("⚠️ Bazada hali hech qanday natija yo'q.")
        return

    filename = f"natijalar_{uuid.uuid4().hex[:6]}.csv"
    with open(filename, mode='w', newline='', encoding='utf-8-sig') as file:
        writer = csv.writer(file)
        writer.writerow(["Foydalanuvchi ID", "Ismi", "Username", "Test nomi", "To'g'ri javob", "Jami savol", "Vaqt (sek)"])
        
        for r, u in records:
            name = u.full_name if u else "Noma'lum"
            username = f"@{u.username}" if (u and u.username) else "Yo'q"
            writer.writerow([r.user_id, name, username, r.quiz_name, r.score, r.total, r.time_spent])

    doc = FSInputFile(filename)
    await message.answer_document(doc, caption="📊 Barcha test natijalari (Excel/CSV formati)", parse_mode="HTML")
    
    await temp_msg.delete()
    os.remove(filename)

@admin_router.message(Command("clear"), F.from_user.id == settings.ADMIN_ID)
async def clear_state(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("🧹 Holat tozalandi. Yangi fayl yuklashingiz mumkin.", reply_markup=ReplyKeyboardRemove())

@admin_router.message(F.document, F.from_user.id == settings.ADMIN_ID)
async def handle_docx_file(message: types.Message, state: FSMContext, bot: Bot):
    document = message.document
    if not document.file_name.endswith('.docx'):
        await message.answer("⚠️ Iltimos, faqat .docx formatidagi fayl yuboring.")
        return

    file_id = document.file_id
    file = await bot.get_file(file_id)
    file_path = file.file_path
    
    local_filename = f"temp_{uuid.uuid4()}.docx"
    await bot.download_file(file_path, local_filename)

    try:
        doc = Document(local_filename)
        questions = []
        current_q = None

        for para in doc.paragraphs:
            text = para.text.replace('\xa0', ' ').strip()
            if not text:
                continue
            
            if re.match(r'^\d+', text):
                if current_q and len(current_q['variantlar']) >= 2:
                    questions.append(current_q)
                current_q = {'savol': text, 'variantlar': [], 'togri': 0}
            elif current_q is not None:
                is_correct = False
                
                if text.startswith('*'):
                    is_correct = True
                elif not text.startswith('#') and not text.startswith('-'):
                    is_correct = True
                    
                clean_text = re.sub(r'^[ \t*#\-+]+', '', text).strip()
                
                if clean_text:
                    if is_correct:
                        current_q['togri'] = len(current_q['variantlar'])
                    current_q['variantlar'].append(clean_text)

        if current_q and len(current_q['variantlar']) >= 2:
            questions.append(current_q)

        if not questions:
            await message.answer("❌ Fayl ichidan savollar topilmadi. Formatni tekshiring.")
            return

        quiz_id = str(uuid.uuid4())[:8]
        quiz_name = document.file_name.replace('.docx', '')
        
        await state.update_data(quiz_id=quiz_id, quiz_name=quiz_name, questions=questions)
        
        await message.answer(
            f"✅ Fayl o'qildi. <b>{len(questions)} ta</b> savol topildi.\n\n"
            "⏱ Har bir savol uchun vaqtni (soniyada) tanlang yoki yozing:", 
            reply_markup=time_kb,
            parse_mode="HTML"
        )
        await state.set_state(QuizState.waiting_for_time)

    except Exception as e:
        await message.answer(f"⚠️ Xatolik yuz berdi: {e}")
    finally:
        if os.path.exists(local_filename):
            os.remove(local_filename)

@admin_router.message(QuizState.waiting_for_time, F.from_user.id == settings.ADMIN_ID)
async def set_time_handler(message: types.Message, state: FSMContext, bot: Bot):
    if not message.text.isdigit():
        await message.answer("⚠️ Iltimos, faqat raqam kiriting (masalan: 20)")
        return
        
    vaqt = int(message.text)
    data = await state.get_data()
    quiz_id = data['quiz_id']
    quiz_name = data['quiz_name']
    questions = data['questions']
    
    async with async_session_maker() as session:
        new_quiz = Quiz(
            id=quiz_id,
            name=quiz_name,
            time_limit=vaqt,
            questions=questions
        )
        session.add(new_quiz)
        await session.commit()
        
    await state.clear()
    
    bot_info = await bot.get_me()
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
    
    await message.answer("✅ Test muvaffaqiyatli PostgreSQL bazasiga saqlandi!", reply_markup=ReplyKeyboardRemove())
    await message.answer(text, reply_markup=markup, parse_mode="HTML", disable_web_page_preview=True)
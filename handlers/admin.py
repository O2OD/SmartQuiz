import os
import re
import uuid
import datetime
import pandas as pd
from docx import Document
from aiogram import Router, Bot, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    ReplyKeyboardRemove, FSInputFile,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from sqlalchemy import select, func, delete
from core.config import settings
from database.engine import async_session_maker
from database.models import Result, Quiz, User

admin_router = Router()

class QuizState(StatesGroup):
    waiting_for_file = State()
    waiting_for_subject = State()
    waiting_for_range = State()
    waiting_for_time = State()

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
        "<i>Barcha testlarni ko'rish uchun botga /start bosing. Excel uchun /export.</i>"
    )
    await message.answer(text, parse_mode="HTML")

@admin_router.message(Command("export"), F.from_user.id == settings.ADMIN_ID)
async def export_results(message: types.Message):
    temp_msg = await message.answer("⏳ Ma'lumotlar Excelga yuklanmoqda...")
    
    async with async_session_maker() as session:
        stmt = select(Result, User).join(User, Result.user_id == User.user_id, isouter=True).order_by(Result.id)
        db_result = await session.execute(stmt)
        records = db_result.all()

    if not records:
        await temp_msg.edit_text("⚠️ Bazada hali hech qanday natija yo'q.")
        return

    filename = f"Natijalar_{uuid.uuid4().hex[:6]}.xlsx"
    data = []
    
    for r, u in records:
        name = u.full_name if u else "Noma'lum"
        username = f"@{u.username}" if (u and u.username) else "Yo'q"
        
        time_str = "Noma'lum"
        if hasattr(r, 'created_at') and r.created_at:
            time_str = r.created_at.strftime("%Y-%m-%d %H:%M")
        elif hasattr(r, 'id'):
            time_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

        # Excel ustunlari: Ism, Username, Test nomi, Yechilgan savollar, To'g'ri javob, Vaqt
        data.append({
            "Ismi": name,
            "Username": username,
            "Test nomi": r.quiz_name,
            "Yechilgan savollar": r.total,
            "To'g'ri javoblar": r.score,
            "Vaqti": time_str
        })

    df = pd.DataFrame(data)
    df.to_excel(filename, index=False)

    doc = FSInputFile(filename)
    await message.answer_document(doc, caption="📊 Barcha test natijalari", parse_mode="HTML")
    
    await temp_msg.delete()
    os.remove(filename)

@admin_router.callback_query(F.data.startswith("delquiz_"), F.from_user.id == settings.ADMIN_ID)
async def delete_quiz_handler(call: types.CallbackQuery):
    quiz_id = call.data.split("delquiz_")[1]
    async with async_session_maker() as session:
        q = await session.get(Quiz, quiz_id)
        if q:
            # 1. Shu testning bazadagi nomini yasaymiz
            quiz_name = f"{q.subject} {q.range_text}"
            
            # 2. Shu testga tegishli barcha ishlangan NATIJALARNI o'chirib tashlaymiz
            await session.execute(delete(Result).where(Result.quiz_name == quiz_name))
            
            # 3. Testning o'zini o'chiramiz
            await session.delete(q)
            await session.commit()
            
            await call.answer("✅ Test va unga tegishli barcha natijalar butunlay o'chirildi!", show_alert=True)
            await call.message.delete()
        else:
            await call.answer("Test topilmadi yoki allaqachon o'chirilgan.", show_alert=True)
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
        await state.update_data(quiz_id=quiz_id, questions=questions)
        
        await message.answer(
            f"✅ Fayl o'qildi. <b>{len(questions)} ta</b> savol topildi.\n\n"
            "Endi bu test uchun <b>Fan nomini</b> kiriting:\n"
            "<i>(Masalan: Suniy intellekt, Kiberxavfsizlik asoslari)</i>",
            parse_mode="HTML",
            reply_markup=ReplyKeyboardRemove()
        )
        await state.set_state(QuizState.waiting_for_subject)

    except Exception as e:
        await message.answer(f"⚠️ Xatolik yuz berdi: {e}")
    finally:
        if os.path.exists(local_filename):
            os.remove(local_filename)

@admin_router.message(QuizState.waiting_for_subject, F.from_user.id == settings.ADMIN_ID)
async def set_subject_handler(message: types.Message, state: FSMContext):
    await state.update_data(subject=message.text.strip())
    await message.answer(
        "📝 Endi ushbu test uchun <b>Oraliqni</b> kiriting:\n"
        "<i>(Masalan: 1-50, 51-100)</i>",
        parse_mode="HTML"
    )
    await state.set_state(QuizState.waiting_for_range)

@admin_router.message(QuizState.waiting_for_range, F.from_user.id == settings.ADMIN_ID)
async def set_range_handler(message: types.Message, state: FSMContext):
    await state.update_data(range_text=message.text.strip())
    
    time_ikb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="20", callback_data="settime_20"),
                InlineKeyboardButton(text="30", callback_data="settime_30")
            ],
            [
                InlineKeyboardButton(text="40", callback_data="settime_40"),
                InlineKeyboardButton(text="50", callback_data="settime_50")
            ]
        ]
    )
    
    await message.answer(
        "⏱ Har bir savol uchun vaqtni (soniyada) tanlang:", 
        reply_markup=time_ikb
    )
    await state.set_state(QuizState.waiting_for_time)

@admin_router.callback_query(QuizState.waiting_for_time, F.data.startswith("settime_"), F.from_user.id == settings.ADMIN_ID)
async def set_time_cb_handler(call: types.CallbackQuery, state: FSMContext):
    vaqt = int(call.data.split("_")[1])
    data = await state.get_data()
    
    quiz_id = data['quiz_id']
    subject = data['subject']
    range_text = data['range_text']
    questions = data['questions']
    
    async with async_session_maker() as session:
        new_quiz = Quiz(
            id=quiz_id,
            subject=subject,
            range_text=range_text,
            time_limit=vaqt,
            questions=questions
        )
        session.add(new_quiz)
        await session.commit()
        
    await state.clear()
    
    text = (
        f"✅ <b>Test muvaffaqiyatli saqlandi!</b>\n\n"
        f"🏷 <b>Fan:</b> {subject}\n"
        f"🔢 <b>Oraliq:</b> {range_text}\n"
        f"📊 <b>Savollar:</b> {len(questions)} ta\n"
        f"⏳ <b>Vaqt:</b> Har biriga {vaqt} soniya\n\n"
        "<i>Foydalanuvchilar botga /start berganda ushbu test menyuda ko'rinadi. O'chirish uchun Fan ustiga bosganingizda O'chirish tugmasi chiqadi.</i>"
    )
    await call.message.edit_text(text, parse_mode="HTML")
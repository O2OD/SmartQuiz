import os
import urllib.parse
import uuid
from docx import Document
from aiogram import Router, Bot, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from core.config import settings
from handlers.solo_quiz import db_quizzes

admin_router = Router()

class QuizState(StatesGroup):
    waiting_for_file = State()
    waiting_for_time = State()

time_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="15"), KeyboardButton(text="20"), KeyboardButton(text="25")],
        [KeyboardButton(text="30"), KeyboardButton(text="45"), KeyboardButton(text="60")]
    ],
    resize_keyboard=True,
    one_time_keyboard=True
)

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
            text = para.text.strip()
            if not text:
                continue
            
            if text[0].isdigit() and (text[1] == '.' or text[2] == '.'):
                if current_q and len(current_q['variantlar']) >= 2:
                    questions.append(current_q)
                current_q = {'savol': text, 'variantlar': [], 'togri': 0}
            elif current_q is not None:
                is_correct = text.startswith('*')
                clean_text = text[1:].strip() if is_correct else text
                
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
        
        db_quizzes[quiz_id] = {
            'name': quiz_name,
            'questions': questions,
            'time': 15 
        }
        
        await state.update_data(quiz_id=quiz_id)
        await message.answer(
            f"✅ Fayl o'qildi. <b>{len(questions)} ta</b> savol topildi.\n\n"
            "⏱ Har bir savol uchun vaqtni (soniyada) tanlang yoki yozing:", 
            reply_markup=time_kb,
            parse_mode="HTML"
        )
        await state.set_state(QuizState.waiting_for_time)

    except Exception as e:
        await message.answer(f"⚠️ Faylni o'qishda xatolik yuz berdi: {e}")
    finally:
        if os.path.exists(local_filename):
            os.remove(local_filename)

@admin_router.message(QuizState.waiting_for_time, F.from_user.id == settings.ADMIN_ID)
async def set_time_handler(message: types.Message, state: FSMContext, bot: Bot):
    if not message.text.isdigit():
        await message.answer("⚠️ Iltimos, faqat raqam kiriting (masalan: 15)")
        return
        
    vaqt = int(message.text)
    data = await state.get_data()
    quiz_id = data['quiz_id']
    
    db_quizzes[quiz_id]['time'] = vaqt
    await state.clear()
    
    bot_info = await bot.get_me()
    quiz_name = db_quizzes[quiz_id]['name']
    q_count = len(db_quizzes[quiz_id]['questions'])
    
    bot_link = f"https://t.me/{bot_info.username}?start=solo_{quiz_id}"
    share_text = f"Men {quiz_name} testini yechmoqchiman. Sen ham sinab ko'r!"
    share_url = f"https://t.me/share/url?url={bot_link}&text={urllib.parse.quote(share_text)}"
    
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="▶️ Boshlash", url=bot_link)],
        [InlineKeyboardButton(text="↗️ Ulashish", url=share_url)]
    ])
    
    text = (
        f"🏷 <b>Mavzu:</b> {quiz_name}\n"
        f"📊 <b>Savollar:</b> {q_count} ta\n"
        f"⏳ <b>Vaqt:</b> Har biriga {vaqt} soniya\n\n"
        "Quyidagi tugmalar orqali testni o'zingiz ishlashingiz yoki do'stlaringizga ulashishingiz mumkin.\n\n"
        "👨‍💻 <b>Admin:</b> <a href='https://t.me/PigeonPY'>OZOD</a>"
    )
    
    await message.answer("✅ Test muvaffaqiyatli saqlandi!", reply_markup=ReplyKeyboardRemove())
    await message.answer(text, reply_markup=markup, parse_mode="HTML", disable_web_page_preview=True)
import uuid
import os
import csv
import urllib.parse
import contextlib
from io import StringIO
from aiogram import Router, Bot, F, types
from aiogram.filters import CommandStart, CommandObject, Command
from aiogram.types import (
    InlineKeyboardMarkup, 
    InlineKeyboardButton, 
    ReplyKeyboardMarkup, 
    KeyboardButton, 
    ReplyKeyboardRemove,
    BufferedInputFile
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select, func, desc

from core.config import settings
from services.docx_parser import async_parse_docx
from handlers.solo_quiz import db_quizzes, prepare_solo_test
from database.engine import async_session_maker
from database.models import User, Result

admin_router = Router()

class QuizState(StatesGroup):
    waiting_for_time = State()

def format_time(seconds):
    m = int(seconds) // 60
    s = int(seconds) % 60
    return f"{m}m {s}s" if m > 0 else f"{s}s"

async def save_user_to_db(user: types.User):
    async with async_session_maker() as db:
        existing_user = await db.get(User, user.id)
        if not existing_user:
            new_user = User(
                user_id=user.id,
                full_name=user.full_name,
                username=user.username or "mavjud_emas"
            )
            db.add(new_user)
            await db.commit()

admin_dashboard_kb = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="📊 Umumiy Statistika", callback_data="admin_stats")],
        [InlineKeyboardButton(text="💾 Barcha Natijalar (Excel)", callback_data="admin_export")],
        [InlineKeyboardButton(text="🧹 Holatni Tozalash", callback_data="admin_clear")]
    ]
)

@admin_router.message(CommandStart())
async def start_handler(message: types.Message, command: CommandObject, bot: Bot):
    await save_user_to_db(message.from_user)
    
    args = command.args
    if not args:
        if message.from_user.id == settings.ADMIN_ID:
            await message.answer(
                "👑 <b>Admin Panelga Xush Kelibsiz!</b>\n\n"
                "📝 <b>Yangi test yaratish uchun:</b>\n"
                "Shunchaki <code>.docx</code> formatidagi test faylini yuboring.\n\n"
                "⚙️ <b>Boshqaruv:</b>\n"
                "Pastdagi tugmalar orqali bot ma'lumotlarini boshqaring.",
                reply_markup=admin_dashboard_kb,
                parse_mode="HTML"
            )
        else:
            await message.answer(
                "🤖 <b>SmartQuiz Botiga xush kelibsiz!</b>\n\n"
                "Bu bot orqali siz turli xil testlarni ishlashingiz, o'z bilimingizni sinab ko'rishingiz mumkin.\n\n"
                "⚠️ <i>Sizda test yaratish huquqi yo'q. Agar siz ham shunday testlar tuzmoqchi bo'lsangiz yoki hamkorlik qilmoqchi bo'lsangiz, asoschiga murojaat qiling:</i> @PigeonPY",
                parse_mode="HTML"
            )
        return

    if args.startswith("solo_"):
        quiz_id = args.split("_")[1]
        await prepare_solo_test(message, quiz_id, bot)
    elif args.startswith("group_"):
        await message.answer("👥 Gurux rejimi tez orada ishga tushadi! Hozircha yakkaxon rejimda ishlashingiz mumkin.")

@admin_router.message(Command("clear"))
async def clear_command_handler(message: types.Message, state: FSMContext):
    await state.clear()
    if message.from_user.id == settings.ADMIN_ID:
        await message.answer("🧹 Holat tozalandi! Yangi test faylini (.docx) yuborishingiz mumkin.", reply_markup=ReplyKeyboardRemove())
    else:
        await message.answer("🧹 Xotira tozalandi!\n\nTest ishlashni boshlash uchun sizga berilgan maxsus ssilka ustiga bosing.", reply_markup=ReplyKeyboardRemove())

@admin_router.callback_query(F.data == "admin_clear")
async def admin_clear_cb(call: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await call.answer("🧹 Barcha jarayonlar tozalandi!", show_alert=True)
    await call.message.answer("Sessiya tozalandi. Qanday yordam bera olaman?", reply_markup=ReplyKeyboardRemove())

@admin_router.callback_query(F.data == "admin_stats", F.from_user.id == settings.ADMIN_ID)
async def stats_cb(call: types.CallbackQuery):
    await call.answer("Statistika yuklanmoqda...")
    async with async_session_maker() as db:
        stmt = (
            select(
                User.full_name,
                Result.quiz_name,
                func.count(Result.id).label("attempts"),
                func.max(Result.score).label("best_score"),
                func.max(Result.total).label("total_q")
            )
            .join(User, User.user_id == Result.user_id)
            .group_by(User.full_name, Result.quiz_name)
            .order_by(desc("attempts"))
            .limit(15)
        )
        records = await db.execute(stmt)
        results = records.all()

    if not results:
        await call.message.answer("Hozircha hech qanday natija yo'q.")
        return

    text = "📊 <b>Top-15 Eng Faol Foydalanuvchilar:</b>\n\n"
    for row in results:
        text += f"👤 <b>{row.full_name}</b>\n"
        text += f"📝 Test: {row.quiz_name}\n"
        text += f"🔄 Urinishlar: {row.attempts} marta\n"
        text += f"🏆 Eng yaxshi natija: {row.best_score}/{row.total_q}\n"
        text += "〰️〰️〰️〰️〰️〰️〰️\n"

    await call.message.answer(text, parse_mode="HTML")

@admin_router.callback_query(F.data == "admin_export", F.from_user.id == settings.ADMIN_ID)
async def export_cb(call: types.CallbackQuery):
    await call.answer("Excel tayyorlanmoqda, kuting...")
    
    async with async_session_maker() as db:
        stmt = select(User.full_name, User.username, Result.quiz_name, Result.score, Result.total, Result.time_spent, Result.date).join(User, User.user_id == Result.user_id).order_by(desc(Result.date))
        records = await db.execute(stmt)
        results = records.all()

    if not results:
        await call.message.answer("Hozircha baza bo'sh.")
        return

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(['Ism-Familiya', 'Username', 'Test Nomi', 'To\'g\'ri javoblar', 'Jami savollar', 'Sarflangan vaqt', 'Sana'])
    
    for row in results:
        pretty_time = format_time(row.time_spent)
        writer.writerow([row.full_name, f"@{row.username}", row.quiz_name, row.score, row.total, pretty_time, row.date.strftime("%Y-%m-%d %H:%M")])
        
    csv_bytes = output.getvalue().encode('utf-8-sig')
    document = BufferedInputFile(csv_bytes, filename="barcha_natijalar.csv")
    
    await call.message.answer_document(document, caption="📊 Barcha natijalar ro'yxati.")

@admin_router.callback_query(F.data == "delete_this_msg")
async def delete_this_msg_cb(call: types.CallbackQuery):
    with contextlib.suppress(Exception):
        await call.message.delete()
    await call.answer()

@admin_router.message(F.document & (F.from_user.id == settings.ADMIN_ID))
async def handle_document(message: types.Message, bot: Bot, state: FSMContext):
    if not message.document.file_name.endswith('.docx'):
        await message.answer("⚠️ Faqat .docx fayl yuboring.")
        return
        
    msg = await message.answer("⏳ Fayl o'qilmoqda...")
    file_path = f"{message.document.file_id}.docx"
    await bot.download(message.document, destination=file_path)
    
    with open(file_path, "rb") as f:
        file_bytes = f.read()
    os.remove(file_path)
    
    savollar = await async_parse_docx(file_bytes)
    
    if not savollar:
        await msg.edit_text("❌ Xato! Fayldan savollar topilmadi. Formatni tekshiring.")
        return
        
    quiz_id = str(uuid.uuid4())[:8]
    db_quizzes[quiz_id] = {
        'name': message.document.file_name.replace('.docx', ''), 
        'questions': savollar, 
        'time': 15
    }
    
    await state.set_state(QuizState.waiting_for_time)
    await state.update_data(quiz_id=quiz_id)
    
    markup = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="10"), KeyboardButton(text="15"), KeyboardButton(text="20")], 
            [KeyboardButton(text="30"), KeyboardButton(text="45"), KeyboardButton(text="60")]
        ], 
        resize_keyboard=True
    )
    
    await msg.delete()
    await message.answer("⏱ Har bir savol uchun vaqtni (soniyada) tanlang yoki yozing:", reply_markup=markup)

@admin_router.message(QuizState.waiting_for_time, F.from_user.id == settings.ADMIN_ID)
async def set_time_handler(message: types.Message, state: FSMContext, bot: Bot):
    if not message.text.isdigit():
        return
        
    vaqt = int(message.text)
    data = await state.get_data()
    quiz_id = data['quiz_id']
    
    db_quizzes[quiz_id]['time'] = vaqt
    await state.clear()
    
    bot_info = await bot.get_me()
    bot_username = bot_info.username
    quiz_name = db_quizzes[quiz_id]['name']
    q_count = len(db_quizzes[quiz_id]['questions'])
    
    bot_link = f"https://t.me/{bot_username}?start=solo_{quiz_id}"
    
    share_text = (
        f"👆 Yuqoridagi ssilka orqali testni boshlang!\n\n"
        f"📚 Mavzu: {quiz_name}\n"
        f"🔢 Savollar soni: {q_count} ta\n"
        f"⏳ Ajratilgan vaqt: {vaqt} soniya\n"
        f"👨‍💻 Admin: @PigeonPY"
    )
    
    # 100% ishonchli usul (url parametri qaytarildi)
    share_url = f"https://t.me/share/url?url={bot_link}&text={urllib.parse.quote(share_text)}"
    
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="👤 Solo ishlash", url=bot_link),
            InlineKeyboardButton(text="👥 Guruhga qo'shish", url=f"https://t.me/{bot_username}?startgroup=group_{quiz_id}")
        ],
        [
            InlineKeyboardButton(text="↗️ Do'stlarga ulashish", url=share_url)
        ],
        [
            InlineKeyboardButton(text="🗑 Xabarni o'chirish", callback_data="delete_this_msg")
        ]
    ])
    
    text = (
        f"✅ <b>Test muvaffaqiyatli yaratildi!</b>\n\n"
        f"🏷 <b>Mavzu:</b> {quiz_name}\n"
        f"📊 <b>Savollar:</b> {q_count} ta\n"
        f"⏳ <b>Vaqt:</b> Har biriga {vaqt} soniya\n\n"
        f"<i>Quyidagi tugmalar orqali testni o'zingiz ishlashingiz yoki do'stlaringizga ulashishingiz mumkin.</i>"
    )
    
    await message.answer("Test saqlandi.", reply_markup=ReplyKeyboardRemove())
    await message.answer(text, reply_markup=markup, parse_mode="HTML")
import os
import io
import datetime
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile
from sqlalchemy import select, func
import openpyxl

from core.config import settings
from database.engine import async_session_maker
from database.models import User, Quiz, Result

admin_router = Router()

def is_admin(user_id: int) -> bool:
    return user_id == settings.ADMIN_ID

@admin_router.message(Command("stats"))
async def admin_stats(message: types.Message):
    if not is_admin(message.from_user.id):
        return

    today_start = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    async with async_session_maker() as session:
        users_count = await session.scalar(select(func.count(User.user_id))) or 0
        quizzes_count = await session.scalar(select(func.count(Quiz.id))) or 0
        
        # Testning "Boshlash" tugmasi bosilgan jami marta
        results_count = await session.scalar(select(func.sum(Quiz.play_count))) or 0

        today_users = await session.scalar(
            select(func.count(User.user_id)).where(User.created_at >= today_start)
        ) or 0
        
        # O'rtacha foiz va boshqalar
        avg_score_res = await session.execute(
            select(func.sum(Result.score), func.sum(Result.total))
        )
        total_correct, total_asked = avg_score_res.first()
        avg_percentage = round((total_correct / total_asked * 100), 1) if total_asked else 0

    text = (
        "📈 <b>Platforma umumiy statistikasi:</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"👥 <b>Foydalanuvchilar:</b> {users_count} nafar (Bugun: +{today_users})\n"
        f"📝 <b>Yaratilgan testlar:</b> {quizzes_count} ta\n"
        f"🎯 <b>Test boshlangan umumiy soni:</b> {results_count} marta\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 <b>O'rtacha to'g'ri ishlash:</b> {avg_percentage}%\n"
        f"⚡️ <i>Ma'lumotlar bazadan to'g'ridan-to'g'ri olindi.</i>"
    )
    await message.answer(text, parse_mode="HTML")

@admin_router.message(Command("admin_quizzes"))
async def list_quizzes_for_admin(message: types.Message):
    if not is_admin(message.from_user.id):
        return

    async with async_session_maker() as session:
        stmt = (
            select(Quiz.id, Quiz.subject, Quiz.owner_id, Quiz.play_count)
            .order_by(Quiz.play_count.desc())
            .limit(10)
        )
        res = await session.execute(stmt)
        quizzes = res.all()

    if not quizzes:
        return await message.answer("Bazada hali yaratilgan testlar yo'q.")

    text = "📊 <b>Eng ko'p ishlangan testlar (Top 10):</b>\n\n"
    buttons = []
    for q_id, subject, owner_id, plays in quizzes:
        text += (
            f"🔹 <b>{subject}</b>\n"
            f"   ├ Boshlangan: <b>{plays}</b> marta\n"
            f"   └ Muallif ID: <code>{owner_id}</code>\n\n"
        )
        buttons.append([InlineKeyboardButton(text=f"🗑 O'chirish: {subject[:20]}", callback_data=f"del_quiz_{q_id}")])

    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer(text, reply_markup=kb, parse_mode="HTML")

@admin_router.callback_query(F.data.startswith("del_quiz_"))
async def delete_quiz_admin(call: types.CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer("Bu buyruq faqat admin uchun!", show_alert=True)

    quiz_id = call.data.split("del_quiz_")[1]
    async with async_session_maker() as session:
        quiz = await session.get(Quiz, quiz_id)
        if quiz:
            await session.delete(quiz)
            await session.commit()
            await call.answer("Test o'chirildi!", show_alert=True)
            await call.message.delete()
        else:
            await call.answer("Test topilmadi yoki allaqachon o'chirilgan.", show_alert=True)

@admin_router.message(Command("export"))
async def export_results_excel(message: types.Message):
    if not is_admin(message.from_user.id):
        return

    msg = await message.answer("⏳ Excel hisobot tayyorlanmoqda...")

    async with async_session_maker() as session:
        stmt = (
            select(
                Result.id,
                User.full_name,
                User.username,
                Quiz.subject,
                Result.score,
                Result.total,
                Result.time_spent,
                Result.created_at
            )
            .join(User, Result.user_id == User.user_id)
            .join(Quiz, Result.quiz_id == Quiz.id)
            .order_by(Result.created_at.desc())
        )
        records = (await session.execute(stmt)).all()

    if not records:
        await msg.delete()
        return await message.answer("Hali hech qanday test natijalari mavjud emas.")

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Natijalar"

    headers = ["№", "F.I.SH", "Username", "Test mavzusi", "To'g'ri", "Jami", "Sarflangan vaqt (s)", "Sana"]
    ws.append(headers)

    for idx, row in enumerate(records, start=1):
        created_str = row.created_at.strftime("%Y-%m-%d %H:%M") if row.created_at else ""
        ws.append([
            idx,
            row.full_name or "Noma'lum",
            f"@{row.username}" if row.username else "-",
            row.subject,
            row.score,
            row.total,
            row.time_spent,
            created_str
        ])

    for col in ws.columns:
        max_len = max(len(str(cell.value or "")) for cell in col)
        col_letter = openpyxl.utils.get_column_letter(col[0].column)
        ws.column_dimensions[col_letter].width = max(max_len + 3, 12)

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    filename = f"Natijalar_{datetime.date.today()}.xlsx"
    await message.answer_document(
        document=BufferedInputFile(buffer.read(), filename=filename),
        caption="📊 <b>Barcha test natijalari to'liq hisoboti</b>",
        parse_mode="HTML"
    )
    await msg.delete()
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# 1. Test yakunlangandan keyingi menyu (Foydalanuvchi uchun)
def get_result_kb(quiz_id: str, subject: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                # Xuddi shu testni boshidan ishlash
                InlineKeyboardButton(text="🔄 Boshidan", callback_data=f"start_solo_{quiz_id}"),
                # Boshqa oraliqni tanlash uchun o'sha fanga qaytish
                InlineKeyboardButton(text="⬅️ Orqaga", callback_data=f"fan_{subject}")
            ],
            [
                # Fanlar ro'yxatiga butunlay qaytish
                InlineKeyboardButton(text="🔙 Fanlarga qaytish", callback_data="back_to_subjects")
            ]
        ]
    )


# 2. Test yaratayotganda vaqt tanlash menyusi (Admin uchun)
def get_time_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="20 soniya", callback_data="settime_20"),
                InlineKeyboardButton(text="30 soniya", callback_data="settime_30")
            ],
            [
                InlineKeyboardButton(text="40 soniya", callback_data="settime_40"),
                InlineKeyboardButton(text="50 soniya", callback_data="settime_50")
            ]
        ]
    )
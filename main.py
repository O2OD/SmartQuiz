import asyncio
import os
import uuid
from dotenv import load_dotenv
import docx
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, CommandObject
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramRetryAfter

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

db_quizzes = {}
user_sessions = {}

def parse_docx(file_path):
    doc = docx.Document(file_path)
    savollar = []
    joriy_savol = None
    
    for p in doc.paragraphs:
        text = p.text.strip()
        if not text:
            continue
            
        if text[0].isdigit() and (text[1] == '.' or text[2] == '.'):
            if joriy_savol and len(joriy_savol['variantlar']) >= 2:
                savollar.append(joriy_savol)
            joriy_savol = {"savol": text, "variantlar": [], "togri": 0}
        elif joriy_savol and len(joriy_savol['variantlar']) < 10:
            if text.startswith('*') or text.startswith('+'):
                joriy_savol['togri'] = len(joriy_savol['variantlar'])
                text = text[1:].strip()
            joriy_savol['variantlar'].append(text)
            
    if joriy_savol and len(joriy_savol['variantlar']) >= 2:
        savollar.append(joriy_savol)
        
    return savollar

@dp.message(F.document & (F.from_user.id == ADMIN_ID))
async def handle_document(message: types.Message):
    if not message.document.file_name.endswith('.docx'):
        await message.answer("Faqat .docx formatidagi fayl yuboring.")
        return

    msg = await message.answer("⏳ Fayl o'qilmoqda...")
    file_id = message.document.file_id
    file_path = f"{file_id}.docx"
    
    try:
        file = await bot.get_file(file_id)
        await bot.download_file(file.file_path, file_path)
        
        savollar = parse_docx(file_path)
        if not savollar:
            await msg.edit_text("Fayl ichidan testlar topilmadi. Formatni tekshiring.")
            return

        quiz_id = str(uuid.uuid4())[:8]
        db_quizzes[quiz_id] = {
            "name": message.document.file_name.replace('.docx', ''),
            "questions": savollar
        }

        bot_info = await bot.get_me()
        bot_username = bot_info.username

        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="👤 Yakkaxon ishlash", url=f"https://t.me/{bot_username}?start=solo_{quiz_id}")],
            [InlineKeyboardButton(text="👥 Guruhda ishlash", url=f"https://t.me/{bot_username}?startgroup=group_{quiz_id}")]
        ])
        
        await msg.edit_text(
            f"✅ <b>{len(savollar)}</b> ta savol muvaffaqiyatli yuklandi!\n\n"
            f"Test nomi: {db_quizzes[quiz_id]['name']}\n"
            f"Quyidagi tugmalar orqali testni boshlang yoki guruhga ulashing.",
            reply_markup=markup,
            parse_mode="HTML"
        )
    except Exception as e:
        await msg.edit_text(f"Xatolik: {str(e)}")
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)

@dp.message(F.document & (F.from_user.id != ADMIN_ID))
async def ignore_others(message: types.Message):
    pass

@dp.message(CommandStart())
async def start_handler(message: types.Message, command: CommandObject):
    args = command.args
    
    if not args:
        if message.from_user.id == ADMIN_ID:
            await message.answer("Assalomu alaykum. Test yaratish uchun .docx fayl yuboring.")
        else:
            await message.answer("Assalomu alaykum. Testda qatnashish uchun maxsus ssilkadan kiring.")
        return

    if args.startswith("solo_") or args.startswith("group_"):
        mode, quiz_id = args.split("_", 1)
        quiz = db_quizzes.get(quiz_id)
        
        if not quiz:
            await message.answer("Test topilmadi yoki yakunlangan.")
            return

        await message.answer(f"🚀 <b>{quiz['name']}</b> testi boshlanmoqda. Tayyor turing!", parse_mode="HTML")
        await send_quiz_questions(message.chat.id, quiz['questions'])

async def send_quiz_questions(chat_id, questions):
    for q in questions:
        try:
            await bot.send_poll(
                chat_id=chat_id,
                question=q['savol'][:300],
                options=[opt[:100] for opt in q['variantlar']],
                type="quiz",
                correct_option_id=q['togri'],
                is_anonymous=False,
                open_period=45
            )
            await asyncio.sleep(2) 
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after + 1)
            await bot.send_poll(
                chat_id=chat_id,
                question=q['savol'][:300],
                options=[opt[:100] for opt in q['variantlar']],
                type="quiz",
                correct_option_id=q['togri'],
                is_anonymous=False,
                open_period=45
            )
        except Exception as e:
            print(f"Xato: {e}")
            await asyncio.sleep(5)

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
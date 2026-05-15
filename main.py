import asyncio
import os
import uuid
import random
import time
import csv
import asyncpg
import docx
from io import StringIO
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, CommandObject
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, BufferedInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
DB_USER = os.getenv("DB_USER")
DB_PASS = os.getenv("DB_PASS")
DB_NAME = os.getenv("DB_NAME")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

db_pool = None
db_quizzes = {}
active_polls = {}
solo_sessions = {}
group_sessions = {}

class QuizState(StatesGroup):
    waiting_for_time = State()

async def init_db():
    global db_pool
    db_pool = await asyncpg.create_pool(user=DB_USER, password=DB_PASS, database=DB_NAME, host=DB_HOST, port=DB_PORT)
    async with db_pool.acquire() as conn:
        await conn.execute("CREATE TABLE IF NOT EXISTS users (user_id BIGINT PRIMARY KEY, full_name TEXT, username TEXT)")
        await conn.execute("CREATE TABLE IF NOT EXISTS results (id SERIAL PRIMARY KEY, user_id BIGINT, quiz_name TEXT, score INTEGER, total INTEGER, time_spent REAL, date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")

async def save_user(user_id, full_name, username):
    async with db_pool.acquire() as conn:
        await conn.execute("INSERT INTO users (user_id, full_name, username) VALUES ($1, $2, $3) ON CONFLICT (user_id) DO UPDATE SET full_name = EXCLUDED.full_name, username = EXCLUDED.username", user_id, full_name, username)

async def save_result(user_id, quiz_name, score, total, time_spent):
    async with db_pool.acquire() as conn:
        await conn.execute("INSERT INTO results (user_id, quiz_name, score, total, time_spent) VALUES ($1, $2, $3, $4, $5)", user_id, quiz_name, score, total, time_spent)

def parse_docx(file_path):
    doc = docx.Document(file_path)
    savollar = []
    joriy_savol = None
    for p in doc.paragraphs:
        text = p.text.strip()
        if not text: 
            continue
        if text[0].isdigit() and ("." in text[:4] or ")" in text[:4]):
            if joriy_savol and len(joriy_savol['variantlar']) >= 2:
                savollar.append(joriy_savol)
            joriy_savol = {"savol": text, "variantlar": [], "togri": 0}
        elif joriy_savol:
            if text.startswith('*'):
                joriy_savol['togri'] = len(joriy_savol['variantlar'])
                text = text.replace('*', '', 1).strip()
                joriy_savol['variantlar'].append(text)
            elif text.startswith('#'):
                text = text.replace('#', '', 1).strip()
                joriy_savol['variantlar'].append(text)
    if joriy_savol and len(joriy_savol['variantlar']) >= 2:
        savollar.append(joriy_savol)
    for q in savollar:
        v_copy = q['variantlar'].copy()
        correct_text = v_copy[q['togri']]
        random.shuffle(v_copy)
        q['variantlar'] = v_copy
        q['togri'] = v_copy.index(correct_text)
    return savollar

def format_time(seconds):
    m = int(seconds) // 60
    s = int(seconds) % 60
    return f"{m}m {s}s" if m > 0 else f"{s}s"

@dp.message(F.document & (F.from_user.id == ADMIN_ID))
async def handle_document(message: types.Message, state: FSMContext):
    if not message.document.file_name.endswith('.docx'):
        await message.answer("Faqat .docx fayl yuboring.")
        return
    msg = await message.answer("⏳ Tahlil qilinmoqda...")
    file_path = f"{message.document.file_id}.docx"
    await bot.download(message.document, destination=file_path)
    savollar = parse_docx(file_path)
    if not savollar:
        await msg.edit_text("Xato format! (1. Savol, *Javob)")
        return
    quiz_id = str(uuid.uuid4())[:8]
    db_quizzes[quiz_id] = {'name': message.document.file_name.replace('.docx', ''), 'questions': savollar, 'time': 15}
    await state.set_state(QuizState.waiting_for_time)
    await state.update_data(quiz_id=quiz_id)
    markup = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="10 soniya"), KeyboardButton(text="15 soniya"), KeyboardButton(text="20 soniya")], [KeyboardButton(text="25 soniya"), KeyboardButton(text="30 soniya")]], resize_keyboard=True)
    await msg.delete()
    await message.answer("Har bir savol uchun vaqtni tanlang:", reply_markup=markup)
    os.remove(file_path)

@dp.message(QuizState.waiting_for_time, F.from_user.id == ADMIN_ID)
async def set_time_handler(message: types.Message, state: FSMContext):
    t_map = {"10 soniya": 10, "15 soniya": 15, "20 soniya": 20, "25 soniya": 25, "30 soniya": 30}
    vaqt = t_map.get(message.text)
    if not vaqt: 
        return
    data = await state.get_data()
    db_quizzes[data['quiz_id']]['time'] = vaqt
    await state.clear()
    bot_info = await bot.get_me()
    markup = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="👤 Yakkaxon", url=f"https://t.me/{bot_info.username}?start=solo_{data['quiz_id']}")], [InlineKeyboardButton(text="👥 Guruhda", url=f"https://t.me/{bot_info.username}?startgroup=group_{data['quiz_id']}")]])
    await message.answer("Sozlamalar saqlandi.", reply_markup=ReplyKeyboardRemove())
    await message.answer(f"Vaqt: {message.text}\nTestni ulashing:", reply_markup=markup)

@dp.message(F.text == "/admin", F.from_user.id == ADMIN_ID)
async def admin_panel(message: types.Message):
    async with db_pool.acquire() as conn:
        u_count = await conn.fetchval("SELECT COUNT(*) FROM users")
        recent = await conn.fetch("SELECT u.full_name, r.quiz_name, r.score, r.total FROM results r JOIN users u ON r.user_id = u.user_id ORDER BY r.date DESC LIMIT 15")
    text = f"📊 Jami foydalanuvchilar: {u_count}\n\nOxirgi natijalar:\n"
    for r in recent: 
        text += f"👤 {r[0]} | {r[1]} | {r[2]}/{r[3]}\n"
    await message.answer(text)

@dp.message(F.text == "/export", F.from_user.id == ADMIN_ID)
async def export_results(message: types.Message):
    async with db_pool.acquire() as conn:
        res = await conn.fetch("SELECT u.full_name, u.username, r.quiz_name, r.score, r.total, r.time_spent, r.date FROM results r JOIN users u ON r.user_id = u.user_id ORDER BY r.date DESC")
    if not res: 
        return
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(['FIO', 'Username', 'Test', 'Ball', 'Jami', 'Vaqt', 'Sana'])
    for r in res: 
        writer.writerow([r[0], f"@{r[1]}" if r[1] else "-", r[2], r[3], r[4], round(r[5], 2), r[6]])
    await message.answer_document(BufferedInputFile(output.getvalue().encode('utf-8-sig'), filename="results.csv"))

control_kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="⏸ Pauza"), KeyboardButton(text="⏹ Yakunlash")]], resize_keyboard=True)
resume_kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="▶️ Davom etish"), KeyboardButton(text="🔄 Boshidan")], [KeyboardButton(text="⏹ Yakunlash")]], resize_keyboard=True)

@dp.message(CommandStart())
async def start_handler(message: types.Message, command: CommandObject):
    await save_user(message.from_user.id, message.from_user.full_name, message.from_user.username)
    if not command.args:
        if message.from_user.id == ADMIN_ID:
            await message.answer("Salom Admin! Fayl yuboring.")
        else:
            await message.answer("Salom! Savol tuzish uchun @nick_xandrel ga murojaat qiling.")
        return
    if command.args.startswith("solo_"):
        qid = command.args.split("_")[1]
        solo_sessions[message.from_user.id] = {'qid': qid, 'idx': 0, 'score': 0, 'miss': 0, 'status': 'active', 'pid': None, 'start': time.time()}
        await message.answer("Test boshlandi!", reply_markup=control_kb)
        await ask_solo(message.from_user.id)
    elif command.args.startswith("group_"):
        asyncio.create_task(run_group(message.chat.id, command.args.split("_")[1]))

@dp.message(F.text == "⏸ Pauza")
async def pause_solo(message: types.Message):
    if message.from_user.id in solo_sessions:
        solo_sessions[message.from_user.id]['status'] = 'paused'
        await message.answer("Test pauzada.", reply_markup=resume_kb)

@dp.message(F.text == "▶️ Davom etish")
async def resume_solo(message: types.Message):
    uid = message.from_user.id
    if uid in solo_sessions and solo_sessions[uid]['status'] == 'paused':
        solo_sessions[uid]['status'], solo_sessions[uid]['miss'] = 'active', 0
        await message.answer("Davom etamiz...", reply_markup=control_kb)
        await ask_solo(uid)

@dp.message(F.text == "⏹ Yakunlash")
async def stop_solo(message: types.Message):
    if message.from_user.id in solo_sessions: 
        await finish_solo(message.from_user.id)

async def ask_solo(uid):
    s = solo_sessions.get(uid)
    if not s or s['status'] != 'active': 
        return
    q_data = db_quizzes[s['qid']]
    if s['idx'] >= len(q_data['questions']):
        await finish_solo(uid)
        return
    q = q_data['questions'][s['idx']]
   
    msg = await bot.send_poll(
        chat_id=uid, 
        question=f"{s['idx']+1}. {q['savol'][:295]}", 
        options=[o[:100] for o in q['variantlar']], 
        type="quiz", 
        is_anonymous=False, 
        correct_option_id=q['togri'], 
        open_period=q_data['time']
    )
    s['pid'] = msg.poll.id
    active_polls[msg.poll.id] = {'type': 'solo', 'uid': uid, 'mid': msg.message_id, 'cid': q['togri'], 'idx': s['idx']}

@dp.poll_answer()
async def handle_answer(pa: types.PollAnswer):
    pi = active_polls.get(pa.poll_id)
    if not pi: 
        return
    correct = pa.option_ids and pa.option_ids[0] == pi['cid']
    if pi['type'] == 'solo':
        s = solo_sessions.get(pi['uid'])
        if not s or s.get('pid') != pa.poll_id: 
            return
        s['pid'], s['miss'] = None, 0
        if correct: s['score'] += 1
        try: 
            await bot.stop_poll(pi['uid'], pi['mid'])
        except:
            pass
        s['idx'] += 1
        await ask_solo(pi['uid'])
    elif pi['type'] == 'group':
        gs = group_sessions.get(pi['chat_id'])
        if gs:
            u = gs['users'].setdefault(pa.user.id, {'name': pa.user.full_name, 'score': 0, 'time': 0.0})
            if correct: 
                u['score'] += 1
            u['time'] += (time.time() - pi['start'])
            await save_user(pa.user.id, pa.user.full_name, pa.user.username or "")

@dp.poll()
async def handle_close(p: types.Poll):
    if p.is_closed:
    
        pi = active_polls.pop(p.id, None)
        
        if pi and pi['type'] == 'solo':
            uid = pi['uid']
            s = solo_sessions.get(uid)
            
         
            if s and s['status'] == 'active' and s.get('pid') == p.id:
                s['pid'] = None
                s['miss'] += 1
                s['idx'] += 1
                
              
                if s['miss'] >= 2:
                    s['status'] = 'paused'
                  
                    await bot.send_message(
                        chat_id=uid,
                        text="⏸ <b>Test avtomatik pauza qilindi.</b>\n\nSiz ketma-ket 2 ta savolni o'tkazib yubordingiz. Davom etishga tayyor bo'lsangiz, tugmani bosing.",
                        reply_markup=resume_kb,
                        parse_mode="HTML"
                    )
                else:
              
                    await ask_solo(uid)

async def finish_solo(uid):
    s = solo_sessions.pop(uid, None)
    if not s: 
        return
    q = db_quizzes[s['qid']]
    dur = time.time() - s['start']
    await save_result(uid, q['name'], s['score'], len(q['questions']), dur)
    await bot.send_message(uid, f"🏁 Natija: {s['score']}/{len(q['questions'])} | Vaqt: {format_time(dur)}", reply_markup=ReplyKeyboardRemove())

async def run_group(cid, qid):
    q_data = db_quizzes[qid]
    group_sessions[cid] = {'qid': qid, 'users': {}}
    for i, q in enumerate(q_data['questions']):
        # Argumentlar nomi bilan:
        msg = await bot.send_poll(
            chat_id=cid, 
            question=f"{i+1}. {q['savol'][:295]}", 
            options=[o[:100] for o in q['variantlar']], 
            type="quiz", 
            is_anonymous=False, 
            correct_option_id=q['togri'], 
            open_period=q_data['time']
        )
        active_polls[msg.poll.id] = {'type': 'group', 'chat_id': cid, 'cid': q['togri'], 'start': time.time()}
        await asyncio.sleep(q_data['time'] + 1)
    users = group_sessions.pop(cid, {})['users']
    res = sorted(users.values(), key=lambda x: (-x['score'], x['time']))
    txt = "🏆 Guruh Reytingi:\n"
    for i, u in enumerate(res[:15]): 
        txt += f"{i+1}. {u['name']} - {u['score']} ({format_time(u['time'])})\n"
    await bot.send_message(cid, txt)

async def main():
    await init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
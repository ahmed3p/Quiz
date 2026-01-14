import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, BotCommand, ReplyKeyboardRemove
import re
import random
import os
import io
import uuid
import json
import time
import threading
import logging
from datetime import datetime
from fpdf import FPDF
import PyPDF2
from flask import Flask
from deep_translator import GoogleTranslator

# ==============================
# ⚙️ الإعدادات العامة
# ==============================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.getenv('BOT_TOKEN')
ADMIN_ID = 782049835
REQUIRED_CHANNELS = ['@ahmedaqe', '@am2up']
BOT_NAME = "Quizni | كويزني"

bot = telebot.TeleBot(TOKEN)
app = Flask('')

# ==============================
# 💾 إدارة البيانات
# ==============================
FILES = {
    'users': 'users.json', 
    'saved': 'saved.json', 
    'history': 'history.json',
    'shared': 'shared.json', 
    'fixed': 'fixed_quizzes.json'
}

def load_data(f, d):
    if os.path.exists(f):
        try: return json.load(open(f, 'r', encoding='utf-8'))
        except: pass
    return d

def save_data(f, d):
    try: json.dump(d, open(f, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    except: pass

user_data = load_data(FILES['users'], {})
user_saved = load_data(FILES['saved'], {})
user_history = load_data(FILES['history'], {})
shared_quizzes = load_data(FILES['shared'], {})
fixed_quizzes = load_data(FILES['fixed'], {})

user_sessions = {}
user_settings = {}
default_settings = {'timer': False, 'clean_mode': True}

# ==============================
# 🎮 نظام الألعاب (Gamification V2)
# ==============================
RANKS = {
    0: "مبتدئ 🐣",
    500: "مجتهد 📚",
    1500: "متوسط 🎓",
    3000: "متقدم 🌟",
    6000: "عبقري 🧠",
    10000: "أسطورة 💎"
}

def get_rank_info(xp):
    current_rank = "مبتدئ 🐣"
    next_rank = "مجتهد 📚"
    next_xp = 500
    
    sorted_ranks = sorted(RANKS.items())
    for points, title in sorted_ranks:
        if xp >= points:
            current_rank = title
        else:
            next_rank = title
            next_xp = points
            break
            
    return current_rank, next_rank, next_xp

def update_stats(user_id, name="User", is_correct=False, file_uploaded=False):
    uid = str(user_id)
    if uid not in user_data: user_data[uid] = {}
    
    defaults = {
        'name': name, 'xp': 0, 'total_correct': 0, 'files_uploaded': 0, 
        'streak': 0, 'badges': [], 'last_active': '', 'active_days': 0
    }
    for k, v in defaults.items():
        if k not in user_data[uid]: user_data[uid][k] = v
    
    # تحديث الاسم دائماً
    user_data[uid]['name'] = name
    
    ud = user_data[uid]
    today = datetime.now().strftime("%Y-%m-%d")
    
    if ud['last_active'] != today:
        ud['last_active'] = today
        ud['active_days'] += 1
    
    if file_uploaded:
        ud['files_uploaded'] += 1
        if ud['files_uploaded'] >= 1 and 'bookworm' not in ud['badges']: ud['badges'].append('bookworm')

    if is_correct:
        ud['total_correct'] += 1
        ud['streak'] += 1
        ud['xp'] += 10
        
        # الشارات
        if ud['total_correct'] >= 50 and 'sniper' not in ud['badges']: ud['badges'].append('sniper')
        if ud['total_correct'] >= 200 and 'genius' not in ud['badges']: ud['badges'].append('genius')
        if ud['streak'] >= 10 and 'fire' not in ud['badges']: ud['badges'].append('fire')
    else:
        if not file_uploaded: ud['streak'] = 0

    save_data(FILES['users'], user_data)

@app.route('/')
def home(): return "V39 Ultimate Running"
def run(): app.run(host='0.0.0.0', port=8080)
def keep_alive(): threading.Thread(target=run).start()
  # ==============================
# 🚜 FUNDAMENTAL PARSER (V4)
# (CORE LOGIC - DO NOT EDIT)
# ==============================
def parse_questions_from_text(text):
    text = text.replace('\ufeff', '').replace('\r', '')
    
    answer_key = {}
    for m in re.finditer(r'(\d+)[\s\.\-\):]+([a-eA-E1-5])(?!\w)', text):
        try:
            q = int(m.group(1))
            c = {'a':0,'b':1,'c':2,'d':3,'e':4,'1':0,'2':1,'3':2,'4':3,'5':4}.get(m.group(2).lower(), 0)
            answer_key[q] = c
        except: pass

    lines = text.split('\n')
    questions = []
    curr = {'txt': [], 'opts': [], 'mark': []}
    
    p_opt = re.compile(r'^\s*(\*?)\s*[\(\[]?\s*([a-eA-E]|[1-5]|[\-\*])[\.\)\]\-:\s]+(.+)', re.IGNORECASE)
    p_qs = re.compile(r'^\s*(?:Q|س|S)?\s*(\d+)[\.\)\-:\s]+(.+)', re.IGNORECASE)
    
    expected_q_num = 1

    def save():
        if not curr['txt'] or len(curr['opts']) < 2: return
        q_text = "\n".join(curr['txt']).strip()
        correct = curr['mark'][0] if curr['mark'] else None
        
        if not correct:
            idx = len(questions) + 1
            if idx in answer_key and answer_key[idx] < len(curr['opts']):
                correct = curr['opts'][answer_key[idx]]
        
        if not correct and curr['opts']: correct = random.choice(curr['opts'])
        questions.append({'q': q_text, 'opts': curr['opts'], 'correct_txt': correct})

    for line in lines:
        line = line.strip()
        if not line: continue
        if re.match(r'(?:Answer|Key|مفتاح|Page|صفحة)', line, re.IGNORECASE): continue
        if line.isdigit(): continue

        m_q = p_qs.match(line)
        is_new = False
        
        if m_q:
            q_num = int(m_q.group(1))
            if q_num == expected_q_num or len(curr['opts']) > 0 or len(curr['txt']) == 0:
                is_new = True
                expected_q_num = q_num + 1
            elif q_num == 1:
                is_new = True
                expected_q_num = 2

        if is_new:
            save()
            curr = {'txt': [], 'opts': [], 'mark': []}
            curr['txt'].append(m_q.group(2).strip())
        else:
            m_opt = p_opt.match(line)
            if m_opt and len(line) < 300:
                content = m_opt.group(3).strip()
                if not content: content = m_opt.group(2) + " " + m_opt.group(3)
                curr['opts'].append(content)
                if m_opt.group(1) == '*' or line.startswith('*'): curr['mark'].append(content)
            else:
                if not curr['opts']: curr['txt'].append(line)
    
    save()
    return questions
  # ==============================
# 🎨 UI & Helpers
# ==============================

def get_welcome_msg():
    return (
        f"👋 **أهلاً بك في {BOT_NAME}**\n\n"
        "🚀 **ابدأ دراستك بذكاء:**\n"
        "أرسل أي ملف (PDF/TXT) وسأحوله لاختبار تفاعلي مع نظام تقييم متطور!\n\n"
        "👇 **القائمة الرئيسية:**"
    )

def main_menu_markup(chat_id):
    saved_count = len(user_saved.get(str(chat_id), []))
    mk = InlineKeyboardMarkup(row_width=2)
    mk.add(
        InlineKeyboardButton("📤 رفع ملف", callback_data="new_quiz"),
        InlineKeyboardButton("📂 أرشيف ملفاتي", callback_data="my_files_archive")
    )
    mk.add(
        InlineKeyboardButton(f"⭐️ المفضلة ({saved_count})", callback_data="open_saved"),
        InlineKeyboardButton("⚔️ تحدي صديق", callback_data="create_challenge_link")
    )
    mk.add(
        InlineKeyboardButton("👤 إنجازاتي", callback_data="my_profile"),
        InlineKeyboardButton("🏆 المتصدرين", callback_data="leaderboard")
    )
    mk.add(
        InlineKeyboardButton("⚙️ الإعدادات", callback_data="settings_menu"),
        InlineKeyboardButton("📚 اختبارات جاهزة", callback_data="list_fixed")
    )
    return mk

def settings_markup(chat_id):
    if chat_id not in user_settings: user_settings[chat_id] = default_settings.copy()
    s = user_settings[chat_id]
    t = "✅ مفعّل" if s['timer'] else "❌ معطّل"
    c = "✅ مفعّل" if s['clean_mode'] else "❌ معطّل"
    mk = InlineKeyboardMarkup()
    mk.add(InlineKeyboardButton(f"⏱ المؤقت (45ث): {t}", callback_data="toggle_timer"))
    mk.add(InlineKeyboardButton(f"🧹 تنظيف الشات: {c}", callback_data="toggle_clean"))
    mk.add(InlineKeyboardButton("🔙 رجوع", callback_data="main_menu"))
    return mk

class PDF(FPDF):
    def header(self):
        try:
            self.set_font('Arial', 'B', 14)
            self.cell(0, 10, 'Quizni Exam', 0, 1, 'C')
            self.ln(5)
        except: pass

def create_pdf_file(questions, filename):
    try:
        pdf = PDF()
        pdf.add_page()
        pdf.set_font("Arial", size=11)
        for i, q in enumerate(questions):
            try:
                q_txt = q['q'].encode('latin-1', 'replace').decode('latin-1')
                corr = q['correct_txt'].encode('latin-1', 'replace').decode('latin-1')
                pdf.set_font("Arial", 'B', 11)
                pdf.multi_cell(0, 8, f"Q{i+1}: {q_txt}")
                pdf.set_font("Arial", size=10)
                for opt in q['opts']:
                    o_txt = opt.encode('latin-1', 'replace').decode('latin-1')
                    pdf.cell(0, 5, f" - {o_txt}", 0, 1)
                pdf.set_font("Arial", 'B', 10)
                pdf.cell(0, 8, f" [Ans]: {corr}", 0, 1)
                pdf.ln(3)
            except: continue
        pdf.output(filename)
        return True
    except: return False

def check_sub(chat_id, user_id):
    not_joined = []
    for ch in REQUIRED_CHANNELS:
        try:
            status = bot.get_chat_member(ch, user_id).status
            if status not in ['creator', 'administrator', 'member']: not_joined.append(ch)
        except: 
            # إذا لم يتمكن البوت من التحقق (ليس أدمن)، نعتبر المستخدم غير مشترك للأمان
            not_joined.append(ch)
            
    if not_joined:
        mk = InlineKeyboardMarkup(row_width=1)
        for ch in not_joined: mk.add(InlineKeyboardButton(f"🔔 اشتراك في {ch}", url=f"https://t.me/{ch.replace('@', '')}"))
        mk.add(InlineKeyboardButton("✅ تم الاشتراك (تحقق)", callback_data="check_sub_again"))
        try: bot.send_message(chat_id, "⛔️ **عذراً، يجب الاشتراك في القنوات التالية:**", reply_markup=mk, parse_mode="Markdown")
        except: pass
        return False
    return True

def save_to_history(user_id, file_name, questions):
    uid = str(user_id)
    if uid not in user_history: user_history[uid] = []
    user_history[uid].insert(0, {'id': str(uuid.uuid4())[:8], 'name': file_name, 'date': datetime.now().strftime("%Y-%m-%d"), 'count': len(questions), 'questions': questions})
    # يحتفظ بآخر 5 ملفات فقط
    if len(user_history[uid]) > 5: user_history[uid].pop()
    save_data(FILES['history'], user_history)

def translate_text(text):
    try: return GoogleTranslator(source='auto', target='ar').translate(text)
    except: return "خطأ ترجمة"
# ==============================
# 🎮 المنطق & الأدمن
# ==============================
def send_question(chat_id):
    s = user_sessions.get(chat_id)
    if not s: return
    if s['current'] >= len(s['questions']):
        show_results(chat_id)
        return

    q = s['questions'][s['current']]
    current_num = s['current'] + 1
    total = len(s['questions'])
    
    # Progress Bar
    percent_bar = int((current_num / total) * 10)
    bar = "■" * percent_bar + "□" * (10 - percent_bar)
    header_text = f"Q {current_num}/{total} [{bar}]"

    opts = q['opts'].copy()
    random.shuffle(opts)
    try: c_idx = opts.index(q['correct_txt'])
    except: c_idx = 0
    
    s['poll_map'] = s.get('poll_map', {})
    
    mk = InlineKeyboardMarkup()
    mk.row(InlineKeyboardButton("ترجمة 🇮🇶", callback_data="trans_q"))
    
    # زر الحفظ (Toggle)
    uid = str(chat_id)
    is_saved = any(sv['q'] == q['q'] for sv in user_saved.get(uid, []))
    save_txt = "✅ محفوظ (إلغاء)" if is_saved else "⭐️ حفظ"
    
    mk.row(InlineKeyboardButton(save_txt, callback_data="toggle_save"), InlineKeyboardButton("⏭️ تخطي", callback_data="skip"))
    mk.row(InlineKeyboardButton("🏠 إنهاء", callback_data="exit"), InlineKeyboardButton("📤 مشاركة", callback_data="share_current"))

    if chat_id not in user_settings: user_settings[chat_id] = default_settings.copy()
    timer = 45 if user_settings[chat_id]['timer'] else None

    try:
        msg = bot.send_poll(chat_id, f"{header_text}\n{q['q']}", opts, type='quiz', correct_option_id=c_idx, reply_markup=mk, is_anonymous=False, open_period=timer)
        s['poll_map'][msg.poll.id] = {'correct': c_idx, 'q_index': s['current']}
    except:
        txt = f"**{header_text}**\n{q['q']}\n\n"
        for i, o in enumerate(opts): txt += f"{i+1}. {o}\n"
        txt += f"\n|| الحل: {q['correct_txt']} ||"
        bot.send_message(chat_id, txt, parse_mode="Markdown", reply_markup=mk)

def show_results(chat_id):
    s = user_sessions.get(chat_id)
    score = s.get('score', 0)
    total = len(s['questions'])
    wrong_count = len(s.get('wrong_indices', []))
    percent = int((score / total) * 100) if total > 0 else 0
    
    # التحديث النهائي للنقاط
    uid = str(chat_id)
    # ملاحظة: نمرر اسم افتراضي هنا، الاسم الحقيقي يتم تحديثه مع كل تفاعل
    update_stats(uid, name="User") 
    
    share_text = f"حققت {percent}% في اختبار على {BOT_NAME} 🧠🔥"
    msg = (f"🎉 **انتهى الاختبار!**\n━━━━━━━━━━━━\n📊 النسبة: **{percent}%**\n✅ صحيح: {score} | ❌ خطأ: {wrong_count}")

    mk = InlineKeyboardMarkup(row_width=2)
    if wrong_count > 0: mk.add(InlineKeyboardButton("🔁 مراجعة الأخطاء", callback_data="review_mistakes"))
    mk.add(InlineKeyboardButton("🔗 مشاركة النتيجة", switch_inline_query=share_text))
    mk.add(InlineKeyboardButton("📥 تحميل PDF", callback_data="export_pdf"))
    mk.add(InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="main_menu"))
    
    bot.send_message(chat_id, msg, parse_mode="Markdown", reply_markup=mk)
    if chat_id in user_sessions: s['finished'] = True

# --- لوحة الأدمن (المفصلة) ---
@bot.message_handler(commands=['admin'])
def admin_panel(msg):
    if str(msg.from_user.id) != str(ADMIN_ID): return
    
    # تجميع الإحصائيات
    total_users = len(user_data)
    total_files = sum(len(v) for v in user_history.values())
    total_saved_q = sum(len(v) for v in user_saved.values())
    total_fixed_q = len(fixed_quizzes)
    
    # عدد المستخدمين النشطين اليوم (بناء على last_active)
    today = datetime.now().strftime("%Y-%m-%d")
    active_today = sum(1 for u in user_data.values() if u.get('last_active') == today)

    txt = (
        "👮‍♂️ **لوحة التحكم المتقدمة:**\n"
        "━━━━━━━━━━━━━━━━\n"
        f"👥 المستخدمين الكلي: `{total_users}`\n"
        f"🔥 النشطين اليوم: `{active_today}`\n"
        f"📂 الملفات المحللة: `{total_files}`\n"
        f"💾 الأسئلة المحفوظة: `{total_saved_q}`\n"
        f"📚 الاختبارات الجاهزة: `{total_fixed_q}`\n"
        "🤖 الحالة: **ممتاز ✅**"
    )
    bot.reply_to(msg, txt, parse_mode="Markdown")

@bot.message_handler(commands=['add_quiz'])
def add_fixed_quiz(msg):
    if str(msg.from_user.id) != str(ADMIN_ID): return
    cid = msg.chat.id
    if cid not in user_sessions or not user_sessions[cid].get('questions'):
        bot.reply_to(msg, "❌ **خطأ:** لا يوجد اختبار نشط لحفظه.")
        return
    try: name = msg.text.split(maxsplit=1)[1]
    except: bot.reply_to(msg, "❌ الصيغة: `/add_quiz الاسم`"); return

    qs = user_sessions[cid]['questions']
    qid = str(uuid.uuid4())[:8]
    fixed_quizzes[qid] = {'name': name, 'questions': qs, 'date': datetime.now().strftime("%Y-%m-%d")}
    save_data(FILES['fixed'], fixed_quizzes)
    bot.reply_to(msg, f"✅ **تم الحفظ:** {name}")
      # ==============================
# 📦 BUFFER & HANDLERS
# ==============================
text_buffer = {}
buffer_timers = {}

def process_buffered_text(chat_id):
    try:
        full_text = text_buffer.get(chat_id, "").strip()
        if chat_id in text_buffer: del text_buffer[chat_id]
        if chat_id in buffer_timers: del buffer_timers[chat_id]
        if len(full_text) < 5: return 
        
        bot.send_message(chat_id, "⏳ **جاري التحليل...**")
        qs = parse_questions_from_text(full_text)
        if len(qs) >= 1:
            save_to_history(chat_id, f"نص {datetime.now().strftime('%H:%M')}", qs)
            # تحديث الإحصائيات مع الاسم الحالي (سيتم جلبه لاحقاً في التفاعلات)
            update_stats(chat_id, file_uploaded=True) 
            user_sessions[chat_id] = {'questions': qs, 'current': 0, 'score': 0, 'wrong_indices': [], 'poll_map': {}}
            bot.send_message(chat_id, f"✅ **تم!** ({len(qs)} سؤال)")
            send_question(chat_id)
        else: bot.send_message(chat_id, "❌ فشل التحليل.", reply_markup=main_menu_markup(chat_id))
    except Exception as e: logger.error(f"Buffer: {e}")

# --- الأوامر ---
@bot.message_handler(commands=['start', 'profile', 'settings', 'admin'])
def handle_cmds(msg):
    bot.set_my_commands([BotCommand("start", "الرئيسية"), BotCommand("profile", "إنجازاتي"), BotCommand("settings", "الإعدادات")])
    cid = msg.chat.id
    if not check_sub(cid, msg.from_user.id): return

    if msg.text.startswith('/start'):
        # تنظيف الكيبورد
        tmp = bot.send_message(cid, "🔄", reply_markup=ReplyKeyboardRemove())
        bot.delete_message(cid, tmp.message_id)

        args = msg.text.split()
        if len(args) > 1:
            payload = args[1]
            if payload in shared_quizzes:
                user_sessions[cid] = {'questions': shared_quizzes[payload], 'current': 0, 'score': 0, 'wrong_indices': [], 'poll_map': {}}
                bot.send_message(cid, "⚔️ **قبلت التحدي!**")
                send_question(cid)
                return
        bot.send_message(cid, get_welcome_msg(), reply_markup=main_menu_markup(cid), parse_mode="Markdown")
        
    elif msg.text == '/profile': # يرسل رسالة جديدة لضمان العمل
        callback(type('obj', (object,), {'message': msg, 'data': 'my_profile', 'id': '0', 'from_user': msg.from_user})())
    elif msg.text == '/settings':
        callback(type('obj', (object,), {'message': msg, 'data': 'settings_menu', 'id': '0', 'from_user': msg.from_user})())

@bot.message_handler(content_types=['document'])
def doc_handler(msg):
    cid = msg.chat.id
    if not check_sub(cid, msg.from_user.id): return
    msg_wait = bot.send_message(cid, "⏳ **جاري قراءة الملف...**")
    try:
        info = bot.get_file(msg.document.file_id)
        data = bot.download_file(info.file_path)
        text = ""
        if msg.document.file_name.lower().endswith('.pdf'):
            try:
                reader = PyPDF2.PdfReader(io.BytesIO(data))
                for p in reader.pages: text += p.extract_text() + "\n"
            except: pass
        else: text = data.decode('utf-8', 'ignore')
        
        qs = parse_questions_from_text(text)
        if qs:
            save_to_history(cid, msg.document.file_name, qs)
            update_stats(cid, name=msg.from_user.first_name, file_uploaded=True)
            user_sessions[cid] = {'questions': qs, 'current': 0, 'score': 0, 'wrong_indices': [], 'poll_map': {}}
            bot.edit_message_text(f"✅ **تم التجهيز!** ({len(qs)} سؤال)", cid, msg_wait.message_id)
            time.sleep(1)
            send_question(cid)
        else: bot.edit_message_text("❌ لم يتم العثور على أسئلة", cid, msg_wait.message_id)
    except: bot.send_message(cid, "❌ خطأ في الملف")

@bot.poll_answer_handler()
def poll_ans(ans):
    uid = ans.user.id
    if uid in user_sessions and ans.poll_id in user_sessions[uid].get('poll_map', {}):
        p_data = user_sessions[uid]['poll_map'][ans.poll_id]
        if ans.option_ids[0] == p_data['correct']:
            user_sessions[uid]['score'] += 1
            # هنا لا نملك كائن User لتحديث الاسم، نحدث النقاط فقط
            update_stats(uid, is_correct=True)
        else:
            if 'wrong_indices' not in user_sessions[uid]: user_sessions[uid]['wrong_indices'] = []
            user_sessions[uid]['wrong_indices'].append(p_data['q_index'])
            update_stats(uid, is_correct=False)

@bot.callback_query_handler(func=lambda c: True)
def callback(call):
    cid = call.message.chat.id
    d = call.data
    
    if d == "check_sub_again":
        if check_sub(cid, call.from_user.id): bot.send_message(cid, "✅ أهلاً بك!", reply_markup=main_menu_markup(cid))
        return
    if not check_sub(cid, call.from_user.id): return

    # --- التنقل ---
    if d == "main_menu":
        try: bot.edit_message_text(get_welcome_msg(), cid, call.message.message_id, reply_markup=main_menu_markup(cid), parse_mode="Markdown")
        except: bot.send_message(cid, get_welcome_msg(), reply_markup=main_menu_markup(cid), parse_mode="Markdown")

    elif d == "my_profile":
        uid = str(cid)
        # تحديث الاسم لضمان ظهوره في المتصدرين
        update_stats(uid, name=call.from_user.first_name)
        ud = user_data.get(uid)
        curr_rank, next_rank, next_xp = get_rank_info(ud['xp'])
        
        badges_str = " ".join([{'bookworm':'📚','sniper':'🎯','genius':'🧠','fire':'🔥'}.get(b, '') for b in ud.get('badges', [])])
        
        msg = (
            f"👤 **الملف الشخصي**\n"
            f"━━━━━━━━━━━━\n"
            f"📛 الاسم: {call.from_user.first_name}\n"
            f"💎 نقاط الخبرة: `{ud['xp']}`\n"
            f"🏅 الرتبة الحالية: {curr_rank}\n"
            f"🚀 الرتبة القادمة: {next_rank} (عند {next_xp})\n"
            f"📂 ملفات مرفوعة: `{ud.get('files_uploaded', 0)}`\n"
            f"✅ إجابات صحيحة: `{ud.get('total_correct', 0)}`\n"
            f"🎖 الشارات: {badges_str if badges_str else 'لا يوجد'}"
        )
        mk = InlineKeyboardMarkup().add(InlineKeyboardButton("🔙 رجوع", callback_data="main_menu"))
        # إذا تم استدعاؤه من أمر /profile (رسالة جديدة) نرسل رسالة، وإلا نعدل
        try: bot.edit_message_text(msg, cid, call.message.message_id, reply_markup=mk, parse_mode="Markdown")
        except: bot.send_message(cid, msg, reply_markup=mk, parse_mode="Markdown")

    elif d == "leaderboard":
        # ترتيب حسب XP
        sorted_users = sorted(user_data.items(), key=lambda x: x[1].get('xp', 0), reverse=True)[:10]
        msg = "🏆 **لوحة المتصدرين (توب 10):**\n━━━━━━━━━━━━\n"
        
        medals = ["🥇", "🥈", "🥉"]
        for i, (k, v) in enumerate(sorted_users):
            rank_icon = medals[i] if i < 3 else f"**{i+1}.**"
            # استخدام الاسم المحفوظ
            u_name = v.get('name', 'User')
            # إذا الاسم طويل جداً نقصه
            if len(u_name) > 15: u_name = u_name[:12] + "..."
            msg += f"{rank_icon} {u_name} — 💎 {v.get('xp', 0)}\n"
            
        mk = InlineKeyboardMarkup().add(InlineKeyboardButton("🔙 رجوع", callback_data="main_menu"))
        bot.edit_message_text(msg, cid, call.message.message_id, reply_markup=mk, parse_mode="Markdown")

    # --- الأرشيف والملفات ---
    elif d == "my_files_archive":
        uid = str(cid)
        files = user_history.get(uid, [])
        if not files: return bot.answer_callback_query(call.id, "📭 الأرشيف فارغ", show_alert=True)
        mk = InlineKeyboardMarkup()
        for f in files: mk.add(InlineKeyboardButton(f"📄 {f['name']} ({f['count']})", callback_data=f"load_{f['id']}"))
        mk.add(InlineKeyboardButton("🗑 مسح الأرشيف", callback_data="clear_archive"))
        mk.add(InlineKeyboardButton("🔙 رجوع", callback_data="main_menu"))
        bot.edit_message_text("📂 **أرشيف ملفاتك (آخر 5):**", cid, call.message.message_id, reply_markup=mk, parse_mode="Markdown")

    elif d == "clear_archive":
        uid = str(cid)
        user_history[uid] = []
        save_data(FILES['history'], user_history)
        bot.answer_callback_query(call.id, "تم مسح الأرشيف")
        bot.edit_message_text("🗑 **تم مسح الأرشيف بنجاح.**", cid, call.message.message_id, reply_markup=main_menu_markup(cid), parse_mode="Markdown")

    elif d.startswith("load_"):
        fid = d.split("_")[1]
        uid = str(cid)
        f = next((x for x in user_history.get(uid, []) if x['id'] == fid), None)
        if f:
            user_sessions[cid] = {'questions': f['questions'], 'current': 0, 'score': 0, 'wrong_indices': [], 'poll_map': {}}
            bot.send_message(cid, f"♻️ **تم استرجاع:** {f['name']}")
            send_question(cid)

    # --- باقي الوظائف (كما هي) ---
    elif d == "settings_menu":
        bot.edit_message_text("⚙️ **الإعدادات:**", cid, call.message.message_id, reply_markup=settings_markup(cid))
    elif d in ["toggle_timer", "toggle_clean"]:
        user_settings.setdefault(cid, default_settings.copy())
        k = 'timer' if d == "toggle_timer" else 'clean_mode'
        user_settings[cid][k] = not user_settings[cid][k]
        bot.edit_message_reply_markup(cid, call.message.message_id, reply_markup=settings_markup(cid))
    elif d == "toggle_save":
        if cid not in user_sessions: return
        q = user_sessions[cid]['questions'][user_sessions[cid]['current']]
        uid = str(cid)
        if uid not in user_saved: user_saved[uid] = []
        found = False
        for i, s in enumerate(user_saved[uid]):
            if s['q'] == q['q']: user_saved[uid].pop(i); found = True; break
        if not found: user_saved[uid].append(q); bot.answer_callback_query(call.id, "✅ تم الحفظ")
        else: bot.answer_callback_query(call.id, "🗑 تم الإلغاء")
        save_data(FILES['saved'], user_saved)
        try:
            new_mk = call.message.reply_markup
            new_mk.keyboard[1][0].text = "⭐️ حفظ" if found else "✅ محفوظ (إلغاء)"
            bot.edit_message_reply_markup(cid, call.message.message_id, reply_markup=new_mk)
        except: pass
    elif d == "trans_q":
        if cid in user_sessions:
            q = user_sessions[cid]['questions'][user_sessions[cid]['current']]
            full_txt = q['q'] + "\n\n" + "\n".join(q['opts'])
            bot.answer_callback_query(call.id, "جاري الترجمة...")
            tr = translate_text(full_txt)
            bot.send_message(cid, f"🇮🇶 **الترجمة:**\n\n{tr}")
    elif d == "create_challenge_link" or d == "share_current":
        if cid in user_sessions:
            qid = str(uuid.uuid4())[:8]
            shared_quizzes[qid] = user_sessions[cid]['questions']
            save_data(FILES['shared'], shared_quizzes)
            bot.send_message(cid, f"⚔️ **رابط التحدي:**\n`https://t.me/{bot.get_me().username}?start={qid}`", parse_mode="Markdown")
        else: bot.answer_callback_query(call.id, "يجب أن تكون في اختبار!", show_alert=True)
    elif d == "review_mistakes":
        if cid in user_sessions:
            s = user_sessions[cid]
            wrong_qs = [s['questions'][i] for i in s.get('wrong_indices', [])]
            if wrong_qs:
                user_sessions[cid] = {'questions': wrong_qs, 'current': 0, 'score': 0, 'poll_map': {}}
                bot.send_message(cid, "🔁 **مراجعة الأخطاء:**")
                send_question(cid)
            else: bot.answer_callback_query(call.id, "لا توجد أخطاء!", show_alert=True)
    elif d == "open_saved":
        s = user_saved.get(str(cid), [])
        if s: 
            user_sessions[cid] = {'questions': s, 'current': 0, 'score': 0, 'poll_map': {}}
            bot.send_message(cid, f"⭐️ **المفضلة:** {len(s)} سؤال")
            send_question(cid)
        else: bot.answer_callback_query(call.id, "المفضلة فارغة", show_alert=True)
    elif d == "skip":
        user_sessions[cid]['current'] += 1
        if user_settings.get(cid, default_settings)['clean_mode']:
            try: bot.delete_message(cid, call.message.message_id)
            except: pass
        send_question(cid)
    elif d == "exit": show_results(cid)
    elif d == "export_pdf":
        if cid in user_sessions:
            fname = f"Quizni_{cid}.pdf"
            bot.answer_callback_query(call.id, "جاري التصدير...")
            if create_pdf_file(user_sessions[cid]['questions'], fname):
                with open(fname, 'rb') as f: bot.send_document(cid, f)
                os.remove(fname)
            else: bot.send_message(cid, "❌ مشكلة خطوط")
        else: bot.answer_callback_query(call.id, "انتهت الجلسة", show_alert=True)
    elif d == "new_quiz": bot.send_message(cid, "📂 **أرسل ملفك الآن:**")
    elif d == "list_fixed":
        if not fixed_quizzes: return bot.answer_callback_query(call.id, "فارغ", show_alert=True)
        mk = InlineKeyboardMarkup(row_width=1)
        for qid, data in fixed_quizzes.items():
            row = [InlineKeyboardButton(f"📑 {data['name']}", callback_data=f"fix_{qid}")]
            if str(call.from_user.id) == str(ADMIN_ID): row.append(InlineKeyboardButton("🗑", callback_data=f"del_{qid}"))
            mk.row(*row)
        mk.add(InlineKeyboardButton("🔙 رجوع", callback_data="main_menu"))
        bot.edit_message_text("**📚 الاختبارات الجاهزة:**", cid, call.message.message_id, reply_markup=mk, parse_mode="Markdown")
    elif d.startswith("fix_"):
        qid = d.split("_")[1]
        if qid in fixed_quizzes:
            user_sessions[cid] = {'questions': fixed_quizzes[qid]['questions'], 'current': 0, 'score': 0, 'wrong_indices': [], 'poll_map': {}}
            bot.send_message(cid, f"🚀 **بدء: {fixed_quizzes[qid]['name']}**")
            send_question(cid)
    elif d.startswith("del_"):
        if str(call.from_user.id) != str(ADMIN_ID): return
        qid = d.split("_")[1]
        if qid in fixed_quizzes:
            del fixed_quizzes[qid]
            save_data(FILES['fixed'], fixed_quizzes)
            bot.answer_callback_query(call.id, "تم الحذف")
            call.data = "list_fixed"
            callback(call)

@bot.message_handler(func=lambda m: True)
def text_handler(msg):
    cid = msg.chat.id
    if not check_sub(cid, msg.from_user.id): return
    if len(msg.text.strip()) < 5: return 

    if cid in buffer_timers: buffer_timers[cid].cancel()
    if cid not in text_buffer: text_buffer[cid] = ""
    text_buffer[cid] += msg.text.strip() + "\n"
    t = threading.Timer(1.5, process_buffered_text, args=[cid])
    buffer_timers[cid] = t
    t.start()

if __name__ == "__main__":
    keep_alive()
    bot.infinity_polling()
      

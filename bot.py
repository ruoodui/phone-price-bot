import os
import pandas as pd
import json
import io
from datetime import datetime
from thefuzz import process

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, filters, ContextTypes
)

# ======= إعدادات =======
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PRICES_PATH = os.path.join(BASE_DIR, "prices.xlsx")
URLS_PATH = os.path.join(BASE_DIR, "phones_urls.json")
USERS_FILE = os.path.join(BASE_DIR, "users.json")
TOKEN = os.getenv("TOKEN")
CHANNEL_USERNAME = "@mitech808"
ADMIN_IDS = [193646746]

# ======= إدارة المستخدمين =======
def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_users(users):
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, indent=2, ensure_ascii=False)

def store_user(user):
    users = load_users()
    user_id = str(user.id)
    today = datetime.now().strftime("%Y-%m-%d")

    if user_id not in users:
        users[user_id] = {
            "name": user.full_name,
            "username": user.username,
            "id": user.id,
            "active_dates": [today]
        }
    else:
        dates = users[user_id].get("active_dates", [])
        if today not in dates:
            dates.append(today)
        users[user_id]["active_dates"] = dates

    save_users(users)

# ======= تحميل البيانات =======
def load_excel_prices(path=PRICES_PATH):
    df = pd.read_excel(path)
    df = df.dropna(subset=["الاسم (name)", "السعر (price)", "الذاكره (Rom)"])
    phone_map = {}
    for _, row in df.iterrows():
        name = str(row["الاسم (name)"]).strip()
        price = str(row["السعر (price)"]).strip()
        rom = str(row["الذاكره (Rom)"]).strip()
        phone_map.setdefault(name, []).append({"price": price, "rom": rom})
    return phone_map

def load_phone_urls(filepath=URLS_PATH):
    with open(filepath, encoding="utf-8") as f:
        data = json.load(f)
    url_map = {}
    for brand_devices in data.values():
        for phone in brand_devices:
            name = phone.get("name")
            url = phone.get("url", "🔗 غير متوفر")
            if name:
                url_map[name.strip()] = url
    return url_map

price_data = load_excel_prices()
phone_urls = load_phone_urls()

def fuzzy_get_url(name):
    if name in phone_urls:
        return phone_urls[name]
    matches = process.extract(name, phone_urls.keys(), limit=1)
    if matches and matches[0][1] >= 80:
        return phone_urls[matches[0][0]]
    return "https://t.me/mitech808"

WELCOME_MSG = (
    "👋 مرحبًا بك في بوت أسعار الموبايلات!\n\n"
    "📱 أرسل اسم الجهاز (مثال: Galaxy S25 Ultra)\n"
    "💰 أو أرسل السعر (مثال: 1300000) للبحث عن أجهزة في هذا النطاق.\n"
    "🔄 استخدم الأمر /compare لمقارنة جهازين."
)

# ======= تحقق الاشتراك =======
async def check_user_subscription(user_id, context):
    try:
        member = await context.bot.get_chat_member(chat_id=CHANNEL_USERNAME, user_id=user_id)
        return member.status in ["member", "creator", "administrator"]
    except Exception as e:
        print("⚠️ Subscription check failed:", e)
        return False

async def send_subscription_required(update: Update):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 انضم إلى قناتنا", url=f"https://t.me/{CHANNEL_USERNAME.lstrip('@')}")],
        [InlineKeyboardButton("📸 تابعنا على إنستغرام", url="https://www.instagram.com/mitech808")],
        [InlineKeyboardButton("🔄 تحقق من الاشتراك", callback_data="check_subscription")]
    ])
    await update.message.reply_text(
        "🔒 يرجى الانضمام إلى قناتنا على تليغرام من أجل استخدام البوت 😍✅\n\n"
        f"📢 قناة التليغرام: {CHANNEL_USERNAME}\n"
        "📸 أيضًا يجب متابعة حساب الإنستغرام:\n"
        "https://www.instagram.com/mitech808\n\n"
        "✅ بعد الاشتراك، اضغط على /start للبدء الآن.",
        reply_markup=keyboard
    )

# ======= إحصائيات =======
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ هذا الأمر مخصص للمشرف فقط.")
        return

    users = load_users()
    all_dates = set()
    for u in users.values():
        all_dates.update(u.get("active_dates", []))

    if not all_dates:
        await update.message.reply_text("❌ لا توجد تواريخ مسجلة.")
        return

    sorted_dates = sorted(all_dates, reverse=True)
    keyboard = [
        [InlineKeyboardButton(date, callback_data=f"show_stats:{date}")]
        for date in sorted_dates
    ]
    await update.message.reply_text(
        "📅 اختر التاريخ لعرض الإحصائية:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def stats_by_date_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.from_user.id not in ADMIN_IDS:
        await query.edit_message_text("❌ هذا الخيار مخصص للمشرف فقط.")
        return

    _, target_date = query.data.split(":", 1)
    users = load_users()
    matched_users = [u for u in users.values() if target_date in u.get("active_dates", [])]

    msg = f"📅 إحصائية المستخدمين في يوم: {target_date}\n"
    msg += f"👥 العدد: {len(matched_users)}\n\n"

    for user in matched_users:
        name = user['name']
        username = f"@{user['username']}" if user['username'] else "—"
        msg += f"🆔 {user['id']} | {name} | {username}\n"

    await query.edit_message_text(msg)

    if matched_users:
        df = pd.DataFrame(matched_users)
        df = df[["id", "name", "username", "active_dates"]]
        df.columns = ["User ID", "Name", "Username", "Active Dates"]

        excel_io = io.BytesIO()
        df.to_excel(excel_io, index=False, engine='openpyxl')
        excel_io.seek(0)

        await context.bot.send_document(
            chat_id=query.message.chat_id,
            document=excel_io,
            filename=f"UserStats_{target_date}.xlsx",
            caption="📄 ملف إحصائية المستخدمين لهذا اليوم"
        )

# ======= تشغيل البوت =======
def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CallbackQueryHandler(stats_by_date_button, pattern="^show_stats:"))

    print("✅ البوت يعمل الآن...")
    app.run_polling()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not await check_user_subscription(user_id, context):
        return await send_subscription_required(update)

    store_user(update.effective_user)
    await update.message.reply_text(WELCOME_MSG)

if __name__ == "__main__":
    main()

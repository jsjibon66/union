import os
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

DB = "microjob.db"


def db():
    return sqlite3.connect(DB)


def setup():
    con = db()
    cur = con.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            balance REAL DEFAULT 0
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            description TEXT,
            reward REAL,
            status TEXT DEFAULT 'open'
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER,
            user_id INTEGER,
            proof TEXT,
            status TEXT DEFAULT 'pending'
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS withdrawals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            method TEXT,
            number TEXT,
            amount REAL,
            status TEXT DEFAULT 'pending'
        )
    """)

    con.commit()
    con.close()


def add_user(user_id):
    con = db()
    cur = con.cursor()
    cur.execute(
        "INSERT OR IGNORE INTO users(user_id,balance) VALUES(?,0)",
        (user_id,)
    )
    con.commit()
    con.close()


def main_menu():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🧑‍💻 কাজ দেখুন", callback_data="jobs"),
            InlineKeyboardButton("💰 ব্যালেন্স", callback_data="balance")
        ],
        [
            InlineKeyboardButton("📋 আমার কাজ", callback_data="myjobs"),
            InlineKeyboardButton("💸 টাকা উত্তোলন", callback_data="withdraw")
        ],
        [
            InlineKeyboardButton("👤 প্রোফাইল", callback_data="profile"),
            InlineKeyboardButton("📞 সাপোর্ট", callback_data="support")
        ],
    ])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    add_user(user.id)

    await update.message.reply_text(
        f"স্বাগতম {user.first_name}!\n\n"
        "এখানে বৈধ Micro Job করে রিওয়ার্ড অর্জন করতে পারবেন।",
        reply_markup=main_menu()
    )


async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    add_user(user_id)

    if query.data == "balance":
        con = db()
        cur = con.cursor()
        cur.execute(
            "SELECT balance FROM users WHERE user_id=?",
            (user_id,)
        )
        balance = cur.fetchone()[0]
        con.close()

        await query.message.reply_text(
            f"💰 আপনার ব্যালেন্স: {balance:.2f} টাকা"
        )

    elif query.data == "profile":
        await query.message.reply_text(
            f"👤 আপনার প্রোফাইল\n\n"
            f"User ID: {user_id}"
        )

    elif query.data == "jobs":
        con = db()
        cur = con.cursor()
        cur.execute("""
            SELECT id,title,description,reward
            FROM jobs
            WHERE status='open'
            ORDER BY id DESC
        """)
        jobs = cur.fetchall()
        con.close()

        if not jobs:
            await query.message.reply_text(
                "📭 বর্তমানে কোনো কাজ পাওয়া যাচ্ছে না।"
            )
            return

        for job_id, title, description, reward in jobs:
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "✅ কাজটি নিন",
                        callback_data=f"take_{job_id}"
                    )
                ]
            ])

            await query.message.reply_text(
                f"🧑‍💻 {title}\n\n"
                f"{description}\n\n"
                f"💰 Reward: {reward:.2f} টাকা",
                reply_markup=keyboard
            )

    elif query.data.startswith("take_"):
        job_id = int(query.data.split("_")[1])

        con = db()
        cur = con.cursor()
        cur.execute(
            "SELECT title,description,reward FROM jobs WHERE id=? AND status='open'",
            (job_id,)
        )
        job = cur.fetchone()
        con.close()

        if not job:
            await query.message.reply_text("❌ কাজটি আর available নেই।")
            return

        context.user_data["job_id"] = job_id

        await query.message.reply_text(
            f"📝 কাজ: {job[0]}\n\n"
            f"{job[1]}\n\n"
            "কাজ শেষ করার পর আপনার proof/screenshot এখানে পাঠান।"
        )

    elif query.data == "withdraw":
        context.user_data["withdraw_step"] = "method"

        await query.message.reply_text(
            "💸 টাকা উত্তোলন\n\n"
            "মাধ্যম নির্বাচন করুন:\n"
            "1️⃣ bKash\n"
            "2️⃣ Nagad\n\n"
            "শুধু লিখুন: bKash অথবা Nagad"
        )

    elif query.data == "myjobs":
        con = db()
        cur = con.cursor()
        cur.execute("""
            SELECT jobs.title, submissions.status
            FROM submissions
            JOIN jobs ON jobs.id=submissions.job_id
            WHERE submissions.user_id=?
            ORDER BY submissions.id DESC
        """, (user_id,))
        rows = cur.fetchall()
        con.close()

        if not rows:
            await query.message.reply_text("📋 এখনো কোনো কাজ জমা দেননি।")
            return

        text = "📋 আপনার কাজ:\n\n"
        for title, status in rows:
            text += f"• {title} — {status}\n"

        await query.message.reply_text(text)

    elif query.data == "support":
        await query.message.reply_text(
            "📞 Support\n\n"
            "সমস্যা হলে Admin-এর সাথে যোগাযোগ করুন।"
        )


async def messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    # Proof submission
    if "job_id" in context.user_data:
        job_id = context.user_data.pop("job_id")

        con = db()
        cur = con.cursor()

        cur.execute(
            "INSERT INTO submissions(job_id,user_id,proof) VALUES(?,?,?)",
            (job_id, user_id, text)
        )

        con.commit()
        con.close()

        await update.message.reply_text(
            "✅ আপনার কাজের proof জমা হয়েছে।\n"
            "Admin যাচাই করার পর reward যোগ হবে।"
        )

        if ADMIN_ID:
            await context.bot.send_message(
                ADMIN_ID,
                f"📥 নতুন Job Submission\n\n"
                f"User ID: {user_id}\n"
                f"Job ID: {job_id}\n\n"
                f"Proof:\n{text}"
            )

        return

    # Withdrawal
    if context.user_data.get("withdraw_step") == "method":
        if text.lower() not in ["bkash", "nagad"]:
            await update.message.reply_text(
                "শুধু bKash অথবা Nagad লিখুন।"
            )
            return

        context.user_data["withdraw_method"] = text
        context.user_data["withdraw_step"] = "number"

        await update.message.reply_text(
            "📱 এখন আপনার bKash/Nagad নম্বর লিখুন:"
        )
        return

    if context.user_data.get("withdraw_step") == "number":
        context.user_data["withdraw_number"] = text
        context.user_data["withdraw_step"] = "amount"

        await update.message.reply_text(
            "💰 কত টাকা তুলতে চান লিখুন:"
        )
        return

    if context.user_data.get("withdraw_step") == "amount":
        try:
            amount = float(text)
        except ValueError:
            await update.message.reply_text("সঠিক টাকার পরিমাণ লিখুন।")
            return

        method = context.user_data["withdraw_method"]
        number = context.user_data["withdraw_number"]

        con = db()
        cur = con.cursor()

        cur.execute(
            "SELECT balance FROM users WHERE user_id=?",
            (user_id,)
        )
        balance = cur.fetchone()[0]

        if amount <= 0 or amount > balance:
            con.close()
            await update.message.reply_text(
                f"❌ পর্যাপ্ত ব্যালেন্স নেই।\n"
                f"বর্তমান ব্যালেন্স: {balance:.2f} টাকা"
            )
            return

        cur.execute("""
            INSERT INTO withdrawals(user_id,method,number,amount)
            VALUES(?,?,?,?)
        """, (user_id, method, number, amount))

        cur.execute(
            "UPDATE users SET balance=balance-? WHERE user_id=?",
            (amount, user_id)
        )

        con.commit()
        con.close()

        context.user_data.clear()

        await update.message.reply_text(
            "✅ Withdrawal request জমা হয়েছে।\n"
            "Admin যাচাই করে পেমেন্ট করবেন।"
        )

        if ADMIN_ID:
            await context.bot.send_message(
                ADMIN_ID,
                f"💸 নতুন Withdrawal Request\n\n"
                f"User: {user_id}\n"
                f"Method: {method}\n"
                f"Number: {number}\n"
                f"Amount: {amount:.2f}"
            )

        return


def run():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN সেট করা হয়নি।")

    setup()

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button))
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, messages)
    )

    print("Micro Job Bot started...")
    app.run_polling()


if __name__ == "__main__":
    run()

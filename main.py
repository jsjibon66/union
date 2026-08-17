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

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

MIN_WITHDRAW = 100
MAX_WITHDRAW = 5000

DB_NAME = "bot.db"


def db():
    return sqlite3.connect(DB_NAME)


def setup_database():
    con = db()
    cur = con.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            name TEXT,
            username TEXT,
            balance REAL DEFAULT 0
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            description TEXT,
            reward REAL,
            link TEXT,
            active INTEGER DEFAULT 1
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            task_id INTEGER,
            proof TEXT,
            status TEXT DEFAULT 'pending',
            UNIQUE(user_id, task_id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS withdrawals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount REAL,
            method TEXT,
            number TEXT,
            status TEXT DEFAULT 'pending'
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount REAL,
            kind TEXT,
            note TEXT
        )
    """)

    con.commit()
    con.close()


def add_user(user):
    con = db()
    cur = con.cursor()

    cur.execute("""
        INSERT OR IGNORE INTO users
        (user_id, name, username, balance)
        VALUES (?, ?, ?, 0)
    """, (
        user.id,
        user.first_name or "",
        user.username or ""
    ))

    con.commit()
    con.close()


def get_balance(user_id):
    con = db()
    cur = con.cursor()

    cur.execute(
        "SELECT balance FROM users WHERE user_id=?",
        (user_id,)
    )

    row = cur.fetchone()
    con.close()

    return row[0] if row else 0


def user_menu():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📋 কাজ করুন", callback_data="tasks"),
            InlineKeyboardButton("💰 ব্যালেন্স", callback_data="balance")
        ],
        [
            InlineKeyboardButton("💸 টাকা তুলুন", callback_data="withdraw"),
            InlineKeyboardButton("📜 ইতিহাস", callback_data="history")
        ],
        [
            InlineKeyboardButton("👥 রেফার", callback_data="referral"),
            InlineKeyboardButton("🎧 সাপোর্ট", callback_data="support")
        ]
    ])


def admin_menu():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("➕ নতুন Task", callback_data="admin_new_task"),
            InlineKeyboardButton("📋 Tasks", callback_data="admin_tasks")
        ],
        [
            InlineKeyboardButton("📝 Proof", callback_data="admin_proofs"),
            InlineKeyboardButton("💸 Withdrawals", callback_data="admin_withdrawals")
        ],
        [
            InlineKeyboardButton("👥 Users", callback_data="admin_users"),
            InlineKeyboardButton("📊 Statistics", callback_data="admin_stats")
        ]
    ])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user
    add_user(user)

    if user.id == ADMIN_ID:

        await update.message.reply_text(
            "👑 <b>ADMIN PANEL</b>\n\n"
            "স্বাগতম Admin!\n"
            "নিচের মেনু থেকে কাজ নির্বাচন করুন।",
            parse_mode="HTML",
            reply_markup=admin_menu()
        )

    else:

        await update.message.reply_text(
            "🎉 <b>স্বাগতম Task Rewards Bot-এ!</b>\n\n"
            "📋 কাজ সম্পন্ন করুন\n"
            "💰 Reward উপার্জন করুন\n"
            "💸 Minimum withdrawal: ৳100\n\n"
            "নিচের মেনু থেকে শুরু করুন 👇",
            parse_mode="HTML",
            reply_markup=user_menu()
        )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    data = query.data

    # =========================
    # USER BALANCE
    # =========================

    if data == "balance":

        balance = get_balance(user_id)

        await query.message.reply_text(
            f"💰 <b>আপনার ব্যালেন্স</b>\n\n"
            f"💵 ৳{balance:.2f}",
            parse_mode="HTML",
            reply_markup=user_menu()
        )

    # =========================
    # TASK LIST
    # =========================

    elif data == "tasks":

        con = db()
        cur = con.cursor()

        cur.execute("""
            SELECT id, title, description, reward, link
            FROM tasks
            WHERE active=1
            ORDER BY id DESC
        """)

        tasks = cur.fetchall()
        con.close()

        if not tasks:

            await query.message.reply_text(
                "📭 বর্তমানে কোনো Task নেই।\n\n"
                "পরে আবার চেষ্টা করুন।",
                reply_markup=user_menu()
            )

            return

        for task in tasks:

            task_id, title, description, reward, link = task

            con = db()
            cur = con.cursor()

            cur.execute("""
                SELECT 1
                FROM submissions
                WHERE user_id=? AND task_id=?
            """, (user_id, task_id))

            already_done = cur.fetchone()

            con.close()

            if already_done:
                continue

            keyboard = []

            if link:

                keyboard.append([
                    InlineKeyboardButton(
                        "🔗 Task খুলুন",
                        url=link
                    )
                ])

            keyboard.append([
                InlineKeyboardButton(
                    "📸 Proof জমা দিন",
                    callback_data=f"submit_{task_id}"
                )
            ])

            await query.message.reply_text(
                f"📋 <b>{title}</b>\n\n"
                f"📝 {description or 'কোনো বিবরণ নেই'}\n\n"
                f"💰 Reward: ৳{reward:.2f}",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

    # =========================
    # SUBMIT PROOF
    # =========================

    elif data.startswith("submit_"):

        task_id = int(data.split("_")[1])

        context.user_data["proof_task"] = task_id

        await query.message.reply_text(
            "📸 <b>Proof জমা দিন</b>\n\n"
            "Task সম্পন্ন করার screenshot অথবা প্রয়োজনীয় তথ্য পাঠান।",
            parse_mode="HTML"
        )

    # =========================
    # WITHDRAW
    # =========================

    elif data == "withdraw":

        balance = get_balance(user_id)

        if balance < MIN_WITHDRAW:

            await query.message.reply_text(
                f"❌ আপনার ব্যালেন্স যথেষ্ট নয়।\n\n"
                f"💰 বর্তমান: ৳{balance:.2f}\n"
                f"📌 Minimum withdrawal: ৳{MIN_WITHDRAW}",
                reply_markup=user_menu()
            )

            return

        context.user_data["withdraw_step"] = "amount"

        await query.message.reply_text(
            f"💸 <b>Withdrawal</b>\n\n"
            f"কত টাকা তুলতে চান লিখুন।\n\n"
            f"Minimum: ৳{MIN_WITHDRAW}\n"
            f"Maximum: ৳{MAX_WITHDRAW}",
            parse_mode="HTML"
        )

    # =========================
    # HISTORY
    # =========================

    elif data == "history":

        con = db()
        cur = con.cursor()

        cur.execute("""
            SELECT amount, kind, note
            FROM transactions
            WHERE user_id=?
            ORDER BY id DESC
            LIMIT 10
        """, (user_id,))

        rows = cur.fetchall()
        con.close()

        if not rows:

            text = "📜 এখনো কোনো transaction নেই।"

        else:

            text = "📜 <b>Transaction History</b>\n\n"

            for amount, kind, note in rows:

                text += (
                    f"💰 ৳{amount:.2f}\n"
                    f"📌 {kind}\n"
                    f"📝 {note}\n\n"
                )

        await query.message.reply_text(
            text,
            parse_mode="HTML",
            reply_markup=user_menu()
        )

    # =========================
    # REFERRAL
    # =========================

    elif data == "referral":

        bot = await context.bot.get_me()

        link = (
            f"https://t.me/{bot.username}"
            f"?start=ref_{user_id}"
        )

        await query.message.reply_text(
            "👥 <b>Referral</b>\n\n"
            "আপনার Referral Link:\n\n"
            f"<code>{link}</code>",
            parse_mode="HTML",
            reply_markup=user_menu()
        )

    # =========================
    # SUPPORT
    # =========================

    elif data == "support":

        await query.message.reply_text(
            "🎧 <b>Support</b>\n\n"
            "সমস্যা হলে Admin-এর সাথে যোগাযোগ করুন।",
            parse_mode="HTML",
            reply_markup=user_menu()
        )

    # =========================
    # ADMIN STATISTICS
    # =========================

    elif data == "admin_stats":

        if user_id != ADMIN_ID:
            return

        con = db()
        cur = con.cursor()

        cur.execute("SELECT COUNT(*) FROM users")
        users = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM tasks")
        tasks = cur.fetchone()[0]

        cur.execute("""
            SELECT COUNT(*)
            FROM submissions
            WHERE status='pending'
        """)

        proofs = cur.fetchone()[0]

        cur.execute("""
            SELECT COUNT(*)
            FROM withdrawals
            WHERE status='pending'
        """)

        withdrawals = cur.fetchone()[0]

        con.close()

        await query.message.reply_text(
            f"📊 <b>Statistics</b>\n\n"
            f"👥 Users: {users}\n"
            f"📋 Tasks: {tasks}\n"
            f"📝 Pending Proof: {proofs}\n"
            f"💸 Pending Withdrawal: {withdrawals}",
            parse_mode="HTML",
            reply_markup=admin_menu()
        )

    # =========================
    # ADMIN USERS
    # =========================

    elif data == "admin_users":

        if user_id != ADMIN_ID:
            return

        con = db()
        cur = con.cursor()

        cur.execute("SELECT COUNT(*) FROM users")

        total = cur.fetchone()[0]

        con.close()

        await query.message.reply_text(
            f"👥 মোট User: <b>{total}</b>",
            parse_mode="HTML",
            reply_markup=admin_menu()
        )

    # =========================
    # ADMIN TASKS
    # =========================

    elif data == "admin_tasks":

        if user_id != ADMIN_ID:
            return

        con = db()
        cur = con.cursor()

        cur.execute("""
            SELECT id, title, reward, active
            FROM tasks
            ORDER BY id DESC
        """)

        tasks = cur.fetchall()

        con.close()

        if not tasks:

            await query.message.reply_text(
                "📭 এখনো কোনো Task তৈরি হয়নি।",
                reply_markup=admin_menu()
            )

            return

        text = "📋 <b>All Tasks</b>\n\n"

        for task_id, title, reward, active in tasks:

            status = "🟢 Active" if active else "🔴 Off"

            text += (
                f"#{task_id} — {title}\n"
                f"💰 ৳{reward:.2f}\n"
                f"{status}\n\n"
            )

        await query.message.reply_text(
            text,
            parse_mode="HTML",
            reply_markup=admin_menu()
        )

    # =========================
    # ADMIN NEW TASK
    # =========================

    elif data == "admin_new_task":

        if user_id != ADMIN_ID:
            return

        context.user_data["admin_step"] = "title"

        await query.message.reply_text(
            "➕ <b>নতুন Task</b>\n\n"
            "Task-এর নাম লিখুন।",
            parse_mode="HTML"
        )

    # =========================
    # ADMIN PROOFS
    # =========================

    elif data == "admin_proofs":

        if user_id != ADMIN_ID:
            return

        con = db()
        cur = con.cursor()

        cur.execute("""
            SELECT
                s.id,
                s.user_id,
                s.task_id,
                s.proof,
                t.title,
                t.reward
            FROM submissions s
            JOIN tasks t ON t.id=s.task_id
            WHERE s.status='pending'
            ORDER BY s.id DESC
        """)

        rows = cur.fetchall()

        con.close()

        if not rows:

            await query.message.reply_text(
                "📭 কোনো pending proof নেই।",
                reply_markup=admin_menu()
            )

            return

        for submission_id, uid, task_id, proof, title, reward in rows:

            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "✅ Approve",
                        callback_data=f"approve_{submission_id}"
                    ),
                    InlineKeyboardButton(
                        "❌ Reject",
                        callback_data=f"reject_{submission_id}"
                    )
                ]
            ])

            await query.message.reply_text(
                f"📝 <b>Proof #{submission_id}</b>\n\n"
                f"👤 User: <code>{uid}</code>\n"
                f"📋 Task: {title}\n"
                f"💰 Reward: ৳{reward:.2f}\n\n"
                f"📄 Proof:\n{proof}",
                parse_mode="HTML",
                reply_markup=keyboard
            )

    # =========================
    # APPROVE PROOF
    # =========================

    elif data.startswith("approve_"):

        if user_id != ADMIN_ID:
            return

        submission_id = int(data.split("_")[1])

        con = db()
        cur = con.cursor()

        cur.execute("""
            SELECT s.user_id, s.task_id, t.reward
            FROM submissions s
            JOIN tasks t ON t.id=s.task_id
            WHERE s.id=? AND s.status='pending'
        """, (submission_id,))

        row = cur.fetchone()

        if not row:

            con.close()

            await query.message.reply_text(
                "⚠️ এই submission আর pending নেই."
            )

            return

        target_user, task_id, reward = row

        cur.execute("""
            UPDATE submissions
            SET status='approved'
            WHERE id=?
        """, (submission_id,))

        cur.execute("""
            UPDATE users
            SET balance=balance+?
            WHERE user_id=?
        """, (reward, target_user))

        cur.execute("""
            INSERT INTO transactions
            (user_id, amount, kind, note)
            VALUES (?, ?, ?, ?)
        """, (
            target_user,
            reward,
            "Task Reward",
            f"Task #{task_id}"
        ))

        con.commit()
        con.close()

        await context.bot.send_message(
            target_user,
            f"🎉 <b>Task Approved!</b>\n\n"
            f"💰 Reward: ৳{reward:.2f}\n"
            f"💵 আপনার নতুন Balance: ৳{get_balance(target_user):.2f}",
            parse_mode="HTML"
        )

        await query.message.reply_text(
            "✅ Proof approved এবং reward যোগ হয়েছে।"
        )

    # =========================
    # REJECT PROOF
    # =========================

    elif data.startswith("reject_"):

        if user_id != ADMIN_ID:
            return

        submission_id = int(data.split("_")[1])

        con = db()
        cur = con.cursor()

        cur.execute("""
            SELECT user_id
            FROM submissions
            WHERE id=? AND status='pending'
        """, (submission_id,))

        row = cur.fetchone()

        if row:

            target_user = row[0]

            cur.execute("""
                UPDATE submissions
                SET status='rejected'
                WHERE id=?
            """, (submission_id,))

            con.commit()

            await context.bot.send_message(
                target_user,
                "❌ আপনার Task proof reject করা হয়েছে।"
            )

        con.close()

        await query.message.reply_text(
            "❌ Proof rejected."
        )

    # =========================
    # ADMIN WITHDRAWALS
    # =========================

    elif data == "admin_withdrawals":

        if user_id != ADMIN_ID:
            return

        con = db()
        cur = con.cursor()

        cur.execute("""
            SELECT id, user_id, amount, method, number
            FROM withdrawals
            WHERE status='pending'
            ORDER BY id DESC
        """)

        rows = cur.fetchall()

        con.close()

        if not rows:

            await query.message.reply_text(
                "📭 কোনো pending withdrawal নেই।",
                reply_markup=admin_menu()
            )

            return

        for withdrawal_id, uid, amount, method, number in rows:

            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "✅ Approve",
                        callback_data=f"approve_w_{withdrawal_id}"
                    ),
                    InlineKeyboardButton(
                        "❌ Reject",
                        callback_data=f"reject_w_{withdrawal_id}"
                    )
                ]
            ])

            await query.message.reply_text(
                f"💸 <b>Withdrawal #{withdrawal_id}</b>\n\n"
                f"👤 User: <code>{uid}</code>\n"
                f"💰 Amount: ৳{amount:.2f}\n"
                f"📱 Method: {method}\n"
                f"☎️ Number: <code>{number}</code>",
                parse_mode="HTML",
                reply_markup=keyboard
            )

    # =========================
    # APPROVE WITHDRAWAL
    # =========================

    elif data.startswith("approve_w_"):

        if user_id != ADMIN_ID:
            return

        withdrawal_id = int(data.split("_")[2])

        con = db()
        cur = con.cursor()

        cur.execute("""
            SELECT user_id, amount
            FROM withdrawals
            WHERE id=? AND status='pending'
        """, (withdrawal_id,))

        row = cur.fetchone()

        if not row:

            con.close()

            await query.message.reply_text(
                "⚠️ Withdrawal আর pending নেই।"
            )

            return

        target_user, amount = row

        cur.execute("""
            UPDATE withdrawals
            SET status='approved'
            WHERE id=?
        """, (withdrawal_id,))

        con.commit()
        con.close()

        await context.bot.send_message(
            target_user,
            f"✅ আপনার ৳{amount:.2f} withdrawal approve হয়েছে।"
        )

        await query.message.reply_text(
            "✅ Withdrawal approved."
        )

    # =========================
    # REJECT WITHDRAWAL
    # =========================

    elif data.startswith("reject_w_"):

        if user_id != ADMIN_ID:
            return

        withdrawal_id = int(data.split("_")[2])

        con = db()
        cur = con.cursor()

        cur.execute("""
            SELECT user_id, amount
            FROM withdrawals
            WHERE id=? AND status='pending'
        """, (withdrawal_id,))

        row = cur.fetchone()

        if not row:

            con.close()

            await query.message.reply_text(
                "⚠️ Withdrawal আর pending নেই।"
            )

            return

        target_user, amount = row

        cur.execute("""
            UPDATE withdrawals
            SET status='rejected'
            WHERE id=?
        """, (withdrawal_id,))

        cur.execute("""
            UPDATE users
            SET balance=balance+?
            WHERE user_id=?
        """, (amount, target_user))

        cur.execute("""
            INSERT INTO transactions
            (user_id, amount, kind, note)
            VALUES (?, ?, ?, ?)
        """, (
            target_user,
            amount,
            "Refund",
            f"Withdrawal #{withdrawal_id} rejected"
        ))

        con.commit()
        con.close()

        await context.bot.send_message(
            target_user,
            f"❌ আপনার withdrawal reject হয়েছে।\n"
            f"💰 ৳{amount:.2f} balance-এ ফেরত দেওয়া হয়েছে।"
        )

        await query.message.reply_text(
            "❌ Withdrawal rejected এবং balance ফেরত দেওয়া হয়েছে।"
        )


async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user
    text = update.message.text.strip()

    add_user(user)

    # =========================
    # WITHDRAW AMOUNT
    # =========================

    if context.user_data.get("withdraw_step") == "amount":

        try:
            amount = float(text)

        except ValueError:

            await update.message.reply_text(
                "❌ শুধু amount লিখুন। যেমন: 100"
            )

            return

        if amount < MIN_WITHDRAW:

            await update.message.reply_text(
                f"❌ Minimum withdrawal ৳{MIN_WITHDRAW}"
            )

            return

        if amount > MAX_WITHDRAW:

            await update.message.reply_text(
                f"❌ Maximum withdrawal ৳{MAX_WITHDRAW}"
            )

            return

        if amount > get_balance(user.id):

            await update.message.reply_text(
                "❌ আপনার balance যথেষ্ট নয়।"
            )

            return

        context.user_data["withdraw_amount"] = amount
        context.user_data["withdraw_step"] = "method"

        await update.message.reply_text(
            "📱 Payment method লিখুন:\n\n"
            "bKash অথবা Nagad"
        )

        return

    # =========================
    # WITHDRAW METHOD
    # =========================

    if context.user_data.get("withdraw_step") == "method":

        method = text.lower()

        if method not in ["bkash", "nagad"]:

            await update.message.reply_text(
                "❌ শুধু bKash অথবা Nagad লিখুন।"
            )

            return

        context.user_data["withdraw_method"] = (
            "bKash" if method == "bkash" else "Nagad"
        )

        context.user_data["withdraw_step"] = "number"

        await update.message.reply_text(
            "☎️ আপনার bKash/Nagad নম্বর লিখুন।"
        )

        return

    # =========================
    # WITHDRAW NUMBER
    # =========================

    if context.user_data.get("withdraw_step") == "number":

        amount = context.user_data["withdraw_amount"]
        method = context.user_data["withdraw_method"]
        number = text

        if amount > get_balance(user.id):

            context.user_data.clear()

            await update.message.reply_text(
                "❌ আপনার balance পরিবর্তিত হয়েছে। আবার চেষ্টা করুন।"
            )

            return

        con = db()
        cur = con.cursor()

        cur.execute("""
            UPDATE users
            SET balance=balance-?
            WHERE user_id=?
        """, (amount, user.id))

        cur.execute("""
            INSERT INTO withdrawals
            (user_id, amount, method, number)
            VALUES (?, ?, ?, ?)
        """, (
            user.id,
            amount,
            method,
            number
        ))

        withdrawal_id = cur.lastrowid

        con.commit()
        con.close()

        await update.message.reply_text(
            "✅ <b>Withdrawal Request Submitted!</b>\n\n"
            f"💰 Amount: ৳{amount:.2f}\n"
            f"📱 Method: {method}\n"
            f"☎️ Number: {number}\n\n"
            "⏳ Admin verification-এর জন্য অপেক্ষা করুন।",
            parse_mode="HTML",
            reply_markup=user_menu()
        )

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "💸 Withdrawal দেখুন",
                    callback_data="admin_withdrawals"
                )
            ]
        ])

        await context.bot.send_message(
            ADMIN_ID,
            f"💸 <b>New Withdrawal Request</b>\n\n"
            f"🆔 Request: #{withdrawal_id}\n"
            f"👤 User: <code>{user.id}</code>\n"
            f"💰 Amount: ৳{amount:.2f}\n"
            f"📱 Method: {method}\n"
            f"☎️ Number: <code>{number}</code>",
            parse_mode="HTML",
            reply_markup=keyboard
        )

        context.user_data.clear()

        return

    # =========================
    # PROOF
    # =========================

    if "proof_task" in context.user_data:

        task_id = context.user_data["proof_task"]

        con = db()
        cur = con.cursor()

        try:

            cur.execute("""
                INSERT INTO submissions
                (user_id, task_id, proof)
                VALUES (?, ?, ?)
            """, (
                user.id,
                task_id,
                text
            ))

            con.commit()

        except sqlite3.IntegrityError:

            con.close()
            context.user_data.clear()

            await update.message.reply_text(
                "⚠️ এই Task-এর proof আগে জমা দিয়েছেন।",
                reply_markup=user_menu()
            )

            return

        cur.execute("""
            SELECT title, reward
            FROM tasks
            WHERE id=?
        """, (task_id,))

        task = cur.fetchone()

        con.close()

        await update.message.reply_text(
            "✅ Proof জমা হয়েছে!\n\n"
            "📝 Admin verification-এর পর reward যোগ হবে।",
            reply_markup=user_menu()
        )

        await context.bot.send_message(
            ADMIN_ID,
            f"📝 <b>New Task Proof</b>\n\n"
            f"👤 User: <code>{user.id}</code>\n"
            f"📋 Task ID: {task_id}\n"
            f"💰 Reward: ৳{task[1] if task else 0}\n\n"
            f"📄 Proof:\n{text}",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "📝 Proof দেখুন",
                        callback_data="admin_proofs"
                    )
                ]
            ])
        )

        context.user_data.clear()

        return

    # =========================
    # ADMIN TASK CREATION
    # =========================

    if user.id == ADMIN_ID:

        step = context.user_data.get("admin_step")

        if step == "title":

            context.user_data["new_title"] = text
            context.user_data["admin_step"] = "description"

            await update.message.reply_text(
                "📝 Task-এর description লিখুন।"
            )

            return

        if step == "description":

            context.user_data["new_description"] = text
            context.user_data["admin_step"] = "reward"

            await update.message.reply_text(
                "💰 Task reward লিখুন। যেমন: 2"
            )

            return

        if step == "reward":

            try:

                reward = float(text)

            except ValueError:

                await update.message.reply_text(
                    "❌ সঠিক সংখ্যা লিখুন।"
                )

                return

            context.user_data["new_reward"] = reward
            context.user_data["admin_step"] = "link"

            await update.message.reply_text(
                "🔗 Task-এর link পাঠান।"
            )

            return

        if step == "link":

            title = context.user_data["new_title"]
            description = context.user_data["new_description"]
            reward = context.user_data["new_reward"]
            link = text

            con = db()
            cur = con.cursor()

            cur.execute("""
                INSERT INTO tasks
                (title, description, reward, link)
                VALUES (?, ?, ?, ?)
            """, (
                title,
                description,
                reward,
                link
            ))

            con.commit()
            con.close()

            context.user_data.clear()

            await update.message.reply_text(
                "✅ <b>নতুন Task তৈরি হয়েছে!</b>",
                parse_mode="HTML",
                reply_markup=admin_menu()
            )

            return

    await update.message.reply_text(
        "🏠 মেনু থেকে একটি অপশন নির্বাচন করুন।",
        reply_markup=user_menu()
    )


def main():

    if not BOT_TOKEN:

        raise RuntimeError(
            "BOT_TOKEN সেট করা হয়নি।"
        )

    if not ADMIN_ID:

        raise RuntimeError(
            "ADMIN_ID সেট করা হয়নি।"
        )

    setup_database()

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(
        CommandHandler("start", start)
    )

    app.add_handler(
        CallbackQueryHandler(button_handler)
    )

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            text_handler
        )
    )

    print("🤖 Bot is running...")

    app.run_polling()


if __name__ == "__main__":
    main()

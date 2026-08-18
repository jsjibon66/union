import os
import sqlite3
from html import escape

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# =========================================================
# CONFIG
# =========================================================

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

MIN_WITHDRAW = 100
MAX_WITHDRAW = 5000

REFERRAL_REWARD = 5.0

SUPPORT_USERNAME = "Hasanroy53"
UPDATE_CHANNEL = "https://t.me/MicroJobBD1"

DB_NAME = "bot.db"


# =========================================================
# DATABASE
# =========================================================

def db():
    con = sqlite3.connect(DB_NAME, timeout=30)
    con.execute("PRAGMA foreign_keys = ON")
    return con


def setup_database():
    con = db()
    cur = con.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            name TEXT,
            username TEXT,
            balance REAL DEFAULT 0,
            referred_by INTEGER,
            referral_reward_paid INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            reward REAL NOT NULL,
            link TEXT,
            max_users INTEGER DEFAULT 0,
            active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            task_id INTEGER NOT NULL,
            proof TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, task_id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS withdrawals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            method TEXT NOT NULL,
            number TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            kind TEXT NOT NULL,
            note TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ---------------------------------------------------------
    # OLD DATABASE MIGRATION
    # ---------------------------------------------------------

    user_cols = {
        x[1] for x in cur.execute(
            "PRAGMA table_info(users)"
        ).fetchall()
    }

    if "referred_by" not in user_cols:
        cur.execute(
            "ALTER TABLE users ADD COLUMN referred_by INTEGER"
        )

    if "referral_reward_paid" not in user_cols:
        cur.execute(
            "ALTER TABLE users ADD COLUMN referral_reward_paid INTEGER DEFAULT 0"
        )

    if "created_at" not in user_cols:
        cur.execute(
            "ALTER TABLE users ADD COLUMN created_at TIMESTAMP"
        )

    task_cols = {
        x[1] for x in cur.execute(
            "PRAGMA table_info(tasks)"
        ).fetchall()
    }

    if "max_users" not in task_cols:
        cur.execute(
            "ALTER TABLE tasks ADD COLUMN max_users INTEGER DEFAULT 0"
        )

    if "created_at" not in task_cols:
        cur.execute(
            "ALTER TABLE tasks ADD COLUMN created_at TIMESTAMP"
        )

    con.commit()
    con.close()


# =========================================================
# HELPERS
# =========================================================

def money(amount):
    return f"৳{float(amount):.2f}"


def safe(text):
    return escape(str(text or ""))


def add_user(user, referrer_id=None):

    con = db()
    cur = con.cursor()

    cur.execute("""
        INSERT OR IGNORE INTO users
        (user_id, name, username, balance, referred_by)
        VALUES (?, ?, ?, 0, ?)
    """, (
        user.id,
        user.first_name or "",
        user.username or "",
        referrer_id
    ))

    cur.execute("""
        UPDATE users
        SET name=?, username=?
        WHERE user_id=?
    """, (
        user.first_name or "",
        user.username or "",
        user.id
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

    return float(row[0]) if row else 0


def add_balance(user_id, amount, kind, note):

    con = db()
    cur = con.cursor()

    cur.execute("""
        UPDATE users
        SET balance=balance+?
        WHERE user_id=?
    """, (amount, user_id))

    cur.execute("""
        INSERT INTO transactions
        (user_id, amount, kind, note)
        VALUES (?, ?, ?, ?)
    """, (
        user_id,
        amount,
        kind,
        note
    ))

    con.commit()
    con.close()


def remove_balance(user_id, amount):

    con = db()
    cur = con.cursor()

    cur.execute("""
        UPDATE users
        SET balance=balance-?
        WHERE user_id=? AND balance>=?
    """, (
        amount,
        user_id,
        amount
    ))

    success = cur.rowcount == 1

    con.commit()
    con.close()

    return success


def task_completed_count(task_id):

    con = db()
    cur = con.cursor()

    cur.execute("""
        SELECT COUNT(*)
        FROM submissions
        WHERE task_id=?
        AND status IN ('pending','approved')
    """, (task_id,))

    count = cur.fetchone()[0]

    con.close()

    return count


# =========================================================
# USER MENU
# =========================================================

def user_menu():

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "📋 কাজ করুন",
                callback_data="tasks"
            ),
            InlineKeyboardButton(
                "💰 ব্যালেন্স",
                callback_data="balance"
            )
        ],
        [
            InlineKeyboardButton(
                "💸 টাকা তুলুন",
                callback_data="withdraw"
            ),
            InlineKeyboardButton(
                "📜 ইতিহাস",
                callback_data="history"
            )
        ],
        [
            InlineKeyboardButton(
                "👥 রেফার করুন",
                callback_data="referral"
            ),
            InlineKeyboardButton(
                "🎧 সাপোর্ট",
                callback_data="support"
            )
        ],
        [
            InlineKeyboardButton(
                "📢 Bot Update / Challenge",
                url=UPDATE_CHANNEL
            )
        ],
        [
            InlineKeyboardButton(
                "🏠 Start / Home",
                callback_data="home"
            )
        ]
    ])


# =========================================================
# ADMIN MENU
# =========================================================

def admin_menu():

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "➕ নতুন Task",
                callback_data="admin_new_task"
            ),
            InlineKeyboardButton(
                "📋 Tasks",
                callback_data="admin_tasks"
            )
        ],
        [
            InlineKeyboardButton(
                "📝 Proof",
                callback_data="admin_proofs"
            ),
            InlineKeyboardButton(
                "💸 Withdrawals",
                callback_data="admin_withdrawals"
            )
        ],
        [
            InlineKeyboardButton(
                "👥 Users",
                callback_data="admin_users"
            ),
            InlineKeyboardButton(
                "📊 Statistics",
                callback_data="admin_stats"
            )
        ],
        [
            InlineKeyboardButton(
                "📢 Broadcast",
                callback_data="admin_broadcast"
            )
        ],
        [
            InlineKeyboardButton(
                "🏠 Admin Home",
                callback_data="admin_home"
            )
        ]
    ])


# =========================================================
# START
# =========================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user

    referrer_id = None

    if context.args:
        arg = context.args[0]

        if arg.startswith("ref_"):
            try:
                referrer_id = int(arg.replace("ref_", ""))
            except:
                referrer_id = None

    if referrer_id == user.id:
        referrer_id = None

    add_user(user, referrer_id)

    context.user_data.clear()

    if user.id == ADMIN_ID:

        await update.message.reply_text(
            "👑 <b>ADMIN PANEL</b>\n\n"
            "স্বাগতম Admin!\n\n"
            "নিচের মেনু থেকে কাজ করুন।",
            parse_mode="HTML",
            reply_markup=admin_menu()
        )

    else:

        await update.message.reply_text(
            "🎉 <b>স্বাগতম Micro Job BD!</b>\n\n"
            "📋 কাজ করুন\n"
            "💰 Reward উপার্জন করুন\n"
            "👥 বন্ধু রেফার করে প্রতি সফল Referral-এ "
            f"{money(REFERRAL_REWARD)} পান\n"
            f"💸 Minimum withdrawal: {money(MIN_WITHDRAW)}\n\n"
            "নিচের মেনু থেকে শুরু করুন 👇",
            parse_mode="HTML",
            reply_markup=user_menu()
        )


# =========================================================
# BUTTON HANDLER
# =========================================================

async def button_handler(update, context):

    query = update.callback_query

    await query.answer()

    user_id = query.from_user.id
    data = query.data

    # =====================================================
    # HOME
    # =====================================================

    if data == "home":

        if user_id == ADMIN_ID:

            await query.message.reply_text(
                "👑 <b>ADMIN PANEL</b>",
                parse_mode="HTML",
                reply_markup=admin_menu()
            )

        else:

            await query.message.reply_text(
                "🏠 <b>Micro Job BD</b>\n\n"
                "আপনার মেনু থেকে একটি অপশন নির্বাচন করুন 👇",
                parse_mode="HTML",
                reply_markup=user_menu()
            )

        return

    # =====================================================
    # ADMIN HOME
    # =====================================================

    if data == "admin_home":

        if user_id != ADMIN_ID:
            return

        await query.message.reply_text(
            "👑 <b>ADMIN PANEL</b>",
            parse_mode="HTML",
            reply_markup=admin_menu()
        )

        return

    # =====================================================
    # BALANCE
    # =====================================================

    if data == "balance":

        balance = get_balance(user_id)

        await query.message.reply_text(
            f"💰 <b>আপনার Balance</b>\n\n"
            f"💵 {money(balance)}",
            parse_mode="HTML",
            reply_markup=user_menu()
        )

        return

    # =====================================================
    # TASKS
    # =====================================================

    if data == "tasks":

        con = db()
        cur = con.cursor()

        cur.execute("""
            SELECT id, title, description, reward, link, max_users
            FROM tasks
            WHERE active=1
            ORDER BY id DESC
        """)

        tasks = cur.fetchall()

        con.close()

        shown = 0

        for task in tasks:

            task_id, title, description, reward, link, max_users = task

            done_count = task_completed_count(task_id)

            if max_users > 0 and done_count >= max_users:

                con = db()
                cur = con.cursor()

                cur.execute("""
                    UPDATE tasks
                    SET active=0
                    WHERE id=?
                """, (task_id,))

                con.commit()
                con.close()

                continue

            con = db()
            cur = con.cursor()

            cur.execute("""
                SELECT status
                FROM submissions
                WHERE user_id=? AND task_id=?
            """, (
                user_id,
                task_id
            ))

            already = cur.fetchone()

            con.close()

            if already:
                continue

            shown += 1

            if max_users == 0:
                limit_text = "♾️ Unlimited"
            else:
                remaining = max_users - done_count
                limit_text = (
                    f"👥 Limit: {max_users}\n"
                    f"📌 বাকি: {remaining}"
                )

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
                f"📋 <b>{safe(title)}</b>\n\n"
                f"📝 {safe(description)}\n\n"
                f"💰 Reward: {money(reward)}\n"
                f"{limit_text}",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

        if shown == 0:

            await query.message.reply_text(
                "📭 বর্তমানে কোনো নতুন Task নেই।",
                reply_markup=user_menu()
            )

        return

    # =====================================================
    # SUBMIT PROOF
    # =====================================================

    if data.startswith("submit_"):

        task_id = int(data.split("_")[1])

        con = db()
        cur = con.cursor()

        cur.execute("""
            SELECT title, max_users
            FROM tasks
            WHERE id=? AND active=1
        """, (task_id,))

        task = cur.fetchone()

        con.close()

        if not task:

            await query.message.reply_text(
                "❌ এই Task আর available নেই."
            )

            return

        max_users = task[1]

        if max_users > 0:

            count = task_completed_count(task_id)

            if count >= max_users:

                await query.message.reply_text(
                    "❌ এই Task-এর limit পূর্ণ হয়ে গেছে।"
                )

                return

        context.user_data["proof_task"] = task_id

        await query.message.reply_text(
            "📸 <b>Proof জমা দিন</b>\n\n"
            "Task শেষ করে Screenshot/Photo পাঠান।\n\n"
            "📌 ছবির সাথে চাইলে Caption-ও দিতে পারেন।",
            parse_mode="HTML"
        )

        return

    # =====================================================
    # WITHDRAW
    # =====================================================

    if data == "withdraw":

        balance = get_balance(user_id)

        if balance < MIN_WITHDRAW:

            await query.message.reply_text(
                f"❌ Balance যথেষ্ট নয়।\n\n"
                f"💰 আপনার Balance: {money(balance)}\n"
                f"📌 Minimum: {money(MIN_WITHDRAW)}",
                reply_markup=user_menu()
            )

            return

        context.user_data["withdraw_step"] = "amount"

        await query.message.reply_text(
            "💸 <b>Withdrawal</b>\n\n"
            f"Minimum: {money(MIN_WITHDRAW)}\n"
            f"Maximum: {money(MAX_WITHDRAW)}\n\n"
            "কত টাকা তুলতে চান লিখুন।",
            parse_mode="HTML"
        )

        return

    # =====================================================
    # HISTORY
    # =====================================================

    if data == "history":

        con = db()
        cur = con.cursor()

        cur.execute("""
            SELECT amount, kind, note
            FROM transactions
            WHERE user_id=?
            ORDER BY id DESC
            LIMIT 20
        """, (user_id,))

        rows = cur.fetchall()

        con.close()

        if not rows:

            text = "📜 এখনো কোনো Transaction নেই।"

        else:

            text = "📜 <b>Transaction History</b>\n\n"

            for amount, kind, note in rows:

                text += (
                    f"💰 {money(amount)}\n"
                    f"📌 {safe(kind)}\n"
                    f"📝 {safe(note)}\n\n"
                )

        await query.message.reply_text(
            text,
            parse_mode="HTML",
            reply_markup=user_menu()
        )

        return

    # =====================================================
    # REFERRAL
    # =====================================================

    if data == "referral":

        bot = await context.bot.get_me()

        link = (
            f"https://t.me/{bot.username}"
            f"?start=ref_{user_id}"
        )

        await query.message.reply_text(
            "👥 <b>Referral Program</b>\n\n"
            f"🎁 প্রতি সফল Referral-এ "
            f"<b>{money(REFERRAL_REWARD)}</b> পাবেন।\n\n"
            "বন্ধুকে আপনার Referral Link দিয়ে Bot-এ "
            "Join করান।\n\n"
            "🔗 <b>Your Referral Link:</b>\n"
            f"<code>{link}</code>",
            parse_mode="HTML",
            reply_markup=user_menu()
        )

        return

    # =====================================================
    # SUPPORT
    # =====================================================

    if data == "support":

        await query.message.reply_text(
            "🎧 <b>Support</b>\n\n"
            "কোনো সমস্যা হলে আমাদের Admin-এর সাথে যোগাযোগ করুন।\n\n"
            "👤 Admin: @Hasanroy53",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "👤 Admin-কে Message করুন",
                        url=f"https://t.me/{SUPPORT_USERNAME}"
                    )
                ],
                [
                    InlineKeyboardButton(
                        "🏠 Home",
                        callback_data="home"
                    )
                ]
            ])
        )

        return

    # =====================================================
    # ADMIN CHECK
    # =====================================================

    if data.startswith("admin_") or \
       data.startswith("approve_") or \
       data.startswith("reject_"):

        if user_id != ADMIN_ID:
            return

    # =====================================================
    # ADMIN STATISTICS
    # =====================================================

    if data == "admin_stats":

        con = db()
        cur = con.cursor()

        cur.execute("SELECT COUNT(*) FROM users")
        users = cur.fetchone()[0]

        cur.execute("""
            SELECT COUNT(*)
            FROM users
            WHERE referred_by IS NOT NULL
        """)
        referred = cur.fetchone()[0]

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
            "📊 <b>Statistics</b>\n\n"
            f"👥 Users: {users}\n"
            f"👥 Referred Users: {referred}\n"
            f"📋 Tasks: {tasks}\n"
            f"📝 Pending Proof: {proofs}\n"
            f"💸 Pending Withdrawal: {withdrawals}",
            parse_mode="HTML",
            reply_markup=admin_menu()
        )

        return

    # =====================================================
    # ADMIN USERS
    # =====================================================

    if data == "admin_users":

        con = db()
        cur = con.cursor()

        cur.execute("""
            SELECT user_id, name, username, balance
            FROM users
            ORDER BY user_id DESC
            LIMIT 30
        """)

        rows = cur.fetchall()

        con.close()

        if not rows:

            await query.message.reply_text(
                "👥 কোনো User নেই।",
                reply_markup=admin_menu()
            )

            return

        text = "👥 <b>Users</b>\n\n"

        for uid, name, username, balance in rows:

            uname = f"@{username}" if username else "No Username"

            text += (
                f"🆔 <code>{uid}</code>\n"
                f"👤 {safe(name)} ({safe(uname)})\n"
                f"💰 {money(balance)}\n\n"
            )

        await query.message.reply_text(
            text,
            parse_mode="HTML",
            reply_markup=admin_menu()
        )

        return

    # =====================================================
    # ADMIN TASKS
    # =====================================================

    if data == "admin_tasks":

        con = db()
        cur = con.cursor()

        cur.execute("""
            SELECT id, title, reward, max_users, active
            FROM tasks
            ORDER BY id DESC
        """)

        rows = cur.fetchall()

        con.close()

        if not rows:

            await query.message.reply_text(
                "📭 কোনো Task নেই।",
                reply_markup=admin_menu()
            )

            return

        text = "📋 <b>All Tasks</b>\n\n"

        for tid, title, reward, limit, active in rows:

            used = task_completed_count(tid)

            status = "🟢 Active" if active else "🔴 Off"

            limit_text = (
                "Unlimited"
                if limit == 0
                else f"{used}/{limit}"
            )

            text += (
                f"#{tid} — {safe(title)}\n"
                f"💰 {money(reward)}\n"
                f"👥 Limit: {limit_text}\n"
                f"{status}\n\n"
            )

        await query.message.reply_text(
            text,
            parse_mode="HTML",
            reply_markup=admin_menu()
        )

        return

    # =====================================================
    # NEW TASK
    # =====================================================

    if data == "admin_new_task":

        context.user_data.clear()

        context.user_data["admin_step"] = "title"

        await query.message.reply_text(
            "➕ <b>New Task</b>\n\n"
            "১️⃣ Task-এর নাম লিখুন।",
            parse_mode="HTML"
        )

        return

    # =====================================================
    # ADMIN PROOFS
    # =====================================================

    if data == "admin_proofs":

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
                "📭 কোনো Pending Proof নেই।",
                reply_markup=admin_menu()
            )

            return

        for sid, uid, tid, proof, title, reward in rows:

            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "✅ Approve",
                        callback_data=f"approve_{sid}"
                    ),
                    InlineKeyboardButton(
                        "❌ Reject",
                        callback_data=f"reject_{sid}"
                    )
                ]
            ])

            if proof.startswith("PHOTO:"):

                file_id = proof.split("|CAPTION:")[0].replace(
                    "PHOTO:", ""
                )

                caption = proof.split("|CAPTION:", 1)[1]

                await context.bot.send_photo(
                    chat_id=ADMIN_ID,
                    photo=file_id,
                    caption=(
                        f"📝 Proof #{sid}\n\n"
                        f"👤 User: {uid}\n"
                        f"📋 {title}\n"
                        f"💰 Reward: {money(reward)}\n\n"
                        f"📄 Caption:\n{caption}"
                    ),
                    reply_markup=keyboard
                )

            else:

                await query.message.reply_text(
                    f"📝 <b>Proof #{sid}</b>\n\n"
                    f"👤 User: <code>{uid}</code>\n"
                    f"📋 Task: {safe(title)}\n"
                    f"💰 Reward: {money(reward)}\n\n"
                    f"📄 {safe(proof)}",
                    parse_mode="HTML",
                    reply_markup=keyboard
                )

        return

    # =====================================================
    # APPROVE PROOF
    # =====================================================

    if data.startswith("approve_"):

        sid = int(data.split("_")[1])

        con = db()
        cur = con.cursor()

        cur.execute("""
            SELECT s.user_id, s.task_id, t.reward
            FROM submissions s
            JOIN tasks t ON t.id=s.task_id
            WHERE s.id=? AND s.status='pending'
        """, (sid,))

        row = cur.fetchone()

        if not row:

            con.close()

            await query.message.reply_text(
                "⚠️ এই Proof আর Pending নেই।"
            )

            return

        target_user, task_id, reward = row

        cur.execute("""
            UPDATE submissions
            SET status='approved'
            WHERE id=?
        """, (sid,))

        cur.execute("""
            UPDATE users
            SET balance=balance+?
            WHERE user_id=?
        """, (
            reward,
            target_user
        ))

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

        new_balance = get_balance(target_user)

        await context.bot.send_message(
            target_user,
            "🎉 <b>Task Approved!</b>\n\n"
            f"💰 Reward: {money(reward)}\n"
            f"💵 New Balance: {money(new_balance)}",
            parse_mode="HTML"
        )

        await query.message.reply_text(
            "✅ Proof Approved এবং Reward যোগ হয়েছে।"
        )

        return

    # =====================================================
    # REJECT PROOF
    # =====================================================

    if data.startswith("reject_"):

        sid = int(data.split("_")[1])

        con = db()
        cur = con.cursor()

        cur.execute("""
            SELECT user_id
            FROM submissions
            WHERE id=? AND status='pending'
        """, (sid,))

        row = cur.fetchone()

        if row:

            target_user = row[0]

            cur.execute("""
                UPDATE submissions
                SET status='rejected'
                WHERE id=?
            """, (sid,))

            con.commit()

            await context.bot.send_message(
                target_user,
                "❌ আপনার Task Proof Reject করা হয়েছে।\n\n"
                "আবার সঠিক Proof জমা দিতে পারেন।"
            )

        con.close()

        await query.message.reply_text(
            "❌ Proof rejected."
        )

        return

    # =====================================================
    # ADMIN WITHDRAWALS
    # =====================================================

    if data == "admin_withdrawals":

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
                "📭 কোনো Pending Withdrawal নেই।",
                reply_markup=admin_menu()
            )

            return

        for wid, uid, amount, method, number in rows:

            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "✅ Approve",
                        callback_data=f"approve_w_{wid}"
                    ),
                    InlineKeyboardButton(
                        "❌ Reject",
                        callback_data=f"reject_w_{wid}"
                    )
                ]
            ])

            await query.message.reply_text(
                f"💸 <b>Withdrawal #{wid}</b>\n\n"
                f"👤 User: <code>{uid}</code>\n"
                f"💰 Amount: {money(amount)}\n"
                f"📱 Method: {safe(method)}\n"
                f"☎️ Number: <code>{safe(number)}</code>",
                parse_mode="HTML",
                reply_markup=keyboard
            )

        return

    # =====================================================
    # APPROVE WITHDRAWAL
    # =====================================================

    if data.startswith("approve_w_"):

        wid = int(data.split("_")[2])

        con = db()
        cur = con.cursor()

        cur.execute("""
            SELECT user_id, amount
            FROM withdrawals
            WHERE id=? AND status='pending'
        """, (wid,))

        row = cur.fetchone()

        if not row:

            con.close()

            await query.message.reply_text(
                "⚠️ Withdrawal আর Pending নেই।"
            )

            return

        uid, amount = row

        cur.execute("""
            UPDATE withdrawals
            SET status='approved'
            WHERE id=?
        """, (wid,))

        con.commit()
        con.close()

        await context.bot.send_message(
            uid,
            f"✅ আপনার {money(amount)} Withdrawal Approved হয়েছে।"
        )

        await query.message.reply_text(
            "✅ Withdrawal Approved."
        )

        return

    # =====================================================
    # REJECT WITHDRAWAL
    # =====================================================

    if data.startswith("reject_w_"):

        wid = int(data.split("_")[2])

        con = db()
        cur = con.cursor()

        cur.execute("""
            SELECT user_id, amount
            FROM withdrawals
            WHERE id=? AND status='pending'
        """, (wid,))

        row = cur.fetchone()

        if not row:

            con.close()

            await query.message.reply_text(
                "⚠️ Withdrawal আর Pending নেই।"
            )

            return

        uid, amount = row

        cur.execute("""
            UPDATE withdrawals
            SET status='rejected'
            WHERE id=?
        """, (wid,))

        cur.execute("""
            UPDATE users
            SET balance=balance+?
            WHERE user_id=?
        """, (
            amount,
            uid
        ))

        cur.execute("""
            INSERT INTO transactions
            (user_id, amount, kind, note)
            VALUES (?, ?, ?, ?)
        """, (
            uid,
            amount,
            "Refund",
            f"Withdrawal #{wid} rejected"
        ))

        con.commit()
        con.close()

        await context.bot.send_message(
            uid,
            f"❌ Withdrawal Reject হয়েছে।\n\n"
            f"💰 {money(amount)} আপনার Balance-এ ফেরত দেওয়া হয়েছে।"
        )

        await query.message.reply_text(
            "❌ Withdrawal rejected এবং balance ফেরত দেওয়া হয়েছে।"
        )

        return

    # =====================================================
    # BROADCAST START
    # =====================================================

    if data == "admin_broadcast":

        context.user_data.clear()

        context.user_data["admin_step"] = "broadcast"

        await query.message.reply_text(
            "📢 <b>Broadcast</b>\n\n"
            "যে Message সব User-কে পাঠাতে চান সেটি লিখুন।",
            parse_mode="HTML"
        )

        return


# =========================================================
# PHOTO PROOF
# =========================================================

async def photo_handler(update, context):

    user = update.effective_user

    add_user(user)

    if "proof_task" not in context.user_data:

        await update.message.reply_text(
            "📸 আগে একটি Task নির্বাচন করুন।",
            reply_markup=user_menu()
        )

        return

    task_id = context.user_data["proof_task"]

    con = db()
    cur = con.cursor()

    cur.execute("""
        SELECT title, reward, max_users, active
        FROM tasks
        WHERE id=?
    """, (task_id,))

    task = cur.fetchone()

    if not task:

        con.close()
        context.user_data.clear()

        await update.message.reply_text(
            "❌ Task পাওয়া যায়নি।"
        )

        return

    title, reward, max_users, active = task

    if not active:

        con.close()
        context.user_data.clear()

        await update.message.reply_text(
            "❌ এই Task এখন বন্ধ।"
        )

        return

    if max_users > 0:

        count = task_completed_count(task_id)

        if count >= max_users:

            con.close()
            context.user_data.clear()

            await update.message.reply_text(
                "❌ এই Task-এর Limit পূর্ণ হয়ে গেছে।"
            )

            return

    cur.execute("""
        SELECT id
        FROM submissions
        WHERE user_id=? AND task_id=?
    """, (
        user.id,
        task_id
    ))

    if cur.fetchone():

        con.close()
        context.user_data.clear()

        await update.message.reply_text(
            "⚠️ এই Task-এর Proof আগে জমা দিয়েছেন।"
        )

        return

    photo = update.message.photo[-1]

    file_id = photo.file_id

    caption = update.message.caption or ""

    proof = (
        f"PHOTO:{file_id}|CAPTION:{caption}"
    )

    cur.execute("""
        INSERT INTO submissions
        (user_id, task_id, proof)
        VALUES (?, ?, ?)
    """, (
        user.id,
        task_id,
        proof
    ))

    submission_id = cur.lastrowid

    con.commit()
    con.close()

    context.user_data.clear()

    await update.message.reply_text(
        "✅ <b>Screenshot জমা হয়েছে!</b>\n\n"
        "⏳ Admin আপনার Proof দেখে Approve করবেন।",
        parse_mode="HTML",
        reply_markup=user_menu()
    )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "📝 Proof দেখুন",
                callback_data="admin_proofs"
            )
        ]
    ])

    await context.bot.send_photo(
        chat_id=ADMIN_ID,
        photo=file_id,
        caption=(
            f"📝 <b>NEW PHOTO PROOF</b>\n\n"
            f"🆔 Proof #{submission_id}\n"
            f"👤 User: <code>{user.id}</code>\n"
            f"📋 Task: {safe(title)}\n"
            f"💰 Reward: {money(reward)}\n\n"
            f"📄 Caption:\n{safe(caption) if caption else 'None'}"
        ),
        parse_mode="HTML",
        reply_markup=keyboard
    )


# =========================================================
# TEXT HANDLER
# =========================================================

async def text_handler(update, context):

    user = update.effective_user

    text = update.message.text.strip()

    add_user(user)

    # =====================================================
    # WITHDRAW AMOUNT
    # =====================================================

    if context.user_data.get("withdraw_step") == "amount":

        try:
            amount = float(text)
        except:
            await update.message.reply_text(
                "❌ সঠিক Amount লিখুন। যেমন: 100"
            )
            return

        if amount < MIN_WITHDRAW:
            await update.message.reply_text(
                f"❌ Minimum Withdrawal {money(MIN_WITHDRAW)}"
            )
            return

        if amount > MAX_WITHDRAW:
            await update.message.reply_text(
                f"❌ Maximum Withdrawal {money(MAX_WITHDRAW)}"
            )
            return

        if amount > get_balance(user.id):
            await update.message.reply_text(
                "❌ আপনার Balance যথেষ্ট নয়।"
            )
            return

        context.user_data["withdraw_amount"] = amount
        context.user_data["withdraw_step"] = "method"

        await update.message.reply_text(
            "📱 Payment Method লিখুন:\n\n"
            "bKash অথবা Nagad"
        )

        return

    # =====================================================
    # WITHDRAW METHOD
    # =====================================================

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
            "☎️ আপনার bKash/Nagad Number লিখুন।"
        )

        return

    # =====================================================
    # WITHDRAW NUMBER
    # =====================================================

    if context.user_data.get("withdraw_step") == "number":

        amount = context.user_data["withdraw_amount"]

        method = context.user_data["withdraw_method"]

        number = text

        if amount > get_balance(user.id):

            context.user_data.clear()

            await update.message.reply_text(
                "❌ Balance যথেষ্ট নয়। আবার চেষ্টা করুন।"
            )

            return

        if not remove_balance(user.id, amount):

            context.user_data.clear()

            await update.message.reply_text(
                "❌ Withdrawal process করা যায়নি।"
            )

            return

        con = db()
        cur = con.cursor()

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

        wid = cur.lastrowid

        con.commit()
        con.close()

        context.user_data.clear()

        await update.message.reply_text(
            "✅ <b>Withdrawal Request Submitted!</b>\n\n"
            f"💰 Amount: {money(amount)}\n"
            f"📱 Method: {method}\n"
            f"☎️ Number: {safe(number)}\n\n"
            "⏳ Admin verification-এর জন্য অপেক্ষা করুন।",
            parse_mode="HTML",
            reply_markup=user_menu()
        )

        await context.bot.send_message(
            ADMIN_ID,
            "💸 <b>NEW WITHDRAWAL</b>\n\n"
            f"🆔 Request: #{wid}\n"
            f"👤 User: <code>{user.id}</code>\n"
            f"💰 Amount: {money(amount)}\n"
            f"📱 Method: {method}\n"
            f"☎️ Number: <code>{safe(number)}</code>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "💸 Withdrawal দেখুন",
                        callback_data="admin_withdrawals"
                    )
                ]
            ])
        )

        return

    # =====================================================
    # TEXT PROOF
    # =====================================================

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

            sid = cur.lastrowid

            con.commit()

        except sqlite3.IntegrityError:

            con.close()
            context.user_data.clear()

            await update.message.reply_text(
                "⚠️ এই Task-এর Proof আগে জমা দিয়েছেন।"
            )

            return

        cur.execute("""
            SELECT title, reward
            FROM tasks
            WHERE id=?
        """, (task_id,))

        task = cur.fetchone()

        con.close()

        context.user_data.clear()

        await update.message.reply_text(
            "✅ Proof জমা হয়েছে!\n\n"
            "⏳ Admin verification-এর পর Reward যোগ হবে।",
            reply_markup=user_menu()
        )

        await context.bot.send_message(
            ADMIN_ID,
            "📝 <b>NEW TEXT PROOF</b>\n\n"
            f"🆔 Proof #{sid}\n"
            f"👤 User: <code>{user.id}</code>\n"
            f"📋 Task: {safe(task[0] if task else 'Unknown')}\n"
            f"💰 Reward: {money(task[1] if task else 0)}\n\n"
            f"📄 Proof:\n{safe(text)}",
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

        return

    # =====================================================
    # ADMIN
    # =====================================================

    if user.id == ADMIN_ID:

        step = context.user_data.get("admin_step")

        # -------------------------------------------------
        # NEW TASK: TITLE
        # -------------------------------------------------

        if step == "title":

            context.user_data["new_title"] = text

            context.user_data["admin_step"] = "description"

            await update.message.reply_text(
                "📝 Task Description লিখুন।"
            )

            return

        # -------------------------------------------------
        # DESCRIPTION
        # -------------------------------------------------

        if step == "description":

            context.user_data["new_description"] = text

            context.user_data["admin_step"] = "reward"

            await update.message.reply_text(
                "💰 Task Reward লিখুন। যেমন: 5"
            )

            return

        # -------------------------------------------------
        # REWARD
        # -------------------------------------------------

        if step == "reward":

            try:
                reward = float(text)
            except:

                await update.message.reply_text(
                    "❌ সঠিক সংখ্যা লিখুন।"
                )

                return

            context.user_data["new_reward"] = reward

            context.user_data["admin_step"] = "link"

            await update.message.reply_text(
                "🔗 Task-এর Link পাঠান।"
            )

            return

        # -------------------------------------------------
        # LINK
        # -------------------------------------------------

        if step == "link":

            context.user_data["new_link"] = text

            context.user_data["admin_step"] = "limit"

            await update.message.reply_text(
                "👥 <b>Task Limit</b>\n\n"
                "এই Task সর্বোচ্চ কতজন User করতে পারবে?\n\n"
                "উদাহরণ:\n"
                "100\n"
                "200\n"
                "500\n\n"
                "♾️ Unlimited চাইলে <b>0</b> লিখুন।",
                parse_mode="HTML"
            )

            return

        # -------------------------------------------------
        # LIMIT
        # -------------------------------------------------

        if step == "limit":

            try:
                limit = int(text)
            except:

                await update.message.reply_text(
                    "❌ শুধু সংখ্যা লিখুন। যেমন: 100 অথবা 0"
                )

                return

            if limit < 0:

                await update.message.reply_text(
                    "❌ Limit 0 বা তার বেশি হতে হবে।"
                )

                return

            title = context.user_data["new_title"]

            description = context.user_data["new_description"]

            reward = context.user_data["new_reward"]

            link = context.user_data["new_link"]

            con = db()
            cur = con.cursor()

            cur.execute("""
                INSERT INTO tasks
                (title, description, reward, link, max_users)
                VALUES (?, ?, ?, ?, ?)
            """, (
                title,
                description,
                reward,
                link,
                limit
            ))

            task_id = cur.lastrowid

            con.commit()
            con.close()

            context.user_data.clear()

            limit_text = (
                "Unlimited"
                if limit == 0
                else str(limit)
            )

            await update.message.reply_text(
                "✅ <b>Task Created Successfully!</b>\n\n"
                f"🆔 Task ID: {task_id}\n"
                f"📋 {safe(title)}\n"
                f"💰 Reward: {money(reward)}\n"
                f"👥 Limit: {limit_text}",
                parse_mode="HTML",
                reply_markup=admin_menu()
            )

            return

        # -------------------------------------------------
        # BROADCAST
        # -------------------------------------------------

        if step == "broadcast":

            context.user_data.clear()

            con = db()
            cur = con.cursor()

            cur.execute(
                "SELECT user_id FROM users"
            )

            users = cur.fetchall()

            con.close()

            sent = 0
            failed = 0

            for (uid,) in users:

                try:

                    await context.bot.send_message(
                        uid,
                        text
                    )

                    sent += 1

                except:

                    failed += 1

            await update.message.reply_text(
                "📢 <b>Broadcast Complete</b>\n\n"
                f"✅ Sent: {sent}\n"
                f"❌ Failed: {failed}",
                parse_mode="HTML",
                reply_markup=admin_menu()
            )

            return

    # =====================================================
    # DEFAULT
    # =====================================================

    await update.message.reply_text(
        "🏠 মেনু থেকে একটি অপশন নির্বাচন করুন।",
        reply_markup=(
            admin_menu()
            if user.id == ADMIN_ID
            else user_menu()
        )
    )


# =========================================================
# MAIN
# =========================================================

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

    app = (
        Application
        .builder()
        .token(BOT_TOKEN)
        .build()
    )

    # /start
    app.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    # All buttons
    app.add_handler(
        CallbackQueryHandler(
            button_handler
        )
    )

    # Photo / Screenshot proof
    app.add_handler(
        MessageHandler(
            filters.PHOTO,
            photo_handler
        )
    )

    # Text messages
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            text_handler
        )
    )

    print("🤖 Micro Job BD Bot is running...")

    app.run_polling()


if __name__ == "__main__":
    main()

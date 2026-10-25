import os
import sqlite3
import logging
from datetime import datetime

from dotenv import load_dotenv
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

# ==============================
# Altofan Social Bot
# ==============================

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 8504714019
DB_FILE = "data/bot.db"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


# ==============================
# Database
# ==============================

os.makedirs("data", exist_ok=True)


def db():
    return sqlite3.connect(DB_FILE)


def init_db():
    with db() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                name TEXT,
                username TEXT,
                joined TEXT
            )
        """)

        con.execute("""
            CREATE TABLE IF NOT EXISTS services (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                active INTEGER DEFAULT 1
            )
        """)

        con.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                service TEXT,
                details TEXT,
                status TEXT DEFAULT 'جديد',
                created TEXT
            )
        """)

        con.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)

        con.execute("""
            CREATE TABLE IF NOT EXISTS creator_accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                platform TEXT NOT NULL,
                profile_url TEXT NOT NULL,
                niche TEXT NOT NULL,
                collaboration TEXT NOT NULL,
                created TEXT NOT NULL,
                UNIQUE(user_id, platform, profile_url)
            )
        """)

        order_columns = {
            row[1] for row in con.execute("PRAGMA table_info(orders)")
        }
        if "customer_name" not in order_columns:
            con.execute("ALTER TABLE orders ADD COLUMN customer_name TEXT DEFAULT ''")
        if "phone" not in order_columns:
            con.execute("ALTER TABLE orders ADD COLUMN phone TEXT DEFAULT ''")

        con.execute("""
            CREATE TABLE IF NOT EXISTS support_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                message TEXT NOT NULL,
                status TEXT DEFAULT 'جديد',
                created TEXT NOT NULL
            )
        """)

        defaults = {
            "bot_name": "Altofan Social",
            "welcome": "أهلاً بيك في Altofan Social 🚀",
            "support": "@AltofanSocial",
            "maintenance": "0",
        }

        for key, value in defaults.items():
            con.execute(
                "INSERT OR IGNORE INTO settings VALUES (?, ?)",
                (key, value),
            )

        count = con.execute(
            "SELECT COUNT(*) FROM services"
        ).fetchone()[0]

        if count == 0:
            services = [
                (
                    "إدارة صفحات السوشيال ميديا",
                    "تنظيم المحتوى وتحسين حضور العلامة التجارية",
                    1,
                ),
                (
                    "تصميم منشورات السوشيال ميديا",
                    "تصميم منشورات إعلانية واحترافية",
                    1,
                ),
                (
                    "كتابة المحتوى",
                    "أفكار ومنشورات تسويقية مناسبة لجمهورك",
                    1,
                ),
                (
                    "إعداد خطة تسويقية",
                    "خطة محتوى تساعد على تطوير حسابك",
                    1,
                ),
            ]

            con.executemany(
                """
                INSERT INTO services (name, description, active)
                VALUES (?, ?, ?)
                """,
                services,
            )


def get_setting(key, default=""):
    with db() as con:
        row = con.execute(
            "SELECT value FROM settings WHERE key = ?",
            (key,),
        ).fetchone()

    return row[0] if row else default


def set_setting(key, value):
    with db() as con:
        con.execute(
            """
            INSERT INTO settings (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )


def is_admin(user_id):
    return user_id == ADMIN_ID


def main_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "📱 الخدمات",
                callback_data="services",
            ),
            InlineKeyboardButton(
                "💰 الباقات والأسعار",
                callback_data="packages",
            ),
        ],
        [
            InlineKeyboardButton(
                "🛒 اطلب خدمة",
                callback_data="new_order",
            ),
            InlineKeyboardButton(
                "📋 طلباتي",
                callback_data="my_orders",
            ),
        ],
        [
            InlineKeyboardButton(
                "💡 نصائح التسويق",
                callback_data="tips",
            ),
            InlineKeyboardButton(
                "🆘 الدعم الفني",
                callback_data="support",
            ),
        ],
        [
            InlineKeyboardButton(
                "📈 اكتشف الحسابات",
                callback_data="discover_accounts",
            ),
        ],
        [
            InlineKeyboardButton(
                "ℹ️ عن البوت",
                callback_data="about",
            ),
        ],
    ])


def admin_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "📊 الإحصائيات",
                callback_data="admin_stats",
            ),
            InlineKeyboardButton(
                "📦 إدارة الطلبات",
                callback_data="admin_orders",
            ),
        ],
        [
            InlineKeyboardButton(
                "🛠 إدارة الخدمات",
                callback_data="admin_services",
            ),
            InlineKeyboardButton(
                "➕ إضافة خدمة",
                callback_data="admin_add_service",
            ),
        ],
        [
            InlineKeyboardButton(
                "⚙️ الإعدادات",
                callback_data="admin_settings",
            ),
            InlineKeyboardButton(
                "🔧 الصيانة",
                callback_data="admin_maintenance",
            ),
        ],
        [
            InlineKeyboardButton(
                "🏠 القائمة الرئيسية",
                callback_data="home",
            ),
        ],
    ])


# ==============================
# Start
# ==============================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    with db() as con:
        con.execute(
            """
            INSERT INTO users (user_id, name, username, joined)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                name = excluded.name,
                username = excluded.username
            """,
            (
                user.id,
                user.full_name,
                user.username or "",
                datetime.now().strftime("%Y-%m-%d %H:%M"),
            ),
        )

    context.user_data.pop("state", None)

    if (
        get_setting("maintenance", "0") == "1"
        and not is_admin(user.id)
    ):
        await update.message.reply_text(
            "🛠 البوت تحت الصيانة حاليًا.\n"
            "حاول مرة أخرى لاحقًا."
        )
        return

    name = get_setting("bot_name", "Altofan Social")
    welcome = get_setting(
        "welcome",
        "أهلاً بيك في Altofan Social 🚀",
    )

    await update.message.reply_text(
        f"✨ <b>{name}</b>\n\n"
        f"{welcome}\n\n"
        "اختار الخدمة اللي محتاجها من القائمة 👇",
        reply_markup=main_keyboard(),
        parse_mode="HTML",
    )


# ==============================
# Services and orders
# ==============================

def get_services(active_only=True):
    with db() as con:
        if active_only:
            return con.execute(
                """
                SELECT id, name, description, active
                FROM services WHERE active = 1
                ORDER BY id
                """
            ).fetchall()

        return con.execute(
            """
            SELECT id, name, description, active
            FROM services ORDER BY id
            """
        ).fetchall()


async def show_services(query):
    services = get_services()

    if not services:
        await query.edit_message_text(
            "لا توجد خدمات متاحة حاليًا.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    "🏠 الرئيسية",
                    callback_data="home",
                )
            ]]),
        )
        return

    text = "📱 <b>خدمات Altofan Social</b>\n\n"

    for service_id, name, description, active in services:
        text += f"🔹 <b>{name}</b>\n"
        if description:
            text += f"{description}\n"
        text += "\n"

    text += "للطلب، اضغط على «اطلب خدمة»."

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "🛒 اطلب خدمة",
                    callback_data="new_order",
                )
            ],
            [
                InlineKeyboardButton(
                    "🏠 الرئيسية",
                    callback_data="home",
                )
            ],
        ]),
    )


async def new_order(query, context):
    services = get_services()

    if not services:
        await query.edit_message_text(
            "عذرًا، لا توجد خدمات متاحة للطلب حاليًا.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    "🏠 الرئيسية",
                    callback_data="home",
                )
            ]]),
        )
        return

    buttons = []

    for service_id, name, description, active in services:
        buttons.append([
            InlineKeyboardButton(
                f"📌 {name}",
                callback_data=f"choose_service:{service_id}",
            )
        ])

    buttons.append([
        InlineKeyboardButton(
            "❌ إلغاء",
            callback_data="home",
        )
    ])

    await query.edit_message_text(
        "🛒 <b>طلب خدمة جديدة</b>\n\n"
        "اختار الخدمة اللي محتاجها:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


# ==============================
# Main callback handler
# ==============================

async def button_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    data = query.data

    if (
        get_setting("maintenance", "0") == "1"
        and not is_admin(user_id)
    ):
        await query.edit_message_text(
            "🛠 البوت تحت الصيانة حاليًا."
        )
        return

    if data == "home":
        context.user_data.pop("state", None)

        await query.edit_message_text(
            f"✨ {get_setting('bot_name', 'Altofan Social')}\n\n"
            "اختار من القائمة الرئيسية 👇",
            reply_markup=main_keyboard(),
        )

    elif data == "services":
        await show_services(query)

    elif data == "packages":
        await query.edit_message_text(
            "💰 <b>الباقات والأسعار</b>\n\n"
            "الأسعار بتتحدد حسب الخدمة المطلوبة "
            "وحجم الشغل.\n\n"
            "📌 اطلب الخدمة عشان نراجع التفاصيل "
            "ونحدد السعر قبل تأكيد التنفيذ.\n\n"
            "لا توجد أسعار ثابتة مضافة حتى الآن.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "🛒 اطلب خدمة",
                        callback_data="new_order",
                    )
                ],
                [
                    InlineKeyboardButton(
                        "🏠 الرئيسية",
                        callback_data="home",
                    )
                ],
            ]),
        )

    elif data == "new_order":
        context.user_data.pop("state", None)
        await new_order(query, context)

    elif data.startswith("choose_service:"):
        service_id = int(data.split(":")[1])
        services = get_services()

        selected = next(
            (s for s in services if s[0] == service_id),
            None,
        )

        if not selected:
            await query.edit_message_text(
                "الخدمة دي مش متاحة حاليًا."
            )
            return

        context.user_data["state"] = "order_name"
        context.user_data["selected_service"] = selected[1]

        await query.edit_message_text(
            f"✅ اخترت: {selected[1]}\n\n"
            "👤 اكتب اسمك بالكامل أولًا.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    "❌ إلغاء",
                    callback_data="cancel",
                )
            ]]),
        )

    elif data.startswith("support_reply:"):
        if not is_admin(user_id):
            await query.answer("غير مسموح لك.", show_alert=True)
            return
        target_id = int(data.split(":", 1)[1])
        context.user_data["state"] = f"support_reply:{target_id}"
        await query.message.reply_text(
            f"✍️ اكتب ردك على المستخدم {target_id} في رسالة واحدة.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ إلغاء", callback_data="cancel")
            ]]),
        )

    elif data == "cancel":
        context.user_data.pop("state", None)
        for key in (
            "selected_service", "customer_name", "customer_phone",
            "support_reply_user",
        ):
            context.user_data.pop(key, None)

        await query.edit_message_text(
            "تم إلغاء العملية.",
            reply_markup=main_keyboard(),
        )

    elif data == "my_orders":
        with db() as con:
            orders = con.execute(
                """
                SELECT id, service, status, created
                FROM orders
                WHERE user_id = ?
                ORDER BY id DESC LIMIT 10
                """,
                (user_id,),
            ).fetchall()

        if not orders:
            text = "📋 لسه معندكش طلبات مسجلة."
        else:
            text = "📋 <b>آخر طلباتك</b>\n\n"

            for order_id, service, status, created in orders:
                text += (
                    f"🆔 الطلب: #{order_id}\n"
                    f"📌 الخدمة: {service}\n"
                    f"📍 الحالة: {status}\n"
                    f"🕒 التاريخ: {created}\n\n"
                )

        await query.edit_message_text(
            text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    "🏠 الرئيسية",
                    callback_data="home",
                )
            ]]),
        )

    elif data == "support":
        context.user_data["state"] = "support_message"
        await query.edit_message_text(
            "🆘 الدعم الفني\n\n"
            "اكتب استفسارك أو شكواك في رسالة واحدة، "
            "وسنرسلها للإدارة للرد عليك.\n\n"
            "لا ترسل كلمات مرور أو أكواد تحقق.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ إلغاء", callback_data="cancel")
            ]]),
        )

    elif data == "tips":
        await query.edit_message_text(
            "💡 <b>نصائح لتطوير حسابك</b>\n\n"
            "1️⃣ انشر محتوى مفيد بانتظام.\n"
            "2️⃣ استخدم صورًا وتصميمات واضحة.\n"
            "3️⃣ اكتب وصفًا مناسبًا لكل منشور.\n"
            "4️⃣ تفاعل مع جمهورك بشكل طبيعي.\n"
            "5️⃣ راجع نتائج المحتوى وطوّر خطتك.\n\n"
            "النمو الحقيقي يحتاج محتوى جيدًا واستمرارية.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    "🏠 الرئيسية",
                    callback_data="home",
                )
            ]]),
        )

    elif data == "about":
        await query.edit_message_text(
            "ℹ️ <b>عن Altofan Social</b>\n\n"
            "منصة لطلب خدمات تصميم المحتوى "
            "وإدارة حسابات السوشيال ميديا.\n\n"
            "يتم تسجيل الطلب ومراجعته قبل الاتفاق "
            "على السعر والتنفيذ.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    "🏠 الرئيسية",
                    callback_data="home",
                )
            ]]),
        )

    elif data == "discover_accounts":
        await query.edit_message_text(
            "📈 <b>اكتشف الحسابات</b>\\n\\n"
            "سجّل حسابك أو استعرض حسابات صُنّاع المحتوى "
            "المسجلين للتعارف والتعاون الحقيقي.\\n\\n"
            "اختر:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    "➕ أضف حسابي",
                    callback_data="discover_add",
                )],
                [InlineKeyboardButton(
                    "🔎 استعرض الحسابات",
                    callback_data="discover_list",
                )],
                [InlineKeyboardButton(
                    "🏠 الرئيسية",
                    callback_data="home",
                )],
            ]),
        )

    elif data == "discover_add":
        context.user_data.pop("state", None)
        await query.edit_message_text(
            "📱 اختر المنصة التي تريد تسجيل حسابك عليها:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    "📸 إنستجرام",
                    callback_data="discover_platform:Instagram",
                )],
                [InlineKeyboardButton(
                    "🎵 تيك توك",
                    callback_data="discover_platform:TikTok",
                )],
                [InlineKeyboardButton(
                    "📘 فيسبوك",
                    callback_data="discover_platform:Facebook",
                )],
                [InlineKeyboardButton(
                    "▶️ يوتيوب",
                    callback_data="discover_platform:YouTube",
                )],
                [InlineKeyboardButton(
                    "❌ إلغاء",
                    callback_data="discover_accounts",
                )],
            ]),
        )

    elif data.startswith("discover_platform:"):
        platform = data.split(":", 1)[1]
        if platform not in ("Instagram", "TikTok", "Facebook", "YouTube"):
            await query.edit_message_text("المنصة غير صحيحة.")
            return

        context.user_data["discovery_platform"] = platform
        context.user_data["state"] = "discovery_link"
        await query.edit_message_text(
            f"✅ المنصة: {platform}\\n\\n"
            "ابعت رابط حسابك العام كاملًا.\\n"
            "مثال: https://www.example.com/youraccount\\n\\n"
            "لا ترسل كلمة المرور أو أكواد التحقق.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    "❌ إلغاء",
                    callback_data="cancel",
                )
            ]]),
        )

    elif data == "discover_list":
        with db() as con:
            accounts = con.execute(
                """
                SELECT platform, profile_url, niche, collaboration
                FROM creator_accounts
                ORDER BY id DESC
                LIMIT 20
                """
            ).fetchall()

        if not accounts:
            text = (
                "🔎 لا توجد حسابات مسجلة حتى الآن.\\n"
                "كن أول من يضيف حسابه!"
            )
        else:
            text = "🔎 <b>الحسابات المسجلة</b>\\n\\n"
            for platform, url, niche, collaboration in accounts:
                safe_platform = (
                    platform.replace("&", "&amp;")
                    .replace("<", "&lt;")
                    .replace(">", "&gt;")
                )
                safe_niche = (
                    niche.replace("&", "&amp;")
                    .replace("<", "&lt;")
                    .replace(">", "&gt;")
                )
                safe_url = (
                    url.replace("&", "&amp;")
                    .replace('"', "&quot;")
                    .replace("<", "&lt;")
                    .replace(">", "&gt;")
                )
                text += (
                    f"📱 <b>{safe_platform}</b>\\n"
                    f"🔗 <a href=\"{safe_url}\">فتح الحساب</a>\\n"
                    f"🎯 المجال: {safe_niche}\\n"
                    f"🤝 التعاون: {collaboration}\\n\\n"
                )

        await query.edit_message_text(
            text,
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    "➕ أضف حسابي",
                    callback_data="discover_add",
                )],
                [InlineKeyboardButton(
                    "↩️ رجوع",
                    callback_data="discover_accounts",
                )],
                [InlineKeyboardButton(
                    "🏠 الرئيسية",
                    callback_data="home",
                )],
            ]),
        )

    elif data.startswith("discover_collab:"):
        if context.user_data.get("state") != "discovery_collaboration":
            await query.edit_message_text(
                "انتهت هذه العملية. افتح اكتشف الحسابات وحاول مجددًا.",
                reply_markup=main_keyboard(),
            )
            return

        choice = data.split(":", 1)[1]
        if choice not in ("yes", "no"):
            await query.edit_message_text("اختيار غير صحيح.")
            return

        platform = context.user_data.get("discovery_platform")
        url = context.user_data.get("discovery_url")
        niche = context.user_data.get("discovery_niche")

        if not all((platform, url, niche)):
            context.user_data.pop("state", None)
            await query.edit_message_text(
                "بيانات التسجيل غير مكتملة. ابدأ من جديد.",
                reply_markup=main_keyboard(),
            )
            return

        collaboration = "يقبل التعاون" if choice == "yes" else "لا يقبل التعاون حاليًا"

        try:
            with db() as con:
                con.execute(
                    """
                    INSERT INTO creator_accounts
                    (user_id, platform, profile_url, niche, collaboration, created)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(user_id, platform, profile_url)
                    DO UPDATE SET niche = excluded.niche,
                                  collaboration = excluded.collaboration,
                                  created = excluded.created
                    """,
                    (
                        query.from_user.id,
                        platform,
                        url,
                        niche,
                        collaboration,
                        datetime.now().strftime("%Y-%m-%d %H:%M"),
                    ),
                )
        except sqlite3.Error:
            logger.exception("Could not save creator account")
            await query.edit_message_text(
                "حصل خطأ أثناء حفظ الحساب. حاول مرة أخرى."
            )
            return

        for key in (
            "state",
            "discovery_platform",
            "discovery_url",
            "discovery_niche",
        ):
            context.user_data.pop(key, None)

        await query.edit_message_text(
            "✅ تم تسجيل حسابك بنجاح!\\n\\n"
            f"📱 المنصة: {platform}\\n"
            f"🎯 المجال: {niche}\\n"
            f"🤝 {collaboration}\\n\\n"
            "يمكنك الآن استعراض الحسابات المسجلة.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    "🔎 استعرض الحسابات",
                    callback_data="discover_list",
                )],
                [InlineKeyboardButton(
                    "🏠 الرئيسية",
                    callback_data="home",
                )],
            ]),
        )

    # Admin panel
    elif data == "admin":
        if not is_admin(user_id):
            await query.edit_message_text("غير مسموح لك.")
            return

        await query.edit_message_text(
            "👨‍💻 <b>لوحة تحكم المسؤول</b>",
            parse_mode="HTML",
            reply_markup=admin_keyboard(),
        )

    elif data == "admin_stats":
        if not is_admin(user_id):
            return

        with db() as con:
            users = con.execute(
                "SELECT COUNT(*) FROM users"
            ).fetchone()[0]

            total_orders = con.execute(
                "SELECT COUNT(*) FROM orders"
            ).fetchone()[0]

            new_orders = con.execute(
                "SELECT COUNT(*) FROM orders WHERE status = 'جديد'"
            ).fetchone()[0]

            active_services = con.execute(
                "SELECT COUNT(*) FROM services WHERE active = 1"
            ).fetchone()[0]

        await query.edit_message_text(
            "📊 <b>إحصائيات البوت</b>\n\n"
            f"👥 المستخدمون: {users}\n"
            f"📦 إجمالي الطلبات: {total_orders}\n"
            f"🆕 الطلبات الجديدة: {new_orders}\n"
            f"🛠 الخدمات المتاحة: {active_services}",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    "↩️ لوحة الإدارة",
                    callback_data="admin",
                )
            ]]),
        )

    elif data == "admin_orders":
        if not is_admin(user_id):
            return

        with db() as con:
            orders = con.execute(
                """
                SELECT id, user_id, service, status
                FROM orders ORDER BY id DESC LIMIT 15
                """
            ).fetchall()

        if not orders:
            text = "📦 لا توجد طلبات حتى الآن."
            buttons = []
        else:
            text = "📦 <b>إدارة الطلبات</b>\n\n"
            buttons = []

            for oid, uid, service, status in orders:
                text += (
                    f"#{oid} | {service}\n"
                    f"المستخدم: {uid} | الحالة: {status}\n\n"
                )

                buttons.append([
                    InlineKeyboardButton(
                        f"#{oid} — تغيير الحالة",
                        callback_data=f"order_status:{oid}",
                    )
                ])

        buttons.append([
            InlineKeyboardButton(
                "↩️ لوحة الإدارة",
                callback_data="admin",
            )
        ])

        await query.edit_message_text(
            text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(buttons),
        )

    elif data.startswith("order_status:"):
        if not is_admin(user_id):
            return

        order_id = int(data.split(":")[1])

        with db() as con:
            exists = con.execute(
                "SELECT id FROM orders WHERE id = ?",
                (order_id,),
            ).fetchone()

        if not exists:
            await query.edit_message_text("الطلب غير موجود.")
            return

        await query.edit_message_text(
            f"اختر الحالة الجديدة للطلب #{order_id}:",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "🆕 جديد",
                        callback_data=f"set_status:{order_id}:جديد",
                    ),
                    InlineKeyboardButton(
                        "🔄 قيد التنفيذ",
                        callback_data=f"set_status:{order_id}:قيد التنفيذ",
                    ),
                ],
                [
                    InlineKeyboardButton(
                        "✅ مكتمل",
                        callback_data=f"set_status:{order_id}:مكتمل",
                    ),
                    InlineKeyboardButton(
                        "❌ مرفوض",
                        callback_data=f"set_status:{order_id}:مرفوض",
                    ),
                ],
                [
                    InlineKeyboardButton(
                        "↩️ رجوع للطلبات",
                        callback_data="admin_orders",
                    )
                ],
            ]),
        )

    elif data.startswith("set_status:"):
        if not is_admin(user_id):
            return

        parts = data.split(":", 2)
        order_id = int(parts[1])
        status = parts[2]

        allowed = ["جديد", "قيد التنفيذ", "مكتمل", "مرفوض"]

        if status not in allowed:
            return

        with db() as con:
            row = con.execute(
                "SELECT user_id FROM orders WHERE id = ?",
                (order_id,),
            ).fetchone()

            if row:
                con.execute(
                    "UPDATE orders SET status = ? WHERE id = ?",
                    (status, order_id),
                )

        if row:
            try:
                await context.bot.send_message(
                    chat_id=row[0],
                    text=(
                        f"📦 تحديث على طلبك #{order_id}\n"
                        f"الحالة الجديدة: {status}"
                    ),
                )
            except Exception:
                logger.warning(
                    "Could not notify user about order %s",
                    order_id,
                )

        await query.edit_message_text(
            f"تم تحديث الطلب #{order_id} إلى: {status}",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "📦 الطلبات",
                        callback_data="admin_orders",
                    )
                ],
                [
                    InlineKeyboardButton(
                        "👨‍💻 لوحة الإدارة",
                        callback_data="admin",
                    )
                ],
            ]),
        )

    elif data == "admin_services":
        if not is_admin(user_id):
            return

        services = get_services(active_only=False)
        buttons = []

        text = "🛠 <b>إدارة الخدمات</b>\n\n"

        for sid, name, description, active in services:
            status = "🟢 متاحة" if active else "🔴 متوقفة"
            text += f"#{sid} — {name}\n{status}\n\n"

            buttons.append([
                InlineKeyboardButton(
                    f"{'🔴 إيقاف' if active else '🟢 تفعيل'} #{sid}",
                    callback_data=f"toggle_service:{sid}",
                )
            ])

        buttons.extend([
            [
                InlineKeyboardButton(
                    "➕ إضافة خدمة",
                    callback_data="admin_add_service",
                )
            ],
            [
                InlineKeyboardButton(
                    "↩️ لوحة الإدارة",
                    callback_data="admin",
                )
            ],
        ])

        await query.edit_message_text(
            text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(buttons),
        )

    elif data.startswith("toggle_service:"):
        if not is_admin(user_id):
            return

        sid = int(data.split(":")[1])

        with db() as con:
            con.execute(
                """
                UPDATE services
                SET active = CASE WHEN active = 1 THEN 0 ELSE 1 END
                WHERE id = ?
                """,
                (sid,),
            )

        services = get_services(active_only=False)
        buttons = []

        text = "🛠 <b>إدارة الخدمات</b>\n\n"

        for service_id, name, description, active in services:
            status = "🟢 متاحة" if active else "🔴 متوقفة"
            text += f"#{service_id} — {name}\n{status}\n\n"

            buttons.append([
                InlineKeyboardButton(
                    f"{'🔴 إيقاف' if active else '🟢 تفعيل'} #{service_id}",
                    callback_data=f"toggle_service:{service_id}",
                )
            ])

        buttons.append([
            InlineKeyboardButton(
                "↩️ لوحة الإدارة",
                callback_data="admin",
            )
        ])

        await query.edit_message_text(
            text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(buttons),
        )

    elif data == "admin_add_service":
        if not is_admin(user_id):
            return

        context.user_data["state"] = "add_service"

        await query.edit_message_text(
            "➕ اكتب اسم الخدمة ووصفها في رسالة واحدة.\n\n"
            "استخدم الشكل ده:\n"
            "اسم الخدمة | وصف الخدمة\n\n"
            "مثال:\n"
            "تصميم لوجو | تصميم هوية بصرية مميزة\n\n"
            "للإلغاء، اضغط الزر.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    "❌ إلغاء",
                    callback_data="cancel",
                )
            ]]),
        )

    elif data == "admin_settings":
        if not is_admin(user_id):
            return

        await query.edit_message_text(
            "⚙️ <b>إعدادات البوت</b>\n\n"
            f"الاسم: {get_setting('bot_name')}\n"
            f"الدعم: {get_setting('support')}\n"
            f"الصيانة: {get_setting('maintenance')}\n\n"
            "اختار الإعداد اللي عايز تعدله:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "✏️ اسم البوت",
                        callback_data="setting:bot_name",
                    ),
                    InlineKeyboardButton(
                        "💬 رسالة الترحيب",
                        callback_data="setting:welcome",
                    ),
                ],
                [
                    InlineKeyboardButton(
                        "🆘 حساب الدعم",
                        callback_data="setting:support",
                    ),
                ],
                [
                    InlineKeyboardButton(
                        "↩️ لوحة الإدارة",
                        callback_data="admin",
                    )
                ],
            ]),
        )

    elif data.startswith("setting:"):
        if not is_admin(user_id):
            return

        key = data.split(":", 1)[1]

        allowed = {
            "bot_name": "اكتب الاسم الجديد للبوت:",
            "welcome": "اكتب رسالة الترحيب الجديدة:",
            "support": "اكتب حساب الدعم أو وسيلة التواصل:",
        }

        if key not in allowed:
            return

        context.user_data["state"] = f"setting:{key}"

        await query.edit_message_text(
            allowed[key],
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    "❌ إلغاء",
                    callback_data="cancel",
                )
            ]]),
        )

    elif data == "admin_maintenance":
        if not is_admin(user_id):
            return

        current = get_setting("maintenance", "0")
        new_value = "0" if current == "1" else "1"
        set_setting("maintenance", new_value)

        status = "مفعّلة 🛠" if new_value == "1" else "متوقفة ✅"

        await query.edit_message_text(
            f"تم تحديث وضع الصيانة.\nالحالة الحالية: {status}",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    "↩️ لوحة الإدارة",
                    callback_data="admin",
                )
            ]]),
        )


# ==============================
# Incoming text
# ==============================

async def text_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    user = update.effective_user
    message = update.effective_message
    state = context.user_data.get("state")

    if not state:
        await message.reply_text(
            "استخدم الأزرار الموجودة في القائمة الرئيسية.",
            reply_markup=main_keyboard(),
        )
        return

    if state == "discovery_link":
        url = message.text.strip()
        if (
            not url.startswith(("https://", "http://"))
            or len(url) > 500
            or any(ch.isspace() for ch in url)
        ):
            await message.reply_text(
                "الرابط غير صحيح. ابعت رابطًا عامًا يبدأ بـ https:// أو http://."
            )
            return

        context.user_data["discovery_url"] = url
        context.user_data["state"] = "discovery_niche"
        await message.reply_text(
            "🎯 اكتب مجال المحتوى الخاص بحسابك، "
            "مثل التصميم أو التعليم أو الترفيه أو التجارة."
        )

    elif state == "discovery_niche":
        niche = message.text.strip()
        if not 2 <= len(niche) <= 80:
            await message.reply_text(
                "اكتب مجالًا من 2 إلى 80 حرفًا."
            )
            return

        context.user_data["discovery_niche"] = niche
        context.user_data["state"] = "discovery_collaboration"
        await message.reply_text(
            "🤝 هل تقبل التعاون مع صُنّاع محتوى آخرين؟",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    "✅ أقبل التعاون",
                    callback_data="discover_collab:yes",
                )],
                [InlineKeyboardButton(
                    "❌ لا حاليًا",
                    callback_data="discover_collab:no",
                )],
                [InlineKeyboardButton(
                    "❌ إلغاء",
                    callback_data="cancel",
                )],
            ]),
        )

    elif state == "order_name":
        customer_name = message.text.strip()
        if not 2 <= len(customer_name) <= 100:
            await message.reply_text("اكتب اسمًا من 2 إلى 100 حرف.")
            return
        context.user_data["customer_name"] = customer_name
        context.user_data["state"] = "order_phone"
        await message.reply_text(
            "📱 اكتب رقم هاتفك للتواصل معك بخصوص الطلب.\n"
            "اكتب الرقم مع مفتاح الدولة إن أمكن."
        )

    elif state == "order_phone":
        phone = message.text.strip()
        digits = sum(ch.isdigit() for ch in phone)
        if digits < 7 or len(phone) > 30:
            await message.reply_text("رقم الهاتف غير واضح. أعد كتابته من فضلك.")
            return
        context.user_data["customer_phone"] = phone
        context.user_data["state"] = "order_details"
        await message.reply_text(
            "📝 اكتب تفاصيل طلبك في رسالة واحدة.\n"
            "مثال: رابط الصفحة، نوع التصميم، الكمية المطلوبة، وأي ملاحظات.\n\n"
            "⚠️ لا ترسل كلمات مرور أو أكواد تحقق."
        )

    elif state == "support_message":
        support_text = message.text.strip()
        if not 2 <= len(support_text) <= 3500:
            await message.reply_text("اكتب رسالة من 2 إلى 3500 حرف.")
            return
        created = datetime.now().strftime("%Y-%m-%d %H:%M")
        with db() as con:
            cur = con.execute(
                "INSERT INTO support_messages (user_id, message, status, created) "
                "VALUES (?, ?, 'جديد', ?)",
                (user.id, support_text, created),
            )
            support_id = cur.lastrowid
        context.user_data.pop("state", None)
        await message.reply_text(
            f"✅ تم إرسال رسالتك للدعم الفني. رقم المتابعة: #{support_id}",
            reply_markup=main_keyboard(),
        )
        try:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=(
                    f"🆘 رسالة دعم جديدة #{support_id}\n\n"
                    f"👤 العميل: {user.full_name}\n"
                    f"🆔 المستخدم: {user.id}\n"
                    f"💬 الرسالة:\n{support_text}"
                ),
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(
                        "↩️ الرد على العميل",
                        callback_data=f"support_reply:{user.id}",
                    )
                ]]),
            )
        except Exception:
            logger.exception("Could not notify administrator about support message")

    elif state.startswith("support_reply:"):
        if not is_admin(user.id):
            context.user_data.pop("state", None)
            await message.reply_text("غير مسموح لك.")
            return
        target_id = int(state.split(":", 1)[1])
        reply_text = message.text.strip()
        if not reply_text:
            await message.reply_text("اكتب نص الرد.")
            return
        try:
            await context.bot.send_message(
                chat_id=target_id,
                text=f"💬 رد الدعم الفني من Altofan Social:\n\n{reply_text}",
            )
            context.user_data.pop("state", None)
            await message.reply_text("✅ تم إرسال الرد للعميل.", reply_markup=admin_keyboard())
        except Exception:
            logger.exception("Could not send support reply")
            await message.reply_text("تعذر إرسال الرد. قد يكون العميل لم يبدأ البوت.")

    elif state == "order_details":
        service = context.user_data.get(
            "selected_service",
            "خدمة غير محددة",
        )
        customer_name = context.user_data.get("customer_name", user.full_name)
        phone = context.user_data.get("customer_phone", "")

        details = message.text.strip()

        if len(details) < 3:
            await message.reply_text(
                "من فضلك اكتب تفاصيل أوضح للطلب."
            )
            return

        with db() as con:
            cursor = con.execute(
                """
                INSERT INTO orders
                (user_id, service, details, status, created, customer_name, phone)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user.id,
                    service,
                    details,
                    "جديد",
                    datetime.now().strftime("%Y-%m-%d %H:%M"),
                    customer_name,
                    phone,
                ),
            )
            order_id = cursor.lastrowid

        context.user_data.pop("state", None)
        context.user_data.pop("selected_service", None)

        await message.reply_text(
            f"✅ تم تسجيل طلبك بنجاح!\n\n"
            f"🆔 رقم الطلب: #{order_id}\n"
            f"📌 الخدمة: {service}\n"
            "📍 الحالة: جديد\n\n"
            "سيتم مراجعة الطلب قبل الاتفاق على السعر والتنفيذ.",
            reply_markup=main_keyboard(),
        )

        try:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=(
                    f"🆕 طلب جديد #{order_id}\n\n"
                    f"👤 العميل: {customer_name}\n"
                    f"📱 الهاتف: {phone}\n"
                    f"🆔 المستخدم: {user.id}\n"
                    f"📌 الخدمة: {service}\n"
                    f"📝 التفاصيل:\n{details}"
                ),
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(
                        "📦 إدارة الطلبات",
                        callback_data="admin_orders",
                    )
                ]]),
            )
        except Exception:
            logger.exception("Could not notify administrator")

    elif state == "add_service":
        if not is_admin(user.id):
            context.user_data.pop("state", None)
            await message.reply_text("غير مسموح لك.")
            return

        parts = message.text.split("|", 1)
        name = parts[0].strip()
        description = parts[1].strip() if len(parts) > 1 else ""

        if not name:
            await message.reply_text(
                "اسم الخدمة مطلوب. حاول مرة أخرى."
            )
            return

        with db() as con:
            con.execute(
                """
                INSERT INTO services (name, description, active)
                VALUES (?, ?, 1)
                """,
                (name[:100], description[:500]),
            )

        context.user_data.pop("state", None)

        await message.reply_text(
            f"✅ تمت إضافة الخدمة: {name}",
            reply_markup=admin_keyboard(),
        )

    elif state.startswith("setting:"):
        if not is_admin(user.id):
            context.user_data.pop("state", None)
            await message.reply_text("غير مسموح لك.")
            return

        key = state.split(":", 1)[1]
        value = message.text.strip()

        if not value:
            await message.reply_text("القيمة لا يمكن أن تكون فارغة.")
            return

        if key == "support" and len(value) > 150:
            await message.reply_text(
                "وسيلة التواصل طويلة جدًا. حاول مرة أخرى."
            )
            return

        set_setting(key, value[:1000])
        context.user_data.pop("state", None)

        await message.reply_text(
            "✅ تم حفظ الإعداد بنجاح.",
            reply_markup=admin_keyboard(),
        )


# ==============================
# Error handling
# ==============================

async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE,
):
    logger.error(
        "حدث خطأ أثناء معالجة تحديث",
        exc_info=context.error,
    )


# ==============================
# Run bot
# ==============================

def main():
    if not TOKEN:
        raise RuntimeError(
            "لم يتم العثور على BOT_TOKEN. "
            "أضف التوكن في ملف .env"
        )

    init_db()

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler(
        "admin",
        lambda update, context: admin_command(update, context),
    ))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            text_handler,
        )
    )
    app.add_error_handler(error_handler)

    logger.info("Altofan Social Bot is running...")
    app.run_polling()


async def admin_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not is_admin(update.effective_user.id):
        await update.effective_message.reply_text(
            "⛔ غير مسموح لك بالدخول."
        )
        return

    await update.effective_message.reply_text(
        "👨‍💻 لوحة تحكم Altofan Social",
        reply_markup=admin_keyboard(),
    )


if __name__ == "__main__":
    main()

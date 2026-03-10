import io
import re
import sqlite3
import random
import time
from pathlib import Path
from datetime import timedelta

import discord
from discord.ext import commands
from discord import app_commands
import chat_exporter

# =========================
# CONFIG
# =========================
import os
TOKEN = os.getenv("TOKEN")
GUILD_ID = 1417106737185685619

WELCOME_CHANNEL_ID = 1417106737554788412
LOG_CHANNEL_ID = 1480716135254069430
SUGGESTIONS_CHANNEL_ID = 0
AUTO_ROLE_ID = 0

ANTI_LINK_ENABLED = True

STAFF_ROLE_IDS = [
    1441970562325807254,
    1478529581731545220,
    1480257429689073765,
    1441970810741854309,
]

HELP_ROLE_IDS = [
    1441970562325807254,
    1478529581731545220,
    1480257429689073765,
    1441970810741854309,
    1441973266775543870,
    1441972979058737292,
    1417106737185685624,
    1480243157345108089,
    1480241926320951427,
    1480243898600128532,
    1441972877539803209,
    1480244323013361704,
]

QUESTION_ROLE_IDS = STAFF_ROLE_IDS
REPORT_ROLE_IDS = STAFF_ROLE_IDS

HELP_CATEGORY = "مساعدة"
QUESTION_CATEGORY = "استفسارات"
REPORT_CATEGORY = "بلاغات"

ROLE_MENU_ROLES = {
    "🎮 Gamer": 0,
    "🎤 Mic User": 0,
    "🎨 Designer": 0,
    "💻 Developer": 0,
}

XP_MIN = 8
XP_MAX = 15
XP_COOLDOWN_SECONDS = 30

# =========================
# BOT
# =========================

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.message_content = True
intents.moderation = True

bot = commands.Bot(command_prefix="!", intents=intents)

DB_PATH = Path("bot_data.db")
xp_cooldowns = {}
giveaways = {}

# =========================
# DATABASE
# =========================

def db():
    return sqlite3.connect(DB_PATH)

def setup_db():
    conn = db()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS xp (
            guild_id INTEGER,
            user_id INTEGER,
            xp INTEGER DEFAULT 0,
            level INTEGER DEFAULT 0,
            PRIMARY KEY (guild_id, user_id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS suggestions (
            suggestion_id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER,
            user_id INTEGER,
            content TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS warns (
            warn_id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER,
            user_id INTEGER,
            moderator_id INTEGER,
            reason TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS staff_stats (
            guild_id INTEGER,
            user_id INTEGER,
            claimed INTEGER DEFAULT 0,
            closed INTEGER DEFAULT 0,
            PRIMARY KEY (guild_id, user_id)
        )
    """)

    conn.commit()
    conn.close()

def get_setting(key: str, default: int = 0):
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = cur.fetchone()
    conn.close()
    if row:
        try:
            return int(row[0])
        except Exception:
            return default
    return default

def set_setting(key: str, value: int):
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO settings (key, value)
        VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value
    """, (key, str(value)))
    conn.commit()
    conn.close()

def next_ticket_number():
    value = get_setting("ticket_counter", 1)
    set_setting("ticket_counter", value + 1)
    return value

def ensure_xp(guild_id: int, user_id: int):
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT OR IGNORE INTO xp (guild_id, user_id, xp, level)
        VALUES (?, ?, 0, 0)
    """, (guild_id, user_id))
    conn.commit()
    conn.close()

def add_xp(guild_id: int, user_id: int, amount: int):
    ensure_xp(guild_id, user_id)
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT xp, level FROM xp WHERE guild_id=? AND user_id=?", (guild_id, user_id))
    xp, level = cur.fetchone()

    new_xp = xp + amount
    new_level = int((new_xp // 100) ** 0.5)

    cur.execute("""
        UPDATE xp SET xp=?, level=?
        WHERE guild_id=? AND user_id=?
    """, (new_xp, new_level, guild_id, user_id))
    conn.commit()
    conn.close()
    return level, new_level, new_xp

def get_xp(guild_id: int, user_id: int):
    ensure_xp(guild_id, user_id)
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT xp, level FROM xp WHERE guild_id=? AND user_id=?", (guild_id, user_id))
    row = cur.fetchone()
    conn.close()
    return row if row else (0, 0)

def get_top_xp(guild_id: int, limit: int = 10):
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        SELECT user_id, xp, level
        FROM xp
        WHERE guild_id=?
        ORDER BY xp DESC
        LIMIT ?
    """, (guild_id, limit))
    rows = cur.fetchall()
    conn.close()
    return rows

def add_warn(guild_id: int, user_id: int, mod_id: int, reason: str):
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO warns (guild_id, user_id, moderator_id, reason)
        VALUES (?, ?, ?, ?)
    """, (guild_id, user_id, mod_id, reason))
    warn_id = cur.lastrowid
    conn.commit()
    conn.close()
    return warn_id

def get_warns(guild_id: int, user_id: int):
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        SELECT warn_id, moderator_id, reason
        FROM warns
        WHERE guild_id=? AND user_id=?
        ORDER BY warn_id ASC
    """, (guild_id, user_id))
    rows = cur.fetchall()
    conn.close()
    return rows

def remove_warn(warn_id: int):
    conn = db()
    cur = conn.cursor()
    cur.execute("DELETE FROM warns WHERE warn_id=?", (warn_id,))
    ok = cur.rowcount > 0
    conn.commit()
    conn.close()
    return ok

def update_staff_stat(guild_id: int, user_id: int, field: str):
    if field not in {"claimed", "closed"}:
        return
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT OR IGNORE INTO staff_stats (guild_id, user_id, claimed, closed)
        VALUES (?, ?, 0, 0)
    """, (guild_id, user_id))
    cur.execute(f"""
        UPDATE staff_stats
        SET {field} = {field} + 1
        WHERE guild_id=? AND user_id=?
    """, (guild_id, user_id))
    conn.commit()
    conn.close()

def get_staff_stats(guild_id: int, user_id: int):
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        SELECT claimed, closed
        FROM staff_stats
        WHERE guild_id=? AND user_id=?
    """, (guild_id, user_id))
    row = cur.fetchone()
    conn.close()
    return row if row else (0, 0)

# =========================
# HELPERS
# =========================

def has_staff(member: discord.Member):
    return any(role.id in STAFF_ROLE_IDS for role in member.roles)

def get_log_channel(guild: discord.Guild):
    return guild.get_channel(LOG_CHANNEL_ID)

def get_category(guild: discord.Guild, name: str):
    return discord.utils.get(guild.categories, name=name)

def ticket_owner(guild: discord.Guild, channel: discord.TextChannel):
    if not channel.topic:
        return None
    for part in channel.topic.split("|"):
        if part.startswith("OWNER_ID:"):
            try:
                return guild.get_member(int(part.split(":")[1]))
            except Exception:
                return None
    return None

def ticket_type(name: str):
    clean = name.replace("claimed-", "")
    if clean.startswith("help-"):
        return "طلب مساعدة"
    if clean.startswith("question-"):
        return "استفسار"
    if clean.startswith("report-"):
        return "بلاغ عن إداري"
    return "عام"

def build_overwrites(guild: discord.Guild, user: discord.Member, role_ids: list[int]):
    ow = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, attach_files=True),
        guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, manage_channels=True, manage_messages=True),
    }
    for role_id in role_ids:
        role = guild.get_role(role_id)
        if role:
            ow[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
    return ow

async def send_log(
    guild: discord.Guild,
    title: str,
    color: discord.Color,
    *,
    channel: discord.TextChannel | None = None,
    user: discord.Member | discord.User | None = None,
    actor: discord.Member | discord.User | None = None,
    extra: list[tuple[str, str]] | None = None,
    file: discord.File | None = None,
):
    log = get_log_channel(guild)
    if not log:
        return

    embed = discord.Embed(title=title, color=color)

    if channel:
        embed.add_field(name="الشات", value=channel.mention, inline=True)
        embed.add_field(name="النوع", value=ticket_type(channel.name), inline=True)
        embed.add_field(name="الآيدي", value=str(channel.id), inline=True)

    if user:
        embed.add_field(name="العضو", value=f"{user.mention} (`{user.id}`)", inline=False)

    if actor:
        embed.add_field(name="تم بواسطة", value=f"{actor.mention}", inline=False)

    if extra:
        for n, v in extra:
            embed.add_field(name=n, value=v, inline=False)

    embed.set_footer(text="Life Mic Up Logs")

    if file:
        await log.send(embed=embed, file=file)
    else:
        await log.send(embed=embed)

# =========================
# LOG EVENTS
# =========================

@bot.event
async def on_message_delete(message: discord.Message):
    if not message.guild or message.author.bot:
        return
    text = message.content or "بدون نص"
    if len(text) > 1000:
        text = text[:1000] + "..."
    embed = discord.Embed(title="🗑️ حذف رسالة", color=discord.Color.red())
    embed.add_field(name="العضو", value=message.author.mention, inline=False)
    embed.add_field(name="القناة", value=message.channel.mention, inline=False)
    embed.add_field(name="المحتوى", value=text, inline=False)
    log = get_log_channel(message.guild)
    if log:
        await log.send(embed=embed)

@bot.event
async def on_message_edit(before: discord.Message, after: discord.Message):
    if not before.guild or before.author.bot or before.content == after.content:
        return
    old = before.content or "بدون نص"
    new = after.content or "بدون نص"
    if len(old) > 800:
        old = old[:800] + "..."
    if len(new) > 800:
        new = new[:800] + "..."
    embed = discord.Embed(title="✏️ تعديل رسالة", color=discord.Color.orange())
    embed.add_field(name="العضو", value=before.author.mention, inline=False)
    embed.add_field(name="القناة", value=before.channel.mention, inline=False)
    embed.add_field(name="قبل", value=old, inline=False)
    embed.add_field(name="بعد", value=new, inline=False)
    log = get_log_channel(before.guild)
    if log:
        await log.send(embed=embed)

@bot.event
async def on_member_ban(guild: discord.Guild, user: discord.User):
    await send_log(guild, "🔨 Ban Event", discord.Color.red(), user=user)

@bot.event
async def on_member_unban(guild: discord.Guild, user: discord.User):
    await send_log(guild, "🔓 Unban Event", discord.Color.green(), user=user)

# =========================
# WELCOME
# =========================

@bot.event
async def on_member_join(member: discord.Member):
    if AUTO_ROLE_ID:
        role = member.guild.get_role(AUTO_ROLE_ID)
        if role:
            try:
                await member.add_roles(role, reason="Auto role")
            except Exception:
                pass

    ch = bot.get_channel(WELCOME_CHANNEL_ID)
    if ch:
        embed = discord.Embed(
            title="🎉 عضو جديد وصل!",
            description=f"أهلاً وسهلاً {member.mention} في السيرفر",
            color=discord.Color.purple()
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="الاسم", value=member.name, inline=True)
        embed.add_field(name="عدد الأعضاء", value=str(member.guild.member_count), inline=True)
        await ch.send(embed=embed)

    await send_log(member.guild, "📥 Member Joined", discord.Color.green(), user=member)

@bot.event
async def on_member_remove(member: discord.Member):
    await send_log(member.guild, "📤 Member Left", discord.Color.dark_red(), user=member)

# =========================
# XP + ANTI LINK
# =========================

LINK_RE = re.compile(r"(https?://|www\.)", re.IGNORECASE)

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or not message.guild:
        await bot.process_commands(message)
        return

    if ANTI_LINK_ENABLED and LINK_RE.search(message.content) and not has_staff(message.author):
        try:
            await message.delete()
            await send_log(
                message.guild,
                "🔗 Link Deleted",
                discord.Color.orange(),
                user=message.author,
                extra=[("القناة", message.channel.mention)]
            )
        except Exception:
            pass

    key = (message.guild.id, message.author.id)
    now = time.time()

    if key not in xp_cooldowns or now - xp_cooldowns[key] >= XP_COOLDOWN_SECONDS:
        old_level, new_level, _ = add_xp(
            message.guild.id,
            message.author.id,
            random.randint(XP_MIN, XP_MAX)
        )
        xp_cooldowns[key] = now

        if new_level > old_level:
            try:
                await message.channel.send(f"🎉 مبروك {message.author.mention} وصلت لفل **{new_level}**!")
            except Exception:
                pass

    await bot.process_commands(message)

# =========================
# TICKET MODALS
# =========================

class ReportModal(discord.ui.Modal, title="إبلاغ عن إداري"):
    admin_name = discord.ui.TextInput(label="اسم الإداري", required=True)
    reason = discord.ui.TextInput(label="سبب البلاغ", style=discord.TextStyle.paragraph, required=True)

    async def on_submit(self, interaction: discord.Interaction):
        await create_ticket(
            interaction,
            "report",
            REPORT_CATEGORY,
            REPORT_ROLE_IDS,
            "🚨 بلاغ عن إداري",
            extra=[("اسم الإداري", self.admin_name.value), ("السبب", self.reason.value)]
        )

class AddUserModal(discord.ui.Modal, title="إضافة عضو"):
    user_id = discord.ui.TextInput(label="آيدي العضو", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        if not has_staff(interaction.user):
            await interaction.response.send_message("❌ فقط الإدارة.", ephemeral=True)
            return
        try:
            member = interaction.guild.get_member(int(self.user_id.value))
        except Exception:
            member = None
        if not member:
            await interaction.response.send_message("❌ العضو غير موجود.", ephemeral=True)
            return

        await interaction.channel.set_permissions(
            member,
            view_channel=True,
            send_messages=True,
            read_message_history=True,
            attach_files=True
        )
        await interaction.response.send_message(f"✅ تمت إضافة {member.mention}", ephemeral=True)

class RemoveUserModal(discord.ui.Modal, title="إزالة عضو"):
    user_id = discord.ui.TextInput(label="آيدي العضو", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        if not has_staff(interaction.user):
            await interaction.response.send_message("❌ فقط الإدارة.", ephemeral=True)
            return
        try:
            member = interaction.guild.get_member(int(self.user_id.value))
        except Exception:
            member = None
        if not member:
            await interaction.response.send_message("❌ العضو غير موجود.", ephemeral=True)
            return

        await interaction.channel.set_permissions(member, overwrite=None)
        await interaction.response.send_message(f"✅ تمت إزالة {member.mention}", ephemeral=True)

class RenameModal(discord.ui.Modal, title="إعادة تسمية التذكرة"):
    new_name = discord.ui.TextInput(label="الاسم الجديد", required=True, max_length=90)

    async def on_submit(self, interaction: discord.Interaction):
        if not has_staff(interaction.user):
            await interaction.response.send_message("❌ فقط الإدارة.", ephemeral=True)
            return
        new_name = self.new_name.value.strip().replace(" ", "-").lower()
        await interaction.channel.edit(name=new_name)
        await interaction.response.send_message(f"✅ تم تغيير الاسم إلى `{new_name}`", ephemeral=True)

# =========================
# TICKET VIEW
# =========================

class TicketActions(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="استلام", style=discord.ButtonStyle.primary, emoji="📌", custom_id="ticket_claim")
    async def claim(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not has_staff(interaction.user):
            await interaction.response.send_message("❌ فقط الإدارة.", ephemeral=True)
            return
        if interaction.channel.name.startswith("claimed-"):
            await interaction.response.send_message("❌ التذكرة مستلمة بالفعل.", ephemeral=True)
            return

        await interaction.channel.edit(name=f"claimed-{interaction.channel.name}"[:100])
        update_staff_stat(interaction.guild.id, interaction.user.id, "claimed")

        await interaction.response.send_message(f"📌 تم استلام التذكرة بواسطة {interaction.user.mention}")
        await send_log(
            interaction.guild,
            "📌 Ticket Claimed",
            discord.Color.blurple(),
            channel=interaction.channel,
            user=ticket_owner(interaction.guild, interaction.channel),
            actor=interaction.user
        )

    @discord.ui.button(label="فك الاستلام", style=discord.ButtonStyle.secondary, emoji="↩️", custom_id="ticket_unclaim")
    async def unclaim(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not has_staff(interaction.user):
            await interaction.response.send_message("❌ فقط الإدارة.", ephemeral=True)
            return
        if not interaction.channel.name.startswith("claimed-"):
            await interaction.response.send_message("❌ التذكرة ليست مستلمة.", ephemeral=True)
            return

        await interaction.channel.edit(name=interaction.channel.name.replace("claimed-", "", 1))
        await interaction.response.send_message("✅ تم فك الاستلام.", ephemeral=True)

    @discord.ui.button(label="إعادة تسمية", style=discord.ButtonStyle.secondary, emoji="✏️", custom_id="ticket_rename")
    async def rename(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RenameModal())

    @discord.ui.button(label="إضافة عضو", style=discord.ButtonStyle.success, emoji="➕", custom_id="ticket_add")
    async def add(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AddUserModal())

    @discord.ui.button(label="إزالة عضو", style=discord.ButtonStyle.secondary, emoji="➖", custom_id="ticket_remove")
    async def remove(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RemoveUserModal())

    @discord.ui.button(label="حذف التذكرة", style=discord.ButtonStyle.red, emoji="🗑️", custom_id="ticket_delete")
    async def delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not has_staff(interaction.user):
            await interaction.response.send_message("❌ فقط الإدارة.", ephemeral=True)
            return

        owner = ticket_owner(interaction.guild, interaction.channel)
        file = None

        try:
            transcript = await chat_exporter.export(interaction.channel, guild=interaction.guild, bot=bot)
            if transcript:
                file = discord.File(io.BytesIO(transcript.encode()), filename=f"{interaction.channel.name}.html")
        except Exception as e:
            print("Transcript error:", e)

        update_staff_stat(interaction.guild.id, interaction.user.id, "closed")

        await interaction.response.send_message("🗑️ سيتم حذف التذكرة...", ephemeral=True)
        await send_log(
            interaction.guild,
            "🗑️ Ticket Deleted",
            discord.Color.red(),
            channel=interaction.channel,
            user=owner,
            actor=interaction.user,
            file=file
        )
        await interaction.channel.delete()

class TicketPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="طلب مساعدة", style=discord.ButtonStyle.green, emoji="🎫", custom_id="panel_help")
    async def help(self, interaction: discord.Interaction, button: discord.ui.Button):
        await create_ticket(interaction, "help", HELP_CATEGORY, HELP_ROLE_IDS, "🎫 طلب مساعدة")

    @discord.ui.button(label="استفسار", style=discord.ButtonStyle.primary, emoji="❓", custom_id="panel_question")
    async def question(self, interaction: discord.Interaction, button: discord.ui.Button):
        await create_ticket(interaction, "question", QUESTION_CATEGORY, QUESTION_ROLE_IDS, "❓ استفسار")

    @discord.ui.button(label="إبلاغ عن إداري", style=discord.ButtonStyle.danger, emoji="🚨", custom_id="panel_report")
    async def report(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ReportModal())

async def create_ticket(interaction: discord.Interaction, prefix: str, category_name: str, role_ids: list[int], title: str, extra=None):
    guild = interaction.guild
    user = interaction.user

    for ch in guild.text_channels:
        if ch.topic == f"OWNER_ID:{user.id}|TYPE:{prefix}":
            await interaction.response.send_message(f"لديك تذكرة مفتوحة بالفعل: {ch.mention}", ephemeral=True)
            return

    category = get_category(guild, category_name)
    if not category:
        category = await guild.create_category(category_name)

    channel = await guild.create_text_channel(
        name=f"{prefix}-{next_ticket_number()}",
        category=category,
        overwrites=build_overwrites(guild, user, role_ids),
        topic=f"OWNER_ID:{user.id}|TYPE:{prefix}"
    )

    embed = discord.Embed(title=title, description="اكتب طلبك هنا وسيتم الرد عليك.", color=discord.Color.green())
    embed.add_field(name="صاحب التذكرة", value=user.mention, inline=False)

    if extra:
        for n, v in extra:
            embed.add_field(name=n, value=v, inline=False)

    await channel.send(content=user.mention, embed=embed, view=TicketActions())
    await interaction.response.send_message(f"✅ تم إنشاء التذكرة {channel.mention}", ephemeral=True)

    await send_log(
        guild,
        "📩 Ticket Opened",
        discord.Color.green(),
        channel=channel,
        user=user,
        actor=interaction.user
    )

# =========================
# ROLE MENU
# =========================

class RoleButton(discord.ui.Button):
    def __init__(self, label: str, role_id: int):
        super().__init__(label=label, style=discord.ButtonStyle.secondary, custom_id=f"role_{role_id}")
        self.role_id = role_id

    async def callback(self, interaction: discord.Interaction):
        role = interaction.guild.get_role(self.role_id)
        if not role:
            await interaction.response.send_message("❌ الرتبة غير موجودة.", ephemeral=True)
            return

        if role in interaction.user.roles:
            await interaction.user.remove_roles(role, reason="Role menu remove")
            await interaction.response.send_message(f"✅ تمت إزالة {role.name}", ephemeral=True)
        else:
            await interaction.user.add_roles(role, reason="Role menu add")
            await interaction.response.send_message(f"✅ تمت إضافة {role.name}", ephemeral=True)

class RoleMenuView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        for label, role_id in ROLE_MENU_ROLES.items():
            if role_id:
                self.add_item(RoleButton(label, role_id))

# =========================
# GIVEAWAY + POLL
# =========================

class GiveawayJoinView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="دخول السحب", style=discord.ButtonStyle.success, emoji="🎉", custom_id="giveaway_join")
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        gid = interaction.message.id
        if gid not in giveaways:
            await interaction.response.send_message("❌ السحب غير موجود.", ephemeral=True)
            return
        if interaction.user.id in giveaways[gid]["participants"]:
            await interaction.response.send_message("❌ أنت داخل السحب بالفعل.", ephemeral=True)
            return

        giveaways[gid]["participants"].add(interaction.user.id)
        await interaction.response.send_message("✅ تم إدخالك في السحب.", ephemeral=True)

class PollView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.voters = set()

    @discord.ui.button(label="نعم", style=discord.ButtonStyle.success, emoji="✅")
    async def yes(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id in self.voters:
            await interaction.response.send_message("❌ لقد صوتت بالفعل.", ephemeral=True)
            return
        self.voters.add(interaction.user.id)
        await interaction.response.send_message("✅ تم تسجيل تصويتك: نعم", ephemeral=True)

    @discord.ui.button(label="لا", style=discord.ButtonStyle.danger, emoji="❌")
    async def no(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id in self.voters:
            await interaction.response.send_message("❌ لقد صوتت بالفعل.", ephemeral=True)
            return
        self.voters.add(interaction.user.id)
        await interaction.response.send_message("✅ تم تسجيل تصويتك: لا", ephemeral=True)

# =========================
# SLASH COMMANDS
# =========================

@bot.tree.command(name="ping", description="يفحص سرعة البوت")
async def slash_ping(interaction: discord.Interaction):
    await interaction.response.send_message(f"🏓 Pong! `{round(bot.latency * 1000)}ms`")

@bot.tree.command(name="panel", description="يرسل بانل التذاكر")
async def slash_panel(interaction: discord.Interaction):
    embed = discord.Embed(
        title="📩 نظام التذاكر",
        description="🎫 طلب مساعدة\n❓ استفسار\n🚨 إبلاغ عن إداري",
        color=discord.Color.blurple()
    )
    await interaction.response.send_message(embed=embed, view=TicketPanel())

@bot.tree.command(name="server", description="يعرض معلومات السيرفر")
async def slash_server(interaction: discord.Interaction):
    guild = interaction.guild
    embed = discord.Embed(title="📊 معلومات السيرفر", color=discord.Color.blue())
    embed.add_field(name="اسم السيرفر", value=guild.name, inline=False)
    embed.add_field(name="عدد الأعضاء", value=str(guild.member_count), inline=False)
    embed.add_field(name="تاريخ الإنشاء", value=guild.created_at.strftime("%Y/%m/%d"), inline=False)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="rank", description="يعرض مستواك أو مستوى عضو")
@app_commands.describe(member="اختر عضوًا")
async def slash_rank(interaction: discord.Interaction, member: discord.Member | None = None):
    member = member or interaction.user
    xp, level = get_xp(interaction.guild.id, member.id)
    embed = discord.Embed(title="🏆 Rank", color=discord.Color.green())
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="العضو", value=member.mention, inline=False)
    embed.add_field(name="Level", value=str(level), inline=True)
    embed.add_field(name="XP", value=str(xp), inline=True)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="leaderboard", description="يعرض ترتيب أعلى الأعضاء")
async def slash_leaderboard(interaction: discord.Interaction):
    rows = get_top_xp(interaction.guild.id, 10)
    if not rows:
        await interaction.response.send_message("لا يوجد بيانات بعد.")
        return

    lines = []
    for i, (user_id, xp, level) in enumerate(rows, start=1):
        member = interaction.guild.get_member(user_id)
        name = member.name if member else f"User {user_id}"
        lines.append(f"**{i}.** {name} — Level {level} | XP {xp}")

    embed = discord.Embed(title="🏆 Leaderboard", description="\n".join(lines), color=discord.Color.gold())
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="staffstats", description="إحصائيات إداري")
@app_commands.describe(member="اختر إداريًا")
async def slash_staffstats(interaction: discord.Interaction, member: discord.Member | None = None):
    member = member or interaction.user
    claimed, closed = get_staff_stats(interaction.guild.id, member.id)

    embed = discord.Embed(title="📈 Staff Stats", color=discord.Color.blurple())
    embed.add_field(name="الإداري", value=member.mention, inline=False)
    embed.add_field(name="التذاكر المستلمة", value=str(claimed), inline=True)
    embed.add_field(name="التذاكر المغلقة", value=str(closed), inline=True)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="suggest", description="إرسال اقتراح")
@app_commands.describe(text="اكتب اقتراحك")
async def slash_suggest(interaction: discord.Interaction, text: str):
    if not SUGGESTIONS_CHANNEL_ID:
        await interaction.response.send_message("❌ حط آيدي روم الاقتراحات أولًا.", ephemeral=True)
        return

    channel = interaction.guild.get_channel(SUGGESTIONS_CHANNEL_ID)
    if not channel:
        await interaction.response.send_message("❌ روم الاقتراحات غير موجود.", ephemeral=True)
        return

    conn = db()
    cur = conn.cursor()
    cur.execute("INSERT INTO suggestions (guild_id, user_id, content) VALUES (?, ?, ?)", (interaction.guild.id, interaction.user.id, text))
    sid = cur.lastrowid
    conn.commit()
    conn.close()

    embed = discord.Embed(title=f"💡 اقتراح #{sid}", description=text, color=discord.Color.blurple())
    embed.add_field(name="المرسل", value=interaction.user.mention, inline=False)

    msg = await channel.send(embed=embed)
    await msg.add_reaction("👍")
    await msg.add_reaction("👎")

    await interaction.response.send_message("✅ تم إرسال اقتراحك.", ephemeral=True)

@bot.tree.command(name="rolemenu", description="يرسل Role Menu")
async def slash_rolemenu(interaction: discord.Interaction):
    if not has_staff(interaction.user):
        await interaction.response.send_message("❌ فقط الإدارة.", ephemeral=True)
        return

    valid = any(role_id for role_id in ROLE_MENU_ROLES.values())
    if not valid:
        await interaction.response.send_message("❌ حط آيديات الرتب أولًا داخل ROLE_MENU_ROLES.", ephemeral=True)
        return

    embed = discord.Embed(title="🎭 Role Menu", description="اختر الرتب من الأزرار:", color=discord.Color.gold())
    await interaction.response.send_message(embed=embed, view=RoleMenuView())

# إدارة
@bot.tree.command(name="clear", description="حذف عدد من الرسائل")
@app_commands.describe(amount="عدد الرسائل")
async def slash_clear(interaction: discord.Interaction, amount: app_commands.Range[int, 1, 100]):
    if not has_staff(interaction.user):
        await interaction.response.send_message("❌ فقط الإدارة.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    deleted = await interaction.channel.purge(limit=amount)
    await interaction.followup.send(f"✅ تم حذف {len(deleted)} رسالة.", ephemeral=True)

@bot.tree.command(name="timeout", description="إعطاء تايم أوت")
@app_commands.describe(member="العضو", minutes="بالدقائق", reason="السبب")
async def slash_timeout(interaction: discord.Interaction, member: discord.Member, minutes: app_commands.Range[int, 1, 40320], reason: str = "بدون سبب"):
    if not has_staff(interaction.user):
        await interaction.response.send_message("❌ فقط الإدارة.", ephemeral=True)
        return
    await member.timeout(timedelta(minutes=minutes), reason=reason)
    await interaction.response.send_message(f"✅ تم إعطاء {member.mention} تايم أوت لمدة {minutes} دقيقة.")

@bot.tree.command(name="untimeout", description="فك التايم أوت")
@app_commands.describe(member="العضو")
async def slash_untimeout(interaction: discord.Interaction, member: discord.Member):
    if not has_staff(interaction.user):
        await interaction.response.send_message("❌ فقط الإدارة.", ephemeral=True)
        return
    await member.timeout(None)
    await interaction.response.send_message(f"✅ تم فك التايم أوت عن {member.mention}.")

@bot.tree.command(name="ban", description="باند لعضو")
@app_commands.describe(member="العضو", reason="السبب")
async def slash_ban(interaction: discord.Interaction, member: discord.Member, reason: str = "بدون سبب"):
    if not has_staff(interaction.user):
        await interaction.response.send_message("❌ فقط الإدارة.", ephemeral=True)
        return
    await member.ban(reason=reason)
    await interaction.response.send_message(f"✅ تم باند {member.mention}.")

@bot.tree.command(name="kick", description="كيك لعضو")
@app_commands.describe(member="العضو", reason="السبب")
async def slash_kick(interaction: discord.Interaction, member: discord.Member, reason: str = "بدون سبب"):
    if not has_staff(interaction.user):
        await interaction.response.send_message("❌ فقط الإدارة.", ephemeral=True)
        return
    await member.kick(reason=reason)
    await interaction.response.send_message(f"✅ تم كيك {member.mention}.")

@bot.tree.command(name="lock", description="قفل الشات")
@app_commands.describe(channel="القناة")
async def slash_lock(interaction: discord.Interaction, channel: discord.TextChannel | None = None):
    if not has_staff(interaction.user):
        await interaction.response.send_message("❌ فقط الإدارة.", ephemeral=True)
        return
    channel = channel or interaction.channel
    overwrite = channel.overwrites_for(interaction.guild.default_role)
    overwrite.send_messages = False
    await channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)
    await interaction.response.send_message(f"🔒 تم قفل {channel.mention}.")

@bot.tree.command(name="unlock", description="فتح الشات")
@app_commands.describe(channel="القناة")
async def slash_unlock(interaction: discord.Interaction, channel: discord.TextChannel | None = None):
    if not has_staff(interaction.user):
        await interaction.response.send_message("❌ فقط الإدارة.", ephemeral=True)
        return
    channel = channel or interaction.channel
    overwrite = channel.overwrites_for(interaction.guild.default_role)
    overwrite.send_messages = None
    await channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)
    await interaction.response.send_message(f"🔓 تم فتح {channel.mention}.")

@bot.tree.command(name="warn", description="تحذير عضو")
@app_commands.describe(member="العضو", reason="السبب")
async def slash_warn(interaction: discord.Interaction, member: discord.Member, reason: str = "بدون سبب"):
    if not has_staff(interaction.user):
        await interaction.response.send_message("❌ فقط الإدارة.", ephemeral=True)
        return
    warn_id = add_warn(interaction.guild.id, member.id, interaction.user.id, reason)
    await interaction.response.send_message(f"✅ تم تحذير {member.mention}. رقم التحذير: `{warn_id}`")

@bot.tree.command(name="warnings", description="عرض التحذيرات")
@app_commands.describe(member="العضو")
async def slash_warnings(interaction: discord.Interaction, member: discord.Member):
    if not has_staff(interaction.user):
        await interaction.response.send_message("❌ فقط الإدارة.", ephemeral=True)
        return
    warns = get_warns(interaction.guild.id, member.id)
    if not warns:
        await interaction.response.send_message("لا يوجد تحذيرات لهذا العضو.", ephemeral=True)
        return

    embed = discord.Embed(title=f"⚠️ تحذيرات {member}", color=discord.Color.orange())
    for warn_id, moderator_id, reason in warns[:10]:
        mod = interaction.guild.get_member(moderator_id)
        embed.add_field(name=f"Warn #{warn_id}", value=f"السبب: {reason}\nالمشرف: {mod.mention if mod else moderator_id}", inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="unwarn", description="حذف تحذير")
@app_commands.describe(warn_id="رقم التحذير")
async def slash_unwarn(interaction: discord.Interaction, warn_id: int):
    if not has_staff(interaction.user):
        await interaction.response.send_message("❌ فقط الإدارة.", ephemeral=True)
        return
    ok = remove_warn(warn_id)
    await interaction.response.send_message("✅ تم حذف التحذير." if ok else "❌ التحذير غير موجود.", ephemeral=True)

# Giveaway / Poll
@bot.tree.command(name="giveaway_start", description="بدء Giveaway")
@app_commands.describe(prize="الجائزة", winners="عدد الفائزين", minutes="المدة بالدقائق")
async def giveaway_start(
    interaction: discord.Interaction,
    prize: str,
    winners: app_commands.Range[int, 1, 20],
    minutes: app_commands.Range[int, 1, 10080]
):
    if not has_staff(interaction.user):
        await interaction.response.send_message("❌ فقط الإدارة.", ephemeral=True)
        return

    embed = discord.Embed(
        title="🎉 Giveaway",
        description=f"**الجائزة:** {prize}\n**عدد الفائزين:** {winners}\n**المدة:** {minutes} دقيقة\n\nاضغط الزر للدخول.",
        color=discord.Color.gold()
    )
    await interaction.response.send_message(embed=embed, view=GiveawayJoinView())
    msg = await interaction.original_response()

    giveaways[msg.id] = {
        "prize": prize,
        "winners": winners,
        "participants": set(),
        "channel_id": interaction.channel.id,
        "ended": False,
    }

@bot.tree.command(name="giveaway_end", description="إنهاء Giveaway")
@app_commands.describe(message_id="آيدي رسالة السحب")
async def giveaway_end(interaction: discord.Interaction, message_id: str):
    if not has_staff(interaction.user):
        await interaction.response.send_message("❌ فقط الإدارة.", ephemeral=True)
        return

    try:
        message_id = int(message_id)
    except ValueError:
        await interaction.response.send_message("❌ آيدي غير صحيح.", ephemeral=True)
        return

    if message_id not in giveaways:
        await interaction.response.send_message("❌ السحب غير موجود.", ephemeral=True)
        return

    data = giveaways[message_id]
    if data["ended"]:
        await interaction.response.send_message("❌ السحب منتهي بالفعل.", ephemeral=True)
        return

    users = list(data["participants"])
    if not users:
        data["ended"] = True
        await interaction.response.send_message("❌ لا يوجد مشاركين.", ephemeral=True)
        return

    winners_count = min(data["winners"], len(users))
    winner_ids = random.sample(users, winners_count)
    mentions = [f"<@{uid}>" for uid in winner_ids]
    data["ended"] = True

    channel = interaction.guild.get_channel(data["channel_id"])
    if channel:
        await channel.send(f"🎉 الفائزون في **{data['prize']}**: {', '.join(mentions)}")

    await interaction.response.send_message("✅ تم إنهاء السحب.", ephemeral=True)

@bot.tree.command(name="poll", description="إنشاء تصويت")
@app_commands.describe(question="السؤال")
async def poll(interaction: discord.Interaction, question: str):
    if not has_staff(interaction.user):
        await interaction.response.send_message("❌ فقط الإدارة.", ephemeral=True)
        return

    embed = discord.Embed(title="📊 تصويت جديد", description=f"**السؤال:** {question}", color=discord.Color.blurple())
    await interaction.response.send_message(embed=embed, view=PollView())

# =========================
# STARTUP
# =========================

@bot.event
async def on_ready():
    setup_db()
    bot.add_view(TicketPanel())
    bot.add_view(TicketActions())
    bot.add_view(RoleMenuView())
    bot.add_view(GiveawayJoinView())

    try:
        if GUILD_ID:
            guild_obj = discord.Object(id=GUILD_ID)
            bot.tree.copy_global_to(guild=guild_obj)
            synced = await bot.tree.sync(guild=guild_obj)
            print(f"✅ Synced {len(synced)} guild slash command(s)")
        else:
            synced = await bot.tree.sync()
            print(f"✅ Synced {len(synced)} global slash command(s)")
    except Exception as e:
        print(f"Slash sync error: {e}")

    print(f"✅ Bot ready: {bot.user}")

bot.run(TOKEN)


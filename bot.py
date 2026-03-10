import os
import io
import random
from datetime import timedelta
from threading import Thread

import discord
from discord.ext import commands
from discord import app_commands
from flask import Flask
import chat_exporter

# =========================
# KEEP ALIVE
# =========================

app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is alive!"

def run_web():
    app.run(host="0.0.0.0", port=8000)

def keep_alive():
    Thread(target=run_web).start()

# =========================
# CONFIG
# =========================

TOKEN = os.getenv("TOKEN")
GUILD_ID = 1417106737185685619

WELCOME_CHANNEL_ID = 1417106737554788412
LOG_CHANNEL_ID = 1480716135254069430

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

# =========================
# BOT SETUP
# =========================

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.guilds = True
intents.moderation = True

bot = commands.Bot(command_prefix="!", intents=intents)

ticket_counter = 1
giveaways = {}

# =========================
# HELPERS
# =========================

def has_staff(member: discord.Member) -> bool:
    return any(role.id in STAFF_ROLE_IDS for role in member.roles)

def get_log_channel(guild: discord.Guild):
    return guild.get_channel(LOG_CHANNEL_ID)

def get_category(guild: discord.Guild, name: str):
    return discord.utils.get(guild.categories, name=name)

def ticket_owner(guild: discord.Guild, channel: discord.TextChannel):
    if not channel.topic:
        return None
    if channel.topic.startswith("OWNER_ID:"):
        try:
            return guild.get_member(int(channel.topic.split(":")[1]))
        except Exception:
            return None
    return None

def build_overwrites(guild: discord.Guild, user: discord.Member, role_ids: list[int]):
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        user: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            read_message_history=True,
            attach_files=True,
            embed_links=True,
        ),
        guild.me: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            read_message_history=True,
            manage_channels=True,
            manage_messages=True,
        ),
    }

    for role_id in role_ids:
        role = guild.get_role(role_id)
        if role:
            overwrites[role] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
            )

    return overwrites

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
        embed.add_field(name="الشات", value=channel.mention, inline=False)
        embed.add_field(name="الاسم", value=channel.name, inline=False)

    if user:
        embed.add_field(name="صاحب التذكرة/العضو", value=f"{user.mention} (`{user.id}`)", inline=False)

    if actor:
        embed.add_field(name="تم بواسطة", value=f"{actor.mention}", inline=False)

    if extra:
        for name, value in extra:
            embed.add_field(name=name, value=value, inline=False)

    if file:
        await log.send(embed=embed, file=file)
    else:
        await log.send(embed=embed)

# =========================
# WELCOME + LOGS
# =========================

@bot.event
async def on_member_join(member: discord.Member):
    channel = bot.get_channel(WELCOME_CHANNEL_ID)
    if channel:
        embed = discord.Embed(
            title="🎉 عضو جديد!",
            description=f"أهلاً وسهلاً {member.mention} في السيرفر",
            color=discord.Color.purple()
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="الاسم", value=member.name, inline=True)
        embed.add_field(name="عدد الأعضاء", value=str(member.guild.member_count), inline=True)
        await channel.send(embed=embed)

    await send_log(member.guild, "📥 Member Joined", discord.Color.green(), user=member)

@bot.event
async def on_member_remove(member: discord.Member):
    await send_log(member.guild, "📤 Member Left", discord.Color.red(), user=member)

@bot.event
async def on_message_delete(message: discord.Message):
    if not message.guild or message.author.bot:
        return

    content = message.content or "بدون نص"
    if len(content) > 1000:
        content = content[:1000] + "..."

    await send_log(
        message.guild,
        "🗑️ Message Deleted",
        discord.Color.red(),
        user=message.author,
        extra=[
            ("القناة", message.channel.mention),
            ("المحتوى", content),
        ]
    )

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
            extra_fields=[
                ("اسم الإداري", self.admin_name.value),
                ("سبب البلاغ", self.reason.value),
            ]
        )

class RenameModal(discord.ui.Modal, title="إعادة تسمية التذكرة"):
    new_name = discord.ui.TextInput(label="الاسم الجديد", required=True, max_length=90)

    async def on_submit(self, interaction: discord.Interaction):
        if not has_staff(interaction.user):
            await interaction.response.send_message("❌ فقط الإدارة.", ephemeral=True)
            return

        new_name = self.new_name.value.strip().replace(" ", "-").lower()
        await interaction.channel.edit(name=new_name)
        await interaction.response.send_message(f"✅ تم تغيير الاسم إلى `{new_name}`", ephemeral=True)

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

# =========================
# TICKET VIEWS
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
        await interaction.response.send_message("✅ تم فك استلام التذكرة.", ephemeral=True)

    @discord.ui.button(label="إعادة تسمية", style=discord.ButtonStyle.secondary, emoji="✏️", custom_id="ticket_rename")
    async def rename(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RenameModal())

    @discord.ui.button(label="إضافة عضو", style=discord.ButtonStyle.success, emoji="➕", custom_id="ticket_add_user")
    async def add_user(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AddUserModal())

    @discord.ui.button(label="حذف التذكرة", style=discord.ButtonStyle.red, emoji="🗑️", custom_id="ticket_delete")
    async def delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not has_staff(interaction.user):
            await interaction.response.send_message("❌ فقط الإدارة.", ephemeral=True)
            return

        owner = ticket_owner(interaction.guild, interaction.channel)
        transcript_file = None

        try:
            transcript = await chat_exporter.export(interaction.channel, guild=interaction.guild, bot=bot)
            if transcript:
                transcript_file = discord.File(
                    io.BytesIO(transcript.encode()),
                    filename=f"{interaction.channel.name}.html"
                )
        except Exception as e:
            print("Transcript error:", e)

        await interaction.response.send_message("🗑️ سيتم حذف التذكرة...", ephemeral=True)

        await send_log(
            interaction.guild,
            "🗑️ Ticket Deleted",
            discord.Color.red(),
            channel=interaction.channel,
            user=owner,
            actor=interaction.user,
            file=transcript_file
        )

        await interaction.channel.delete()

class TicketPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="طلب مساعدة", style=discord.ButtonStyle.green, emoji="🎫", custom_id="ticket_help")
    async def help(self, interaction: discord.Interaction, button: discord.ui.Button):
        await create_ticket(interaction, "help", HELP_CATEGORY, HELP_ROLE_IDS, "🎫 طلب مساعدة")

    @discord.ui.button(label="استفسار", style=discord.ButtonStyle.primary, emoji="❓", custom_id="ticket_question")
    async def question(self, interaction: discord.Interaction, button: discord.ui.Button):
        await create_ticket(interaction, "question", QUESTION_CATEGORY, QUESTION_ROLE_IDS, "❓ استفسار")

    @discord.ui.button(label="إبلاغ عن إداري", style=discord.ButtonStyle.danger, emoji="🚨", custom_id="ticket_report")
    async def report(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ReportModal())

async def create_ticket(
    interaction: discord.Interaction,
    prefix: str,
    category_name: str,
    role_ids: list[int],
    title: str,
    extra_fields: list[tuple[str, str]] | None = None,
):
    global ticket_counter

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
        name=f"{prefix}-{ticket_counter}",
        category=category,
        overwrites=build_overwrites(guild, user, role_ids),
        topic=f"OWNER_ID:{user.id}|TYPE:{prefix}"
    )

    ticket_counter += 1

    embed = discord.Embed(title=title, description="اكتب طلبك هنا وسيتم الرد عليك.", color=discord.Color.green())
    embed.add_field(name="صاحب التذكرة", value=user.mention, inline=False)

    if extra_fields:
        for name, value in extra_fields:
            embed.add_field(name=name, value=value, inline=False)

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
@app_commands.describe(member="العضو", minutes="عدد الدقائق", reason="السبب")
async def slash_timeout(
    interaction: discord.Interaction,
    member: discord.Member,
    minutes: app_commands.Range[int, 1, 40320],
    reason: str = "بدون سبب"
):
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
    bot.add_view(TicketPanel())
    bot.add_view(TicketActions())
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

if not TOKEN:
    raise ValueError("TOKEN environment variable is missing")

keep_alive()
bot.run(TOKEN)

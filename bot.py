import os
import discord
from discord.ext import commands

TOKEN = os.getenv("TOKEN")
WELCOME_CHANNEL_ID = 1417106737554788412

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    print(f"✅ البوت اشتغل: {bot.user}")


@bot.event
async def on_member_join(member):
    channel = bot.get_channel(WELCOME_CHANNEL_ID)

    if channel is None:
        print("❌ ما لقيت قناة الترحيب")
        return

    embed = discord.Embed(
        title="🎉 عضو جديد وصل!",
        description=f"أهلاً وسهلاً {member.mention} في سيرفر **Life Mic Up**",
        color=discord.Color.purple()
    )

    embed.set_thumbnail(url=member.display_avatar.url)

    embed.add_field(
        name="👤 اسم العضو",
        value=member.name,
        inline=True
    )

    embed.add_field(
        name="📊 عدد الأعضاء",
        value=str(member.guild.member_count),
        inline=True
    )

    embed.add_field(
        name="💬 نتمنى لك وقت ممتع معنا!",
        value="اقرأ القوانين وتعرف على الأعضاء 👋",
        inline=False
    )

    embed.set_footer(text="Life Mic Up Community")

    await channel.send(embed=embed)


@bot.command()
async def ping(ctx):
    await ctx.send("🏓 Pong!")


@bot.command()
async def server(ctx):
    embed = discord.Embed(
        title="📊 معلومات السيرفر",
        color=discord.Color.blue()
    )

    embed.add_field(name="اسم السيرفر", value=ctx.guild.name, inline=False)
    embed.add_field(name="عدد الأعضاء", value=str(ctx.guild.member_count), inline=False)
    embed.add_field(
        name="تاريخ إنشاء السيرفر",
        value=ctx.guild.created_at.strftime("%Y/%m/%d"),
        inline=False
    )

    await ctx.send(embed=embed)


bot.run(TOKEN)
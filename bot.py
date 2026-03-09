import os
import discord
from discord.ext import commands
from flask import Flask
import threading

TOKEN = os.getenv("TOKEN")
WELCOME_CHANNEL_ID = 1417106737554788412

# ---- web server for Koyeb ----
app = Flask('')

@app.route('/')
def home():
    return "Bot is running!"

def run_web():
    app.run(host='0.0.0.0', port=8000)

def keep_alive():
    t = threading.Thread(target=run_web)
    t.start()

# ---- discord bot ----
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

    embed = discord.Embed(
        title="🎉 عضو جديد وصل!",
        description=f"أهلاً وسهلاً {member.mention} في سيرفر **Life Mic Up**",
        color=discord.Color.purple()
    )

    embed.set_thumbnail(url=member.display_avatar.url)

    embed.add_field(name="👤 اسم العضو", value=member.name)
    embed.add_field(name="📊 عدد الأعضاء", value=str(member.guild.member_count))
    embed.add_field(name="💬 نتمنى لك وقت ممتع معنا!", value="اقرأ القوانين وتعرف على الأعضاء 👋", inline=False)

    embed.set_footer(text="Life Mic Up Community")

    await channel.send(embed=embed)

@bot.command()
async def ping(ctx):
    await ctx.send("🏓 Pong!")

keep_alive()
bot.run(TOKEN)

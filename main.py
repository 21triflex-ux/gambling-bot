import discord
from discord.ext import commands
from dotenv import load_dotenv
import os
import random
from threading import Thread
from flask import Flask
from discord.ui import View, button

# ================== SETUP ==================
load_dotenv()
token = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix='$', intents=intents)

# ================== SETTINGS ==================
START_CP = 1000
INFINITE_USER_ID = 1051632565120933898

# ================== DATA ==================
stats = {}

def get_user(user_id):
    if user_id not in stats:
        stats[user_id] = {"cp": START_CP, "wins": 0, "losses": 0, "earned": 0}
    return stats[user_id]

# ================== CARDS (Blackjack) ==================
SUITS = ["♠️", "♥️", "♦️", "♣️"]
RANKS = ["2","3","4","5","6","7","8","9","10","J","Q","K","A"]

def draw():
    return random.choice(RANKS) + random.choice(SUITS)

def get_rank(card):
    return ''.join(c for c in card if c.isalnum())

def hand_value(hand):
    total, aces = 0, 0
    for c in hand:
        r = get_rank(c)
        if r == "A":
            total += 11
            aces += 1
        elif r in ["K","Q","J"]:
            total += 10
        else:
            total += int(r)
    while total > 21 and aces:
        total -= 10
        aces -= 1
    return total

def is_blackjack(hand):
    return len(hand) == 2 and hand_value(hand) == 21

# ================== SLOTS ==================
SLOTS_SYMBOLS = ["🍒", "🍋", "🍊", "🔔", "⭐", "💎", "7️⃣"]
SLOTS_PAYOUTS = {
    "🍒🍒🍒": 3,
    "🍋🍋🍋": 4,
    "🍊🍊🍊": 5,
    "🔔🔔🔔": 8,
    "⭐⭐⭐": 10,
    "💎💎💎": 20,
    "7️⃣7️⃣7️⃣": 50,
}

def spin_slots():
    return [random.choice(SLOTS_SYMBOLS) for _ in range(3)]

# ================== WEB SERVER ==================
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is alive!"

def run_webserver():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run_webserver)
    t.start()

# ================== BLACKJACK VIEW (same as before) ==================
class GameView(View):
    # ... (Keeping the full GameView class exactly as I gave you last time)
    # I'll omit it here for brevity, but paste the full GameView from my previous response
    # (from def __init__ to the end of the class)# ================== COMMANDS ==================

@bot.command()
async def balance(ctx):
    if ctx.author.id == INFINITE_USER_ID:
        await ctx.send("💰 You have **∞ CP**")
        return
    user = get_user(ctx.author.id)
    await ctx.send(f"💰 You have **{user['cp']} CP**")


@bot.command()
async def stats(ctx):
    user = get_user(ctx.author.id)
    if user["wins"] + user["losses"] == 0:
        winrate = 0
    else:
        winrate = (user["wins"] / (user["wins"] + user["losses"])) * 100

    embed = discord.Embed(title=f"📊 Stats for {ctx.author.name}", color=0x00ff00)
    embed.add_field(name="Balance", value=f"{user['cp']} CP", inline=False)
    embed.add_field(name="Wins", value=user["wins"], inline=True)
    embed.add_field(name="Losses", value=user["losses"], inline=True)
    embed.add_field(name="Win Rate", value=f"{winrate:.1f}%", inline=True)
    embed.add_field(name="Total Earned", value=f"{user['earned']} CP", inline=False)
    await ctx.send(embed=embed)


@bot.command()
async def leaderboard(ctx):
    if not stats:
        await ctx.send("No players yet!")
        return

    sorted_users = sorted(stats.items(), key=lambda x: x[1]["cp"], reverse=True)[:10]
    
    embed = discord.Embed(title="🏆 CP Leaderboard", color=0xFFD700)
    for rank, (user_id, data) in enumerate(sorted_users, 1):
        member = ctx.guild.get_member(user_id)
        name = member.display_name if member else f"User {user_id}"
        embed.add_field(
            name=f"#{rank} {name}",
            value=f"{data['cp']} CP",
            inline=False
        )
    await ctx.send(embed=embed)


@bot.command()
async def send(ctx, member: discord.Member, amount: int):
    if amount <= 0:
        await ctx.send("❌ Amount must be positive!")
        return
    if member.id == ctx.author.id:
        await ctx.send("❌ You can't send money to yourself!")
        return

    sender = get_user(ctx.author.id)
    if ctx.author.id != INFINITE_USER_ID and sender["cp"] < amount:
        await ctx.send("❌ You don't have enough CP!")
        return

    receiver = get_user(member.id)

    if ctx.author.id != INFINITE_USER_ID:
        sender["cp"] -= amount
    receiver["cp"] += amount

    await ctx.send(f"✅ **{ctx.author.name}** sent **{amount} CP** to **{member.name}**!")


@bot.command()
async def slots(ctx, bet: int = 50):
    if bet <= 0:
        await ctx.send("❌ Bet must be positive!")
        return

    user = get_user(ctx.author.id)
    if ctx.author.id != INFINITE_USER_ID and bet > user["cp"]:
        await ctx.send("❌ You don't have enough CP!")
        return

    result = spin_slots()
    combo = "".join(result)

    payout_multiplier = SLOTS_PAYOUTS.get(combo, 0)
    winnings = bet * payout_multiplier

    if ctx.author.id != INFINITE_USER_ID:
        user["cp"] -= bet

    embed = discord.Embed(title="🎰 Slots", color=0xff00ff)
    embed.add_field(name="Result", value=" | ".join(result), inline=False)

    if payout_multiplier > 0:
        if ctx.author.id != INFINITE_USER_ID:
            user["cp"] += winnings
        embed.description = f"**🎉 JACKPOT! You won {winnings} CP!**"
        embed.color = 0x00ff00
        user["wins"] += 1
        user["earned"] += winnings
    else:
        embed.description = "Better luck next time!"
        embed.color = 0xff0000
        user["losses"] += 1

    embed.set_footer(text=f"Bet: {bet} CP | New Balance: {'∞' if ctx.author.id == INFINITE_USER_ID else user['cp']} CP")
    await ctx.send(embed=embed)


# ================== BLACKJACK COMMAND (same as before) ==================
@bot.command()
async def blackjack(ctx, bet: int):
    # ... (paste the full blackjack command from previous version)
    pass  # Replace with the full code I gave earlier


@bot.event
async def on_ready():
    print(f"✅ {bot.user} is online and ready!")
    keep_alive()

bot.run(token)

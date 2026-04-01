import discord
import json
from discord.ext import commands
from dotenv import load_dotenv
import os
import random
from threading import Thread
from flask import Flask
from discord.ui import View, button
from datetime import datetime

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
active_games = {}
daily_data = {}

def get_user(user_id):
    if user_id not in stats:
        stats[user_id] = {"cp": START_CP, "wins": 0, "losses": 0, "earned": 0}
    return stats[user_id]

# ================== CARDS ==================
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

# ================== KEEP ALIVE ==================
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is alive! ✅"

def run_webserver():
    app.run(host='0.0.0.0', port=8080, debug=False)

def keep_alive():
    Thread(target=run_webserver, daemon=True).start()

# ================== GAME VIEW ==================
class GameView(View):
    def __init__(self, ctx, bet):
        super().__init__(timeout=None)
        self.ctx = ctx
        self.player_id = ctx.author.id
        self.original_bet = bet
        self.player_hands = [[draw(), draw()]]
        self.doubled_hands = [False]
        self.dealer = [draw(), draw()]
        self.current = 0
        self.done = False
        self.split_used = False

    async def interaction_check(self, interaction):
        return interaction.user.id == self.player_id

    def current_hand(self):
        return self.player_hands[self.current]

    def get_embed(self, reveal=False):
        embed = discord.Embed(title="🎴 Blackjack", color=0x006400)

        for i, hand in enumerate(self.player_hands):
            marker = "👉 " if i == self.current and not self.done else ""
            bet = self.original_bet * (2 if self.doubled_hands[i] else 1)
            embed.add_field(
                name=f"{marker}Hand {i+1} (Bet: {bet})",
                value=f"{' '.join(hand)} ({hand_value(hand)})",
                inline=False
            )

        dealer_cards = ' '.join(self.dealer) if reveal else self.dealer[0] + " ❓"
        embed.add_field(name="Dealer", value=dealer_cards, inline=False)

        user = get_user(self.ctx.author.id)
        embed.set_footer(text=f"Balance: {'∞' if self.ctx.author.id==INFINITE_USER_ID else user['cp']}")
        return embed

    async def next_hand(self, interaction):
        if self.current < len(self.player_hands) - 1:
            self.current += 1
            await interaction.response.edit_message(embed=self.get_embed(), view=self)
        else:
            await self.finish(interaction)

    async def finish(self, interaction):
        while hand_value(self.dealer) < 17:
            self.dealer.append(draw())

        user = get_user(self.ctx.author.id)
        dealer_val = hand_value(self.dealer)
        net = 0
        infinite = self.ctx.author.id == INFINITE_USER_ID

        for i, hand in enumerate(self.player_hands):
            val = hand_value(hand)
            bet = self.original_bet * (2 if self.doubled_hands[i] else 1)

            if val > 21:
                if not infinite: net -= bet
            elif dealer_val > 21 or val > dealer_val:
                net += bet
            elif val < dealer_val:
                if not infinite: net -= bet

        if not infinite:
            user["cp"] += net

        self.done = True
        self.clear_items()

        embed = self.get_embed(reveal=True)
        embed.set_footer(text=f"Result: {net:+} CP")
        await interaction.response.edit_message(embed=embed, view=self)

    @button(label="Hit", style=discord.ButtonStyle.green)
    async def hit(self, interaction, _):
        self.current_hand().append(draw())
        await interaction.response.edit_message(embed=self.get_embed(), view=self)

    @button(label="Stand", style=discord.ButtonStyle.gray)
    async def stand(self, interaction, _):
        await self.next_hand(interaction)

# ================== COMMANDS ==================

@bot.command()
async def balance(ctx):
    user = get_user(ctx.author.id)
    await ctx.send(f"💰 {'∞' if ctx.author.id==INFINITE_USER_ID else user['cp']} CP")

# 🎁 DAILY BOX
@bot.command()
async def dailybox(ctx):
    uid = ctx.author.id
    now = datetime.utcnow()

    if uid in daily_data and "box" in daily_data[uid]:
        if (now - daily_data[uid]["box"]).total_seconds() < 86400:
            return await ctx.send("⏳ Already claimed.")

    roll = random.randint(1,100)

    if roll <= 60:
        reward = random.randint(100,250)
        tier = "Common"
    elif roll <= 90:
        reward = random.randint(300,600)
        tier = "Rare"
    else:
        reward = random.randint(800,1500)
        tier = "ULTRA"

    if uid != INFINITE_USER_ID:
        get_user(uid)["cp"] += reward

    daily_data.setdefault(uid,{})["box"] = now

    await ctx.send(f"🎁 {tier} Box → +{reward} CP")

# 🔥 DAILY STREAK
@bot.command()
async def daily(ctx):
    uid = ctx.author.id
    now = datetime.utcnow()

    data = daily_data.setdefault(uid, {"streak":0,"last":None})

    if data["last"]:
        diff = (now - data["last"]).total_seconds()
        if diff < 86400:
            return await ctx.send("⏳ Already claimed.")
        data["streak"] = data["streak"]+1 if diff<=172800 else 1
    else:
        data["streak"] = 1

    base = random.randint(150,300)
    bonus = data["streak"]*25
    total = base+bonus

    if uid != INFINITE_USER_ID:
        get_user(uid)["cp"] += total

    data["last"] = now

    await ctx.send(f"🔥 Daily → {total} CP (Streak {data['streak']})")

# ✂️ RPS PvP
@bot.command()
async def rps(ctx, opponent: discord.Member):
    if opponent.bot or opponent == ctx.author:
        return await ctx.send("❌ Invalid opponent.")

    await ctx.send("Check DMs for RPS!")

    choices = {}

    def check(m):
        return m.author in [ctx.author, opponent] and isinstance(m.channel, discord.DMChannel)

    try:
        while len(choices)<2:
            msg = await bot.wait_for("message",timeout=30,check=check)
            if msg.content.lower() not in ["rock","paper","scissors"]:
                continue
            choices[msg.author.id]=msg.content.lower()
    except:
        return await ctx.send("⏰ Timeout.")

    p1,p2 = choices[ctx.author.id], choices[opponent.id]

    def win(a,b):
        if a==b: return None
        return ctx.author if (a=="rock"and b=="scissors") or (a=="paper"and b=="rock") or (a=="scissors"and b=="paper") else opponent

    winner = win(p1,p2)
    bet = 200

    if winner:
        loser = opponent if winner==ctx.author else ctx.author
        if winner.id!=INFINITE_USER_ID: get_user(winner.id)["cp"]+=bet
        if loser.id!=INFINITE_USER_ID: get_user(loser.id)["cp"]-=bet
        await ctx.send(f"🏆 {winner.mention} wins +{bet} CP")
    else:
        await ctx.send("🤝 Tie!")

# ================== EVENTS ==================
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    keep_alive()

# ================== RUN ==================
bot.run(token)

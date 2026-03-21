import discord
from discord.ext import commands
from discord.ui import View
import random
import json
import os
import logging
import webserver
from typing import Dict

# -------------------------
# Setup
# -------------------------
logging.basicConfig(level=logging.INFO)

token = os.getenv("DISCORD_TOKEN")
if not token:
    raise ValueError("DISCORD_TOKEN not set!")

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="$", intents=intents)

CP_FILE = "cp_data.json"

# -------------------------
# Data
# -------------------------
if os.path.exists(CP_FILE):
    with open(CP_FILE, "r") as f:
        CP_DATA: Dict[str, Dict] = json.load(f)
else:
    CP_DATA: Dict[str, Dict] = {}

def save_data():
    with open(CP_FILE, "w") as f:
        json.dump(CP_DATA, f, indent=4)

def ensure_user(user_id):
    if user_id not in CP_DATA:
        CP_DATA[user_id] = {"cp": 1000, "wins": 0, "losses": 0}

# -------------------------
# Cards
# -------------------------
SUITS = ["♠️", "♥️", "♦️", "♣️"]
RANKS = ["2","3","4","5","6","7","8","9","10","J","Q","K","A"]

VALUES = {
    "2":2,"3":3,"4":4,"5":5,"6":6,"7":7,
    "8":8,"9":9,"10":10,"J":10,"Q":10,"K":10,"A":11
}

def draw_card():
    return random.choice(RANKS) + random.choice(SUITS)

def hand_value(hand):
    total = 0
    aces = 0

    for c in hand:
        r = c[:-1]
        total += VALUES[r]
        if r == "A":
            aces += 1

    while total > 21 and aces:
        total -= 10
        aces -= 1

    return total

# -------------------------
# Blackjack View
# -------------------------
class BlackjackView(View):
    def __init__(self, ctx, bet, player, dealer):
        super().__init__(timeout=120)
        self.ctx = ctx
        self.bet = bet
        self.player = player
        self.dealer = dealer
        self.done = False

        ensure_user(str(ctx.author.id))

    def update_cp(self, win=False):
        user = CP_DATA[str(self.ctx.author.id)]
        if win:
            user["cp"] += self.bet
            user["wins"] += 1
        else:
            user["cp"] -= self.bet
            user["losses"] += 1
        save_data()

    async def update_message(self, interaction):
        embed = discord.Embed(title="🎴 Blackjack", color=discord.Color.dark_green())

        embed.add_field(
            name="🧑 You",
            value=f"`{' '.join(self.player)}`\nTotal: **{hand_value(self.player)}**",
            inline=False
        )

        embed.add_field(
            name="🤖 Dealer",
            value=f"`{' '.join(self.dealer)}`\nTotal: **{hand_value(self.dealer)}**",
            inline=False
        )

        embed.add_field(name="💰 Bet", value=f"{self.bet} CP")

        # 🔥 THIS FIXES BUTTONS
        await interaction.response.defer()

        await interaction.message.edit(
            embed=embed,
            view=None if self.done else self
        )

    @discord.ui.button(label="Hit", style=discord.ButtonStyle.green)
    async def hit(self, interaction: discord.Interaction, _):
        if self.done: return

        self.player.append(draw_card())

        if hand_value(self.player) > 21:
            self.update_cp(False)
            self.done = True

        await self.update_message(interaction)

    @discord.ui.button(label="Stand", style=discord.ButtonStyle.gray)
    async def stand(self, interaction: discord.Interaction, _):
        if self.done: return

        while hand_value(self.dealer) < 17:
            self.dealer.append(draw_card())

        p = hand_value(self.player)
        d = hand_value(self.dealer)

        if d > 21 or p > d:
            self.update_cp(True)
        elif p < d:
            self.update_cp(False)

        self.done = True
        await self.update_message(interaction)

    @discord.ui.button(label="Double", style=discord.ButtonStyle.blurple)
    async def double(self, interaction: discord.Interaction, _):
        if self.done: return

        self.bet *= 2
        self.player.append(draw_card())

        if hand_value(self.player) > 21:
            self.update_cp(False)
        else:
            while hand_value(self.dealer) < 17:
                self.dealer.append(draw_card())

            if hand_value(self.dealer) > 21 or hand_value(self.player) > hand_value(self.dealer):
                self.update_cp(True)
            else:
                self.update_cp(False)

        self.done = True
        await self.update_message(interaction)

# -------------------------
# Bet View
# -------------------------
class BetView(View):
    def __init__(self, ctx):
        super().__init__(timeout=30)
        self.ctx = ctx

    async def interaction_check(self, interaction):
        return interaction.user == self.ctx.author

    async def start_game(self, interaction, bet):
        player = [draw_card(), draw_card()]
        dealer = [draw_card(), draw_card()]

        view = BlackjackView(self.ctx, bet, player, dealer)

        embed = discord.Embed(title="🎴 Blackjack", color=discord.Color.dark_green())

        embed.add_field(name="🧑 You", value=" ".join(player), inline=False)
        embed.add_field(name="🤖 Dealer", value=f"{dealer[0]} ❓", inline=False)
        embed.add_field(name="💰 Bet", value=f"{bet} CP", inline=False)

        await interaction.response.edit_message(embed=embed, view=view)

    @discord.ui.button(label="10 CP", style=discord.ButtonStyle.gray)
    async def bet10(self, interaction, _):
        await self.start_game(interaction, 10)

    @discord.ui.button(label="50 CP", style=discord.ButtonStyle.gray)
    async def bet50(self, interaction, _):
        await self.start_game(interaction, 50)

    @discord.ui.button(label="100 CP", style=discord.ButtonStyle.green)
    async def bet100(self, interaction, _):
        await self.start_game(interaction, 100)

# -------------------------
# Commands
# -------------------------
@bot.command()
async def blackjack(ctx):
    await ctx.send("💰 Choose your bet:", view=BetView(ctx))

@bot.command()
async def stats(ctx):
    ensure_user(str(ctx.author.id))
    data = CP_DATA[str(ctx.author.id)]

    embed = discord.Embed(title="📊 Stats", color=discord.Color.green())
    embed.add_field(name="CP", value=data["cp"])
    embed.add_field(name="Wins", value=data["wins"])
    embed.add_field(name="Losses", value=data["losses"])

    await ctx.send(embed=embed)

# -------------------------
# Ready
# -------------------------
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

# -------------------------
# Run
# -------------------------
if __name__ == "__main__":
    webserver.keep_alive()
    bot.run(token)

import discord
from discord.ext import commands
from discord.ui import View, Button
import random
import json
import os
import logging
import asyncio

# If you're using a webserver for keeping alive (Replit/etc)
# import webserver

logging.basicConfig(level=logging.INFO)

token = os.getenv("DISCORD_TOKEN")
if not token:
    raise ValueError("DISCORD_TOKEN not set!")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="$", intents=intents)

CP_FILE = "cp_data.json"

# -------------------------
# Data Management
# -------------------------
CP_DATA = {}

if os.path.exists(CP_FILE):
    try:
        with open(CP_FILE, "r") as f:
            CP_DATA = json.load(f)
    except Exception as e:
        print("Failed to load cp_data.json:", e)

def save_data():
    try:
        with open(CP_FILE, "w") as f:
            json.dump(CP_DATA, f, indent=4)
    except Exception as e:
        print("Failed to save cp_data:", e)

def ensure_user(user_id: str):
    if user_id not in CP_DATA:
        CP_DATA[user_id] = {"cp": 1000, "wins": 0, "losses": 0, "pushes": 0}
    return CP_DATA[user_id]

# -------------------------
# Cards & Logic
# -------------------------
SUITS = ["♠️", "♥️", "♦️", "♣️"]
RANKS = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]
VALUES = {"2":2, "3":3, "4":4, "5":5, "6":6, "7":7, "8":8, "9":9,
          "10":10, "J":10, "Q":10, "K":10, "A":11}

def draw_card():
    return random.choice(RANKS) + random.choice(SUITS)

def hand_value(hand):
    total = 0
    aces = 0
    for card in hand:
        rank = card[:-1]
        total += VALUES[rank]
        if rank == "A":
            aces += 1
    while total > 21 and aces:
        total -= 10
        aces -= 1
    return total

# -------------------------
# Blackjack Game View
# -------------------------
class BlackjackView(View):
    def __init__(self, interaction: discord.Interaction, bet: int, player_hand, dealer_hand):
        super().__init__(timeout=180)
        self.interaction = interaction
        self.bet = bet
        self.player_hand = player_hand
        self.dealer_hand = dealer_hand
        self.original_author = interaction.user
        self.finished = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user == self.original_author

    def get_embed(self, reveal_dealer=False):
        embed = discord.Embed(title="🎴 Blackjack", color=0x006400)

        player_total = hand_value(self.player_hand)
        dealer_total = hand_value(self.dealer_hand) if reveal_dealer else "?"

        embed.add_field(
            name="🧑 You",
            value=f"{'  '.join(self.player_hand)}\n**Total: {player_total}**",
            inline=False
        )
        embed.add_field(
            name="🤖 Dealer",
            value=f"{'  '.join(self.dealer_hand) if reveal_dealer else self.dealer_hand[0] + '  ❓'}\n**Total: {dealer_total}**",
            inline=False
        )
        embed.add_field(name="💰 Bet", value=f"{self.bet} CP", inline=True)

        if self.finished:
            embed.color = 0xFFD700 if "win" in self.result.lower() else 0x8B0000
            embed.set_footer(text=self.result)

        return embed

    async def end_game(self, result: str, win: bool = None):
        self.finished = True
        self.result = result
        user = ensure_user(str(self.original_author.id))

        if win is True:
            user["cp"] += self.bet
            user["wins"] += 1
        elif win is False:
            user["cp"] -= self.bet
            user["losses"] += 1
        else:  # push / tie
            user["pushes"] = user.get("pushes", 0) + 1

        save_data()

        try:
            await self.interaction.message.edit(embed=self.get_embed(reveal_dealer=True), view=None)
        except:
            pass

    async def update(self, interaction: discord.Interaction, reveal_dealer=False):
        if self.finished:
            return
        try:
            await interaction.response.defer()
            await interaction.message.edit(embed=self.get_embed(reveal_dealer), view=self)
        except discord.HTTPException:
            pass

    # ─── Buttons ────────────────────────────────────────
    @discord.ui.button(label="Hit", style=discord.ButtonStyle.green)
    async def hit(self, interaction: discord.Interaction, button: Button):
        if self.finished: return

        self.player_hand.append(draw_card())
        player_val = hand_value(self.player_hand)

        if player_val > 21:
            await self.end_game("Bust! You lose.", win=False)
        else:
            await self.update(interaction)

    @discord.ui.button(label="Stand", style=discord.ButtonStyle.gray)
    async def stand(self, interaction: discord.Interaction, button: Button):
        if self.finished: return

        # Dealer plays
        while hand_value(self.dealer_hand) < 17:
            self.dealer_hand.append(draw_card())

        player_val = hand_value(self.player_hand)
        dealer_val = hand_value(self.dealer_hand)

        if dealer_val > 21:
            await self.end_game("Dealer busts! You win!", win=True)
        elif player_val > dealer_val:
            await self.end_game("You win!", win=True)
        elif player_val < dealer_val:
            await self.end_game("Dealer wins.", win=False)
        else:
            await self.end_game("Push!", win=None)

    @discord.ui.button(label="Double", style=discord.ButtonStyle.blurple)
    async def double(self, interaction: discord.Interaction, button: Button):
        if self.finished: return

        user = ensure_user(str(self.original_author.id))
        if user["cp"] < self.bet:
            await interaction.response.send_message("Not enough CP to double!", ephemeral=True)
            return

        self.bet *= 2
        user["cp"] -= self.bet // 2   # subtract the additional amount
        save_data()

        self.player_hand.append(draw_card())
        player_val = hand_value(self.player_hand)

        if player_val > 21:
            await self.end_game("Bust on double! You lose.", win=False)
            return

        # Dealer plays
        while hand_value(self.dealer_hand) < 17:
            self.dealer_hand.append(draw_card())

        dealer_val = hand_value(self.dealer_hand)

        if dealer_val > 21 or player_val > dealer_val:
            await self.end_game("Double down win!", win=True)
        elif player_val < dealer_val:
            await self.end_game("Double down - dealer wins.", win=False)
        else:
            await self.end_game("Push on double!", win=None)

# -------------------------
# Bet Selection View
# -------------------------
class BetView(View):
    def __init__(self, interaction: discord.Interaction):
        super().__init__(timeout=60)
        self.original_user = interaction.user

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user == self.original_user

    async def start_blackjack(self, interaction: discord.Interaction, bet_amount: int):
        user = ensure_user(str(interaction.user.id))
        if user["cp"] < bet_amount:
            await interaction.response.send_message("Not enough CP!", ephemeral=True)
            return

        user["cp"] -= bet_amount
        save_data()

        player = [draw_card(), draw_card()]
        dealer = [draw_card(), draw_card()]

        view = BlackjackView(interaction, bet_amount, player, dealer)

        embed = view.get_embed(reveal_dealer=False)
        await interaction.response.edit_message(embed=embed, view=view)

    @discord.ui.button(label="10 CP", style=discord.ButtonStyle.gray)
    async def bet10(self, interaction: discord.Interaction, _):
        await self.start_blackjack(interaction, 10)

    @discord.ui.button(label="50 CP", style=discord.ButtonStyle.gray)
    async def bet50(self, interaction: discord.Interaction, _):
        await self.start_blackjack(interaction, 50)

    @discord.ui.button(label="100 CP", style=discord.ButtonStyle.green)
    async def bet100(self, interaction: discord.Interaction, _):
        await self.start_blackjack(interaction, 100)

# -------------------------
# Commands
# -------------------------
@bot.command()
async def blackjack(ctx):
    embed = discord.Embed(title="Blackjack", description="Choose your bet:", color=0x006400)
    view = BetView(ctx.interaction if hasattr(ctx, 'interaction') else None)
    await ctx.send(embed=embed, view=view)

@bot.command()
async def stats(ctx):
    user = ensure_user(str(ctx.author.id))
    embed = discord.Embed(title=f"Stats — {ctx.author}", color=0x00AA00)
    embed.add_field(name="CP", value=user["cp"], inline=True)
    embed.add_field(name="Wins", value=user["wins"], inline=True)
    embed.add_field(name="Losses", value=user["losses"], inline=True)
    embed.add_field(name="Pushes", value=user.get("pushes", 0), inline=True)
    await ctx.send(embed=embed)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    print("Blackjack bot is ready!")

# -------------------------
# Start
# -------------------------
if __name__ == "__main__":
    # webserver.keep_alive()   # uncomment if needed (Replit, etc)
    bot.run(token)

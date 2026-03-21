import discord
from discord.ext import commands
import logging
from dotenv import load_dotenv
import os
import random
import webserver

from discord.ui import View, button

# ================== SETUP ==================
load_dotenv()
token = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='$', intents=intents)

# ================== DATA ==================
balances = {}

START_CP = 1000

SUITS = ["♠️", "♥️", "♦️", "♣️"]
RANKS = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]

def draw():
    return random.choice(RANKS) + random.choice(SUITS)

def get_rank(card):
    return ''.join(ch for ch in card if ch.isalnum())

def hand_value(hand):
    total = 0
    aces = 0

    for c in hand:
        rank = get_rank(c)
        if rank == "A":
            total += 11
            aces += 1
        elif rank in ["K", "Q", "J"]:
            total += 10
        else:
            total += int(rank)

    while total > 21 and aces:
        total -= 10
        aces -= 1

    return total

# ================== GAME ==================
class GameView(View):
    def __init__(self, ctx, bet):
        super().__init__(timeout=120)
        self.ctx = ctx
        self.bet = bet

        self.player_hands = [[draw(), draw()]]
        self.current = 0

        self.dealer = [draw(), draw()]
        self.done = False
        self.split = False

    def current_hand(self):
        return self.player_hands[self.current]

    def get_embed(self, reveal=False):
        embed = discord.Embed(title="🎴 Blackjack", color=0x006400)

        for i, hand in enumerate(self.player_hands):
            marker = "👉 " if i == self.current and not self.done else ""
            embed.add_field(
                name=f"{marker}Hand {i+1}",
                value=f"{' '.join(hand)} ({hand_value(hand)})",
                inline=False
            )

        dealer_val = hand_value(self.dealer) if reveal else "?"
        dealer_cards = ' '.join(self.dealer) if reveal else self.dealer[0] + " ❓"

        embed.add_field(
            name="Dealer",
            value=f"{dealer_cards} ({dealer_val})",
            inline=False
        )

        embed.set_footer(text=f"Bet: {self.bet} CP | Balance: {balances[self.ctx.author.id]}")

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

        dealer_val = hand_value(self.dealer)

        total_win = 0

        for hand in self.player_hands:
            val = hand_value(hand)

            if val > 21:
                total_win -= self.bet
            elif dealer_val > 21 or val > dealer_val:
                total_win += self.bet
            elif val < dealer_val:
                total_win -= self.bet

        balances[self.ctx.author.id] += total_win

        result = f"Result: {total_win:+} CP"

        self.done = True
        self.clear_items()

        embed = self.get_embed(reveal=True)
        embed.set_footer(text=result)

        await interaction.response.edit_message(embed=embed, view=self)

    # ================== BUTTONS ==================

    @button(label="Hit", style=discord.ButtonStyle.green)
    async def hit(self, interaction: discord.Interaction, button: discord.ui.Button):
        hand = self.current_hand()
        hand.append(draw())

        if hand_value(hand) > 21:
            await self.next_hand(interaction)
        else:
            await interaction.response.edit_message(embed=self.get_embed(), view=self)

    @button(label="Stand", style=discord.ButtonStyle.gray)
    async def stand(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.next_hand(interaction)

    @button(label="Double", style=discord.ButtonStyle.blurple)
    async def double(self, interaction: discord.Interaction, button: discord.ui.Button):
        if len(self.current_hand()) != 2:
            return

        self.bet *= 2
        self.current_hand().append(draw())

        await self.next_hand(interaction)

    @button(label="Split", style=discord.ButtonStyle.red)
    async def split_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        hand = self.current_hand()

        if self.split:
            return

        if len(hand) != 2:
            return

        if get_rank(hand[0]) != get_rank(hand[1]):
            await interaction.response.send_message("Can't split.", ephemeral=True)
            return

        self.split = True

        h1 = [hand[0], draw()]
        h2 = [hand[1], draw()]

        self.player_hands = [h1, h2]

        await interaction.response.edit_message(embed=self.get_embed(), view=self)

# ================== COMMANDS ==================

@bot.command()
async def balance(ctx):
    if ctx.author.id not in balances:
        balances[ctx.author.id] = START_CP
    await ctx.send(f"You have {balances[ctx.author.id]} CP")

@bot.command()
async def blackjack(ctx, bet: int):
    if ctx.author.id not in balances:
        balances[ctx.author.id] = START_CP

    if bet <= 0 or bet > balances[ctx.author.id]:
        await ctx.send("Invalid bet.")
        return

    balances[ctx.author.id] -= bet

    view = GameView(ctx, bet)
    await ctx.send(embed=view.get_embed(), view=view)

# ================== RUN ==================

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

if __name__ == "__main__":
    webserver.keep_alive()
    bot.run(token)

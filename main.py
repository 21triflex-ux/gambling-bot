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
if not token:
    raise ValueError("DISCORD_TOKEN not set!")

handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix='$', intents=intents)

# ================== GAME LOGIC ==================
SUITS = ["♠️", "♥️", "♦️", "♣️"]
RANKS = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]

def draw():
    return random.choice(RANKS) + random.choice(SUITS)

# 🔥 FIXED FUNCTION (no more emoji errors)
def hand_value(hand):
    total = 0
    aces = 0

    for c in hand:
        # remove emoji safely
        rank = ''.join(ch for ch in c if ch.isalnum())

        if rank == "A":
            aces += 1
            total += 11
        elif rank in ["K", "Q", "J"]:
            total += 10
        else:
            total += int(rank)

    while total > 21 and aces:
        total -= 10
        aces -= 1

    return total

def is_blackjack(hand):
    return len(hand) == 2 and hand_value(hand) == 21

# ================== UI ==================
class GameView(View):
    def __init__(self, player_hand, dealer_hand):
        super().__init__(timeout=120)
        self.player_hand = player_hand
        self.dealer_hand = dealer_hand
        self.done = False
        self.double_done = False

    def get_embed(self, reveal_dealer=False):
        embed = discord.Embed(title="🎴 Blackjack", color=0x006400)

        p_val = hand_value(self.player_hand)
        d_val = hand_value(self.dealer_hand) if reveal_dealer else "?"

        embed.add_field(
            name="🃏 You",
            value=f"{' '.join(self.player_hand)} **({p_val})**",
            inline=False
        )

        embed.add_field(
            name="🤖 Dealer",
            value=f"{' '.join(self.dealer_hand) if reveal_dealer else self.dealer_hand[0] + ' ❓'} **({d_val})**",
            inline=False
        )

        return embed

    async def end_game(self, interaction, result):
        self.done = True
        self.clear_items()

        embed = self.get_embed(reveal_dealer=True)
        embed.set_footer(text=result)

        await interaction.response.edit_message(embed=embed, view=self)

    # ================== BUTTONS ==================

    @button(label="Hit", style=discord.ButtonStyle.green)
    async def hit(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.done:
            return

        self.player_hand.append(draw())
        val = hand_value(self.player_hand)

        if val > 21:
            await self.end_game(interaction, "💥 Bust! You lose.")
        elif val == 21:
            await self.stand(interaction, button)
        else:
            await interaction.response.edit_message(embed=self.get_embed(), view=self)

    @button(label="Stand", style=discord.ButtonStyle.gray)
    async def stand(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.done:
            return

        while hand_value(self.dealer_hand) < 17:
            self.dealer_hand.append(draw())

        p_val = hand_value(self.player_hand)
        d_val = hand_value(self.dealer_hand)

        if d_val > 21:
            result = "🔥 Dealer busts! You win!"
        elif p_val > d_val:
            result = "🎉 You win!"
        elif p_val < d_val:
            result = "😔 Dealer wins. You lose."
        else:
            result = "🤝 Push!"

        await self.end_game(interaction, result)

    @button(label="Double", style=discord.ButtonStyle.blurple)
    async def double(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.done or self.double_done or len(self.player_hand) != 2:
            return

        self.double_done = True
        self.player_hand.append(draw())

        val = hand_value(self.player_hand)

        if val > 21:
            await self.end_game(interaction, "💥 Bust on double! You lose.")
        else:
            await self.stand(interaction, button)

# ================== COMMANDS ==================

@bot.command()
async def ping(ctx):
    await ctx.send("Pong! 🏓")

@bot.command()
async def blackjack(ctx):
    player = [draw(), draw()]
    dealer = [draw(), draw()]

    view = GameView(player, dealer)
    embed = view.get_embed()

    if is_blackjack(player) and is_blackjack(dealer):
        embed.description = "🤝 Push! Both have Blackjack!"
        view.done = True
        view.clear_items()
    elif is_blackjack(dealer):
        embed.description = "😔 Dealer has Blackjack! You lose."
        view.done = True
        view.clear_items()
    elif is_blackjack(player):
        embed.description = "🃏 Blackjack! You win instantly!"
        view.done = True
        view.clear_items()

    await ctx.send(embed=embed, view=view)

# ================== EVENTS ==================

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

@bot.event
async def on_command_error(ctx, error):
    print(f"ERROR: {error}")
    await ctx.send(f"Error: {error}")

# ================== RUN ==================

if __name__ == "__main__":
    webserver.keep_alive()
    bot.run(token)

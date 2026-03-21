import discord
from discord.ext import commands
import logging
from dotenv import load_dotenv
import os
import random
import webserver

from discord.ui import View, button   # ← added this line

load_dotenv()
token = os.getenv("DISCORD_TOKEN")
if not token:
    raise ValueError("DISCORD_TOKEN not set!")

handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix='$', intents=intents)

RANKS = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]
VALUES = {r: min(10, int(r)) if r.isdigit() else 10 if r in "JQK" else 11 for r in RANKS}

def draw():
    return random.choice(RANKS)

def hand_value(hand):
    total = sum(VALUES[c] for c in hand)
    aces = hand.count("A")
    while total > 21 and aces:
        total -= 10
        aces -= 1
    return total

def is_blackjack(hand):
    return len(hand) == 2 and hand_value(hand) == 21

class GameView(View):
    def __init__(self, player_hand, dealer_hand, split=False):
        super().__init__(timeout=300)
        self.player_hand = player_hand
        self.dealer_hand = dealer_hand
        self.split_hand = None
        self.current_hand = player_hand  # for split support
        self.done = False
        self.split = split
        self.double_done = False
        self.result = ""                     # ← added
        self.message = None                  # ← added (prevents AttributeError)

    def get_embed(self, reveal_dealer=False):
        embed = discord.Embed(title="Blackjack", color=0x006400)
        p_val = hand_value(self.player_hand)
        d_val = hand_value(self.dealer_hand) if reveal_dealer else "?"

        embed.add_field(
            name="Player",
            value=f"{' '.join(self.player_hand)} ({p_val})",
            inline=False
        )
        embed.add_field(
            name="Dealer",
            value=f"{' '.join(self.dealer_hand) if reveal_dealer else self.dealer_hand[0] + ' ?'} ({d_val})",
            inline=False
        )
        if self.done:
            embed.set_footer(text=self.result)
            embed.color = 0x00ff00 if "win" in self.result.lower() else 0xff0000 if "lose" in self.result.lower() else 0xffff00
        return embed

    async def end_game(self, result):
        self.done = True
        self.result = result
        self.clear_items()
        if self.message:  # safety check
            await self.message.edit(embed=self.get_embed(reveal_dealer=True), view=self)

    async def update(self, interaction):
        if self.done: return
        await interaction.response.defer()
        await interaction.message.edit(embed=self.get_embed(), view=self)

    @button(label="Hit", style=discord.ButtonStyle.green)
    async def hit(self, interaction, _):
        if self.done: return
        self.current_hand.append(draw())
        val = hand_value(self.current_hand)
        if val > 21:
            await self.end_game("Bust! You lose.")
        else:
            await self.update(interaction)

    @button(label="Stand", style=discord.ButtonStyle.gray)
    async def stand(self, interaction, _):
        if self.done: return
        # Dealer plays
        while hand_value(self.dealer_hand) < 17:
            self.dealer_hand.append(draw())
        p_val = hand_value(self.current_hand)
        d_val = hand_value(self.dealer_hand)
        if d_val > 21:
            msg = "Dealer busts! You win!"
        elif p_val > d_val:
            msg = "You win!"
        elif p_val < d_val:
            msg = "Dealer wins. You lose."
        else:
            msg = "Push!"
        await self.end_game(msg)

    @button(label="Double", style=discord.ButtonStyle.blurple)
    async def double(self, interaction, _):
        if self.done or self.double_done or len(self.current_hand) != 2:
            return
        self.double_done = True
        self.current_hand.append(draw())
        val = hand_value(self.current_hand)
        if val > 21:
            await self.end_game("Bust on double! You lose.")
            return
        await self.stand(interaction, _)

    @button(label="Split", style=discord.ButtonStyle.red)
    async def split_btn(self, interaction, _):
        if self.done or self.split or len(self.player_hand) != 2 or self.player_hand[0] != self.player_hand[1]:
            await interaction.response.send_message("Cannot split now.", ephemeral=True)
            return
        self.split = True
        self.split_hand = [self.player_hand.pop(), draw()]
        self.current_hand = self.player_hand  # first hand
        self.player_hand.append(draw())       # complete first hand
        embed = self.get_embed()
        embed.description = "Playing first hand. Use buttons for it. Second hand next."
        await interaction.response.defer()
        await interaction.message.edit(embed=embed, view=self)

@bot.command()
async def blackjack(ctx):
    player = [draw(), draw()]
    dealer = [draw(), draw()]

    view = GameView(player, dealer)
    embed = view.get_embed()

    if is_blackjack(player):
        embed.description = "Blackjack! You win!"
        view.done = True
        view.clear_items()
    elif is_blackjack(dealer):
        embed.description = "Dealer has Blackjack. You lose."
        view.done = True
        view.clear_items()

    msg = await ctx.send(embed=embed, view=view)
    view.message = msg   # ← important

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

if __name__ == "__main__":
    webserver.keep_alive()   # assuming this is your Render/UptimeRobot keep-alive function
    bot.run(token)

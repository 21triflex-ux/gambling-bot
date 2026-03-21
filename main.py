import discord
from discord.ext import commands
from discord.ui import View, Button
import random

token = os.getenv("DISCORD_TOKEN")
if not token:
    raise ValueError("DISCORD_TOKEN not set!")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="$", intents=intents)

SUITS = ["♠️", "♥️", "♦️", "♣️"]
RANKS = ["2","3","4","5","6","7","8","9","10","J","Q","K","A"]
VALUES = {r: min(10, int(r)) if r.isdigit() else 10 if r in "JQK" else 11 for r in RANKS}

def draw():
    return random.choice(RANKS) + random.choice(SUITS)

def value(hand):
    total = sum(VALUES[c[:-1]] for c in hand)
    aces = sum(1 for c in hand if c.startswith("A"))
    while total > 21 and aces:
        total -= 10
        aces -= 1
    return total

class BlackjackView(View):
    def __init__(self, interaction, player, dealer):
        super().__init__(timeout=180)
        self.interaction = interaction
        self.player = player
        self.dealer = dealer
        self.user = interaction.user
        self.done = False
        self.result = ""

    async def interaction_check(self, i):
        return i.user == self.user

    def embed(self, reveal=False):
        e = discord.Embed(title="Blackjack", colour=0x006400)
        pt = value(self.player)
        dt = value(self.dealer) if reveal else "?"
        e.add_field(name="You", value=f"{' '.join(self.player)}\n**{pt}**", inline=False)
        e.add_field(name="Dealer", value=f"{' '.join(self.dealer) if reveal else self.dealer[0] + ' ❓'}\n**{dt}**", inline=False)
        if self.done:
            e.colour = 0xFFD700 if "win" in self.result.lower() else 0x8B0000
            e.set_footer(text=self.result)
        return e

    async def finish(self, result):
        self.done = True
        self.result = result
        await self.interaction.message.edit(embed=self.embed(True), view=None)

    async def update(self, i):
        if self.done: return
        await i.response.defer()
        await i.message.edit(embed=self.embed(), view=self)

    @discord.ui.button(label="Hit", style=discord.ButtonStyle.green)
    async def hit(self, i, _):
        if self.done: return
        self.player.append(draw())
        if value(self.player) > 21:
            await self.finish("Bust! You lose.")
        else:
            await self.update(i)

    @discord.ui.button(label="Stand", style=discord.ButtonStyle.gray)
    async def stand(self, i, _):
        if self.done: return
        while value(self.dealer) < 17:
            self.dealer.append(draw())
        p, d = value(self.player), value(self.dealer)
        if d > 21 or p > d:
            await self.finish("You win!")
        elif p < d:
            await self.finish("Dealer wins.")
        else:
            await self.finish("Push!")

    @discord.ui.button(label="Double", style=discord.ButtonStyle.blurple)
    async def double(self, i, _):
        if self.done: return
        self.player.append(draw())
        if value(self.player) > 21:
            await self.finish("Bust on double!")
            return
        while value(self.dealer) < 17:
            self.dealer.append(draw())
        p, d = value(self.player), value(self.dealer)
        if d > 21 or p > d:
            await self.finish("Double down win!")
        elif p < d:
            await self.finish("Double down - dealer wins.")
        else:
            await self.finish("Push on double!")

class BetView(View):
    def __init__(self, interaction):
        super().__init__(timeout=60)
        self.user = interaction.user

    async def interaction_check(self, i):
        return i.user == self.user

    @staticmethod
    async def start(i):
        p = [draw(), draw()]
        d = [draw(), draw()]
        v = BlackjackView(i, p, d)
        await i.response.edit_message(embed=v.embed(), view=v)

    @discord.ui.button(label="Play", style=discord.ButtonStyle.green)
    async def play(self, i, _):
        await self.start(i)

@bot.command()
async def blackjack(ctx):
    e = discord.Embed(title="Blackjack", description="Ready to play?", colour=0x006400)
    await ctx.send(embed=e, view=BetView(ctx))

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

if __name__ == "__main__":
    bot.run(token)

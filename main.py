import discord
from discord.ext import commands
from discord.ui import View, Button
import random
import json
import os
token = os.getenv("DISCORD_TOKEN")
if not token:
    raise ValueError("DISCORD_TOKEN not set!")
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="$", intents=intents)
CP_FILE = "cp_data.json"
CP_DATA = {}
if os.path.exists(CP_FILE):
    with open(CP_FILE, encoding="utf-8") as f:
        CP_DATA = json.load(f)
def save():
    with open(CP_FILE, "w", encoding="utf-8") as f:
        json.dump(CP_DATA, f, indent=4)
def ensure_user(uid):
    if uid not in CP_DATA:
        CP_DATA[uid] = {"cp": 1000, "wins": 0, "losses": 0, "pushes": 0}
    return CP_DATA[uid]
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
    def __init__(self, interaction, bet, player, dealer):
        super().__init__(timeout=180)
        self.interaction = interaction
        self.bet = bet
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
        e.add_field(name="You", value=f"{'  '.join(self.player)}\n**{pt}**", inline=False)
        e.add_field(name="Dealer", value=f"{'  '.join(self.dealer) if reveal else self.dealer[0] + ' ❓'}\n**{dt}**", inline=False)
        e.add_field(name="Bet", value=f"{self.bet} CP")
        if self.done:
            e.colour = 0xFFD700 if "win" in self.result.lower() else 0x8B0000
            e.set_footer(text=self.result)
        return e
    async def finish(self, result, win=None):
        self.done = True
        self.result = result
        u = ensure_user(str(self.user.id))
        if win is True:
            u["cp"] += self.bet
            u["wins"] += 1
        elif win is False:
            u["cp"] -= self.bet
            u["losses"] += 1
        else:
            u["pushes"] = u.get("pushes", 0) + 1
        save()
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
            await self.finish("Bust! You lose.", False)
        else:
            await self.update(i)
    @discord.ui.button(label="Stand", style=discord.ButtonStyle.gray)
    async def stand(self, i, _):
        if self.done: return
        while value(self.dealer) < 17:
            self.dealer.append(draw())
        p, d = value(self.player), value(self.dealer)
        if d > 21 or p > d:
            await self.finish("You win!", True)
        elif p < d:
            await self.finish("Dealer wins.", False)
        else:
            await self.finish("Push!")
    @discord.ui.button(label="Double", style=discord.ButtonStyle.blurple)
    async def double(self, i, _):
        if self.done: return
        u = ensure_user(str(self.user.id))
        extra = self.bet
        if u["cp"] < extra:
            await i.response.send_message("Not enough CP", ephemeral=True)
            return
        self.bet += extra
        u["cp"] -= extra
        save()
        self.player.append(draw())
        if value(self.player) > 21:
            await self.finish("Bust on double!", False)
            return
        while value(self.dealer) < 17:
            self.dealer.append(draw())
        p, d = value(self.player), value(self.dealer)
        if d > 21 or p > d:
            await self.finish("Double win!", True)
        elif p < d:
            await self.finish("Double - dealer wins.", False)
        else:
            await self.finish("Push on double!")
class BetView(View):
    def __init__(self, interaction):
        super().__init__(timeout=60)
        self.user = interaction.user
    async def interaction_check(self, i):
        return i.user == self.user
    @staticmethod
    async def start(i, bet):
        u = ensure_user(str(i.user.id))
        if u["cp"] < bet:
            await i.response.send_message("Not enough CP", ephemeral=True)
            return
        u["cp"] -= bet
        save()
        p = [draw(), draw()]
        d = [draw(), draw()]
        v = BlackjackView(i, bet, p, d)
        await i.response.edit_message(embed=v.embed(), view=v)
    @discord.ui.button(label="10 CP", style=discord.ButtonStyle.gray)
    async def b10(self, i, _): await self.start(i, 10)
    @discord.ui.button(label="50 CP", style=discord.ButtonStyle.gray)
    async def b50(self, i, _): await self.start(i, 50)
    @discord.ui.button(label="100 CP", style=discord.ButtonStyle.green)
    async def b100(self, i, _): await self.start(i, 100)
@bot.command()
async def blackjack(ctx):
    e = discord.Embed(title="Blackjack - Choose bet", colour=0x006400)
    await ctx.send(embed=e, view=BetView(ctx))
@bot.command()
async def stats(ctx):
    u = ensure_user(str(ctx.author.id))
    e = discord.Embed(title=f"Stats - {ctx.author}", colour=0x00AA00)
    e.add_field(name="CP", value=u["cp"])
    e.add_field(name="W", value=u["wins"])
    e.add_field(name="L", value=u["losses"])
    e.add_field(name="P", value=u.get("pushes", 0))
    await ctx.send(embed=e)
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
if __name__ == "__main__":
    bot.run(token)

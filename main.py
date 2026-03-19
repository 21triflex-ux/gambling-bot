import discord
from discord.ext import commands
from discord.ui import View, Button
import random
import webserver
import json
import os
from typing import List, Dict
load_dotenv()
token = os.getenv("DISCORD_TOKEN")
handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix='$', intents=intents)
# -------------------------
# Setup
# -------------------------

CP_FILE = "cp_data.json"

# Load CP data
if os.path.exists(CP_FILE):
    with open(CP_FILE, "r") as file:
        CP_DATA: Dict[str, Dict] = json.load(file)
else:
    CP_DATA: Dict[str, Dict] = {}

# -------------------------
# Blackjack Logic
# -------------------------
CARD_VALUES = {
    "2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7,
    "8": 8, "9": 9, "10": 10, "J": 10, "Q": 10, "K": 10, "A": 11
}

def draw_card() -> str:
    return random.choice(list(CARD_VALUES.keys()))

def hand_value(hand: List[str]) -> int:
    total = sum(CARD_VALUES[c] for c in hand)
    aces = hand.count("A")
    while total > 21 and aces:
        total -= 10
        aces -= 1
    return total

def save_cp_data():
    with open(CP_FILE, "w") as file:
        json.dump(CP_DATA, file, indent=4)

def ensure_user_data(user_id: str):
    if user_id not in CP_DATA:
        CP_DATA[user_id] = {"cp": 1000, "total_earned": 0, "wins": 0, "losses": 0}

# -------------------------
# Blackjack View
# -------------------------
class BlackjackView(View):
    def __init__(self, ctx: commands.Context, bet: int, player_hand: List[str], dealer_hand: List[str]):
        super().__init__(timeout=120)
        self.ctx = ctx
        self.bet = bet
        self.player_hand = player_hand
        self.dealer_hand = dealer_hand
        self.done = False
        self.result_text = ""

        ensure_user_data(str(ctx.author.id))

        if hand_value(self.player_hand) == 21:
            self.done = True
            if hand_value(self.dealer_hand) == 21:
                self.result_text = "Both you and dealer have Blackjack! Push. No CP change."
            else:
                self.result_text = f"Blackjack! You win 1.5x your bet!"
                self.update_cp(win=True, multiplier=1.5)

    def update_cp(self, win: bool = False, multiplier: float = 1.0):
        user_id = str(self.ctx.author.id)
        ensure_user_data(user_id)
        amount = int(self.bet * multiplier)
        CP_DATA[user_id]["cp"] += amount if win else -self.bet
        CP_DATA[user_id]["total_earned"] += amount if win else 0
        if win:
            CP_DATA[user_id]["wins"] += 1
        else:
            CP_DATA[user_id]["losses"] += 1
        save_cp_data()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user == self.ctx.author

    async def end_game(self, message: discord.Message):
        for child in self.children:
            child.disabled = True
        await message.edit(view=self)
        self.stop()

    @discord.ui.button(label="Hit", style=discord.ButtonStyle.green)
    async def hit(self, interaction: discord.Interaction, _button: Button):
        if self.done: return
        self.player_hand.append(draw_card())
        total = hand_value(self.player_hand)
        if total > 21:
            self.result_text = f"You busted with {total}. You lose {self.bet} CP."
            self.update_cp(win=False)
            self.done = True
        await self.update_message(interaction)

    @discord.ui.button(label="Stand", style=discord.ButtonStyle.gray)
    async def stand(self, interaction: discord.Interaction, _button: Button):
        if self.done: return
        await self.dealer_play(interaction)

    @discord.ui.button(label="Double", style=discord.ButtonStyle.blurple)
    async def double(self, interaction: discord.Interaction, _button: Button):
        if self.done: return
        self.bet *= 2
        self.player_hand.append(draw_card())
        total = hand_value(self.player_hand)
        if total > 21:
            self.result_text = f"You busted with {total}. You lose {self.bet} CP."
            self.update_cp(win=False)
        else:
            await self.dealer_play(interaction)
        self.done = True
        await self.update_message(interaction)

    async def dealer_play(self, interaction: discord.Interaction):
        dealer_total = hand_value(self.dealer_hand)
        while dealer_total < 17:
            self.dealer_hand.append(draw_card())
            dealer_total = hand_value(self.dealer_hand)
        player_total = hand_value(self.player_hand)

        if dealer_total > 21 or player_total > dealer_total:
            self.result_text = f"You win! Dealer {dealer_total}, you {player_total}."
            self.update_cp(win=True)
        elif dealer_total == player_total:
            self.result_text = f"Push! Dealer {dealer_total}, you {player_total}."
        else:
            self.result_text = f"You lose. Dealer {dealer_total}, you {player_total}."
            self.update_cp(win=False)
        self.done = True
        await self.update_message(interaction)

    async def update_message(self, interaction: discord.Interaction):
        embed = discord.Embed(title="🎴 Blackjack", color=discord.Color.blue())
        embed.add_field(name="Your Hand", value=" ".join(self.player_hand) + f" ({hand_value(self.player_hand)})", inline=False)
        embed.add_field(name="Dealer Hand", value=" ".join(self.dealer_hand) + f" ({hand_value(self.dealer_hand)})", inline=False)
        embed.add_field(name="Bet", value=f"{self.bet} CP", inline=False)
        if self.result_text:
            embed.add_field(name="Result", value=self.result_text, inline=False)
        await interaction.response.edit_message(embed=embed, view=self if not self.done else None)

# -------------------------
# Commands
# -------------------------
@bot.command()
async def blackjack(ctx: commands.Context, bet: int = 10):
    if bet <= 0:
        await ctx.send("Bet must be positive!")
        return
    user_id = str(ctx.author.id)
    ensure_user_data(user_id)
    if CP_DATA[user_id]["cp"] < bet:
        await ctx.send("Not enough CP!")
        return
    player_hand = [draw_card(), draw_card()]
    dealer_hand = [draw_card(), draw_card()]
    view = BlackjackView(ctx, bet, player_hand, dealer_hand)
    embed = discord.Embed(title="🎴 Blackjack", color=discord.Color.blue())
    embed.add_field(name="Your Hand", value=" ".join(player_hand) + f" ({hand_value(player_hand)})", inline=False)
    embed.add_field(name="Dealer Hand", value=f"{dealer_hand[0]} ?", inline=False)
    embed.add_field(name="Bet", value=f"{bet} CP", inline=False)
    await ctx.send(embed=embed, view=view)

@bot.command()
async def stats(ctx: commands.Context):
    user_id = str(ctx.author.id)
    ensure_user_data(user_id)
    data = CP_DATA[user_id]
    total_games = data["wins"] + data["losses"]
    win_pct = (data["wins"]/total_games*100) if total_games > 0 else 0
    embed = discord.Embed(title=f"{ctx.author.display_name}'s Stats", color=discord.Color.green())
    embed.add_field(name="CP", value=data["cp"])
    embed.add_field(name="Total Earned CP", value=data["total_earned"])
    embed.add_field(name="Wins", value=data["wins"])
    embed.add_field(name="Losses", value=data["losses"])
    embed.add_field(name="Win %", value=f"{win_pct:.2f}%")
    await ctx.send(embed=embed)

@bot.command()
async def leaderboard(ctx: commands.Context):
    sorted_users = sorted(CP_DATA.items(), key=lambda x: x[1]["cp"], reverse=True)
    description = ""
    for i, (user_id, data) in enumerate(sorted_users[:10], start=1):
        try:
            user = await bot.fetch_user(int(user_id))
            name = user.display_name
        except (discord.NotFound, discord.HTTPException):
            name = f"User {user_id}"
        description += f"{i}. {name}: {data['cp']} CP\n"
    embed = discord.Embed(title="🏆 CP Leaderboard", description=description, color=discord.Color.gold())
    await ctx.send(embed=embed)

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user} (ID: {bot.user.id})')
    print('------')
if __name__ == "__main__":
    webserver.keep_alive()
    bot.run(token)
import discord
from discord.ext import commands
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
stats = {}
active_games = {}
START_CP = 1000

def get_user(user_id):
    if user_id not in stats:
        stats[user_id] = {"cp": START_CP, "wins": 0, "losses": 0, "earned": 0}
    return stats[user_id]

# ================== CARDS ==================
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
        self.player_id = ctx.author.id
        self.bet = bet
        self.original_bet = bet
        self.player_hands = [[draw(), draw()]]
        self.current = 0
        self.dealer = [draw(), draw()]
        self.done = False
        self.split = False
        self.first_move_done = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.player_id:
            await interaction.response.send_message(
                "❌ Only the player who started the game can use these buttons.",
                ephemeral=True
            )
            return False
        return True

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
        embed.add_field(name="Dealer", value=f"{dealer_cards} ({dealer_val})", inline=False)
        user = get_user(self.ctx.author.id)
        embed.set_footer(text=f"Bet: {self.bet} CP | Balance: {user['cp']}")
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
        net_change = 0  # do not touch CP until here

        for hand in self.player_hands:
            val = hand_value(hand)
            if val > 21:
                net_change -= self.original_bet
                user["losses"] += 1
            elif dealer_val > 21 or val > dealer_val:
                net_change += self.bet * 2
                user["wins"] += 1
                user["earned"] += self.bet * 2
            elif val < dealer_val:
                net_change -= self.original_bet
                user["losses"] += 1
            else:
                net_change += self.original_bet  # push

        user["cp"] += net_change
        self.done = True
        self.clear_items()
        embed = self.get_embed(reveal=True)
        embed.set_footer(text=f"Result: {net_change:+} CP")
        await interaction.response.edit_message(embed=embed, view=self)

    # ================== BUTTONS ==================
    @button(label="Hit", style=discord.ButtonStyle.green)
    async def hit(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.first_move_done = True
        hand = self.current_hand()
        hand.append(draw())
        if hand_value(hand) > 21:
            await self.next_hand(interaction)
        else:
            await interaction.response.edit_message(embed=self.get_embed(), view=self)

    @button(label="Stand", style=discord.ButtonStyle.gray)
    async def stand(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.first_move_done = True
        await self.next_hand(interaction)

    @button(label="Double", style=discord.ButtonStyle.blurple)
    async def double(self, interaction: discord.Interaction, button: discord.ui.Button):
        if len(self.current_hand()) != 2:
            return
        self.first_move_done = True
        self.bet *= 2
        self.current_hand().append(draw())
        await self.next_hand(interaction)

    @button(label="Split", style=discord.ButtonStyle.red)
    async def split_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        hand = self.current_hand()
        if self.split or len(hand) != 2:
            return
        if get_rank(hand[0]) != get_rank(hand[1]):
            await interaction.response.send_message("Can't split.", ephemeral=True)
            return
        self.split = True
        self.first_move_done = True
        h1 = [hand[0], draw()]
        h2 = [hand[1], draw()]
        self.player_hands = [h1, h2]
        await interaction.response.edit_message(embed=self.get_embed(), view=self)

# ================== COMMANDS ==================
@bot.command()
async def balance(ctx):
    user = get_user(ctx.author.id)
    await ctx.send(f"You have {user['cp']} CP")

@bot.command()
async def blackjack(ctx, bet: int):
    user = get_user(ctx.author.id)
    if bet <= 0 or bet > user["cp"]:
        await ctx.send("Invalid bet.")
        return
    view = GameView(ctx, bet)
    active_games[ctx.author.id] = view
    await ctx.send(embed=view.get_embed(), view=view)

@bot.command()
async def raisebet(ctx, amount: int):
    if ctx.author.id not in active_games:
        await ctx.send("No active game.")
        return
    game = active_games[ctx.author.id]
    user = get_user(ctx.author.id)
    if game.first_move_done:
        await ctx.send("You can only raise before your first move.")
        return
    if amount <= 0 or amount > user["cp"]:
        await ctx.send("Invalid raise.")
        return
    game.bet += amount
    await ctx.send(f"Raised bet by {amount} CP. New bet: {game.bet} CP")

@bot.command()
async def leaderboard(ctx):
    if not stats:
        await ctx.send("No data yet.")
        return
    sorted_users = sorted(stats.items(), key=lambda x: x[1]["cp"], reverse=True)
    embed = discord.Embed(title="🏆 Leaderboard", color=0xFFD700)
    for i, (user_id, data) in enumerate(sorted_users[:10], start=1):
        wins = data["wins"]
        losses = data["losses"]
        total = wins + losses
        winrate = (wins / total * 100) if total > 0 else 0
        user_obj = await bot.fetch_user(user_id)
        embed.add_field(
            name=f"#{i} {user_obj.name}",
            value=(
                f"💰 CP: {data['cp']}\n"
                f"🏆 Wins: {wins} | 💀 Losses: {losses}\n"
                f"📈 Earned: {data['earned']}\n"
                f"📊 Win%: {winrate:.1f}%"
            ),
            inline=False
        )
    await ctx.send(embed=embed)

# ================== EVENTS ==================
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

# ================== RUN ==================
if __name__ == "__main__":
    webserver.keep_alive()
    bot.run(token)

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
START_CP = 1000

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

# ================== GAME ==================
class GameView(View):
    def __init__(self, ctx, bet):
        super().__init__(timeout=120)
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
        if interaction.user.id != self.player_id:
            await interaction.response.send_message("❌ Not your game.", ephemeral=True)
            return False
        return True

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
        dealer_val = hand_value(self.dealer) if reveal else "?"
        embed.add_field(name="Dealer", value=f"{dealer_cards} ({dealer_val})", inline=False)

        user = get_user(self.ctx.author.id)
        embed.set_footer(text=f"Balance: {user['cp']}")
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

        for i, hand in enumerate(self.player_hands):
            val = hand_value(hand)
            bet = self.original_bet * (2 if self.doubled_hands[i] else 1)

            # Blackjack
            if is_blackjack(hand) and not is_blackjack(self.dealer):
                payout = int(bet * 1.5)
                net += payout
                user["wins"] += 1
                user["earned"] += payout
                continue

            if val > 21:
                net -= bet
                user["losses"] += 1

            elif dealer_val > 21 or val > dealer_val:
                net += bet
                user["wins"] += 1
                user["earned"] += bet

            elif val < dealer_val:
                net -= bet
                user["losses"] += 1

        user["cp"] += net
        self.done = True
        self.clear_items()

        embed = self.get_embed(reveal=True)
        embed.set_footer(text=f"Result: {net:+} CP | Balance: {user['cp']}")
        await interaction.response.edit_message(embed=embed, view=self)

    # ===== BUTTONS =====
    @button(label="Hit", style=discord.ButtonStyle.green)
    async def hit(self, interaction, _):
        self.current_hand().append(draw())
        if hand_value(self.current_hand()) > 21:
            await self.next_hand(interaction)
        else:
            await interaction.response.edit_message(embed=self.get_embed(), view=self)

    @button(label="Stand", style=discord.ButtonStyle.gray)
    async def stand(self, interaction, _):
        await self.next_hand(interaction)

    @button(label="Double", style=discord.ButtonStyle.blurple)
    async def double(self, interaction, _):
        if len(self.current_hand()) != 2:
            return

        self.current_hand().append(draw())
        self.doubled_hands[self.current] = True

        await self.next_hand(interaction)

    @button(label="Split", style=discord.ButtonStyle.red)
    async def split(self, interaction, _):
        hand = self.current_hand()
        if self.split_used or len(hand) != 2:
            return

        if get_rank(hand[0]) != get_rank(hand[1]):
            await interaction.response.send_message("Can't split.", ephemeral=True)
            return

        self.split_used = True
        self.player_hands = [
            [hand[0], draw()],
            [hand[1], draw()]
        ]
        self.doubled_hands = [False, False]

        await interaction.response.edit_message(embed=self.get_embed(), view=self)

# ================== COMMANDS ==================
@bot.command()
async def balance(ctx):
    user = get_user(ctx.author.id)
    await ctx.send(f"💰 You have {user['cp']} CP")

@bot.command()
async def blackjack(ctx, bet: int):
    user = get_user(ctx.author.id)

    if bet <= 0 or bet > user["cp"]:
        await ctx.send("Invalid bet.")
        return

    view = GameView(ctx, bet)

    player_bj = is_blackjack(view.player_hands[0])
    dealer_bj = is_blackjack(view.dealer)

    if player_bj and dealer_bj:
        await ctx.send(embed=view.get_embed(reveal=True))
        return

    elif dealer_bj:
        user["cp"] -= bet
        user["losses"] += 1
        embed = view.get_embed(reveal=True)
        embed.set_footer(text=f"Dealer Blackjack! -{bet} CP")
        await ctx.send(embed=embed)
        return

    elif player_bj:
        payout = int(bet * 1.5)
        user["cp"] += payout
        user["wins"] += 1
        user["earned"] += payout
        embed = view.get_embed(reveal=True)
        embed.set_footer(text=f"Blackjack! +{payout} CP")
        await ctx.send(embed=embed)
        return

    await ctx.send(embed=view.get_embed(), view=view)

@bot.command()
async def slots(ctx, bet: int):
    user = get_user(ctx.author.id)

    if bet <= 0 or bet > user["cp"]:
        await ctx.send("Invalid bet.")
        return

    symbols = ["🍒","🍋","🍊","⭐","💎"]
    roll = [random.choice(symbols) for _ in range(3)]

    if len(set(roll)) == 1:
        payout = bet * 3
    elif len(set(roll)) == 2:
        payout = bet * 2
    else:
        payout = -bet

    user["cp"] += payout
    await ctx.send(f"🎰 {' '.join(roll)}\nResult: {payout:+} CP")

@bot.command()
async def send(ctx, member: discord.Member, amount: int):
    sender = get_user(ctx.author.id)
    receiver = get_user(member.id)

    if member.id == ctx.author.id:
        await ctx.send("You can't send to yourself.")
        return

    if amount <= 0 or amount > sender["cp"]:
        await ctx.send("Invalid amount.")
        return

    sender["cp"] -= amount
    receiver["cp"] += amount

    await ctx.send(f"💸 Sent {amount} CP to {member.mention}")

@bot.command()
async def leaderboard(ctx):
    sorted_users = sorted(stats.items(), key=lambda x: x[1]["cp"], reverse=True)

    embed = discord.Embed(title="🏆 Leaderboard", color=0xFFD700)

    for i, (user_id, data) in enumerate(sorted_users[:10], start=1):
        user_obj = await bot.fetch_user(user_id)
        wins = data["wins"]
        losses = data["losses"]
        total = wins + losses
        winrate = (wins / total * 100) if total > 0 else 0

        embed.add_field(
            name=f"#{i} {user_obj.name}",
            value=f"💰 {data['cp']} CP | 📊 {winrate:.1f}%",
            inline=False
        )

    await ctx.send(embed=embed)

# ================== RUN ==================
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

if __name__ == "__main__":
    webserver.keep_alive()
    bot.run(token)

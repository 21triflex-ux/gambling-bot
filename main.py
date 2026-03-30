import discord
from discord.ext import commands
from dotenv import load_dotenv
import os
import random
from threading import Thread
from flask import Flask
from discord.ui import View, button

# ================== SETUP ==================
load_dotenv()
token = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix='$', intents=intents)

# ================== SETTINGS ==================
START_CP = 1000
INFINITE_USER_ID = 1051632565120933898

# ================== DATA ==================
stats = {}
active_games = {}

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
    return ''.join(c for c in card if c.isalnum())

def hand_value(hand):
    total, aces = 0, 0
    for c in hand:
        r = get_rank(c)
        if r == "A":
            total += 11
            aces += 1
        elif r in ["K", "Q", "J"]:
            total += 10
        else:
            total += int(r)
    while total > 21 and aces:
        total -= 10
        aces -= 1
    return total

def is_blackjack(hand):
    return len(hand) == 2 and hand_value(hand) == 21

# ================== WEB SERVER (for Replit/UptimeRobot) ==================
app = Flask(__name__)

@app.route('/')
def home():
    return "Blackjack Bot is alive!"

def run_webserver():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run_webserver)
    t.start()

# ================== GAME VIEW ==================
class GameView(View):
    def __init__(self, ctx, bet: int):
        super().__init__(timeout=None)
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
            await interaction.response.send_message("❌ This is not your game!", ephemeral=True)
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
                name=f"{marker}Hand {i+1} (Bet: {bet} CP)",
                value=f"{' '.join(hand)} **({hand_value(hand)})**",
                inline=False
            )

        dealer_cards = ' '.join(self.dealer) if reveal else f"{self.dealer[0]} ❓"
        dealer_val = hand_value(self.dealer) if reveal else "?"
        embed.add_field(name="🃏 Dealer", value=f"{dealer_cards} **({dealer_val})**", inline=False)

        user = get_user(self.player_id)
        balance = "∞" if self.player_id == INFINITE_USER_ID else user["cp"]
        embed.set_footer(text=f"Balance: {balance} CP")

        return embed

    async def next_hand(self, interaction):
        if self.current < len(self.player_hands) - 1:
            self.current += 1
            await interaction.response.edit_message(embed=self.get_embed(), view=self)
        else:
            await self.finish(interaction)

    async def finish(self, interaction):
        # Dealer plays
        while hand_value(self.dealer) < 17:
            self.dealer.append(draw())

        user = get_user(self.player_id)
        dealer_val = hand_value(self.dealer)
        net = 0
        infinite = self.player_id == INFINITE_USER_ID

        for i, hand in enumerate(self.player_hands):
            val = hand_value(hand)
            bet = self.original_bet * (2 if self.doubled_hands[i] else 1)

            if is_blackjack(hand) and not is_blackjack(self.dealer):
                payout = int(bet * 1.5)
                net += payout
                user["wins"] += 1
                user["earned"] += payout
            elif val > 21:
                if not infinite:
                    net -= bet
                user["losses"] += 1
            elif dealer_val > 21 or val > dealer_val:
                net += bet
                user["wins"] += 1
                user["earned"] += bet
            elif val < dealer_val:
                if not infinite:
                    net -= bet
                user["losses"] += 1
            # Push = 0

        if not infinite:
            user["cp"] += net

        self.done = True
        self.clear_items()

        embed = self.get_embed(reveal=True)
        embed.set_footer(text=f"Result: {net:+} CP | Balance: {'∞' if infinite else user['cp']} CP")
        await interaction.response.edit_message(embed=embed, view=self)

    # Buttons
    @button(label="Hit", style=discord.ButtonStyle.green)
    async def hit(self, interaction, button):
        self.current_hand().append(draw())
        if hand_value(self.current_hand()) > 21:
            await self.next_hand(interaction)
        else:
            await interaction.response.edit_message(embed=self.get_embed(), view=self)

    @button(label="Stand", style=discord.ButtonStyle.gray)
    async def stand(self, interaction, button):
        await self.next_hand(interaction)

    @button(label="Double", style=discord.ButtonStyle.blurple)
    async def double(self, interaction, button):
        hand = self.current_hand()
        if len(hand) != 2:
            await interaction.response.send_message("You can only double on your first two cards.", ephemeral=True)
            return
        self.current_hand().append(draw())
        self.doubled_hands[self.current] = True
        await self.next_hand(interaction)

    @button(label="Split", style=discord.ButtonStyle.red)
    async def split(self, interaction, button):
        hand = self.current_hand()
        if self.split_used or len(hand) != 2 or get_rank(hand[0]) != get_rank(hand[1]):
            await interaction.response.send_message("Cannot split now.", ephemeral=True)
            return

        self.split_used = True
        card1, card2 = hand[0], hand[1]
        self.player_hands = [[card1, draw()], [card2, draw()]]
        self.doubled_hands = [False, False]
        self.current = 0
        await interaction.response.edit_message(embed=self.get_embed(), view=self)

# ================== COMMANDS ==================
@bot.command()
async def balance(ctx):
    if ctx.author.id == INFINITE_USER_ID:
        await ctx.send("💰 You have **∞ CP**")
    else:
        user = get_user(ctx.author.id)
        await ctx.send(f"💰 You have **{user['cp']} CP**")

@bot.command()
async def blackjack(ctx, bet: int):
    if bet <= 0:
        await ctx.send("❌ Bet must be positive!")
        return

    user = get_user(ctx.author.id)
    if ctx.author.id != INFINITE_USER_ID and bet > user["cp"]:
        await ctx.send("❌ You don't have enough CP!")
        return

    view = GameView(ctx, bet)

    # Initial blackjack checks
    player_bj = is_blackjack(view.player_hands[0])
    dealer_bj = is_blackjack(view.dealer)

    if player_bj and dealer_bj:
        embed = view.get_embed(reveal=True)
        embed.set_footer(text="Push - Both have Blackjack")
        await ctx.send(embed=embed)
        return
    elif dealer_bj:
        if ctx.author.id != INFINITE_USER_ID:
            user["cp"] -= bet
        user["losses"] += 1
        embed = view.get_embed(reveal=True)
        embed.set_footer(text=f"Dealer Blackjack! -{bet} CP")
        await ctx.send(embed=embed)
        return
    elif player_bj:
        payout = int(bet * 1.5)
        if ctx.author.id != INFINITE_USER_ID:
            user["cp"] += payout
        user["wins"] += 1
        user["earned"] += payout
        embed = view.get_embed(reveal=True)
        embed.set_footer(text=f"🎉 Blackjack! +{payout} CP")
        await ctx.send(embed=embed)
        return

    # Normal game
    await ctx.send(embed=view.get_embed(), view=view)

# ================== RUN BOT ==================
@bot.event
async def on_ready():
    print(f"✅ {bot.user} is online!")
    keep_alive()  # Keep alive for hosting platforms

bot.run(token)

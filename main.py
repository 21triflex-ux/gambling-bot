import discord
from discord.ext import commands
from dotenv import load_dotenv
import os
import random
from threading import Thread
from flask import Flask
from discord.ui import View, button
from datetime import datetime

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
daily_data = {}

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

# ================== KEEP ALIVE ==================
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is alive! ✅"

@app.route('/ping')
def ping():
    return "pong", 200

def run_webserver():
    app.run(host='0.0.0.0', port=8080, debug=False)

def keep_alive():
    t = Thread(target=run_webserver, daemon=True)
    t.start()

# ================== BLACKJACK VIEW ==================
class GameView(View):
    def __init__(self, ctx, bet):
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
            await interaction.response.send_message("❌ Not your game.", ephemeral=True)
            return False
        return True

    def current_hand(self):
        return self.player_hands[self.current]

    def get_embed(self, reveal=False):
        embed = discord.Embed(title="🎴 Blackjack", color=0x006400)
        for i, hand in enumerate(self.player_hands):
            marker = "👉 " if i == self.current and not self.done else ""
            bet_amount = self.original_bet * (2 if self.doubled_hands[i] else 1)
            embed.add_field(
                name=f"{marker}Hand {i+1} (Bet: {bet_amount})",
                value=f"{' '.join(hand)} ({hand_value(hand)})",
                inline=False
            )
        dealer_cards = ' '.join(self.dealer) if reveal else self.dealer[0] + " ❓"
        dealer_val = hand_value(self.dealer) if reveal else "?"
        embed.add_field(name="Dealer", value=f"{dealer_cards} ({dealer_val})", inline=False)

        balance = "∞" if self.player_id == INFINITE_USER_ID else get_user(self.player_id)["cp"]
        embed.set_footer(text=f"Balance: {balance} CP")
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
                if not infinite: net -= bet
                user["losses"] += 1
            elif dealer_val > 21 or val > dealer_val:
                net += bet
                user["wins"] += 1
                user["earned"] += bet
            elif val < dealer_val:
                if not infinite: net -= bet
                user["losses"] += 1

        if not infinite:
            user["cp"] += net

        self.done = True
        self.clear_items()
        embed = self.get_embed(reveal=True)
        embed.set_footer(text=f"Result: {net:+} CP | Balance: {'∞' if infinite else user['cp']} CP")
        await interaction.response.edit_message(embed=embed, view=self)

    # Buttons
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
            await interaction.response.send_message("Can't double now.", ephemeral=True)
            return
        self.current_hand().append(draw())
        self.doubled_hands[self.current] = True
        await self.next_hand(interaction)

    @button(label="Split", style=discord.ButtonStyle.red)
    async def split(self, interaction, _):
        hand = self.current_hand()
        if self.split_used or len(hand) != 2 or get_rank(hand[0]) != get_rank(hand[1]):
            await interaction.response.send_message("Can't split now.", ephemeral=True)
            return
        self.split_used = True
        self.player_hands = [[hand[0], draw()], [hand[1], draw()]]
        self.doubled_hands = [False, False]
        self.current = 0
        await interaction.response.edit_message(embed=self.get_embed(), view=self)

# ================== COMMANDS ==================
@bot.command()
async def balance(ctx):
    if ctx.author.id == INFINITE_USER_ID:
        return await ctx.send("💰 You have **∞ CP**")
    user = get_user(ctx.author.id)
    await ctx.send(f"💰 You have **{user['cp']} CP**")


@bot.command()
async def give(ctx, member: discord.Member, amount: int):
    if ctx.author.id != INFINITE_USER_ID:
        return await ctx.send("❌ You don't have permission to use this command.")
    if amount <= 0:
        return await ctx.send("❌ Amount must be positive!")
    
    receiver = get_user(member.id)
    receiver["cp"] += amount
    await ctx.send(f"🪄 **Gave {amount} CP** to {member.mention}")


@bot.command()
async def blackjack(ctx, bet: int):
    user = get_user(ctx.author.id)
    if bet <= 0 or (ctx.author.id != INFINITE_USER_ID and bet > user["cp"]):
        return await ctx.send("❌ Invalid bet!")
    
    view = GameView(ctx, bet)
    # Initial checks
    player_bj = is_blackjack(view.player_hands[0])
    dealer_bj = is_blackjack(view.dealer)

    if player_bj and dealer_bj:
        await ctx.send(embed=view.get_embed(reveal=True))
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
        embed.set_footer(text=f"Blackjack! +{payout} CP")
        await ctx.send(embed=embed)
        return

    await ctx.send(embed=view.get_embed(), view=view)


@bot.command()
async def slots(ctx, bet: int = 50):
    user = get_user(ctx.author.id)
    if bet <= 0 or (ctx.author.id != INFINITE_USER_ID and bet > user["cp"]):
        return await ctx.send("❌ Invalid bet!")
    
    symbols = ["🍒","🍋","🍊","⭐","💎","7️⃣"]
    roll = [random.choice(symbols) for _ in range(3)]
    
    if len(set(roll)) == 1:
        payout = bet * 8
    elif len(set(roll)) == 2:
        payout = bet * 2
    else:
        payout = -bet

    if ctx.author.id != INFINITE_USER_ID:
        user["cp"] += payout

    result = "🎉 **BIG WIN!**" if payout > 0 else "😢 Lost"
    await ctx.send(f"🎰 {' '.join(roll)}\n{result} → **{payout:+} CP**")


@bot.command()
async def send(ctx, member: discord.Member, amount: int):
    if member.id == ctx.author.id:
        return await ctx.send("❌ You can't send to yourself!")
    if amount <= 0:
        return await ctx.send("❌ Amount must be positive!")

    sender = get_user(ctx.author.id)
    if ctx.author.id != INFINITE_USER_ID and sender["cp"] < amount:
        return await ctx.send("❌ Not enough CP!")

    receiver = get_user(member.id)
    if ctx.author.id != INFINITE_USER_ID:
        sender["cp"] -= amount
    receiver["cp"] += amount

    await ctx.send(f"✅ Sent **{amount} CP** to {member.mention}")


@bot.command()
async def leaderboard(ctx):
    if not stats:
        return await ctx.send("No players yet.")
    
    sorted_users = sorted(stats.items(), key=lambda x: x[1]["cp"], reverse=True)[:10]
    embed = discord.Embed(title="🏆 CP Leaderboard", color=0xFFD700)
    
    for i, (uid, data) in enumerate(sorted_users, 1):
        try:
            member = ctx.guild.get_member(uid) or await bot.fetch_user(uid)
            name = member.display_name if member else f"User {uid}"
        except:
            name = f"User {uid}"
        
        wins = data["wins"]
        losses = data["losses"]
        total = wins + losses
        winrate = (wins / total * 100) if total > 0 else 0
        
        embed.add_field(
            name=f"#{i} {name}",
            value=f"💰 **{data['cp']} CP**\n🏆 Wins: {wins} | ❌ Losses: {losses}\n📊 Win Rate: {winrate:.1f}%",
            inline=False
        )
    await ctx.send(embed=embed)


@bot.command()
async def dailybox(ctx):
    uid = ctx.author.id
    now = datetime.utcnow()
    if uid in daily_data and "box" in daily_data[uid]:
        if (now - daily_data[uid]["box"]).total_seconds() < 86400:
            return await ctx.send("⏳ You already opened your daily box today.")
    
    roll = random.randint(1, 100)
    if roll <= 60:
        reward = random.randint(100, 250)
        tier = "Common"
    elif roll <= 90:
        reward = random.randint(300, 600)
        tier = "Rare"
    else:
        reward = random.randint(800, 1500)
        tier = "ULTRA"
    
    user = get_user(uid)
    if uid != INFINITE_USER_ID:
        user["cp"] += reward
    daily_data.setdefault(uid, {})["box"] = now
    await ctx.send(f"🎁 **{tier} Box** → +{reward} CP")


@bot.command()
async def daily(ctx):
    uid = ctx.author.id
    now = datetime.utcnow()
    data = daily_data.setdefault(uid, {"streak": 0, "last": None})
    
    if data["last"]:
        diff = (now - data["last"]).total_seconds()
        if diff < 86400:
            return await ctx.send("⏳ You already claimed your daily reward today!")
        data["streak"] = data["streak"] + 1 if diff <= 172800 else 1
    else:
        data["streak"] = 1

    base = random.randint(150, 300)
    bonus = data["streak"] * 25
    total = base + bonus

    user = get_user(uid)
    if uid != INFINITE_USER_ID:
        user["cp"] += total
    data["last"] = now

    await ctx.send(f"🔥 **Daily Reward!**\nBase: {base} CP\nStreak: {data['streak']} (+{bonus} CP)\n💰 **Total: {total} CP**")


@bot.command()
async def rps(ctx, opponent: discord.Member):
    if opponent.bot or opponent == ctx.author:
        return await ctx.send("❌ Invalid opponent.")

    await ctx.send(f"📩 {ctx.author.mention} & {opponent.mention} — Check your DMs!")

    choices = {}
    def check(m):
        return m.author in [ctx.author, opponent] and isinstance(m.channel, discord.DMChannel)

    try:
        while len(choices) < 2:
            msg = await bot.wait_for("message", timeout=60, check=check)
            choice = msg.content.lower().strip()
            if choice not in ["rock", "paper", "scissors"]:
                await msg.author.send("❌ Please reply with `rock`, `paper`, or `scissors`")
                continue
            choices[msg.author.id] = choice
            await msg.author.send("✅ Choice locked!")
    except:
        return await ctx.send("⏰ Game timed out.")

    p1 = choices.get(ctx.author.id)
    p2 = choices.get(opponent.id)

    if p1 == p2:
        return await ctx.send(f"🤝 Tie! Both played **{p1}**")

    winner = ctx.author if (
        (p1 == "rock" and p2 == "scissors") or
        (p1 == "paper" and p2 == "rock") or
        (p1 == "scissors" and p2 == "paper")
    ) else opponent

    bet = 200
    winner_user = get_user(winner.id)
    loser_id = opponent.id if winner == ctx.author else ctx.author.id
    loser_user = get_user(loser_id)

    if winner.id != INFINITE_USER_ID:
        winner_user["cp"] += bet
    if loser_user["cp"] >= bet:
        loser_user["cp"] -= bet

    await ctx.send(f"🏆 **{winner.mention} wins {bet} CP!**")


# ================== EVENTS ==================
@bot.event
async def on_ready():
    print(f"✅ {bot.user} is online!")
    keep_alive()

@bot.event
async def on_message(message):
    if message.author.bot:
        return
    await bot.process_commands(message)


# ================== RUN ==================
if __name__ == "__main__":
    bot.run(token, reconnect=True)

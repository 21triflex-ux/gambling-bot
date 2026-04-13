import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv
import json
import os
import random
from threading import Thread
from flask import Flask
from discord.ui import View, button
from datetime import datetime
import asyncio
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import io

load_dotenv()
token = os.getenv("DISCORD_TOKEN")
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix='$', intents=intents)

# ================== SETTINGS ==================
START_CP = 1000
INFINITE_USER_ID = 1051632565120933898
DATA_FILE = "user_data.json"
DAILY_FILE = "daily_data.json"
MARKET_FILE = "market_data.json"
CHANNEL_ID = 123456789012345678 # ←←← CHANGE TO YOUR REAL CHANNEL ID

MAX_BET = 10000

# Global for RPS
rps_games = {}
# Global for market
market = {}
# Global data
user_data = {}
daily_data = {}
# NEW: Live chart messages (symbol → message object)
live_views = {}

# ================== DATA MANAGEMENT ==================
def load_json(file):
    if not os.path.exists(file):
        return {}
    try:
        with open(file, "r") as f:
            return json.load(f)
    except:
        return {}

def save_json(data, file):
    with open(file, "w") as f:
        json.dump(data, f, indent=4)

def load_all():
    global user_data, daily_data
    user_data = load_json(DATA_FILE)
    daily_data = load_json(DAILY_FILE)
    for uid in list(user_data.keys()):
        stats = user_data[uid]
        if not isinstance(stats.get("cp"), int):
            try:
                stats["cp"] = int(float(stats.get("cp", START_CP)))
            except:
                stats["cp"] = START_CP
        if "wins" not in stats: stats["wins"] = 0
        if "losses" not in stats: stats["losses"] = 0
        if "earned" not in stats: stats["earned"] = 0
       
        # Migrate old portfolio
        if "portfolio" not in stats or not isinstance(stats.get("portfolio"), dict):
            stats["portfolio"] = {}
        port = stats["portfolio"]
        migrated_port = {}
        for sym, val in list(port.items()):
            if not isinstance(val, list):
                migrated_port[sym] = [{"qty": int(val), "buy_price": None, "buy_time": None}]
            else:
                migrated_port[sym] = val
        stats["portfolio"] = migrated_port
        if "transactions" not in stats:
            stats["transactions"] = []

def save_all():
    save_json(user_data, DATA_FILE)
    save_json(daily_data, DAILY_FILE)

def get_user(user_id):
    uid = str(user_id)
    if uid not in user_data:
        user_data[uid] = {
            "cp": START_CP,
            "wins": 0,
            "losses": 0,
            "earned": 0,
            "portfolio": {},
            "transactions": []
        }
    return user_data[uid]

# ================== STOCK MARKET ==================
def load_market():
    global market
    if not os.path.exists(MARKET_FILE):
        market = {
            "GROK": {"name": "Grok AI", "price": 100.50, "prev_price": 100.50, "history": [100.50]},
            "XAI": {"name": "xAI Ventures", "price": 250.75, "prev_price": 250.75, "history": [250.75]},
            "DISC": {"name": "Discord Inc", "price": 78.20, "prev_price": 78.20, "history": [78.20]},
            "JACK": {"name": "Jackpot Inc", "price": 45.10, "prev_price": 45.10, "history": [45.10]},
            "THIEF": {"name": "Shadow Bank", "price": 15.90, "prev_price": 15.90, "history": [15.90]}
        }
        save_market()
        return
    try:
        with open(MARKET_FILE, "r") as f:
            market = json.load(f)
    except:
        market = {
            "GROK": {"name": "Grok AI", "price": 100.50, "prev_price": 100.50, "history": [100.50]},
            "XAI": {"name": "xAI Ventures", "price": 250.75, "prev_price": 250.75, "history": [250.75]},
            "DISC": {"name": "Discord Inc", "price": 78.20, "prev_price": 78.20, "history": [78.20]},
            "JACK": {"name": "Jackpot Inc", "price": 45.10, "prev_price": 45.10, "history": [45.10]},
            "THIEF": {"name": "Shadow Bank", "price": 15.90, "prev_price": 15.90, "history": [15.90]}
        }
        save_market()
    for data in market.values():
        if "history" not in data or not isinstance(data["history"], list):
            data["history"] = [data.get("price", 100.0)]

def save_market():
    with open(MARKET_FILE, "w") as f:
        json.dump(market, f, indent=4)

# ================== LIVE SPARKLINE HELPER ==================
def generate_sparkline(prices, length=20):
    if not prices or len(prices) < 2:
        return "▁▁▁▁▁ (no data yet)"
    recent = prices[-length:]
    min_p = min(recent)
    max_p = max(recent)
    if max_p == min_p:
        return "─" * length
    bars = "▁▂▃▄▅▆▇█"
    delta = (max_p - min_p) / (len(bars) - 1)
    spark = []
    for p in recent:
        idx = int((p - min_p) / delta)
        idx = max(0, min(len(bars)-1, idx))
        spark.append(bars[idx])
    return ''.join(spark)

def make_live_embed(symbol: str, data: dict):
    change_pct = ((data["price"] - data["prev_price"]) / data["prev_price"] * 100) if data.get("prev_price") else 0
    arrow = "📈" if change_pct >= 0 else "📉"
    color = 0x00ff00 if change_pct >= 0 else 0xff4444
    spark = generate_sparkline(data.get("history", []))
    embed = discord.Embed(
        title=f"📈 LIVE {symbol} • {data['name']}",
        description=f"**${data['price']:.2f}** {arrow} **{change_pct:+.2f}%**",
        color=color,
        timestamp=datetime.utcnow()
    )
    embed.add_field(name="Trend (last 20 updates)", value=spark, inline=False)
    embed.set_footer(text="🔴 Live • Updates every 5 minutes • $stoplive SYMBOL to stop")
    return embed

# ================== MARKET UPDATE TASK (now every 5 min) ==================
@tasks.loop(minutes=5)
async def update_market():
    for symbol, data in market.items():
        change_pct = random.uniform(-0.065, 0.065)
        data["prev_price"] = data["price"]
        data["price"] = round(data["price"] * (1 + change_pct), 2)
        data["history"].append(data["price"])
        if len(data["history"]) > 30:
            data["history"] = data["history"][-30:]
    save_market()

    # Auto-update all live views
    for sym, msg in list(live_views.items()):
        if sym not in market:
            continue
        try:
            data = market[sym]
            embed = make_live_embed(sym, data)
            await msg.edit(embed=embed)
        except discord.NotFound:
            live_views.pop(sym, None)
        except Exception:
            pass

@update_market.before_loop
async def before_market():
    await bot.wait_until_ready()

# ================== CARDS (Blackjack + RPS + Thief) ==================
SUITS = ["♠️", "♥️", "♦️", "♣️"]
RANKS = ["2","3","4","5","6","7","8","9","10","J","Q","K","A"]

def draw():
    return random.choice(RANKS) + random.choice(SUITS)

def get_rank(card):
    return ''.join(c for c in card if c.isalnum())

def hand_value(hand):
    total = aces = 0
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
            embed.add_field(name=f"{marker}Hand {i+1} (Bet: {bet_amount})",
                            value=f"{' '.join(hand)} ({hand_value(hand)})", inline=False)
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
        save_all()

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

class RPSView(View):
    def __init__(self, player, opponent, game_id, original_channel):
        super().__init__(timeout=60)
        self.player = player
        self.opponent = opponent
        self.game_id = game_id
        self.original_channel = original_channel

    async def interaction_check(self, interaction):
        return interaction.user.id == self.player.id

    async def record_choice(self, interaction, choice):
        game = rps_games.get(self.game_id)
        if not game:
            await interaction.response.send_message("Game expired.", ephemeral=True)
            return
        game["choices"][self.player.id] = choice
        self.clear_items()
        await interaction.response.edit_message(content=f"✅ You locked in **{choice.upper()}**!", view=self)
        if len(game["choices"]) == 2:
            await self.resolve_game()

    @button(label="🪨 Rock", style=discord.ButtonStyle.gray)
    async def rock(self, interaction, _):
        await self.record_choice(interaction, "rock")

    @button(label="📄 Paper", style=discord.ButtonStyle.gray)
    async def paper(self, interaction, _):
        await self.record_choice(interaction, "paper")

    @button(label="✂️ Scissors", style=discord.ButtonStyle.gray)
    async def scissors(self, interaction, _):
        await self.record_choice(interaction, "scissors")

    async def resolve_game(self):
        game = rps_games[self.game_id]
        p1, p2 = game["players"]
        c1 = game["choices"][p1.id]
        c2 = game["choices"][p2.id]
        if c1 == c2:
            result_msg = f"🤝 Tie! Both played **{c1}**"
            winner = None
        elif (c1 == "rock" and c2 == "scissors") or (c1 == "paper" and c2 == "rock") or (c1 == "scissors" and c2 == "paper"):
            winner = p1
            result_msg = f"🏆 **{p1.mention} wins 200 CP!**"
        else:
            winner = p2
            result_msg = f"🏆 **{p2.mention} wins 200 CP!**"
        await self.original_channel.send(f"**RPS Result**\n{result_msg}")
        bet = 200
        if winner:
            winner_user = get_user(winner.id)
            loser_id = p1.id if winner == p2 else p2.id
            loser_user = get_user(loser_id)
            if winner.id != INFINITE_USER_ID:
                winner_user["cp"] += bet
            if loser_user["cp"] >= bet:
                loser_user["cp"] -= bet
            save_all()
        if self.game_id in rps_games:
            del rps_games[self.game_id]

def pick_weighted_users(count=3):
    users = []
    for uid, stats in user_data.items():
        if int(uid) != INFINITE_USER_ID:
            balance = stats.get("cp", 0)
            if balance >= 5:
                users.append((uid, balance))
    if len(users) < count:
        return users[:count]
    weighted = []
    for uid, balance in users:
        weight = max(1, int(balance ** 0.5))
        weighted.extend([uid] * weight)
    selected = set()
    while len(selected) < count and weighted:
        selected.add(random.choice(weighted))
    return [(uid, user_data[uid]["cp"]) for uid in selected]

async def thief_event(channel):
    try:
        if not user_data:
            return await channel.send("🕵️ No players yet...")
        targets = pick_weighted_users(3)
        if not targets:
            return await channel.send("🕵️ The thief found no worthy targets tonight... (need players with ≥5 CP)")
        results = []
        thief_name = random.choice(["Shadow", "The Bandit", "Night Fox", "Void Walker", "Phantom"])
        total_stolen = 0
        for uid, balance in targets:
            steal_percent = random.uniform(0.06, 0.18)
            stolen = max(15, int(balance * steal_percent))
            stolen = min(stolen, balance)
            user_data[uid]["cp"] -= stolen
            total_stolen += stolen
            results.append((uid, stolen))
        save_all()
        msg = f"**🕵️ {thief_name} has struck in the night!**\n\n"
        for uid, stolen in results:
            msg += f"<@{uid}> lost **{stolen} CP**\n"
        msg += f"\n**Total Stolen:** {total_stolen} CP"
        await channel.send(msg)
    except Exception as e:
        error_msg = f"🕵️ **Thief event failed**: {type(e).__name__} → {e}"
        print(error_msg)
        await channel.send(error_msg)

@tasks.loop(hours=24)
async def run_thief():
    channel = bot.get_channel(CHANNEL_ID)
    if channel:
        await thief_event(channel)

@run_thief.before_loop
async def before_thief():
    await bot.wait_until_ready()

# ================== KEEP ALIVE ==================
app = Flask(__name__)
@app.route('/')
def home():
    return "Bot is alive! ✅"
@app.route('/ping')
def ping():
    return "pong", 200
def keep_alive():
    Thread(target=lambda: app.run(host='0.0.0.0', port=8080, debug=False), daemon=True).start()

# ================== HELPER FUNCTIONS ==================
def apply_diminishing_returns(balance, winnings):
    if balance > 1_000_000:
        return int(winnings * 0.4)
    elif balance > 500_000:
        return int(winnings * 0.5)
    elif balance > 100_000:
        return int(winnings * 0.7)
    return winnings

def get_roulette_color(number: int) -> str:
    if number == 0:
        return "green"
    reds = [1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36]
    return "red" if number in reds else "black"

# ================== COMMANDS ==================
@bot.command()
async def balance(ctx):
    if ctx.author.id == INFINITE_USER_ID:
        return await ctx.send("💰 You have **∞ CP**")
    user = get_user(ctx.author.id)
    await ctx.send(f"💰 You have **{user['cp']} CP**")

@bot.command()
async def bal(ctx):
    await balance(ctx)

@bot.command()
async def give(ctx, member: discord.Member, amount: int):
    if ctx.author.id != INFINITE_USER_ID:
        return await ctx.send("❌ You don't have permission to use this command.")
    if amount <= 0:
        return await ctx.send("❌ Amount must be positive!")
    receiver = get_user(member.id)
    receiver["cp"] += amount
    await ctx.send(f"🪄 Gave **{amount} CP** to {member.mention}")
    save_all()

@bot.command()
async def blackjack(ctx, bet: int):
    user = get_user(ctx.author.id)
    if bet <= 0 or (ctx.author.id != INFINITE_USER_ID and bet > user["cp"]):
        return await ctx.send("❌ Invalid bet!")
    view = GameView(ctx, bet)
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
        save_all()
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
        save_all()
        return
    await ctx.send(embed=view.get_embed(), view=view)

# ================== SLOTS ==================
@bot.command()
async def slots(ctx, bet: int):
    user_id = ctx.author.id
    user = get_user(user_id)
    if ctx.author.id == INFINITE_USER_ID:
        balance = float('inf')
    else:
        balance = user["cp"]
    if bet <= 0:
        await ctx.send("Bet must be positive.")
        return
    if bet > MAX_BET:
        await ctx.send(f"Max bet is {MAX_BET} CP")
        return
    if ctx.author.id != INFINITE_USER_ID and balance < bet:
        await ctx.send("Not enough CP!")
        return
    if ctx.author.id != INFINITE_USER_ID:
        user["cp"] -= bet
    symbols = ["🍒", "🍋", "🍊", "💎", "7️⃣"]
    final = [random.choice(symbols) for _ in range(3)]
    msg = await ctx.send("🎰 Spinning the reels...")
    for i in range(5):
        if i == 4:
            spin = final[:]
        else:
            spin = [random.choice(symbols) for _ in range(3)]
        await msg.edit(content=f"🎰 {' | '.join(spin)}")
        await asyncio.sleep(0.20 + i * 0.08)
    win = False
    multiplier = 0
    if final[0] == final[1] == final[2]:
        multiplier = 6
        win = True
    elif final[0] == final[1] or final[1] == final[2]:
        multiplier = 3
        win = True

    if win:
        winnings = bet * multiplier
        winnings = apply_diminishing_returns(balance, winnings)
        tax = int(winnings * 0.05)
        winnings_after_tax = winnings - tax
        if ctx.author.id != INFINITE_USER_ID:
            user["cp"] += winnings_after_tax
            user["wins"] += 1
            user["earned"] += winnings_after_tax
        result_text = (
            f"🎰 {' | '.join(final)}\n\n"
            f"🎉 **WIN!** Multiplier: `x{multiplier}`\n"
            f"Bet: `{bet}` CP\n"
            f"Win before tax: `{winnings}` CP\n"
            f"Tax (5%): `{tax}` CP\n"
            f"**You gained: `{winnings_after_tax}` CP**"
        )
    else:
        if ctx.author.id != INFINITE_USER_ID:
            user["losses"] += 1
        result_text = (
            f"🎰 {' | '.join(final)}\n\n"
            f"💀 **You lost `{bet}` CP**"
        )
    await msg.edit(content=result_text)
    save_all()

# ================== ROULETTE ==================
@bot.command()
async def roulette(ctx, bet: int, choice: str):
    user_id = ctx.author.id
    user = get_user(user_id)
    if ctx.author.id == INFINITE_USER_ID:
        balance = float('inf')
    else:
        balance = user["cp"]
    if bet <= 0:
        await ctx.send("Bet must be positive.")
        return
    if bet > MAX_BET:
        await ctx.send(f"Max bet is {MAX_BET} CP")
        return
    if ctx.author.id != INFINITE_USER_ID and balance < bet:
        await ctx.send("Not enough CP!")
        return
    choice = choice.lower().strip()
    if choice in ["red", "black", "even", "odd"]:
        bet_type = choice
        chosen_number = None
    else:
        try:
            num = int(choice)
            if 0 <= num <= 36:
                bet_type = "number"
                chosen_number = num
            else:
                raise ValueError
        except:
            return await ctx.send("❌ Invalid choice! Use: `red`, `black`, `even`, `odd`, or a number `0-36`")
    if ctx.author.id != INFINITE_USER_ID:
        user["cp"] -= bet
    winning_number = random.randint(0, 36)
    winning_color = "green" if winning_number == 0 else "red" if winning_number in [1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36] else "black"
    msg = await ctx.send("🎡 Spinning the roulette wheel...")
    for i in range(6):
        if i == 5:
            spin_num = winning_number
        else:
            spin_num = random.randint(0, 36)
        color_emoji = "🟢" if spin_num == 0 else "🔴" if get_roulette_color(spin_num) == "red" else "⚫"
        await msg.edit(content=f"🎡 {spin_num} {color_emoji}")
        await asyncio.sleep(0.18 + i * 0.09)
    win = False
    if bet_type == "number":
        win = (winning_number == chosen_number)
        multiplier = 36
    else:
        if bet_type == "red":
            win = (winning_color == "red")
        elif bet_type == "black":
            win = (winning_color == "black")
        elif bet_type == "even":
            win = (winning_number != 0 and winning_number % 2 == 0)
        elif bet_type == "odd":
            win = (winning_number != 0 and winning_number % 2 == 1)
        multiplier = 2
    color_emoji_final = "🟢" if winning_number == 0 else "🔴" if winning_color == "red" else "⚫"
    if win:
        winnings = bet * multiplier
        winnings = apply_diminishing_returns(balance, winnings)
        tax = int(winnings * 0.05)
        winnings_after_tax = winnings - tax
        if ctx.author.id != INFINITE_USER_ID:
            user["cp"] += winnings_after_tax
            user["wins"] += 1
            user["earned"] += winnings_after_tax
        result_text = (
            f"🎡 **{winning_number}** {color_emoji_final}\n\n"
            f"🎉 **WIN!** You bet on `{choice.upper()}`\n"
            f"Multiplier: `x{multiplier}`\n"
            f"Bet: `{bet}` CP\n"
            f"Win before tax: `{winnings}` CP\n"
            f"Tax (5%): `{tax}` CP\n"
            f"**You gained: `{winnings_after_tax}` CP**"
        )
    else:
        if ctx.author.id != INFINITE_USER_ID:
            user["losses"] += 1
        result_text = (
            f"🎡 **{winning_number}** {color_emoji_final}\n\n"
            f"💀 **You lost `{bet}` CP**\n"
            f"You bet on `{choice.upper()}`"
        )
    await msg.edit(content=result_text)
    save_all()

# ================== STATS ==================
@bot.command()
async def stats(ctx):
    user = get_user(ctx.author.id)
    wins = user.get("wins", 0)
    losses = user.get("losses", 0)
    total_games = wins + losses
    winrate = (wins / total_games * 100) if total_games > 0 else 0.0
    earned = user.get("earned", 0)
    if ctx.author.id == INFINITE_USER_ID:
        cp_display = "∞"
    else:
        cp_display = user["cp"]
    embed = discord.Embed(title=f"📊 {ctx.author.display_name}'s Stats", color=0x00ff00)
    embed.add_field(name="💰 Balance", value=f"**{cp_display} CP**", inline=False)
    embed.add_field(name="🎮 Games Played", value=f"`{total_games}`", inline=True)
    embed.add_field(name="🏆 Wins", value=f"`{wins}`", inline=True)
    embed.add_field(name="💀 Losses", value=f"`{losses}`", inline=True)
    embed.add_field(name="📈 Win Rate", value=f"`{winrate:.1f}%`", inline=True)
    embed.add_field(name="💵 Total Earned", value=f"`{earned} CP`", inline=False)
    embed.set_footer(text="Stats from Blackjack, Slots & Roulette")
    await ctx.send(embed=embed)

# ================== STOCK COMMANDS ==================
@bot.command()
async def buy(ctx, symbol: str, quantity: int):
    symbol = symbol.upper()
    if symbol not in market:
        return await ctx.send("❌ Invalid stock symbol!")
    if quantity <= 0:
        return await ctx.send("❌ Quantity must be positive!")
    user = get_user(ctx.author.id)
    price = market[symbol]["price"]
    cost = price * quantity
    if ctx.author.id != INFINITE_USER_ID and user["cp"] < cost:
        return await ctx.send(f"❌ Not enough CP! Need ${cost:.2f}")
    port = user.setdefault("portfolio", {})
    if symbol not in port:
        port[symbol] = []
    port[symbol].append({
        "qty": quantity,
        "buy_price": price,
        "buy_time": datetime.utcnow().isoformat()
    })
    user.setdefault("transactions", []).append({
        "symbol": symbol,
        "action": "buy",
        "qty": quantity,
        "price": price,
        "time": datetime.utcnow().isoformat(),
        "total": cost
    })
    if ctx.author.id != INFINITE_USER_ID:
        user["cp"] -= cost
    await ctx.send(f"✅ Bought **{quantity} {symbol}** for **${cost:.2f}** (joined at {datetime.utcnow().strftime('%H:%M')})")
    save_all()

@bot.command()
async def sell(ctx, symbol: str, quantity: int):
    symbol = symbol.upper()
    if symbol not in market:
        return await ctx.send("❌ Invalid stock symbol!")
    if quantity <= 0:
        return await ctx.send("❌ Quantity must be positive!")
    user = get_user(ctx.author.id)
    port = user.get("portfolio", {})
    if symbol not in port or not port[symbol]:
        return await ctx.send("❌ You don't own any shares of this stock!")
    total_owned = sum(lot["qty"] for lot in port[symbol])
    if total_owned < quantity:
        return await ctx.send(f"❌ You only own {total_owned} shares!")
    price = market[symbol]["price"]
    proceeds = 0.0
    remaining = quantity
    i = 0
    while remaining > 0 and i < len(port[symbol]):
        lot = port[symbol][i]
        sell_qty = min(remaining, lot["qty"])
        proceeds += sell_qty * price
        lot["qty"] -= sell_qty
        if lot["qty"] <= 0:
            del port[symbol][i]
        else:
            i += 1
        remaining -= sell_qty
    if not port[symbol]:
        del port[symbol]
    user.setdefault("transactions", []).append({
        "symbol": symbol,
        "action": "sell",
        "qty": quantity,
        "price": price,
        "time": datetime.utcnow().isoformat(),
        "total": proceeds
    })
    if ctx.author.id != INFINITE_USER_ID:
        user["cp"] += proceeds
    await ctx.send(f"✅ Sold **{quantity} {symbol}** for **${proceeds:.2f}** (sold at {datetime.utcnow().strftime('%H:%M')})")
    save_all()

@bot.command(aliases=["port", "holdings"])
async def portfolio(ctx):
    user = get_user(ctx.author.id)
    port = user.get("portfolio", {})
    if not port:
        return await ctx.send("📉 You don't own any stocks yet. Use `$market` to see prices!")
    embed = discord.Embed(title=f"📊 {ctx.author.display_name}'s Portfolio", color=0x00ff00)
    total_value = 0.0
    for symbol, lots in port.items():
        if symbol not in market:
            continue
        current_price = market[symbol]["price"]
        total_qty = sum(l["qty"] for l in lots)
        stock_value = total_qty * current_price
        total_value += stock_value
        lots_text = ""
        for lot in lots:
            if lot.get("buy_time"):
                buy_dt = datetime.fromisoformat(lot["buy_time"])
                buy_str = buy_dt.strftime("%Y-%m-%d %H:%M")
            else:
                buy_str = "Unknown"
            bp = f"${lot['buy_price']:.2f}" if lot.get("buy_price") is not None else "N/A"
            lots_text += f"• {lot['qty']} @ {bp} (joined {buy_str})\n"
        embed.add_field(
            name=f"{symbol} • {total_qty} shares (${stock_value:.2f})",
            value=lots_text.strip() or "No lots",
            inline=False
        )
    embed.set_footer(text=f"Total Portfolio Value: ${total_value:.2f} CP")
    transactions = user.get("transactions", [])[-5:]
    if transactions:
        trans_text = ""
        for t in reversed(transactions):
            ttime = datetime.fromisoformat(t["time"]).strftime("%m-%d %H:%M")
            emoji = "🟢" if t["action"] == "buy" else "🔴"
            trans_text += f"{emoji} {ttime} | {t['action'].upper()} {t['qty']} {t['symbol']} @ ${t['price']:.2f} = ${t['total']:.2f}\n"
        embed.add_field(name="📜 Recent Stock Transactions", value=trans_text.strip(), inline=False)
    await ctx.send(embed=embed)

@bot.command(aliases=["charts", "graph"])
async def chart(ctx, symbol: str):
    symbol = symbol.upper()
    if symbol not in market:
        return await ctx.send("❌ Invalid stock symbol! Use `$market` to see available ones.")
    data = market[symbol]
    prices = data.get("history", [])
    if len(prices) < 2:
        return await ctx.send("📉 Not enough price history yet. Wait for a few market updates.")
    candles = []
    for i in range(1, len(prices)):
        o = prices[i-1]
        c = prices[i]
        avg_price = (o + c) / 2
        wick_range = avg_price * random.uniform(0.018, 0.085)
        high = max(o, c) + wick_range * random.uniform(0.6, 1.4)
        low = min(o, c) - wick_range * random.uniform(0.6, 1.4)
        high = max(high, max(o, c) + 0.01)
        low = min(low, min(o, c) - 0.01)
        candles.append({
            "open": o, 
            "high": round(high, 2), 
            "low": round(low, 2), 
            "close": c
        })
    fig, ax = plt.subplots(figsize=(12, 6))
    width = 0.6
    for idx, candle in enumerate(candles):
        color = '#00ff88' if candle["close"] >= candle["open"] else '#ff4444'
        body_bottom = min(candle["open"], candle["close"])
        body_height = abs(candle["close"] - candle["open"])
        ax.add_patch(Rectangle(
            (idx - width / 2, body_bottom),
            width,
            body_height,
            facecolor=color,
            edgecolor="black",
            linewidth=1
        ))
        ax.plot([idx, idx], [candle["low"], candle["high"]], color="black", linewidth=1.5)
    ax.set_title(f"📈 {symbol} • {data['name']} Candlestick Chart (Last {len(candles)} updates)")
    ax.set_xlabel("Updates (every 5 minutes)")
    ax.set_ylabel("Price (CP)")
    ax.grid(True, alpha=0.3)
    step = max(1, len(candles) // 6)
    ax.set_xticks(range(0, len(candles), step))
    ax.set_xticklabels([str(i) for i in range(0, len(candles), step)])
    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight', dpi=150)
    buf.seek(0)
    plt.close()
    file = discord.File(buf, filename=f"{symbol}_candlestick.png")
    await ctx.send(f"**{symbol} Candlestick Chart**", file=file)

# ================== NEW LIVE CHART COMMANDS ==================
@bot.command(aliases=["live"])
async def livechart(ctx, symbol: str):
    symbol = symbol.upper()
    if symbol not in market:
        return await ctx.send("❌ Invalid stock symbol! Use `$market` to see available ones.")
    if symbol in live_views:
        return await ctx.send("❌ A live chart for this stock is already running.")
    
    data = market[symbol]
    embed = make_live_embed(symbol, data)
    msg = await ctx.send(embed=embed)
    live_views[symbol] = msg
    await ctx.send(f"✅ **Live chart started for {symbol}!** It will update automatically every 5 minutes.")

@bot.command()
async def stoplive(ctx, symbol: str = None):
    if not symbol:
        return await ctx.send("❌ Please specify a symbol: `$stoplive SYMBOL`")
    symbol = symbol.upper()
    if symbol in live_views:
        try:
            await live_views[symbol].delete()
        except:
            pass
        live_views.pop(symbol, None)
        await ctx.send(f"✅ Stopped live chart for **{symbol}**.")
    else:
        await ctx.send(f"❌ No active live chart for **{symbol}**.")

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
    save_all()

@bot.command()
async def leaderboard(ctx):
    if not user_data:
        return await ctx.send("No players yet.")
    sorted_users = sorted(user_data.items(), key=lambda x: x[1]["cp"], reverse=True)[:10]
    embed = discord.Embed(title="🏆 CP Leaderboard", color=0xFFD700)
    for i, (uid, data) in enumerate(sorted_users, 1):
        try:
            member = ctx.guild.get_member(int(uid)) or await bot.fetch_user(int(uid))
            name = member.display_name if member else f"User {uid}"
        except:
            name = f"User {uid}"
        wins = data["wins"]
        losses = data["losses"]
        total = wins + losses
        winrate = (wins / total * 100) if total > 0 else 0
        embed.add_field(name=f"#{i} {name}",
                        value=f"💰 **{data['cp']} CP**\n🏆 Wins: {wins} | ❌ Losses: {losses}\n📊 Win Rate: {winrate:.1f}%",
                        inline=False)
    await ctx.send(embed=embed)

@bot.command()
async def dailybox(ctx):
    uid = str(ctx.author.id)
    now = datetime.utcnow()
    user_daily = daily_data.setdefault(uid, {})
    if "box" in user_daily:
        last = datetime.fromisoformat(user_daily["box"])
        if (now - last).total_seconds() < 86400:
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
    user = get_user(ctx.author.id)
    if ctx.author.id != INFINITE_USER_ID:
        user["cp"] += reward
    user_daily["box"] = now.isoformat()
    await ctx.send(f"🎁 **{tier} Box** → +{reward} CP")
    save_all()

@bot.command()
async def daily(ctx):
    uid = str(ctx.author.id)
    now = datetime.utcnow()
    data = daily_data.setdefault(uid, {"streak": 0, "last": None})
    if data["last"]:
        last = datetime.fromisoformat(data["last"])
        diff = (now - last).total_seconds()
        if diff < 86400:
            return await ctx.send("⏳ You already claimed your daily reward today!")
        data["streak"] = data["streak"] + 1 if diff <= 172800 else 1
    else:
        data["streak"] = 1
    base = random.randint(150, 300)
    bonus = data["streak"] * 25
    total = base + bonus
    user = get_user(ctx.author.id)
    if ctx.author.id != INFINITE_USER_ID:
        user["cp"] += total
    data["last"] = now.isoformat()
    await ctx.send(f"🔥 **Daily Reward!**\nBase: {base} CP\nStreak: {data['streak']} (+{bonus} CP)\n💰 **Total: {total} CP**")
    save_all()

@bot.command()
async def rps(ctx, opponent: discord.Member):
    if opponent.bot or opponent == ctx.author:
        return await ctx.send("❌ Invalid opponent.")
    game_id = tuple(sorted([ctx.author.id, opponent.id]))
    if game_id in rps_games:
        return await ctx.send("❌ A game between you two is already running.")
    rps_games[game_id] = {"choices": {}, "players": [ctx.author, opponent], "channel": ctx.channel}
    await ctx.send(f"📩 {ctx.author.mention} & {opponent.mention} — Check your **DMs** for interactive Rock Paper Scissors buttons!")
    for player in [ctx.author, opponent]:
        view = RPSView(player, opponent, game_id, ctx.channel)
        try:
            await player.send("**🪨 Rock Paper Scissors!**\nChoose your move below:", view=view)
        except discord.Forbidden:
            await ctx.send(f"❌ Could not DM {player.mention} (they have DMs disabled).")
            if game_id in rps_games:
                del rps_games[game_id]
            return

@bot.command()
async def thiefdebug(ctx):
    if ctx.author.id != INFINITE_USER_ID:
        return await ctx.send("❌ Owner only.")
    await ctx.send(f"**Thief Debug**\nPlayers in data: {len(user_data)}")

@bot.command(aliases=["stocks"])
async def market(ctx):
    if not market:
        await ctx.send("📉 Market data not loaded yet.")
        return
    embed = discord.Embed(title="📈 Live Stock Market", color=0x00ff00, timestamp=ctx.message.created_at)
    for symbol, data in market.items():
        change = ((data["price"] - data["prev_price"]) / data["prev_price"] * 100) if data["prev_price"] else 0
        arrow = "📈" if change >= 0 else "📉"
        embed.add_field(
            name=f"{symbol} • {data['name']}",
            value=f"**${data['price']:.2f}** {arrow} **{change:+.1f}%**",
            inline=False
        )
    embed.set_footer(text="Prices update every 5 minutes • $buy / $sell / $portfolio / $chart / $livechart")
    await ctx.send(embed=embed)

# ================== EVENTS ==================
@bot.event
async def on_ready():
    load_all()
    load_market()
    print(f"✅ {bot.user} is online! Live stock charts enabled.")
    keep_alive()
    run_thief.start()
    update_market.start()
 
    async def autosave():
        while True:
            await asyncio.sleep(300)
            save_all()
    bot.loop.create_task(autosave())

@bot.event
async def on_message(message):
    if message.author.bot:
        return
    await bot.process_commands(message)

# ================== RUN ==================
if __name__ == "__main__":
    bot.run(token, reconnect=True)

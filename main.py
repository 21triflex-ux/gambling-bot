import discord
from discord.ext import commands
from discord.ui import View, Button
import random
import json
import os
import logging

# If you're using a keep-alive webserver (Replit, Render, etc.)
# import webserver

logging.basicConfig(level=logging.INFO)

token = os.getenv("DISCORD_TOKEN")
if not token:
    raise ValueError("DISCORD_TOKEN not set!")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="$", intents=intents)

CP_FILE = "cp_data.json"

# ─── Data ────────────────────────────────────────────
CP_DATA: dict = {}

if os.path.exists(CP_FILE):
    try:
        with open(CP_FILE, encoding="utf-8") as file:
            CP_DATA = json.load(file)
    except json.JSONDecodeError as exc:
        print(f"Invalid JSON in {CP_FILE}: {exc}")
    except OSError as exc:
        print(f"Failed to read {CP_FILE}: {exc}")

def save_data() -> None:
    try:
        with open(CP_FILE, "w", encoding="utf-8") as file:
            json.dump(CP_DATA, file, indent=4)
    except OSError as exc:
        print(f"Failed to save {CP_FILE}: {exc}")

def ensure_user(user_id: str) -> dict:
    if user_id not in CP_DATA:
        CP_DATA[user_id] = {"cp": 1000, "wins": 0, "losses": 0, "pushes": 0}
    return CP_DATA[user_id]

# ─── Cards ───────────────────────────────────────────
SUITS = ["♠️", "♥️", "♦️", "♣️"]
RANKS = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]
VALUES = {r: min(10, i) if i <= 10 else 10 if r in "JQK" else 11
          for i, r in enumerate(RANKS, 2)}

def draw_card() -> str:
    return random.choice(RANKS) + random.choice(SUITS)

def hand_value(hand: list[str]) -> int:
    total = sum(VALUES[card[:-1]] for card in hand)
    aces = sum(1 for card in hand if card.startswith("A"))
    while total > 21 and aces:
        total -= 10
        aces -= 1
    return total

# ─── Game View ───────────────────────────────────────
class BlackjackView(View):
    def __init__(self, interaction: discord.Interaction, bet: int,
                 player_hand: list[str], dealer_hand: list[str]):
        super().__init__(timeout=180)
        self.interaction = interaction
        self.bet = bet
        self.player_hand = player_hand
        self.dealer_hand = dealer_hand
        self.original_user = interaction.user
        self.finished = False
        self.result: str = ""   # initialized here

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user == self.original_user

    def get_embed(self, reveal_dealer: bool = False) -> discord.Embed:
        embed = discord.Embed(title="🎴 Blackjack", colour=0x006400)

        p_total = hand_value(self.player_hand)
        d_total = hand_value(self.dealer_hand) if reveal_dealer else "?"

        embed.add_field(
            name="🧑 You",
            value=f"{'  '.join(self.player_hand)}\n**Total: {p_total}**",
            inline=False
        )
        embed.add_field(
            name="🤖 Dealer",
            value=f"{'  '.join(self.dealer_hand) if reveal_dealer else self.dealer_hand[0] + '  ❓'}\n**Total: {d_total}**",
            inline=False
        )
        embed.add_field(name="💰 Bet", value=f"{self.bet} CP", inline=True)

        if self.finished:
            colour = 0xFFD700 if "win" in self.result.lower() else 0x8B0000
            embed.colour = colour
            embed.set_footer(text=self.result)

        return embed

    async def end_game(self, result: str, win: bool | None = None) -> None:
        self.finished = True
        self.result = result

        user = ensure_user(str(self.original_user.id))

        if win is True:
            user["cp"] += self.bet
            user["wins"] += 1
        elif win is False:
            user["cp"] -= self.bet
            user["losses"] += 1
        else:  # push / tie
            user["pushes"] = user.get("pushes", 0) + 1

        save_data()

        try:
            await self.interaction.message.edit(
                embed=self.get_embed(reveal_dealer=True),
                view=None
            )
        except discord.HTTPException:
            pass

    async def update(self, interaction: discord.Interaction) -> None:
        if self.finished:
            return
        try:
            await interaction.response.defer()
            await interaction.message.edit(embed=self.get_embed(), view=self)
        except discord.HTTPException:
            pass

    # ─── Buttons ─────────────────────────────────────
    @discord.ui.button(label="Hit", style=discord.ButtonStyle.green)
    async def hit(self, interaction: discord.Interaction, _button: Button) -> None:
        if self.finished:
            return

        self.player_hand.append(draw_card())
        if hand_value(self.player_hand) > 21:
            await self.end_game("Bust! You lose.", win=False)
        else:
            await self.update(interaction)

    @discord.ui.button(label="Stand", style=discord.ButtonStyle.gray)
    async def stand(self, interaction: discord.Interaction, _button: Button) -> None:
        if self.finished:
            return

        while hand_value(self.dealer_hand) < 17:
            self.dealer_hand.append(draw_card())

        p = hand_value(self.player_hand)
        d = hand_value(self.dealer_hand)

        if d > 21:
            await self.end_game("Dealer busts! You win!", win=True)
        elif p > d:
            await self.end_game("You win!", win=True)
        elif p < d:
            await self.end_game("Dealer wins.", win=False)
        else:
            await self.end_game("Push!", win=None)

    @discord.ui.button(label="Double", style=discord.ButtonStyle.blurple)
    async def double(self, interaction: discord.Interaction, _button: Button) -> None:
        if self.finished:
            return

        user = ensure_user(str(self.original_user.id))
        additional = self.bet
        if user["cp"] < additional:
            await interaction.response.send_message("Not enough CP to double!", ephemeral=True)
            return

        self.bet += additional
        user["cp"] -= additional
        save_data()

        self.player_hand.append(draw_card())
        p_val = hand_value(self.player_hand)

        if p_val > 21:
            await self.end_game("Bust on double! You lose.", win=False)
            return

        while hand_value(self.dealer_hand) < 17:
            self.dealer_hand.append(draw_card())

        d_val = hand_value(self.dealer_hand)

        if d_val > 21 or p_val > d_val:
            await self.end_game("Double down win!", win=True)
        elif p_val < d_val:
            await self.end_game("Double down - dealer wins.", win=False)
        else:
            await self.end_game("Push on double!", win=None)

# ─── Bet Selection ───────────────────────────────────
class BetView(View):
    def __init__(self, interaction: discord.Interaction):
        super().__init__(timeout=60)
        self.original_user = interaction.user

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user == self.original_user

    @staticmethod
    async def start_blackjack(interaction: discord.Interaction, bet_amount: int) -> None:
        user = ensure_user(str(interaction.user.id))
        if user["cp"] < bet_amount:
            await interaction.response.send_message("Not enough CP!", ephemeral=True)
            return

        user["cp"] -= bet_amount
        save_data()

        player = [draw_card(), draw_card()]
        dealer = [draw_card(), draw_card()]

        view = BlackjackView(interaction, bet_amount, player, dealer)
        embed = view.get_embed(reveal_dealer=False)

        await interaction.response.edit_message(embed=embed, view=view)

    @discord.ui.button(label="10 CP", style=discord.ButtonStyle.gray)
    async def bet10(self, interaction: discord.Interaction, _button: Button) -> None:
        await self.start_blackjack(interaction, 10)

    @discord.ui.button(label="50 CP", style=discord.ButtonStyle.gray)
    async def bet50(self, interaction: discord.Interaction, _button: Button) -> None:
        await self.start_blackjack(interaction, 50)

    @discord.ui.button(label="100 CP", style=discord.ButtonStyle.green)
    async def bet100(self, interaction: discord.Interaction, _button: Button) -> None:
        await self.start_blackjack(interaction, 100)

# ─── Commands ────────────────────────────────────────
@bot.command()
async def blackjack(ctx: commands.Context) -> None:
    embed = discord.Embed(
        title="Blackjack",
        description="Choose your bet:",
        colour=0x006400
    )
    view = BetView(ctx.interaction if hasattr(ctx, "interaction") else None)  # safe fallback
    await ctx.send(embed=embed, view=view)

@bot.command()
async def stats(ctx: commands.Context) -> None:
    user = ensure_user(str(ctx.author.id))
    embed = discord.Embed(title=f"Stats — {ctx.author}", colour=0x00AA00)
    embed.add_field(name="CP",     value=user["cp"],     inline=True)
    embed.add_field(name="Wins",   value=user["wins"],   inline=True)
    embed.add_field(name="Losses", value=user["losses"], inline=True)
    embed.add_field(name="Pushes", value=user.get("pushes", 0), inline=True)
    await ctx.send(embed=embed)

@bot.event
async def on_ready() -> None:
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    print("Blackjack bot is ready!")

# ─── Start ───────────────────────────────────────────
if __name__ == "__main__":
    # webserver.keep_alive()   # uncomment if needed
    bot.run(token)

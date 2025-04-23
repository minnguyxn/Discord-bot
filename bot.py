import discord
from discord.ext import commands
from discord import app_commands, ui, Interaction
import json
import os
import random

TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = os.getenv("GUILD_ID")

intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

EVENT_FILE = 'lucky_event.json'
ROLE_PREFIX = "V"
MAX_ROLE_LEVEL = 10

def load_event():
    if not os.path.exists(EVENT_FILE):
        return None
    with open(EVENT_FILE, 'r') as f:
        return json.load(f)

def save_event(data):
    with open(EVENT_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def get_draws_from_roles(member):
    max_draws = 0
    for role in member.roles:
        if role.name.upper().startswith(ROLE_PREFIX):
            try:
                level = int(role.name.upper().replace(ROLE_PREFIX, ""))
                if 1 <= level <= MAX_ROLE_LEVEL:
                    max_draws = max(max_draws, level)
            except:
                continue
    return max_draws

class DrawView(ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=None)
        self.user_id = user_id

    @ui.button(label="🎲 Draw Ticket", style=discord.ButtonStyle.green)
    async def draw(self, interaction: Interaction, button: ui.Button):
        event = load_event()
        uid = str(interaction.user.id)

        if uid not in event["participants"]:
            await interaction.response.send_message("❌ You are not registered!", ephemeral=False)
            return

        p = event["participants"][uid]
        if p["draws_left"] <= 0:
            await interaction.response.send_message("⚠️ No more draws left!", ephemeral=False)
            return

        if not event["tickets"]:
            await interaction.response.send_message("❌ No more tickets!", ephemeral=False)
            return

        ticket = random.choice(event["tickets"])
        event["tickets"].remove(ticket)
        p["tickets"].append(ticket)
        p["draws_left"] -= 1

        prize = event["prizes"].get(str(ticket), None)
        save_event(event)

        if prize:
            result = f"🎉 {interaction.user.mention} drew ticket **{ticket}** and won **{prize}**!"
        else:
            result = f"{interaction.user.mention} drew ticket **{ticket}** — no prize 😢"

        await interaction.channel.send(result)

@bot.event
async def on_ready():
    print(f"Bot is online: {bot.user}")
    try:
        synced = await bot.tree.sync(guild=discord.Object(id=int(GUILD_ID)))
        print(f"Synced {len(synced)} commands.")
    except Exception as e:
        print("Sync error:", e)

@bot.tree.command(name="create_event", description="Create a lucky draw event", guild=discord.Object(id=int(GUILD_ID)))
@app_commands.describe(event_name="Event name", total_tickets="Number of tickets")
async def create_event(interaction: Interaction, event_name: str, total_tickets: int):
    tickets = list(range(1, total_tickets + 1))
    prizes = {
        "1": "🎁 First Prize",
        "2": "🥈 Second Prize",
        "3": "🥉 Third Prize"
    }

    event = {
        "event_name": event_name,
        "max_tickets": total_tickets,
        "tickets": tickets,
        "participants": {},
        "prizes": prizes
    }
    save_event(event)
    await interaction.channel.send(f"✅ Event **{event_name}** created with {total_tickets} tickets!")

@bot.tree.command(name="register", description="Register for the event", guild=discord.Object(id=int(GUILD_ID)))
async def register(interaction: Interaction):
    event = load_event()
    if not event:
        await interaction.channel.send("❌ No event created.")
        return

    uid = str(interaction.user.id)
    if uid in event["participants"]:
        await interaction.channel.send("⚠️ You are already registered!")
        return

    draws = get_draws_from_roles(interaction.user)
    if draws == 0:
        await interaction.channel.send("❌ No valid role (V1–V10) found!")
        return

    event["participants"][uid] = {
        "name": interaction.user.display_name,
        "draws_left": draws,
        "tickets": []
    }
    save_event(event)

    await interaction.channel.send(
        f"✅ {interaction.user.mention} registered successfully with {draws} draw(s) available!",
        view=DrawView(interaction.user.id)
    )

@bot.tree.command(name="cancel_event", description="Cancel current event", guild=discord.Object(id=int(GUILD_ID)))
async def cancel_event(interaction: Interaction):
    if os.path.exists(EVENT_FILE):
        os.remove(EVENT_FILE)
        await interaction.channel.send("🚫 The current event has been cancelled.")
    else:
        await interaction.channel.send("❌ No event to cancel.")

@bot.tree.command(name="add_mem", description="Add a participant to the event", guild=discord.Object(id=int(GUILD_ID)))
@app_commands.describe(ten_nguoi="Tên người tham gia")
@app_commands.checks.has_role("MOD")
async def add_mem(interaction: Interaction, ten_nguoi: str):
    event = load_event()
    if not event:
        await interaction.response.send_message("❌ Chưa có sự kiện nào được tạo.", ephemeral=True)
        return

    uid = str(interaction.user.id)
    if uid in event["participants"]:
        await interaction.response.send_message("⚠️ Bạn đã đăng ký rồi!", ephemeral=True)
        return

    event["participants"][uid] = {
        "name": ten_nguoi,
        "draws_left": 1,
        "tickets": []
    }
    save_event(event)

    await interaction.response.send_message(f"✅ Đã thêm {ten_nguoi} vào sự kiện.", ephemeral=True)

bot.run(TOKEN)

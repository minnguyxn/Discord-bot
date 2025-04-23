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
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ You are not allowed to draw here!", ephemeral=False)
            return

        event = load_event()
        uid = str(interaction.user.id)

        if uid not in event["participants"]:
            await interaction.response.send_message("❌ You haven't registered yet!", ephemeral=False)
            return

        p = event["participants"][uid]
        if p["draws_left"] <= 0:
            await interaction.response.send_message("⚠️ You have no draws left!", ephemeral=False)
            return

        if not event["tickets"]:
            await interaction.response.send_message("❌ No tickets left!", ephemeral=False)
            return

        ticket = random.choice(event["tickets"])
        event["tickets"].remove(ticket)
        p["tickets"].append(ticket)
        p["draws_left"] -= 1

        prize = event["prizes"].get(str(ticket), None)
        save_event(event)

        if prize:
            result = f"🎉 **{interaction.user.mention}** drew ticket **#{ticket}** and won **{prize}**!"
        else:
            result = f"🎲 **{interaction.user.mention}** drew ticket **#{ticket}** but did not win."

        await interaction.response.send_message(result) 

@bot.event
async def on_ready():
    print(f"Bot online: {bot.user}")
    try:
        synced = await bot.tree.sync(guild=discord.Object(id=int(GUILD_ID)))
        print(f"Slash commands synced: {len(synced)}")
    except Exception as e:
        print("Sync error:", e)

@bot.tree.command(name="create_event", description="Create a lucky draw event", guild=discord.Object(id=int(GUILD_ID)))
@app_commands.describe(event_name="Event name", number_of_tickets="Number of tickets")
async def create_event(interaction: Interaction, event_name: str, number_of_tickets: int):
    tickets = list(range(1, number_of_tickets + 1))
    prizes = {
        "1": "🎁 First Prize",
        "2": "🥈 Second Prize",
        "3": "🥉 Third Prize"
    }

    event = {
        "event_name": event_name,
        "max_tickets": number_of_tickets,
        "tickets": tickets,
        "participants": {},
        "prizes": prizes
    }
    save_event(event)
    await interaction.response.send_message(f"✅ Event **{event_name}** created with {number_of_tickets} tickets.")

@bot.tree.command(name="register", description="Register for the event", guild=discord.Object(id=int(GUILD_ID)))
async def register(interaction: Interaction):
    event = load_event()
    if not event:
        await interaction.response.send_message("❌ No event has been created yet.", ephemeral=False)
        return

    uid = str(interaction.user.id)
    if uid in event["participants"]:
        await interaction.response.send_message("⚠️ You have already registered!", ephemeral=False)
        return

    draws = get_draws_from_roles(interaction.user)
    if draws == 0:
        await interaction.response.send_message("❌ You do not have a valid role (V1–V10)!", ephemeral=False)
        return

    event["participants"][uid] = {
        "name": interaction.user.display_name,
        "draws_left": draws,
        "tickets": []
    }
    save_event(event)

    await interaction.response.send_message(
        f"✅ You have successfully registered! You have {draws} draws.",
        view=DrawView(interaction.user.id),
        ephemeral=True
    )

# Cancel event command
@bot.tree.command(name="cancel_event", description="Cancel the current event", guild=discord.Object(id=int(GUILD_ID)))
async def cancel_event(interaction: Interaction):
    event = load_event()
    if not event:
        await interaction.response.send_message("❌ No event to cancel.", ephemeral=False)
        return

    os.remove(EVENT_FILE)
    await interaction.response.send_message("✅ The event has been canceled.", ephemeral=False)

bot.run(TOKEN)

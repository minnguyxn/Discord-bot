import discord
from discord.ext import commands
from discord import app_commands
import random
import json
import os

TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = os.getenv("GUILD_ID")

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
bot = commands.Bot(command_prefix="/", intents=intents)

DATA_FILE = "events.json"
events = {}
ROLE_PREFIX = "V"

def load_events():
    global events
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            events = json.load(f)

def save_events():
    with open(DATA_FILE, "w") as f:
        json.dump(events, f)

def get_max_entries(member: discord.Member) -> int:
    for i in range(10, 0, -1):
        if discord.utils.get(member.roles, name=f"{ROLE_PREFIX}{i}"):
            return i
    return 0

@bot.event
async def on_ready():
    load_events()
    await bot.tree.sync()
    print(f"✅ Bot is ready as {bot.user}")

@bot.tree.command(name="create_event", description="Create a lucky number event")
@app_commands.describe(event_name="Event name", num_winners="Number of winners")
async def create_event(interaction: discord.Interaction, event_name: str, num_winners: int):
    if event_name in events:
        await interaction.response.send_message(f"❌ Event `{event_name}` already exists.", ephemeral=False)
        return
    events[event_name] = {
        "creator": interaction.user.id,
        "num_winners": num_winners,
        "entries": {}
    }
    save_events()
    await interaction.response.send_message(f"🎉 Created event `{event_name}` with {num_winners} winners!", ephemeral=False)

@bot.tree.command(name="register", description="Register numbers for an event")
@app_commands.describe(event_name="Event name", number="Your chosen number")
async def register(interaction: discord.Interaction, event_name: str, number: int):
    member = interaction.user
    if event_name not in events:
        await interaction.response.send_message("❌ Event not found.", ephemeral=False)
        return
    max_allowed = get_max_entries(member)
    if max_allowed == 0:
        await interaction.response.send_message("❌ You don't have a valid role (V1–V10).", ephemeral=False)
        return
    event = events[event_name]
    entries = event["entries"].setdefault(str(member.id), [])
    if number in [n for e in event["entries"].values() for n in e]:
        await interaction.response.send_message("❌ This number is already taken.", ephemeral=False)
        return
    if len(entries) >= max_allowed:
        await interaction.response.send_message(f"❌ You can only pick {max_allowed} numbers.", ephemeral=False)
        return
    entries.append(number)
    save_events()
    await interaction.response.send_message(f"✅ {member.mention} picked number `{number}`!", ephemeral=False)

@bot.tree.command(name="list_entries", description="Show list of participants")
@app_commands.describe(event_name="Event name")
async def list_entries(interaction: discord.Interaction, event_name: str):
    if event_name not in events:
        await interaction.response.send_message("❌ Event not found.", ephemeral=False)
        return
    event = events[event_name]
    if not event["entries"]:
        await interaction.response.send_message(f"📭 No entries in event `{event_name}` yet.", ephemeral=False)
        return

    result = ""
    for uid, nums in event["entries"].items():
        if uid.startswith("custom:"):
            display_name = uid[len("custom:"):]
        else:
            try:
                member = await interaction.guild.fetch_member(int(uid))
                display_name = member.mention
            except:
                display_name = f"Unknown User ({uid})"
        numbers = ", ".join(str(n) for n in nums)
        result += f"- {display_name}: {numbers}\n"

    await interaction.response.send_message(f"📋 Participants in `{event_name}`:\n{result}", ephemeral=False)

@bot.tree.command(name="draw_winners", description="Draw winners from an event")
@app_commands.describe(event_name="Event name")
async def draw_winners(interaction: discord.Interaction, event_name: str):
    if event_name not in events:
        await interaction.response.send_message("❌ Event not found.", ephemeral=False)
        return
    event = events[event_name]
    if interaction.user.id != event["creator"]:
        await interaction.response.send_message("❌ Only the creator can draw winners.", ephemeral=False)
        return
    all_entries = [(uid, num) for uid, nums in event["entries"].items() for num in nums]
    if len(all_entries) < event["num_winners"]:
        await interaction.response.send_message("❌ Not enough entries to draw winners.", ephemeral=False)
        return
    winners = random.sample(all_entries, event["num_winners"])
    result = "\n".join([f"<@{uid}>" if not uid.startswith("custom:") else uid[7:] + f" (custom)" + f" with number `{num}`" for uid, num in winners])
    await interaction.response.send_message(f"🏆 **Winners of `{event_name}`:**\n{result}", ephemeral=False)
    del events[event_name]
    save_events()

@bot.tree.command(name="cancel_event", description="Cancel an event")
@app_commands.describe(event_name="Event name")
async def cancel_event(interaction: discord.Interaction, event_name: str):
    if event_name not in events:
        await interaction.response.send_message("❌ Event not found.", ephemeral=False)
        return
    if interaction.user.id != events[event_name]["creator"]:
        await interaction.response.send_message("❌ Only the creator can cancel the event.", ephemeral=False)
        return
    del events[event_name]
    save_events()
    await interaction.response.send_message(f"🚫 Event `{event_name}` has been cancelled.", ephemeral=False)

@bot.tree.command(name="add_mem", description="MOD: Add external user to an event")
@app_commands.describe(event_name="Event name", identifier="User ID or custom name", numbers="Numbers separated by space")
async def add_mem(interaction: discord.Interaction, event_name: str, identifier: str, numbers: str):
    if not discord.utils.get(interaction.user.roles, name="MOD"):
        await interaction.response.send_message("❌ You don't have permission to use this command (requires MOD role).", ephemeral=False)
        return
    if event_name not in events:
        await interaction.response.send_message("❌ Event not found.", ephemeral=False)
        return

    number_list = []
    try:
        number_list = list(map(int, numbers.split()))
    except ValueError:
        await interaction.response.send_message("❌ Invalid number list. Only use space-separated integers.", ephemeral=False)
        return

    # Determine if it's a custom user or a real member
    if identifier.isdigit():
        uid = identifier
        try:
            member = await interaction.guild.fetch_member(int(uid))
            max_allowed = get_max_entries(member)
        except:
            await interaction.response.send_message("❌ Could not find member in server.", ephemeral=False)
            return
    else:
        uid = f"custom:{identifier}"
        max_allowed = 10  # Give full access to custom participants

    current_entries = events[event_name]["entries"].setdefault(uid, [])
    total_after_add = len(current_entries) + len(number_list)
    if total_after_add > max_allowed:
        await interaction.response.send_message(
            f"❌ This user can only have {max_allowed} numbers. Already has {len(current_entries)}.",
            ephemeral=False
        )
        return

    all_chosen = [n for nums in events[event_name]["entries"].values() for n in nums]
    for n in number_list:
        if n in all_chosen:
            await interaction.response.send_message(f"❌ Number `{n}` is already taken.", ephemeral=False)
            return

    current_entries.extend(number_list)
    save_events()
    display_name = f"<@{uid}>" if uid.isdigit() else identifier
    await interaction.response.send_message(f"✅ Added `{display_name}` with numbers: {', '.join(map(str, number_list))}", ephemeral=False)

if __name__ == "__main__":
    bot.run(TOKEN)

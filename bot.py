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
        await interaction.response.send_message(f"❌ The event `{event_name}` already exists.", ephemeral=False)
        return
    events[event_name] = {
        "creator": interaction.user.id,
        "num_winners": num_winners,
        "entries": {}
    }
    save_events()
    await interaction.response.send_message(f"🎉 The event `{event_name}` with {num_winners} winners has been created!", ephemeral=False)

@bot.tree.command(name="register", description="Register a number for an event")
@app_commands.describe(event_name="Event name", number="Number you choose")
async def register(interaction: discord.Interaction, event_name: str, number: int):
    member = interaction.user
    if event_name not in events:
        await interaction.response.send_message("❌ The event does not exist.", ephemeral=False)
        return
    max_allowed = get_max_entries(member)
    if max_allowed == 0:
        await interaction.response.send_message("❌ You do not have the appropriate role (V1–V10).", ephemeral=False)
        return
    event = events[event_name]
    entries = event["entries"].setdefault(str(member.id), [])
    if number in [n for e in event["entries"].values() for n in e]:
        await interaction.response.send_message("❌ This number has already been chosen by someone else.", ephemeral=False)
        return
    if len(entries) >= max_allowed:
        await interaction.response.send_message(f"❌ You can only choose {max_allowed} numbers.", ephemeral=False)
        return
    entries.append(number)
    save_events()
    await interaction.response.send_message(f"✅ {member.mention} has chosen number `{number}`!", ephemeral=False)

@bot.tree.command(name="list_entries", description="Show the list of participants")
@app_commands.describe(event_name="Event name")
async def list_entries(interaction: discord.Interaction, event_name: str):
    if event_name not in events:
        await interaction.response.send_message("❌ The event does not exist.", ephemeral=False)
        return
    event = events[event_name]
    if not event["entries"]:
        await interaction.response.send_message(f"📭 No one has registered for the event `{event_name}`.", ephemeral=False)
        return
    result = ""
    for uid, nums in event["entries"].items():
        member = await interaction.guild.fetch_member(int(uid))
        numbers = ", ".join(str(n) for n in nums)
        result += f"- {member.mention}: {numbers}\n"
    await interaction.response.send_message(f"📋 Registration list for `{event_name}`:\n{result}", ephemeral=False)

@bot.tree.command(name="draw_winners", description="Draw the winners of the event")
@app_commands.describe(event_name="Event name")
async def draw_winners(interaction: discord.Interaction, event_name: str):
    if event_name not in events:
        await interaction.response.send_message("❌ The event does not exist.", ephemeral=False)
        return
    event = events[event_name]
    if interaction.user.id != event["creator"]:
        await interaction.response.send_message("❌ Only the creator of the event can draw winners.", ephemeral=False)
        return
    all_entries = [(uid, num) for uid, nums in event["entries"].items() for num in nums]
    if len(all_entries) < event["num_winners"]:
        await interaction.response.send_message("❌ Not enough entries to draw winners.", ephemeral=False)
        return
    winners = random.sample(all_entries, event["num_winners"])
    result = "\n".join([f"<@{uid}> with number `{num}`" for uid, num in winners])
    await interaction.response.send_message(f"🏆 **Results of the `{event_name}` event:**\n{result}", ephemeral=False)
    del events[event_name]
    save_events()

@bot.tree.command(name="cancel_event", description="Cancel the event")
@app_commands.describe(event_name="Event name")
async def cancel_event(interaction: discord.Interaction, event_name: str):
    if event_name not in events:
        await interaction.response.send_message("❌ The event does not exist.", ephemeral=False)
        return
    if interaction.user.id != events[event_name]["creator"]:
        await interaction.response.send_message("❌ Only the creator of the event can cancel it.", ephemeral=False)
        return
    del events[event_name]
    save_events()
    await interaction.response.send_message(f"🚫 The event `{event_name}` has been canceled.", ephemeral=False)
    
@bot.tree.command(name="add_mem", description="MOD adds a participant to the event")
@app_commands.describe(event_name="Event name", user="User to add", numbers="List of numbers separated by spaces (e.g., 12 15 99)")
async def add_mem(interaction: discord.Interaction, event_name: str, user: discord.Member, numbers: str):
    # Check MOD role
    if not discord.utils.get(interaction.user.roles, name="MOD"):
        await interaction.response.send_message("❌ You do not have permission to use this command (MOD role required).", ephemeral=False)
        return

    if event_name not in events:
        await interaction.response.send_message("❌ The event does not exist.", ephemeral=False)
        return

    number_list = []
    try:
        number_list = list(map(int, numbers.split()))
    except ValueError:
        await interaction.response.send_message("❌ Invalid number list (only numbers, separated by spaces).", ephemeral=False)
        return

    max_allowed = get_max_entries(user)
    if max_allowed == 0:
        await interaction.response.send_message("❌ This user does not have an appropriate role (V1–V10).", ephemeral=False)
        return

    current_entries = events[event_name]["entries"].setdefault(str(user.id), [])
    total_after_add = len(current_entries) + len(number_list)

    if total_after_add > max_allowed:
        await interaction.response.send_message(
            f"❌ This user can only select {max_allowed} numbers. They already selected {len(current_entries)}, can only add {max_allowed - len(current_entries)} numbers.",
            ephemeral=False)
        return

    # Check for duplicate numbers
    all_chosen = [n for uid, nums in events[event_name]["entries"].items() for n in nums]
    for n in number_list:
        if n in all_chosen:
            await interaction.response.send_message(f"❌ The number `{n}` has already been chosen by someone else.", ephemeral=False)
            return

    # Add numbers
    current_entries.extend(number_list)
    save_events()
    await interaction.response.send_message(f"✅ Added {user.mention} with numbers: {', '.join(map(str, number_list))}", ephemeral=False)


# Run the bot
if __name__ == "__main__":
    bot.run(TOKEN)

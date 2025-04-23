import discord
from discord.ext import commands
from discord import app_commands
import random
import json
import os
import threading
from flask import Flask

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

def get_max_entries(member_or_roles) -> int:
    roles = member_or_roles.roles if hasattr(member_or_roles, "roles") else member_or_roles
    for i in range(10, 0, -1):
        if discord.utils.get(roles, name=f"{ROLE_PREFIX}{i}"):
            return i
    return 0

@bot.event
async def on_ready():
    load_events()
    await bot.tree.sync()
    print(f"✅ Bot is ready as {bot.user}")

@bot.tree.command(name="create_event", description="Create a lucky number event")
@app_commands.describe(event_name="Name of the event", num_winners="Number of winners")
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

@bot.tree.command(name="register", description="Register a number for an event")
@app_commands.describe(event_name="Name of the event", number="Your chosen number")
async def register(interaction: discord.Interaction, event_name: str, number: int):
    member = interaction.user
    if event_name not in events:
        await interaction.response.send_message("❌ Event does not exist.", ephemeral=False)
        return
    max_allowed = get_max_entries(member)
    if max_allowed == 0:
        await interaction.response.send_message("❌ You do not have a valid role (V1–V10).", ephemeral=False)
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
    await interaction.response.send_message(f"✅ {member.mention} registered number `{number}`!", ephemeral=False)

@bot.tree.command(name="list_entries", description="List registered users and numbers")
@app_commands.describe(event_name="Name of the event")
async def list_entries(interaction: discord.Interaction, event_name: str):
    if event_name not in events:
        await interaction.response.send_message("❌ Event does not exist.", ephemeral=False)
        return
    event = events[event_name]
    if not event["entries"]:
        await interaction.response.send_message(f"📭 No entries for `{event_name}` yet.", ephemeral=False)
        return
    result = ""
    for uid, nums in event["entries"].items():
        name = uid
        if uid.startswith("custom:"):
            name = uid.replace("custom:", "")
        else:
            try:
                member = await interaction.guild.fetch_member(int(uid))
                name = member.mention
            except:
                name = f"<@{uid}>"
        numbers = ", ".join(str(n) for n in nums)
        result += f"- {name}: {numbers}\n"
    await interaction.response.send_message(f"📋 Entries for `{event_name}`:\n{result}", ephemeral=False)

@bot.tree.command(name="draw_winners", description="Draw winners for the event")
@app_commands.describe(event_name="Name of the event")
async def draw_winners(interaction: discord.Interaction, event_name: str):
    if event_name not in events:
        await interaction.response.send_message("❌ Event does not exist.", ephemeral=False)
        return
    event = events[event_name]
    if interaction.user.id != event["creator"]:
        await interaction.response.send_message("❌ Only the event creator can draw winners.", ephemeral=False)
        return
    all_entries = [(uid, num) for uid, nums in event["entries"].items() for num in nums]
    if len(all_entries) < event["num_winners"]:
        await interaction.response.send_message("❌ Not enough entries to draw winners.", ephemeral=False)
        return
    winners = random.sample(all_entries, event["num_winners"])
    result = "\n".join([f"{uid if uid.startswith('custom:') else f'<@{uid}>'} with number `{num}`" for uid, num in winners])
    await interaction.response.send_message(f"🏆 **Winners of `{event_name}`:**\n{result}", ephemeral=False)
    del events[event_name]
    save_events()

@bot.tree.command(name="cancel_event", description="Cancel an event")
@app_commands.describe(event_name="Name of the event")
async def cancel_event(interaction: discord.Interaction, event_name: str):
    if event_name not in events:
        await interaction.response.send_message("❌ Event does not exist.", ephemeral=False)
        return
    if interaction.user.id != events[event_name]["creator"]:
        await interaction.response.send_message("❌ Only the event creator can cancel it.", ephemeral=False)
        return
    del events[event_name]
    save_events()
    await interaction.response.send_message(f"🚫 Event `{event_name}` has been cancelled.", ephemeral=False)

@bot.tree.command(name="add_mem", description="MOD adds a user to the event by name or ID")
@app_commands.describe(event_name="Event name", name_or_id="User ID or custom name", numbers="Numbers separated by space")
async def add_mem(interaction: discord.Interaction, event_name: str, name_or_id: str, numbers: str):
    if not discord.utils.get(interaction.user.roles, name="MOD"):
        await interaction.response.send_message("❌ You must have the MOD role.", ephemeral=False)
        return
    if event_name not in events:
        await interaction.response.send_message("❌ Event does not exist.", ephemeral=False)
        return
    try:
        number_list = list(map(int, numbers.split()))
    except ValueError:
        await interaction.response.send_message("❌ Invalid number list. Use spaces to separate numbers.", ephemeral=False)
        return

    is_custom = not name_or_id.isdigit()
    user_id = f"custom:{name_or_id}" if is_custom else name_or_id
    current_entries = events[event_name]["entries"].setdefault(user_id, [])
    all_chosen = [n for nums in events[event_name]["entries"].values() for n in nums]

    for n in number_list:
        if n in all_chosen:
            await interaction.response.send_message(f"❌ Number `{n}` is already taken.", ephemeral=False)
            return

    max_allowed = 10  # Default max for unknown users
    if not is_custom:
        try:
            member = await interaction.guild.fetch_member(int(user_id))
            max_allowed = get_max_entries(member)
        except:
            pass

    if len(current_entries) + len(number_list) > max_allowed:
        await interaction.response.send_message(
            f"❌ Max allowed is {max_allowed}. Already registered {len(current_entries)}. Can only add {max_allowed - len(current_entries)} more.",
            ephemeral=False
        )
        return

    current_entries.extend(number_list)
    save_events()
    await interaction.response.send_message(f"✅ Added `{name_or_id}` with numbers: {', '.join(map(str, number_list))}", ephemeral=False)

# Keep-alive server for Render (Web Service only)
app = Flask(__name__)
@app.route('/')
def home():
    return "Bot is running!"
def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
threading.Thread(target=run_web).start()

# Run the bot
if __name__ == "__main__":
    bot.run(TOKEN)

import discord
from discord.ext import commands
from discord import app_commands
from threading import Thread
from flask import Flask
import random
import os
import psycopg2

TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = os.getenv("GUILD_ID")
DATABASE_URL = os.getenv("DATABASE_URL")

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
bot = commands.Bot(command_prefix="/", intents=intents)
events = {}

ROLE_PREFIX = "V"

# Initialize database
def init_db():
    with psycopg2.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    name TEXT PRIMARY KEY,
                    creator_id TEXT NOT NULL,
                    num_winners INTEGER NOT NULL
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS entries (
                    event_name TEXT REFERENCES events(name),
                    user_id TEXT,
                    user_name TEXT,
                    number INTEGER,
                    PRIMARY KEY (event_name, number)
                );
            """)
        conn.commit()
    print("✅ Database initialized.")

# Load events from database
def load_events():
    global events
    events = {}
    with psycopg2.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT name, creator_id, num_winners FROM events;")
            for name, creator_id, num_winners in cur.fetchall():
                events[name] = {
                    "creator": creator_id,
                    "num_winners": num_winners,
                    "entries": {}
                }
            cur.execute("SELECT event_name, user_id, user_name, number FROM entries;")
            for event_name, user_id, user_name, number in cur.fetchall():
                if event_name in events:
                    user_entries = events[event_name]["entries"].setdefault(user_id, {"name": user_name, "numbers": []})
                    user_entries["numbers"].append(number)

# Save events to database
def save_events():
    with psycopg2.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            for event_name, event in events.items():
                cur.execute("""
                    INSERT INTO events (name, creator_id, num_winners)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (name) DO UPDATE
                    SET creator_id = EXCLUDED.creator_id, num_winners = EXCLUDED.num_winners;
                """, (event_name, event["creator"], event["num_winners"]))

            cur.execute("DELETE FROM entries WHERE event_name NOT IN %s;", (tuple(events.keys()),))

            for event_name, event in events.items():
                for user_id, entry in event["entries"].items():
                    name = entry["name"]
                    for number in entry["numbers"]:
                        cur.execute("""
                            INSERT INTO entries (event_name, user_id, user_name, number)
                            VALUES (%s, %s, %s, %s)
                            ON CONFLICT (event_name, number) DO UPDATE
                            SET user_id = EXCLUDED.user_id, user_name = EXCLUDED.user_name;
                        """, (event_name, user_id, name, number))
        conn.commit()

@bot.event
async def on_ready():
    init_db()
    load_events()
    await bot.tree.sync()
    print(f"✅ Bot is ready as {bot.user}")

def get_max_entries(member: discord.Member) -> int:
    for i in range(10, 0, -1):
        if discord.utils.get(member.roles, name=f"{ROLE_PREFIX}{i}"):
            return i
    return 0

@bot.tree.command(name="create_event", description="Create a lucky draw event")
@app_commands.describe(event_name="Event name", num_winners="Number of winners")
async def create_event(interaction: discord.Interaction, event_name: str, num_winners: int):
    await interaction.response.defer()
    if event_name in events:
        await interaction.followup.send(f"❌ Event `{event_name}` already exists.", ephemeral=False)
        return
    events[event_name] = {
        "creator": str(interaction.user.id),
        "num_winners": num_winners,
        "entries": {}
    }
    save_events()
    await interaction.followup.send(f"🎉 Event `{event_name}` created with {num_winners} winner(s)!", ephemeral=False)

@bot.tree.command(name="register", description="Register one or more numbers for an event")
@app_commands.describe(event_name="Event name", numbers="Your chosen numbers (comma-separated)")
async def register(interaction: discord.Interaction, event_name: str, numbers: str):
    await interaction.response.defer()
    member = interaction.user

    if event_name not in events:
        await interaction.followup.send("❌ Event not found.", ephemeral=False)
        return

    max_allowed = get_max_entries(member)
    if max_allowed == 0:
        await interaction.followup.send("❌ You do not have a valid role (V1–V10).", ephemeral=False)
        return

    try:
        chosen_numbers = [int(n.strip()) for n in numbers.split(",")]
    except ValueError:
        await interaction.followup.send("❌ Invalid number list. Use commas to separate numbers.", ephemeral=False)
        return

    if any(n < 0 or n > 9999 for n in chosen_numbers):
        await interaction.followup.send("❌ Only numbers between 0 and 9999 are allowed.", ephemeral=False)
        return

    event = events[event_name]
    all_numbers = [n for e in event["entries"].values() for n in e["numbers"]]
    entries = event["entries"].setdefault(str(member.id), {"name": member.display_name, "numbers": []})

    available_slots = max_allowed - len(entries["numbers"])
    new_numbers = [n for n in chosen_numbers if n not in all_numbers]
    if not new_numbers:
        await interaction.followup.send("❌ All chosen numbers are already taken.", ephemeral=False)
        return

    if len(new_numbers) > available_slots:
        await interaction.followup.send(f"❌ You can only choose {available_slots} more number(s).", ephemeral=False)
        return

    entries["numbers"].extend(new_numbers)
    save_events()
    await interaction.followup.send(f"✅ {member.mention} registered: `{', '.join(map(str, new_numbers))}`", ephemeral=False)

@bot.tree.command(name="list_entries", description="List all registered numbers for an event")
@app_commands.describe(event_name="Event name")
async def list_entries(interaction: discord.Interaction, event_name: str):
    await interaction.response.defer(thinking=True)
    if event_name not in events:
        await interaction.followup.send("❌ Event not found.", ephemeral=True)
        return
    event = events[event_name]
    if not event["entries"]:
        await interaction.followup.send(f"📭 No one has registered for `{event_name}`.", ephemeral=False)
        return
    result = ""
    for user_id, entry in event["entries"].items():
        user_display = entry["name"]
        number_list = ", ".join(str(n) for n in entry["numbers"])
        result += f"- **{user_display}**: {number_list}\n"
    await interaction.followup.send(f"📋 Registered numbers for `{event_name}`:\n{result}", ephemeral=False)

@bot.tree.command(name="draw_winners", description="Draw winners from an event")
@app_commands.describe(event_name="Event name")
async def draw_winners(interaction: discord.Interaction, event_name: str):
    await interaction.response.defer()
    if event_name not in events:
        await interaction.followup.send("❌ Event not found.", ephemeral=False)
        return
    event = events[event_name]
    if str(interaction.user.id) != event["creator"]:
        await interaction.followup.send("❌ Only the creator can draw winners.", ephemeral=False)
        return
    all_entries = [(uid, n) for uid, e in event["entries"].items() for n in e["numbers"]]
    if len(all_entries) < event["num_winners"]:
        await interaction.followup.send("❌ Not enough entries to draw.", ephemeral=False)
        return
    winners = random.sample(all_entries, event["num_winners"])
    result = "\n".join([f"**{events[event_name]['entries'][uid]['name']}** with number `{num}`" for uid, num in winners])
    await interaction.followup.send(f"🏆 **Winners of `{event_name}`:**\n{result}", ephemeral=False)
    del events[event_name]
    save_events()

@bot.tree.command(name="cancel_event", description="Cancel an event")
@app_commands.describe(event_name="Event name")
async def cancel_event(interaction: discord.Interaction, event_name: str):
    await interaction.response.defer()
    if event_name not in events:
        await interaction.followup.send("❌ Event not found.", ephemeral=False)
        return
    if str(interaction.user.id) != events[event_name]["creator"]:
        await interaction.followup.send("❌ Only the creator can cancel this event.", ephemeral=False)
        return
    del events[event_name]
    save_events()
    await interaction.followup.send(f"🚫 Event `{event_name}` has been canceled.", ephemeral=False)

# Check if user is MOD
def is_mod(member: discord.Member) -> bool:
    return any(role.name == "MOD" for role in member.roles)

@bot.tree.command(name="add_mem", description="Add a user to event manually (MOD only)")
@app_commands.describe(event_name="Event name", ingame_name="In-game name", numbers="Numbers (comma-separated)")
async def add_mem(interaction: discord.Interaction, event_name: str, ingame_name: str, numbers: str):
    await interaction.response.defer()
    if not is_mod(interaction.user):
        await interaction.followup.send("❌ This command is MOD only.", ephemeral=True)
        return

    if event_name not in events:
        await interaction.followup.send("❌ Event not found.", ephemeral=False)
        return

    try:
        chosen_numbers = [int(n.strip()) for n in numbers.split(",")]
    except ValueError:
        await interaction.followup.send("❌ Invalid number list. Use commas.", ephemeral=False)
        return

    if any(n < 0 or n > 9999 for n in chosen_numbers):
        await interaction.followup.send("❌ Only numbers between 0 and 9999 are allowed.", ephemeral=False)
        return

    event = events[event_name]
    all_numbers = [n for e in event["entries"].values() for n in e["numbers"]]
    new_numbers = [n for n in chosen_numbers if n not in all_numbers]
    if not new_numbers:
        await interaction.followup.send("❌ All chosen numbers are already taken.", ephemeral=False)
        return

    entries = event["entries"].setdefault(ingame_name, {"name": ingame_name, "numbers": []})
    entries["numbers"].extend(new_numbers)
    save_events()
    await interaction.followup.send(f"✅ Added `{ingame_name}` with numbers: `{', '.join(map(str, new_numbers))}`", ephemeral=False)

@bot.tree.command(name="clear_all_data", description="Clear all event data (MOD only)")
async def clear_all_data(interaction: discord.Interaction):
    await interaction.response.defer()
    if not is_mod(interaction.user):
        await interaction.followup.send("❌ This command is MOD only.", ephemeral=True)
        return
    events.clear()
    with psycopg2.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM entries;")
            cur.execute("DELETE FROM events;")
        conn.commit()
    await interaction.followup.send("🗑️ All data has been cleared!", ephemeral=False)

@bot.tree.command(name="list_events", description="List all available events")
async def list_events(interaction: discord.Interaction):
    await interaction.response.defer()
    if not events:
        await interaction.followup.send("📭 No available events.", ephemeral=False)
        return
    event_list = "\n".join([f"- `{name}` with {info['num_winners']} winner(s)" for name, info in events.items()])
    await interaction.followup.send(f"📅 Current events:\n{event_list}", ephemeral=False)

@bot.tree.command(name="help", description="List all bot commands")
async def help_command(interaction: discord.Interaction):
    await interaction.response.defer()
    commands_list = """
📘 **Available Commands:**
/create_event - Create a lucky draw event
/register - Register numbers for an event
/list_entries - List all registered numbers for an event
/list_events - List all available events
/draw_winners - Draw winners from an event
/cancel_event - Cancel an event
/add_mem - Add user and numbers (MOD only)
/clear_all_data - Clear all event data (MOD only)
/help - Show this help message
"""
    await interaction.followup.send(commands_list, ephemeral=False)

# Flask keep-alive for Render
app = Flask('')

@app.route('/')
def home():
    return "Bot is alive!"

def run():
    app.run(host='0.0.0.0', port=10000)

Thread(target=run).start()

if __name__ == "__main__":
    init_db()
    bot.run(TOKEN)

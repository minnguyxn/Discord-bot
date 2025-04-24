import discord
from discord.ext import commands
from discord import app_commands
from flask import Flask
import random
import json
import os
import psycopg2

TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = os.getenv("GUILD_ID")
DATABASE_URL = os.getenv("DATABASE_URL")

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
bot = commands.Bot(command_prefix="/", intents=intents)

ROLE_PREFIX = "V"

# Khởi tạo cơ sở dữ liệu
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

# Hàm tải dữ liệu sự kiện từ cơ sở dữ liệu
def load_events():
    global events
    events = {}
    with psycopg2.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT name, creator_id, num_winners FROM events;")
            rows = cur.fetchall()
            for row in rows:
                event_name, creator_id, num_winners = row
                events[event_name] = {
                    "creator": creator_id,
                    "num_winners": num_winners,
                    "entries": {}
                }

            cur.execute("SELECT event_name, user_id, user_name, number FROM entries;")
            rows = cur.fetchall()
            for row in rows:
                event_name, user_id, user_name, number = row
                if event_name in events:
                    if user_id not in events[event_name]["entries"]:
                        events[event_name]["entries"][user_id] = []
                    events[event_name]["entries"][user_id].append(number)

# Lưu sự kiện vào cơ sở dữ liệu
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
                for user_id, numbers in event["entries"].items():
                    for number in numbers:
                        cur.execute("""
                            INSERT INTO entries (event_name, user_id, user_name, number)
                            VALUES (%s, %s, %s, %s)
                            ON CONFLICT (event_name, number) DO UPDATE
                            SET user_id = EXCLUDED.user_id, user_name = EXCLUDED.user_name;
                        """, (event_name, user_id, "Unknown", number))  # "Unknown" for now

        conn.commit()

# Khởi tạo khi bot sẵn sàng
@bot.event
async def on_ready():
    init_db()  # Khởi tạo cơ sở dữ liệu khi bot khởi động
    load_events()  # Tải sự kiện từ cơ sở dữ liệu
    await bot.tree.sync()
    print(f"✅ Bot sẵn sàng dưới tên {bot.user}")

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

@bot.tree.command(name="create_event", description="Create a lucky draw event")
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
    await interaction.response.send_message(f"🎉 Event `{event_name}` created with {num_winners} winners!", ephemeral=False)

@bot.tree.command(name="register", description="Register a number for an event")
@app_commands.describe(event_name="Event name", number="Number you choose")
async def register(interaction: discord.Interaction, event_name: str, number: int):
    member = interaction.user
    if event_name not in events:
        await interaction.response.send_message("❌ Event does not exist.", ephemeral=False)
        return
    max_allowed = get_max_entries(member)
    if max_allowed == 0:
        await interaction.response.send_message("❌ You don't have an eligible role (V1–V10).", ephemeral=False)
        return
    event = events[event_name]
    entries = event["entries"].setdefault(str(member.id), [])
    if number in [n for e in event["entries"].values() for n in (e["numbers"] if isinstance(e, dict) else e)]:
        await interaction.response.send_message("❌ Number already taken by someone else.", ephemeral=False)
        return
    if len(entries) >= max_allowed:
        await interaction.response.send_message(f"❌ You can only choose {max_allowed} numbers.", ephemeral=False)
        return
    entries.append(number)
    save_events()
    await interaction.response.send_message(f"✅ {member.mention} chose number `{number}`!", ephemeral=False)

@bot.tree.command(name="list_entries", description="Show all registered numbers for an event")
@app_commands.describe(event_name="Event name")
async def list_entries(interaction: discord.Interaction, event_name: str):
    if event_name not in events:
        await interaction.response.send_message("❌ Event not found.", ephemeral=True)
        return
    await interaction.response.defer(thinking=True)
    event = events[event_name]
    if not event["entries"]:
        await interaction.followup.send(f"📭 No entries yet for `{event_name}`.", ephemeral=False)
        return
    result = ""
    for uid, entry in event["entries"].items():
        if isinstance(entry, dict) and "numbers" in entry and "name" in entry:
            user_display = f"**{entry['name']}**"
            numbers = entry["numbers"]
        else:
            user_display = f"<@{uid}>"
            numbers = entry
        number_list = ", ".join(str(n) for n in numbers)
        result += f"- {user_display}: {number_list}\n"
    await interaction.followup.send(f"📋 Entries for `{event_name}`:\n{result}", ephemeral=False)

@bot.tree.command(name="draw_winners", description="Draw winners from event")
@app_commands.describe(event_name="Event name")
async def draw_winners(interaction: discord.Interaction, event_name: str):
    if event_name not in events:
        await interaction.response.send_message("❌ Event not found.", ephemeral=False)
        return
    event = events[event_name]
    if interaction.user.id != event["creator"]:
        await interaction.response.send_message("❌ Only the creator can draw winners.", ephemeral=False)
        return
    all_entries = [(uid, num) for uid, e in event["entries"].items() for num in (e["numbers"] if isinstance(e, dict) else e)]
    if len(all_entries) < event["num_winners"]:
        await interaction.response.send_message("❌ Not enough entries to draw winners.", ephemeral=False)
        return
    winners = random.sample(all_entries, event["num_winners"])
    result = "\n".join([f"<@{uid}> with number `{num}`" for uid, num in winners])
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
        await interaction.response.send_message("❌ Only the creator can cancel this event.", ephemeral=False)
        return
    del events[event_name]
    save_events()
    await interaction.response.send_message(f"🚫 Event `{event_name}` canceled.", ephemeral=False)

@bot.tree.command(name="add_mem", description="MOD adds a member manually to event")
@app_commands.describe(event_name="Event name", user_id="User ID or name", numbers="Numbers separated by space")
async def add_mem(interaction: discord.Interaction, event_name: str, user_id: str, numbers: str):
    if not discord.utils.get(interaction.user.roles, name="MOD"):
        await interaction.response.send_message("❌ You need the MOD role to use this command.", ephemeral=False)
        return
    if event_name not in events:
        await interaction.response.send_message("❌ Event not found.", ephemeral=False)
        return
    number_list = []
    try:
        number_list = list(map(int, numbers.split()))
    except ValueError:
        await interaction.response.send_message("❌ Invalid number list (use space-separated integers).", ephemeral=False)
        return
    entry = events[event_name]["entries"].setdefault(user_id, {"name": user_id, "numbers": []})
    if isinstance(entry, dict):
        current_entries = entry["numbers"]
        name = entry.get("name", user_id)
    else:
        current_entries = entry
        name = f"<@{user_id}>"
    max_allowed = 10
    if isinstance(user_id, str) and user_id.isdigit():
        member = interaction.guild.get_member(int(user_id))
        if member:
            name = member.display_name
            max_allowed = get_max_entries(member)
    if len(current_entries) + len(number_list) > max_allowed:
        await interaction.response.send_message(f"❌ Can only add {max_allowed - len(current_entries)} more numbers.", ephemeral=False)
        return
    all_chosen = [n for uid, e in events[event_name]["entries"].items() for n in (e["numbers"] if isinstance(e, dict) else e)]
    for n in number_list:
        if n in all_chosen:
            await interaction.response.send_message(f"❌ Number `{n}` already taken.", ephemeral=False)
            return
    current_entries.extend(number_list)
    events[event_name]["entries"][user_id] = {"name": name, "numbers": current_entries}
    save_events()
    await interaction.response.send_message(f"✅ Added **{name}** with numbers: {', '.join(map(str, number_list))}", ephemeral=False)

# Flask keep-alive for Render
app = Flask('')

@app.route('/')
def home():
    return "Bot is alive!"

def run():
    app.run(host='0.0.0.0', port=8080)

Thread(target=run).start()

# Start bot
if __name__ == "__main__":
    init_db()
    bot.run(TOKEN)

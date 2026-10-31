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

            if events:
                cur.execute("DELETE FROM entries WHERE event_name NOT IN %s;", (tuple(events.keys()),))
            else:
                cur.execute("DELETE FROM entries;")

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

# Check if user is MOD
def is_mod(member: discord.Member) -> bool:
    return any(role.name == "R4" for role in member.roles)

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

    try:
        chosen_numbers = [int(n.strip()) for n in numbers.split(",")]
    except ValueError:
        await interaction.followup.send("❌ Định dạng số không hợp lệ. Vui lòng nhập các số cách nhau bằng dấu phẩy (VD: 12, 34).", ephemeral=False)
        return

    if any(n < 0 or n > 9999 for n in chosen_numbers):
        await interaction.followup.send("❌ Chỉ cho phép chọn số từ 0 đến 9999.", ephemeral=False)
        return

    event = events[event_name]
    user_id_str = str(member.id)

    if user_id_str in event["entries"] and len(event["entries"][user_id_str]["numbers"]) >= 1:
        current_number = event["entries"][user_id_str]["numbers"][0]
        await interaction.followup.send(f"❌ Bạn đã đăng ký số `{current_number}` trước đó rồi. Mỗi người chỉ được chọn 1 số duy nhất!", ephemeral=False)
        return

    if len(chosen_numbers) > 1:
        await interaction.followup.send("❌ Bạn chỉ được phép đăng ký 1 số duy nhất cho sự kiện này.", ephemeral=False)
        return

    number = chosen_numbers[0]

    all_taken_numbers = [n for entry_data in event["entries"].values() for n in entry_data["numbers"]]
    if number in all_taken_numbers:
        await interaction.followup.send(f"❌ Số `{number}` đã có người khác đăng ký trước. Vui lòng chọn số khác!", ephemeral=False)
        return

    entries = event["entries"].setdefault(user_id_str, {"name": member.display_name, "numbers": []})
    entries["numbers"].append(number)
    
    save_events()
    await interaction.followup.send(f"✅ {member.mention} đã đăng ký thành công số: `{number}`", ephemeral=False)

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

@bot.tree.command(name="find_lucky_mem", description="Randomly pick lucky winners from a specific role (MOD only)")
@app_commands.describe(role="Chọn role cần quay thưởng", count="Số lượng người thắng cuộc cần tìm")
async def find_lucky_mem(interaction: discord.Interaction, role: discord.Role, count: int):
    await interaction.response.defer()
    if not is_mod(interaction.user):
        await interaction.followup.send("❌ Lệnh này chỉ dành cho MOD.", ephemeral=True)
        return

    members = role.members
    if not members:
        await interaction.followup.send(f"❌ Không tìm thấy thành viên nào sở hữu role `{role.name}`.", ephemeral=False)
        return

    if count <= 0:
        await interaction.followup.send("❌ Số lượng người thắng phải lớn hơn 0.", ephemeral=False)
        return

    if len(members) < count:
        await interaction.followup.send(f"❌ Số lượng thành viên có role `{role.name}` chỉ có {len(members)} người, ít hơn số lượng cần tìm ({count}).", ephemeral=False)
        return

    winners = random.sample(members, count)
    winners_list = "\n".join([f"- {winner.mention} (`{winner.display_name}`)" for winner in winners])
    
    await interaction.followup.send(f"🎉 **Danh sách {count} người may mắn sở hữu role `{role.name}`:**\n{winners_list}", ephemeral=False)

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

@bot.tree.command(name="remove_user_by_name", description="(MOD only) Remove a user and their numbers from an event")
@app_commands.describe(event_name="Event name", display_name="User's display/ingame name")
async def remove_user_by_name(interaction: discord.Interaction, event_name: str, display_name: str):
    await interaction.response.defer()
    if not is_mod(interaction.user):
        await interaction.followup.send("❌ This command is for MODs only.", ephemeral=True)
        return
    if event_name not in events:
        await interaction.followup.send("❌ Event does not exist.", ephemeral=False)
        return

    event = events[event_name]
    to_remove = None
    for user_id, entry in event["entries"].items():
        if entry["name"] == display_name:
            to_remove = user_id
            break

    if not to_remove:
        await interaction.followup.send(f"❌ No one named `{display_name}` found in `{event_name}`.", ephemeral=False)
        return

    del event["entries"][to_remove]
    save_events()
    await interaction.followup.send(f"🗑️ Removed `{display_name}` and all their numbers from `{event_name}`.", ephemeral=False)

@bot.tree.command(name="delete_channels", description="Xóa tất cả các kênh trong server (Admin only)")
async def delete_channels(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Bạn cần quyền Administrator để dùng lệnh này.", ephemeral=True)
        return
    await interaction.response.send_message("⚠️ Lệnh này cực kỳ nguy hiểm. Gõ `/delete_channels_confirm` để xác nhận xóa sạch kênh.")

@bot.tree.command(name="delete_channels_confirm", description="Xác nhận xóa tất cả các kênh trong server")
async def delete_channels_confirm(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Bạn cần quyền Administrator để dùng lệnh này.", ephemeral=True)
        return
    
    await interaction.response.send_message("🔄 Đang tiến hành xóa tất cả các kênh...")
    for channel in interaction.guild.channels:
        try:
            await channel.delete()
            print(f"Đã xóa: {channel.name}")
        except Exception as e:
            print(f"Lỗi khi xóa {channel.name}: {e}")

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
/find_lucky_mem - Pick random winners from a specific role (MOD only)
/add_mem - Add user and numbers (MOD only)
/clear_all_data - Clear all event data (MOD only)
/remove_user_by_name – (MOD only) Remove user from an event
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
    bot.run(TOKEN)

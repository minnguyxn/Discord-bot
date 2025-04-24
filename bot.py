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

# Tải dữ liệu sự kiện
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

# Lưu dữ liệu sự kiện
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

# Ready event
@bot.event
async def on_ready():
    init_db()
    load_events()
    await bot.tree.sync()
    print(f"✅ Bot sẵn sàng dưới tên {bot.user}")

def get_max_entries(member: discord.Member) -> int:
    for i in range(10, 0, -1):
        if discord.utils.get(member.roles, name=f"{ROLE_PREFIX}{i}"):
            return i
    return 0

@bot.tree.command(name="create_event", description="Tạo sự kiện rút thăm may mắn")
@app_commands.describe(event_name="Tên sự kiện", num_winners="Số người thắng")
async def create_event(interaction: discord.Interaction, event_name: str, num_winners: int):
    await interaction.response.defer()
    if event_name in events:
        await interaction.followup.send(f"❌ Sự kiện `{event_name}` đã tồn tại.", ephemeral=False)
        return
    events[event_name] = {
        "creator": str(interaction.user.id),
        "num_winners": num_winners,
        "entries": {}
    }
    save_events()
    await interaction.followup.send(f"🎉 Sự kiện `{event_name}` đã được tạo với {num_winners} người thắng!", ephemeral=False)

@bot.tree.command(name="register", description="Đăng ký số cho sự kiện")
@app_commands.describe(event_name="Tên sự kiện", number="Số bạn chọn")
async def register(interaction: discord.Interaction, event_name: str, number: int):
    await interaction.response.defer()
    member = interaction.user
    if event_name not in events:
        await interaction.followup.send("❌ Sự kiện không tồn tại.", ephemeral=False)
        return
    max_allowed = get_max_entries(member)
    if max_allowed == 0:
        await interaction.followup.send("❌ Bạn không có role hợp lệ (V1–V10).", ephemeral=False)
        return
    event = events[event_name]
    if number in [n for e in event["entries"].values() for n in e["numbers"]]:
        await interaction.followup.send("❌ Số đã được người khác chọn.", ephemeral=False)
        return
    user_id = str(member.id)
    entries = event["entries"].setdefault(user_id, {"name": member.display_name, "numbers": []})
    if len(entries["numbers"]) >= max_allowed:
        await interaction.followup.send(f"❌ Bạn chỉ có thể chọn {max_allowed} số.", ephemeral=False)
        return
    entries["numbers"].append(number)
    save_events()
    await interaction.followup.send(f"✅ {member.mention} đã chọn số `{number}`!", ephemeral=False)

@bot.tree.command(name="list_entries", description="Hiển thị tất cả các số đã đăng ký cho sự kiện")
@app_commands.describe(event_name="Tên sự kiện")
async def list_entries(interaction: discord.Interaction, event_name: str):
    await interaction.response.defer(thinking=True)
    if event_name not in events:
        await interaction.followup.send("❌ Sự kiện không tồn tại.", ephemeral=True)
        return
    event = events[event_name]
    if not event["entries"]:
        await interaction.followup.send(f"📭 Chưa có ai đăng ký cho sự kiện `{event_name}`.", ephemeral=False)
        return
    result = ""
    for user_id, entry in event["entries"].items():
        user_display = entry["name"]
        number_list = ", ".join(str(n) for n in entry["numbers"])
        result += f"- **{user_display}**: {number_list}\n"
    await interaction.followup.send(f"📋 Các số đã đăng ký cho `{event_name}`:\n{result}", ephemeral=False)

@bot.tree.command(name="draw_winners", description="Rút thăm người thắng cuộc từ sự kiện")
@app_commands.describe(event_name="Tên sự kiện")
async def draw_winners(interaction: discord.Interaction, event_name: str):
    await interaction.response.defer()
    if event_name not in events:
        await interaction.followup.send("❌ Sự kiện không tồn tại.", ephemeral=False)
        return
    event = events[event_name]
    if str(interaction.user.id) != event["creator"]:
        await interaction.followup.send("❌ Chỉ người tạo sự kiện mới có thể rút thăm.", ephemeral=False)
        return
    all_entries = [(uid, n) for uid, e in event["entries"].items() for n in e["numbers"]]
    if len(all_entries) < event["num_winners"]:
        await interaction.followup.send("❌ Không đủ người tham gia để rút thăm.", ephemeral=False)
        return
    winners = random.sample(all_entries, event["num_winners"])
    result = "\n".join([f"**{events[event_name]['entries'][uid]['name']}** với số `{num}`" for uid, num in winners])
    await interaction.followup.send(f"🏆 **Người thắng cuộc của `{event_name}`:**\n{result}", ephemeral=False)
    del events[event_name]
    save_events()

@bot.tree.command(name="cancel_event", description="Hủy bỏ sự kiện")
@app_commands.describe(event_name="Tên sự kiện")
async def cancel_event(interaction: discord.Interaction, event_name: str):
    await interaction.response.defer()
    if event_name not in events:
        await interaction.followup.send("❌ Sự kiện không tồn tại.", ephemeral=False)
        return
    if str(interaction.user.id) != events[event_name]["creator"]:
        await interaction.followup.send("❌ Chỉ người tạo sự kiện mới có thể hủy.", ephemeral=False)
        return
    del events[event_name]
    save_events()
    await interaction.followup.send(f"🚫 Sự kiện `{event_name}` đã bị hủy.", ephemeral=False)

# Kiểm tra người dùng có role MOD
def is_mod(member: discord.Member) -> bool:
    return any(role.name == "MOD" for role in member.roles)

# Lệnh thêm người (add_mem) – chỉ MOD
@bot.tree.command(name="add_mem", description="Thêm người vào sự kiện với tên ingame và số (chỉ MOD)")
@app_commands.describe(event_name="Tên sự kiện", ingame_name="Tên ingame người dùng", number="Số bạn chọn")
async def add_mem(interaction: discord.Interaction, event_name: str, ingame_name: str, number: int):
    await interaction.response.defer()
    if not is_mod(interaction.user):
        await interaction.followup.send("❌ Lệnh này chỉ dành cho MOD.", ephemeral=True)
        return
    if event_name not in events:
        await interaction.followup.send("❌ Sự kiện không tồn tại.", ephemeral=False)
        return
    if number in [n for e in events[event_name]["entries"].values() for n in e["numbers"]]:
        await interaction.followup.send("❌ Số đã được người khác chọn.", ephemeral=False)
        return
    entries = events[event_name]["entries"].setdefault(ingame_name, {"name": ingame_name, "numbers": []})
    entries["numbers"].append(number)
    save_events()
    await interaction.followup.send(f"✅ {ingame_name} đã được thêm vào sự kiện `{event_name}` với số `{number}`!", ephemeral=False)

# Lệnh xóa toàn bộ dữ liệu (chỉ MOD)
@bot.tree.command(name="clear_all_data", description="Xóa toàn bộ dữ liệu sự kiện (chỉ MOD)")
async def clear_all_data(interaction: discord.Interaction):
    await interaction.response.defer()
    if not is_mod(interaction.user):
        await interaction.followup.send("❌ Lệnh này chỉ dành cho MOD.", ephemeral=True)
        return
    events.clear()
    with psycopg2.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM entries;")
            cur.execute("DELETE FROM events;")
        conn.commit()
    await interaction.followup.send("🗑️ Tất cả dữ liệu đã bị xóa hoàn toàn!", ephemeral=False)
# Flask keep-alive for Render
app = Flask('')

@app.route('/')
def home():
    return "Bot is alive!"

def run():
    app.run(host='0.0.0.0', port=10000)

Thread(target=run).start()

# Start bot
if __name__ == "__main__":
    init_db()
    bot.run(TOKEN)

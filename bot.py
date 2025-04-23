import discord
from discord.ext import commands
from discord import app_commands
from discord.ui import View, Button
import random
import json
import os
from flask import Flask

# Lấy cổng từ biến môi trường (Render cung cấp cổng qua PORT)
PORT = os.getenv("PORT", 10000)  # Nếu không có biến môi trường, mặc định là 10000

# Tạo Flask app để lắng nghe cổng
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running."

# Lấy Token và Guild ID từ biến môi trường
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = os.getenv("GUILD_ID")

# Cấu hình bot Discord
intents = discord.Intents.default()
intents.guilds = True
intents.members = True
bot = commands.Bot(command_prefix="/", intents=intents)

# Lưu và tải dữ liệu sự kiện
DATA_FILE = "events.json"
events = {}

def load_events():
    global events
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            events = json.load(f)

def save_events():
    with open(DATA_FILE, "w") as f:
        json.dump(events, f)

ROLE_PREFIX = "V"

# Hàm lấy số lượng số tối đa mà một người có thể chọn dựa vào role
def get_max_entries(member: discord.Member) -> int:
    for i in range(10, 0, -1):
        if discord.utils.get(member.roles, name=f"{ROLE_PREFIX}{i}"):
            return i
    return 0

# Event khi bot sẵn sàng
@bot.event
async def on_ready():
    load_events()
    await bot.tree.sync()
    print(f"✅ Bot sẵn sàng dưới tên {bot.user}")

# Slash Commands
@bot.tree.command(name="create_event", description="Tạo sự kiện chọn số may mắn")
@app_commands.describe(event_name="Tên sự kiện", num_winners="Số người thắng")
async def create_event(interaction: discord.Interaction, event_name: str, num_winners: int):
    if event_name in events:
        await interaction.response.send_message(f"❌ Sự kiện `{event_name}` đã tồn tại.", ephemeral=False)
        return
    events[event_name] = {
        "creator": interaction.user.id,
        "num_winners": num_winners,
        "entries": {}
    }
    save_events()
    await interaction.response.send_message(f"🎉 Đã tạo sự kiện `{event_name}` với {num_winners} người thắng!", ephemeral=False)

@bot.tree.command(name="register", description="Đăng ký số vào sự kiện")
@app_commands.describe(event_name="Tên sự kiện", number="Số bạn chọn")
async def register(interaction: discord.Interaction, event_name: str, number: int):
    member = interaction.user
    if event_name not in events:
        await interaction.response.send_message("❌ Sự kiện không tồn tại.", ephemeral=False)
        return
    max_allowed = get_max_entries(member)
    if max_allowed == 0:
        await interaction.response.send_message("❌ Bạn không có role phù hợp (V1–V10).", ephemeral=False)
        return
    event = events[event_name]
    entries = event["entries"].setdefault(str(member.id), [])
    if number in [n for e in event["entries"].values() for n in e]:
        await interaction.response.send_message("❌ Số này đã được chọn bởi người khác.", ephemeral=False)
        return
    if len(entries) >= max_allowed:
        await interaction.response.send_message(f"❌ Bạn chỉ được chọn {max_allowed} số.", ephemeral=False)
        return
    entries.append(number)
    save_events()
    await interaction.response.send_message(f"✅ {member.mention} đã chọn số `{number}`!", ephemeral=False)

@bot.tree.command(name="list_entries", description="Hiển thị danh sách người đã đăng ký")
@app_commands.describe(event_name="Tên sự kiện")
async def list_entries(interaction: discord.Interaction, event_name: str):
    if event_name not in events:
        await interaction.response.send_message("❌ Sự kiện không tồn tại.", ephemeral=False)
        return
    event = events[event_name]
    if not event["entries"]:
        await interaction.response.send_message(f"📭 Chưa có ai đăng ký trong sự kiện `{event_name}`.", ephemeral=False)
        return
    result = ""
    for uid, nums in event["entries"].items():
        member = await interaction.guild.fetch_member(int(uid))
        numbers = ", ".join(str(n) for n in nums)
        result += f"- {member.mention}: {numbers}\n"
    await interaction.response.send_message(f"📋 Danh sách đăng ký trong `{event_name}`:\n{result}", ephemeral=False)

@bot.tree.command(name="draw_winners", description="Rút người thắng cuộc")
@app_commands.describe(event_name="Tên sự kiện")
async def draw_winners(interaction: discord.Interaction, event_name: str):
    if event_name not in events:
        await interaction.response.send_message("❌ Sự kiện không tồn tại.", ephemeral=False)
        return
    event = events[event_name]
    if interaction.user.id != event["creator"]:
        await interaction.response.send_message("❌ Chỉ người tạo sự kiện mới có thể rút.", ephemeral=False)
        return
    all_entries = [(uid, num) for uid, nums in event["entries"].items() for num in nums]
    if len(all_entries) < event["num_winners"]:
        await interaction.response.send_message("❌ Không đủ số để rút người thắng.", ephemeral=False)
        return
    winners = random.sample(all_entries, event["num_winners"])
    result = "\n".join([f"<@{uid}> với số `{num}`" for uid, num in winners])
    await interaction.response.send_message(f"🏆 **Kết quả sự kiện `{event_name}`:**\n{result}", ephemeral=False)
    del events[event_name]
    save_events()

@bot.tree.command(name="cancel_event", description="Hủy sự kiện")
@app_commands.describe(event_name="Tên sự kiện")
async def cancel_event(interaction: discord.Interaction, event_name: str):
    if event_name not in events:
        await interaction.response.send_message("❌ Sự kiện không tồn tại.", ephemeral=False)
        return
    if interaction.user.id != events[event_name]["creator"]:
        await interaction.response.send_message("❌ Chỉ người tạo sự kiện mới có thể hủy.", ephemeral=False)
        return
    del events[event_name]
    save_events()
    await interaction.response.send_message(f"🚫 Đã hủy sự kiện `{event_name}`.", ephemeral=False)

# Chạy Flask server trên cổng 10000
@app.before_first_request
def before_first_request():
    bot.loop.create_task(bot.start(TOKEN))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)

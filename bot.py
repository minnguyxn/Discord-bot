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
    print(f"✅ Bot sẵn sàng dưới tên {bot.user}")

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
    
@bot.tree.command(name="add_mem", description="MOD thêm người vào sự kiện")
@app_commands.describe(event_name="Tên sự kiện", user="Người cần thêm", numbers="Các số, cách nhau bởi dấu cách (VD: 12 15 99)")
async def add_mem(interaction: discord.Interaction, event_name: str, user: discord.Member, numbers: str):
    # Kiểm tra role MOD
    if not discord.utils.get(interaction.user.roles, name="MOD"):
        await interaction.response.send_message("❌ Bạn không có quyền dùng lệnh này (cần role MOD).", ephemeral=False)
        return

    if event_name not in events:
        await interaction.response.send_message("❌ Sự kiện không tồn tại.", ephemeral=False)
        return

    number_list = []
    try:
        number_list = list(map(int, numbers.split()))
    except ValueError:
        await interaction.response.send_message("❌ Danh sách số không hợp lệ (chỉ dùng số, cách nhau bằng dấu cách).", ephemeral=False)
        return

    max_allowed = get_max_entries(user)
    if max_allowed == 0:
        await interaction.response.send_message("❌ Người này không có role phù hợp (V1–V10).", ephemeral=False)
        return

    current_entries = events[event_name]["entries"].setdefault(str(user.id), [])
    total_after_add = len(current_entries) + len(number_list)

    if total_after_add > max_allowed:
        await interaction.response.send_message(
            f"❌ Người dùng này chỉ được chọn {max_allowed} số. Hiện tại đã chọn {len(current_entries)}, chỉ thêm được {max_allowed - len(current_entries)} số.",
            ephemeral=False)
        return

    # Kiểm tra trùng lặp với người khác
    all_chosen = [n for uid, nums in events[event_name]["entries"].items() for n in nums]
    for n in number_list:
        if n in all_chosen:
            await interaction.response.send_message(f"❌ Số `{n}` đã được chọn bởi người khác.", ephemeral=False)
            return

    # Thêm số
    current_entries.extend(number_list)
    save_events()
    await interaction.response.send_message(f"✅ Đã thêm {user.mention} với các số: {', '.join(map(str, number_list))}", ephemeral=False)


# Khởi chạy bot
if __name__ == "__main__":
    bot.run(TOKEN)

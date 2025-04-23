# main.py
import discord
from discord.ext import commands
from discord import app_commands
from discord.ui import View, Button
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

def load_events():
    global events
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            events = json.load(f)

def save_events():
    with open(DATA_FILE, "w") as f:
        json.dump(events, f)

ROLE_PREFIX = "V"

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

# Thêm UI và phân trang sau
class NumberSelectView(View):
    def __init__(self, interaction, event_name, available_numbers, max_per_user, user_id, page=0):
        super().__init__(timeout=60)
        self.interaction = interaction
        self.event_name = event_name
        self.available_numbers = available_numbers
        self.max_per_user = max_per_user
        self.user_id = user_id
        self.page = page
        self.per_page = 25

        start = page * self.per_page
        end = start + self.per_page
        current_page_numbers = self.available_numbers[start:end]

        for number in current_page_numbers:
            self.add_item(Button(label=str(number), custom_id=f"choose:{number}"))

        if page > 0:
            self.add_item(Button(label="⬅️ Trang trước", custom_id="prev"))
        if end < len(available_numbers):
            self.add_item(Button(label="➡️ Trang sau", custom_id="next"))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.user_id

    @discord.ui.button(label="⏹ Hủy", style=discord.ButtonStyle.red, custom_id="cancel")
    async def cancel_button(self, interaction: discord.Interaction, button: Button):
        await interaction.message.delete()

    async def on_error(self, interaction: discord.Interaction, error: Exception, item):
        await interaction.response.send_message("⚠️ Đã có lỗi xảy ra.", ephemeral=True)

@bot.tree.command(name="choose_number", description="Chọn số với giao diện nút")
@app_commands.describe(event_name="Tên sự kiện")
async def choose_number(interaction: discord.Interaction, event_name: str):
    member = interaction.user
    if event_name not in events:
        await interaction.response.send_message("❌ Sự kiện không tồn tại.", ephemeral=False)
        return
    max_allowed = get_max_entries(member)
    if max_allowed == 0:
        await interaction.response.send_message("❌ Bạn không có role V1–V10.", ephemeral=False)
        return

    event = events[event_name]
    your_entries = event["entries"].get(str(member.id), [])
    if len(your_entries) >= max_allowed:
        await interaction.response.send_message("❌ Bạn đã chọn đủ số lượng.", ephemeral=False)
        return

    all_taken = [n for v in event["entries"].values() for n in v]
    available = [i for i in range(1, 101) if i not in all_taken]

    if not available:
        await interaction.response.send_message("⚠️ Không còn số nào trống.", ephemeral=False)
        return

    view = NumberSelectView(interaction, event_name, available, max_allowed, member.id)
    await interaction.response.send_message(f"🎯 Chọn số cho sự kiện `{event_name}`:", view=view, ephemeral=False)

@bot.event
async def on_interaction(interaction: discord.Interaction):
    if interaction.type == discord.InteractionType.component:
        if interaction.data["custom_id"].startswith("choose:"):
            number = int(interaction.data["custom_id"].split(":")[1])
            user_id = str(interaction.user.id)
            event_name = None

            # Tìm event mà interaction đang xử lý
            for name, ev in events.items():
                entries = ev["entries"].get(user_id, [])
                all_taken = [n for v in ev["entries"].values() for n in v]
                if number not in all_taken and len(entries) < get_max_entries(interaction.user):
                    event_name = name
                    break

            if not event_name:
                await interaction.response.send_message("❌ Không thể chọn số này.", ephemeral=True)
                return

            events[event_name]["entries"].setdefault(user_id, []).append(number)
            save_events()
            await interaction.response.send_message(f"✅ Bạn đã chọn số `{number}`!", ephemeral=False)
            return

        elif interaction.data["custom_id"] == "next" or interaction.data["custom_id"] == "prev":
            message = interaction.message
            embed = message.embeds[0] if message.embeds else None
            content = message.content
            lines = content.split("`")
            if len(lines) < 2:
                return
            event_name = lines[1]
            member = interaction.user
            max_allowed = get_max_entries(member)
            all_taken = [n for v in events[event_name]["entries"].values() for n in v]
            available = [i for i in range(1, 101) if i not in all_taken]
            current_page = int(message.components[0].children[0].custom_id.split(":")[1])
            new_page = current_page + 1 if interaction.data["custom_id"] == "next" else current_page - 1

            view = NumberSelectView(interaction, event_name, available, max_allowed, member.id, new_page)
            await interaction.response.edit_message(view=view)

bot.run(TOKEN)

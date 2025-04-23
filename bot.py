import discord
from discord.ext import commands
from discord import app_commands, ui, Interaction
import json
import os
import random

TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = os.getenv("GUILD_ID")

intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

EVENT_FILE = 'lucky_event.json'
ROLE_PREFIX = "V"
MAX_ROLE_LEVEL = 10

def load_event():
    if not os.path.exists(EVENT_FILE):
        return None
    with open(EVENT_FILE, 'r') as f:
        return json.load(f)

def save_event(data):
    with open(EVENT_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def get_draws_from_roles(member):
    max_draws = 0
    for role in member.roles:
        if role.name.upper().startswith(ROLE_PREFIX):
            try:
                level = int(role.name.upper().replace(ROLE_PREFIX, ""))
                if 1 <= level <= MAX_ROLE_LEVEL:
                    max_draws = max(max_draws, level)
            except:
                continue
    return max_draws

class DrawView(ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=None)
        self.user_id = user_id

    @ui.button(label="🎲 Rút Phiếu", style=discord.ButtonStyle.green)
    async def draw(self, interaction: Interaction, button: ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Bạn không được phép rút phiếu tại đây!", ephemeral=True)
            return

        event = load_event()
        uid = str(interaction.user.id)

        if uid not in event["participants"]:
            await interaction.response.send_message("❌ Bạn chưa đăng ký tham gia!", ephemeral=True)
            return

        p = event["participants"][uid]
        if p["draws_left"] <= 0:
            await interaction.response.send_message("⚠️ Bạn đã hết lượt rút!", ephemeral=True)
            return

        if not event["tickets"]:
            await interaction.response.send_message("❌ Hết phiếu để rút!", ephemeral=True)
            return

        ticket = random.choice(event["tickets"])
        event["tickets"].remove(ticket)
        p["tickets"].append(ticket)
        p["draws_left"] -= 1

        prize = event["prizes"].get(str(ticket), None)
        save_event(event)

        if prize:
            result = f"🎉 Bạn đã rút được **phiếu {ticket}** và trúng **{prize}**!"
        else:
            result = f"Bạn đã rút phiếu **{ticket}** — không trúng giải 😢"

        await interaction.response.send_message(result, ephemeral=True)

@bot.event
async def on_ready():
    print(f"Bot online: {bot.user}")
    try:
        synced = await bot.tree.sync(guild=discord.Object(id=int(GUILD_ID)))
        print(f"Slash commands synced: {len(synced)}")
    except Exception as e:
        print("Sync error:", e)

@bot.tree.command(name="tao_sukien", description="Tạo sự kiện bốc thăm", guild=discord.Object(id=int(GUILD_ID)))
@app_commands.describe(ten_sukien="Tên sự kiện", so_phieu="Số phiếu")
async def tao_sukien(interaction: Interaction, ten_sukien: str, so_phieu: int):
  #  if interaction.user != interaction.channel.owner:
   #     await interaction.response.send_message("❌ Chỉ chủ kênh mới có quyền tạo sự kiện.", ephemeral=True)
    #    return

    tickets = list(range(1, so_phieu + 1))
    prizes = {
        "1": "🎁 Giải Nhất",
        "2": "🥈 Giải Nhì",
        "3": "🥉 Giải Ba"
    }

    event = {
        "event_name": ten_sukien,
        "max_tickets": so_phieu,
        "tickets": tickets,
        "participants": {},
        "prizes": prizes
    }
    save_event(event)
    await interaction.response.send_message(f"✅ Đã tạo sự kiện **{ten_sukien}** với {so_phieu} phiếu.")

@bot.tree.command(name="dangky", description="Đăng ký tham gia", guild=discord.Object(id=int(GUILD_ID)))
async def dangky(interaction: Interaction):
    event = load_event()
    if not event:
        await interaction.response.send_message("❌ Chưa có sự kiện nào được tạo.", ephemeral=True)
        return

    uid = str(interaction.user.id)
    if uid in event["participants"]:
        await interaction.response.send_message("⚠️ Bạn đã đăng ký rồi!", ephemeral=True)
        return

    draws = get_draws_from_roles(interaction.user)
    if draws == 0:
        await interaction.response.send_message("❌ Bạn không có role hợp lệ (V1–V10)!", ephemeral=True)
        return

    event["participants"][uid] = {
        "name": interaction.user.display_name,
        "draws_left": draws,
        "tickets": []
    }
    save_event(event)

    await interaction.response.send_message(
        f"✅ Đăng ký thành công! Bạn có {draws} lượt rút.",
        view=DrawView(interaction.user.id),
        ephemeral=True
    )

bot.run(TOKEN)

import discord
from discord.ext import commands
from discord import app_commands
import json
import os
import urllib.parse
import aiohttp
from pathlib import Path
import traceback
from PIL import Image
from io import BytesIO

# ─── Config ───────────────────────────────────────────────
DATA_FILE = "data/lists.json"
MANAGER_ROLE_NAME = "Archive Manager"
OMDB_API_KEY = "911582c4"

# ─── Data helpers ─────────────────────────────────────────
def load_data() -> dict:
    Path("data").mkdir(parents=True, exist_ok=True)
    if not os.path.exists(DATA_FILE):
        return {"lists": {}, "panel_message": {}}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, dict):
                return {"lists": {}, "panel_message": {}}
            if "lists" not in data or not isinstance(data["lists"], dict):
                data["lists"] = {}
            if "panel_message" not in data or not isinstance(data["panel_message"], dict):
                data["panel_message"] = {}
            return data
    except Exception as e:
        print(f"🚨 [Data Error] فشل قراءة الملف: {e}")
        return {"lists": {}, "panel_message": {}}

def save_data(data: dict):
    Path("data").mkdir(parents=True, exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def can_manage(member: discord.Member) -> bool:
    if not isinstance(member, discord.Member):
        return False
    if member.guild_permissions.administrator:
        return True
    return any(r.name == MANAGER_ROLE_NAME for r in member.roles)

def get_title(item) -> str: return item.get("title", "—") if isinstance(item, dict) else str(item)
def get_poster(item) -> str: return item.get("poster", "") if isinstance(item, dict) else ""
def get_desc(item) -> str: return item.get("desc", "") if isinstance(item, dict) else ""
def get_ratings(item) -> dict: return item.get("ratings", {}) if isinstance(item, dict) else {}
def get_year(item) -> str: return item.get("year", "") if isinstance(item, dict) else ""

# ─── OMDB Async Fetcher ───────────────────────────────────
async def fetch_official_theatrical_details(query: str) -> dict:
    try:
        encoded_query = urllib.parse.quote(query.strip())
        url = f"https://www.omdbapi.com/?apikey={OMDB_API_KEY}&t={encoded_query}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=6) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("Response") == "True":
                        return {
                            "title": data.get("Title", query),
                            "poster": data.get("Poster") if data.get("Poster") != "N/A" else "",
                            "year": data.get("Year", ""),
                            "ratings": {}
                        }
    except Exception as e:
        print(f"🚨 [OMDb API Error]: {e}")
    return {"title": query, "poster": "", "year": "", "ratings": {}}

# ─── برمجية دمج البوسترات بجانب بعضها (Grid Generator) ───
async def generate_grid_image(items: list) -> BytesIO:
    valid_posters = [get_poster(item) for item in items if get_poster(item).startswith("http")]
    if not valid_posters:
        return None

    poster_images = []
    async with aiohttp.ClientSession() as session:
        for url in valid_posters[:15]:
            try:
                async with session.get(url, timeout=5) as resp:
                    if resp.status == 200:
                        img_data = await resp.read()
                        img = Image.open(BytesIO(img_data)).convert("RGB")
                        img = img.resize((200, 300))
                        poster_images.append(img)
            except:
                continue

    if not poster_images:
        return None

    columns = 5  
    rows = (len(poster_images) + columns - 1) // columns
    
    grid_width = columns * 200 + (columns - 1) * 10
    grid_height = rows * 300 + (rows - 1) * 15
    
    grid_img = Image.new("RGB", (grid_width, grid_height), color=(47, 49, 54))

    for idx, img in enumerate(poster_images):
        col = idx % columns
        row = idx // columns
        x = col * (200 + 10)
        y = row * (300 + 15)
        grid_img.paste(img, (x, y))

    final_buffer = BytesIO()
    grid_img.save(final_buffer, format="JPEG", quality=90)
    final_buffer.seek(0)
    return final_buffer

# ─── Modals ───────────────────────────────────────────────
class RenameListModal(discord.ui.Modal):
    def __init__(self, current_list_name: str):
        super().__init__(title="تغيير اسم اللستة")
        self.current_list_name = current_list_name
        self.new_name = discord.ui.TextInput(label="اسم اللستة الجديد", required=True)
        self.add_item(self.new_name)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        new_name = self.new_name.value.strip()
        data = load_data()
        if new_name in data["lists"]:
            await interaction.followup.send("❌ الاسم مستخدم بالفعل.", ephemeral=True)
            return
        if self.current_list_name in data["lists"]:
            data["lists"][new_name] = data["lists"].pop(self.current_list_name)
            save_data(data)
            await return_to_main_panel(interaction)

class RateItemModal(discord.ui.Modal):
    def __init__(self, list_name: str, list_names: list[str]):
        super().__init__(title="تقييم العمل بالنجوم")
        self.list_name = list_name
        self.list_names = list_names
        self.item_number = discord.ui.TextInput(label="رقم الفيلم المراد تقييمه", placeholder="1")
        self.user_rating = discord.ui.TextInput(label="التقييم (من 1 إلى 5)", min_length=1, max_length=1)
        self.add_item(self.item_number)
        self.add_item(self.user_rating)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            num = int(self.item_number.value)
            stars = int(self.user_rating.value)
            if not (1 <= stars <= 5): raise ValueError
        except:
            await interaction.followup.send("❌ إدخال خاطئ.", ephemeral=True)
            return

        data = load_data()
        items = data["lists"].get(self.list_name, {}).get("items", [])
        if num < 1 or num > len(items):
            await interaction.followup.send("❌ الرقم غير موجود.", ephemeral=True)
            return

        user_key = interaction.user.display_name
        items[num - 1].setdefault("ratings", {})[user_key] = stars
        save_data(data)
        await update_view_panel(interaction, self.list_name, items, self.list_names)

class AddItemModal(discord.ui.Modal):
    def __init__(self, list_name: str, list_names: list[str]):
        super().__init__(title="إضافة عمل للستة")
        self.list_name = list_name
        self.list_names = list_names
        self.item_title = discord.ui.TextInput(label="اسم الفيلم أو المسلسل")
        self.item_desc = discord.ui.TextInput(label="الوصف أو التقييم الخاص", style=discord.TextStyle.paragraph, required=False)
        self.add_item(self.item_title)
        self.add_item(self.item_desc)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        details = await fetch_official_theatrical_details(self.item_title.value)
        details["desc"] = self.item_desc.value.strip() if self.item_desc.value else ""
        
        data = load_data()
        if self.list_name in data["lists"]:
            data["lists"][self.list_name]["items"].append(details)
            save_data(data)
            await update_view_panel(interaction, self.list_name, data["lists"][self.list_name]["items"], self.list_names)

# ─── تحديث اللستة وعرض البوسترات المدمجة ──────────────────
async def update_view_panel(interaction: discord.Interaction, list_name: str, items: list, list_names: list[str]):
    embed = discord.Embed(
        title=f"Wonderland • {list_name.upper()}", 
        description="اضغط على الأرقام في الأسفل لعرض تفاصيل ومعلومات أي عمل! 👇", 
        color=0xd3beab
    )
    
    grid_buffer = await generate_grid_image(items)
    file = None
    if grid_buffer:
        file = discord.File(grid_buffer, filename="grid.jpg")
        embed.set_image(url="attachment://grid.jpg")
    else:
        embed.description += "\n*(لا توجد بوسترات متوفرة حالياً للعرض كشبكة)*"

    view = ListView(list_name, items, can_manage(interaction.user), list_names)
    
    # تصحيح طريقة التعديل لتتوافق مع الـ Defer والـ Interaction العادي
    if file:
        if interaction.response.is_done():
            await interaction.message.edit(embeds=[embed], attachments=[file], view=view)
        else:
            await interaction.response.edit_message(embeds=[embed], attachments=[file], view=view)
    else:
        if interaction.response.is_done():
            await interaction.message.edit(embeds=[embed], attachments=[], view=view)
        else:
            await interaction.response.edit_message(embeds=[embed], attachments=[], view=view)

# ─── Dynamic List View (مع أزرار مرقمة تفاعلية) ───────────
class ListView(discord.ui.View):
    def __init__(self, current_list_name: str, items: list, is_manager: bool, list_names: list[str]):
        super().__init__(timeout=None)
        self.current_list_name = current_list_name
        self.items = items
        self.list_names = list_names
        
        self.add_item(ManageButton(current_list_name, list_names))
        self.add_item(HomeButton())
        self.add_item(RateButton(current_list_name, list_names))

        for idx, item in enumerate(items[:15]): 
            btn = discord.ui.Button(
                label=f"{idx+1}", 
                style=discord.ButtonStyle.secondary, 
                custom_id=f"detail_btn_{idx}",
                row=1 if idx < 5 else (2 if idx < 10 else 3)
            )
            btn.callback = self.make_item_callback(idx)
            self.add_item(btn)

    def make_item_callback(self, idx: int):
        async def callback(interaction: discord.Interaction):
            item = self.items[idx]
            title = get_title(item)
            year = get_year(item)
            desc = get_desc(item)
            ratings = get_ratings(item)
            poster = get_poster(item)

            detail_embed = discord.Embed(
                title=f"🎬 {title} ({year})" if year else f"🎬 {title}",
                description=desc or "لا يوجد وصف متوفر لهذا العمل بعد.",
                color=0xd3beab
            )
            if poster:
                detail_embed.set_thumbnail(url=poster)

            if ratings:
                rat_text = ""
                for user, stars in ratings.items():
                    rat_text += f"▫️ **{user}**: {'⭐' * int(stars)}\n"
                detail_embed.add_field(name="👥 تقييمات الأعضاء", value=rat_text, inline=False)

            await interaction.response.send_message(embed=detail_embed, ephemeral=True)
        return callback

# ─── بقية أزرار وقوائم التحكم المساعدة ────────────────────
class RateButton(discord.ui.Button):
    def __init__(self, list_name: str, list_names: list[str]):
        super().__init__(emoji="⭐", style=discord.ButtonStyle.success, row=0)
        self.list_name = list_name
        self.list_names = list_names
    async def callback(self, interaction: discord.Interaction):
        # المودال يتطلب استجابة مباشرة ولا يجب عمل defer قبله
        await interaction.response.send_modal(RateItemModal(self.list_name, self.list_names))

class ManageButton(discord.ui.Button):
    def __init__(self, list_name: str, list_names: list[str]):
        super().__init__(emoji="⚙️", style=discord.ButtonStyle.success, row=0)
        self.list_name = list_name
        self.list_names = list_names
    async def callback(self, interaction: discord.Interaction):
        if not can_manage(interaction.user):
            await interaction.response.send_message("⚠️ لوحة الإدارة للمشرفين فقط!", ephemeral=True)
            return
        embed = discord.Embed(title=f"إدارة — {self.list_name}", description="لوحة التحكم باللستة وتعديلاتها.", color=0xd3beab)
        await interaction.response.edit_message(embeds=[embed], attachments=[], view=ManageDashboardView(self.list_name, self.list_names))

class HomeButton(discord.ui.Button):
    def __init__(self): super().__init__(emoji="🏠", style=discord.ButtonStyle.success, row=0)
    async def callback(self, interaction: discord.Interaction): 
        await return_to_main_panel(interaction)

class ManageDashboardView(discord.ui.View):
    def __init__(self, list_name: str, list_names: list[str]):
        super().__init__(timeout=120)
        self.list_name = list_name
        self.list_names = list_names

    @discord.ui.button(label="➕ إضافة عمل جديد", style=discord.ButtonStyle.primary, row=0)
    async def add_item_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AddItemModal(self.list_name, self.list_names))

    @discord.ui.button(label="📝 تعديل اسم اللستة", style=discord.ButtonStyle.secondary, row=0)
    async def rename_list_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RenameListModal(self.list_name))

    @discord.ui.button(emoji="🏠", label="العودة للستة ورؤية البوسترات", style=discord.ButtonStyle.success, row=1)
    async def back_to_view(self, interaction: discord.Interaction, button: discord.ui.Button):
        # تم إزالة الـ defer العشوائي هنا لأن update_view_panel سيتكفل بالاستجابة لتجنب تعليق الديسكورد
        data = load_data()
        items = data["lists"].get(self.list_name, {}).get("items", [])
        await update_view_panel(interaction, self.list_name, items, self.list_names)

class PanelView(discord.ui.View):
    def __init__(self, list_names: list[str]):
        super().__init__(timeout=None)
        self.list_names = list_names
        for name in list_names:
            btn = discord.ui.Button(label=f"{name}", style=discord.ButtonStyle.danger)
            btn.callback = self.make_callback(name)
            self.add_item(btn)

    def make_callback(self, name: str):
        async def callback(interaction: discord.Interaction):
            data = load_data()
            items = data["lists"].get(name, {}).get("items", [])
            await update_view_panel(interaction, name, items, self.list_names)
        return callback

async def return_to_main_panel(interaction: discord.Interaction):
    data = load_data()
    list_names = list(data["lists"].keys())
    lines = "\n".join(f"🔴 **{k.upper()}** — `{len(v.get('items', []))} Entries`" for k, v in data["lists"].items()) if list_names else "لا توجد قوائم متوفرة."
    embed = discord.Embed(title="Wonderland Lists", description=f"\n{lines}\n", color=0xd3beab)
    
    if interaction.response.is_done():
        await interaction.message.edit(embeds=[embed], attachments=[], view=PanelView(list_names))
    else:
        await interaction.response.edit_message(embeds=[embed], attachments=[], view=PanelView(list_names))

async def refresh_panel(interaction: discord.Interaction, channel: discord.TextChannel):
    data = load_data()
    list_names = list(data["lists"].keys())
    lines = "\n".join(f"🔴 **{k.upper()}** — `{len(v.get('items', []))} Entries`" for k, v in data["lists"].items()) if list_names else "لا توجد قوائم متوفرة."
    embed = discord.Embed(title="Wonderland Lists", description=f"\n{lines}\n", color=0xd3beab)
    msg = await channel.send(embed=embed, view=PanelView(list_names))
    data.setdefault("panel_message", {})[str(interaction.guild.id)] = msg.id
    save_data(data)
    await interaction.followup.send("✅ تم إنشاء اللوحة بنجاح!", ephemeral=True)

# ─── Bot Core Setup ───────────────────────────────────────
class WonderlandBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)
        
    async def setup_hook(self):
        # ربط ومزامنة الأوامر المائلة تلقائياً عند التشغيل حتى لا يظهر البوت أوفلاين
        await self.tree.sync()
        print("✨ [Bot] تم تشغيل ومزامنة الأوامر بنجاح واحترافية!")

bot = WonderlandBot()

@bot.tree.command(name="panel", description="Post/refresh the main dashboard.")
@app_commands.guild_only()
async def cmd_panel(interaction: discord.Interaction):
    if not can_manage(interaction.user): 
        await interaction.response.send_message("❌ لا تملك الصلاحية.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    await refresh_panel(interaction, interaction.channel)

@bot.tree.command(name="list_create", description="Create a new category.")
@app_commands.guild_only()
async def cmd_list_create(interaction: discord.Interaction, name: str):
    if not can_manage(interaction.user): 
        await interaction.response.send_message("❌ لا تملك الصلاحية.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    data = load_data()
    data["lists"][name.strip()] = {"description": "", "items": []}
    save_data(data)
    await interaction.followup.send(f"تم إنشاء القائمة **{name}** بنجاح!", ephemeral=True)

TOKEN = os.environ.get("DISCORD_TOKEN")
bot.run(TOKEN)

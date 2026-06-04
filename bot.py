import discord
from discord.ext import commands
from discord import app_commands
import json
import os
import urllib.request
import urllib.parse
from pathlib import Path

# ─── Config ───────────────────────────────────────────────
DATA_FILE = "data/lists.json"
MANAGER_ROLE_NAME = "Archive Manager"
TMDB_API_KEY = "0bce26c0165650e02aec5943e60395ad"

# ─── Data helpers ─────────────────────────────────────────
def load_data() -> dict:
    Path("data").mkdir(parents=True, exist_ok=True)
    if not os.path.exists(DATA_FILE):
        return {"lists": {}, "panel_message": {}}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_data(data: dict):
    Path("data").mkdir(parents=True, exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def can_manage(member: discord.Member) -> bool:
    if member.guild_permissions.administrator:
        return True
    return any(r.name == MANAGER_ROLE_NAME for r in member.roles)

def get_title(item) -> str:
    return item.get("title", "—") if isinstance(item, dict) else item

def get_poster(item) -> str:
    return item.get("poster", "") if isinstance(item, dict) else ""

def get_desc(item) -> str:
    return item.get("desc", "") if isinstance(item, dict) else ""

def get_ratings(item) -> dict:
    return item.get("ratings", {}) if isinstance(item, dict) else {}

# ─── TMDB Official Primary Poster Fetcher ─────────────────
def fetch_official_theatrical_details(query: str) -> dict:
    try:
        encoded_query = urllib.parse.quote(query)
        url = f"https://api.themoviedb.org/3/search/multi?api_key={TMDB_API_KEY}&query={encoded_query}&language=en-US"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as response:
            res_data = json.loads(response.read().decode('utf-8'))
            results = res_data.get("results", [])
            if results:
                movie = results[0]
                title = movie.get("original_title") or movie.get("original_name") or movie.get("title") or query
                poster_path = movie.get("poster_path")
                poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else ""
                return {"title": title, "poster": poster_url, "ratings": {}}
    except Exception as e:
        print(f"Error fetching from TMDB: {e}")
    return {"title": query, "poster": "", "ratings": {}}

# ─── Equalized Miniature Embeds Builder ───────────────────
def build_separate_embeds(list_name: str, items: list) -> list[discord.Embed]:
    if not items:
        embed = discord.Embed(
            title=f"Wonderland • {list_name.upper()}", 
            description="هذه القائمة فارغة حالياً.", 
            color=0x1a1a1a
        )
        return [embed]
    
    embeds = []
    invisible_filler = "\n\u200b " + " " * 45 + " \u200b"
    
    for i, item in enumerate(items[:10]):
        title = get_title(item)
        desc = get_desc(item)
        poster = get_poster(item)
        ratings = get_ratings(item)
        
        embed = discord.Embed(color=0x1a1a1a)
        embed.title = f"{i+1:02d}. {title}"
        content = f"{desc if desc else 'لا يوجد وصف.'}"
        
        if ratings:
            content += "\n\n**👥 تقييمات الأعضاء:**"
            for user_name, star_count in ratings.items():
                try:
                    stars_display = "⭐" * int(star_count)
                except ValueError:
                    stars_display = "⭐"
                content += f"\n▫️ {user_name}: {stars_display}"
                
        embed.description = f"{content}{invisible_filler}"
        if poster:
            embed.set_thumbnail(url=poster)
            
        embeds.append(embed)
    return embeds

# ─── Modals ───────────────────────────────────────────────
class RateItemModal(discord.ui.Modal, title="تقييم العمل بالنجوم"):
    item_number = discord.ui.TextInput(label="رقم الفيلم المراد تقييمه", placeholder="مثال: 1", required=True)
    user_rating = discord.ui.TextInput(label="التقييم (أدخل رقم من 1 إلى 5 فقط)", placeholder="1 أو 2 أو 3 أو 4 أو 5", min_length=1, max_length=1, required=True)

    def __init__(self, list_name: str, list_names: list[str]):
        super().__init__()
        self.list_name = list_name
        self.list_names = list_names

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            num = int(self.item_number.value)
            stars = int(self.user_rating.value)
            if stars < 1 or stars > 5:
                raise ValueError
        except ValueError:
            await interaction.followup.send("❌ يرجى إدخال أرقام صحيحة، والتقييم بين 1 و 5 نجوم.", ephemeral=True)
            return

        data = load_data()
        items = data["lists"].get(self.list_name, {}).get("items", [])
        if num < 1 or num > len(items):
            await interaction.followup.send("❌ رقم الفيلم غير موجود.", ephemeral=True)
            return

        user_key = interaction.user.display_name
        if "ratings" not in items[num - 1] or not isinstance(items[num - 1]["ratings"], dict):
            items[num - 1]["ratings"] = {}
        items[num - 1]["ratings"][user_key] = stars
        save_data(data)
        
        embeds = build_separate_embeds(self.list_name, items)
        view = ListView(self.list_name, items, can_manage(interaction.user), self.list_names, data["lists"])
        await update_global_panel(interaction, embeds, view)
        await interaction.followup.send(f"✅ تم تسجيل تقييمك بنجاح!", ephemeral=True)

class AddItemModal(discord.ui.Modal, title="إضافة عمل للستة"):
    item_title = discord.ui.TextInput(label="اسم الفيلم أو المسلسل (للبحث)", placeholder="مثال: Iron Man", required=True)
    item_desc = discord.ui.TextInput(label="الوصف أو تقييمك الخاص", style=discord.TextStyle.paragraph, required=False, placeholder="اكتب مراجعتك هنا...")

    def __init__(self, list_name: str, list_names: list[str]):
        super().__init__()
        self.list_name = list_name
        self.list_names = list_names

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        details = fetch_official_theatrical_details(self.item_title.value)
        details["desc"] = self.item_desc.value if self.item_desc.value else "فيلم جميل."
        
        data = load_data()
        if self.list_name in data["lists"]:
            data["lists"][self.list_name]["items"].append(details)
            save_data(data)
            
            items = data["lists"][self.list_name]["items"]
            embeds = build_separate_embeds(self.list_name, items)
            view = ListView(self.list_name, items, can_manage(interaction.user), self.list_names, data["lists"])
            await update_global_panel(interaction, embeds, view)
            await interaction.followup.send(f"✅ تمت إضافة العمل بنجاح!", ephemeral=True)

class ChooseItemToManageModal(discord.ui.Modal, title="اختيار فيلم لإدارته"):
    item_number = discord.ui.TextInput(label="أدخل رقم الفيلم المراد تعديله أو التحكم به", placeholder="مثال: 1", required=True)

    def __init__(self, list_name: str, list_names: list[str]):
        super().__init__()
        self.list_name = list_name
        self.list_names = list_names

    async def on_submit(self, interaction: discord.Interaction):
        try:
            num = int(self.item_number.value)
        except ValueError:
            await interaction.response.send_message("❌ يرجى إدخال رقم صحيح.", ephemeral=True)
            return

        data = load_data()
        items = data["lists"].get(self.list_name, {}).get("items", [])
        if num < 1 or num > len(items):
            await interaction.response.send_message("❌ رقم الفيلم غير موجود في القائمة.", ephemeral=True)
            return

        item = items[num - 1]
        embed = discord.Embed(
            title=f"تعديل العمل: {get_title(item)}",
            description=f"الترتيب الحالي للعمل: **{num}**\nالوصف الحالي: {get_desc(item)}",
            color=0x1a1a1a
        )
        view = ItemEditorDashboard(self.list_name, self.list_names, num, item)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

class EditItemDetailsModal(discord.ui.Modal, title="تعديل تفاصيل العمل"):
    def __init__(self, list_name: str, list_names: list[str], index: int, item: dict):
        super().__init__()
        self.list_name = list_name
        self.list_names = list_names
        self.index = index
        self.item = item
        
        self.new_title = discord.ui.TextInput(label="اسم الفيلم الجديد", default=get_title(item), required=True)
        self.new_desc = discord.ui.TextInput(label="الوصف الجديد", style=discord.TextStyle.paragraph, default=get_desc(item), required=False)
        self.new_order = discord.ui.TextInput(label="الترتيب الجديد في القائمة (رقم)", default=str(index + 1), required=True)
        
        self.add_item(self.new_title)
        self.add_item(self.new_desc)
        self.add_item(self.new_order)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            target_pos = int(self.new_order.value)
        except ValueError:
            await interaction.followup.send("❌ الترتيب يجب أن يكون رقماً صحيحاً.", ephemeral=True)
            return

        data = load_data()
        items = data["lists"].get(self.list_name, {}).get("items", [])
        
        if target_pos < 1 or target_pos > len(items):
            target_pos = len(items)

        curr_item = items.pop(self.index)
        curr_item["title"] = self.new_title.value
        curr_item["desc"] = self.new_desc.value if self.new_desc.value else "لا يوجد وصف."
        
        items.insert(target_pos - 1, curr_item)
        save_data(data)

        embeds = build_separate_embeds(self.list_name, items)
        view = ListView(self.list_name, items, can_manage(interaction.user), self.list_names, data["lists"])
        await update_global_panel(interaction, embeds, view)
        await interaction.followup.send("✅ تم تعديل البيانات وإعادة ترتيب الفيلم بنجاح تام!", ephemeral=True)

# ─── Specialized Item Editor Dashboard ────────────────────
class ItemEditorDashboard(discord.ui.View):
    def __init__(self, list_name: str, list_names: list[str], num: int, item: dict):
        super().__init__(timeout=120)
        self.list_name = list_name
        self.list_names = list_names
        self.index = num - 1
        self.item = item

    @discord.ui.button(label="تعديل (الاسم / الوصف / الترتيب)", style=discord.ButtonStyle.primary)
    async def edit_fields(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(EditItemDetailsModal(self.list_name, self.list_names, self.index, self.item))

    @discord.ui.button(label="حذف هذا الفيلم", style=discord.ButtonStyle.danger)
    async def delete_item(self, interaction: discord.Interaction, button: discord.ui.Button):
        data = load_data()
        items = data["lists"].get(self.list_name, {}).get("items", [])
        if 0 <= self.index < len(items):
            items.pop(self.index)
            save_data(data)
        
        embeds = build_separate_embeds(self.list_name, items)
        view = ListView(self.list_name, items, can_manage(interaction.user), self.list_names, data["lists"])
        await update_global_panel(interaction, embeds, view)
        await interaction.response.edit_message(content="✅ تم حذف الفيلم بنجاح وتحديث اللستة.", embed=None, view=None)

# ─── Manage Dashboard View (لوحة التحكم المحدثة بالألوان الجديدة) ──
class ManageDashboardView(discord.ui.View):
    def __init__(self, list_name: str, list_names: list[str]):
        super().__init__(timeout=60)
        self.list_name = list_name
        self.list_names = list_names

    @discord.ui.button(label="إضافة", style=discord.ButtonStyle.primary, row=0)
    async def add_item_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AddItemModal(self.list_name, self.list_names))

    @discord.ui.button(label="الإدارة", style=discord.ButtonStyle.primary, row=0)
    async def manage_items_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ChooseItemToManageModal(self.list_name, self.list_names))

    # تم تغيير لون حذف اللستة كاملة إلى الأحمر للحماية والتحذير البصري
    @discord.ui.button(label="حذف اللستة كاملة", style=discord.ButtonStyle.danger, row=1)
    async def delete_list_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        data = load_data()
        if self.list_name in data["lists"]:
            del data["lists"][self.list_name]
            save_data(data)
        await return_to_main_panel(interaction)

    @discord.ui.button(emoji="🏠", style=discord.ButtonStyle.success, row=1)
    async def back_to_view(self, interaction: discord.Interaction, button: discord.ui.Button):
        data = load_data()
        items = data["lists"].get(self.list_name, {}).get("items", [])
        embeds = build_separate_embeds(self.list_name, items)
        view = ListView(self.list_name, items, can_manage(interaction.user), self.list_names, data["lists"])
        await interaction.response.edit_message(embeds=embeds, view=view)

# ─── Dynamic List View ────────────────────────────────────
class ListView(discord.ui.View):
    def __init__(self, current_list_name: str, items: list, is_manager: bool, list_names: list[str], all_lists_data: dict):
        super().__init__(timeout=None)
        self.current_list_name = current_list_name
        self.list_names = list_names
        self.all_lists_data = all_lists_data
        
        # أصبحت جميع الأزرار الثلاثية باللون الأخضر المتناسق بناءً على طلبك
        self.add_item(ManageButton(current_list_name, list_names))
        self.add_item(HomeButton())
        self.add_item(RateButton(current_list_name, list_names))

        for name in list_names:
            style = discord.ButtonStyle.danger
            btn = discord.ui.Button(
                label=f"{name}",
                custom_id=f"quick_nav_{name}",
                style=style,
                row=1 if len(list_names) <= 5 else 2
            )
            btn.callback = self.make_navigation_callback(name)
            self.add_item(btn)

    def make_navigation_callback(self, name: str):
        async def callback(interaction: discord.Interaction):
            data  = load_data()
            lst   = data["lists"].get(name)
            if not lst:
                await interaction.response.send_message("القائمة غير موجودة.", ephemeral=True)
                return
            items = lst.get("items", [])
            embeds = build_separate_embeds(name, items)
            view  = ListView(name, items, can_manage(interaction.user), self.list_names, data["lists"])
            await interaction.response.edit_message(embeds=embeds, view=view)
        return callback

# ─── Global Helper functions ──────────────────────────────
async def update_global_panel(interaction: discord.Interaction, embeds, view):
    data = load_data()
    panel_info = data.get("panel_message", {})
    guild_key = str(interaction.guild.id)
    msg_id = panel_info.get(guild_key)
    if msg_id:
        try:
            msg = await interaction.channel.fetch_message(msg_id)
            await msg.edit(embeds=embeds, view=view)
        except discord.NotFound:
            pass

# تم تغيير النجمة للأخضر (success)
class RateButton(discord.ui.Button):
    def __init__(self, list_name: str, list_names: list[str]):
        super().__init__(emoji="⭐", style=discord.ButtonStyle.success, row=0)
        self.list_name = list_name
        self.list_names = list_names

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(RateItemModal(self.list_name, self.list_names))

# تم تغيير الترس للأخضر (success)
class ManageButton(discord.ui.Button):
    def __init__(self, list_name: str, list_names: list[str]):
        super().__init__(emoji="⚙️", style=discord.ButtonStyle.success, row=0)
        self.list_name = list_name
        self.list_names = list_names

    async def callback(self, interaction: discord.Interaction):
        if not can_manage(interaction.user):
            await interaction.response.send_message("⚠️ عذراً، لوحة الإدارة مخصصة للمشرفين فقط!", ephemeral=True)
            return
        embed = discord.Embed(
            title=f"إدارة — {self.list_name}",
            description="التحكم الكامل والذكي بمحتوى وتعديل القائمة وترتيب الأعمال.",
            color=0x1a1a1a
        )
        await interaction.response.edit_message(embeds=[embed], view=ManageDashboardView(self.list_name, self.list_names))

# البيت للأخضر (success)
class HomeButton(discord.ui.Button):
    def __init__(self):
        super().__init__(emoji="🏠", style=discord.ButtonStyle.success, row=0)

    async def callback(self, interaction: discord.Interaction):
        await return_to_main_panel(interaction)

# ─── Main Panel View ──────────────────────────────────────
class PanelView(discord.ui.View):
    def __init__(self, list_names: list[str], all_lists_data: dict):
        super().__init__(timeout=None)
        self.list_names = list_names
        for name in list_names:
            btn = discord.ui.Button(
                label=f"{name}",
                custom_id=f"archive_list_{name}",
                style=discord.ButtonStyle.danger
            )
            btn.callback = self.make_callback(name)
            self.add_item(btn)

    def make_callback(self, name: str):
        async def callback(interaction: discord.Interaction):
            data  = load_data()
            lst   = data["lists"].get(name)
            if not lst:
                await interaction.response.send_message("القائمة غير موجودة.", ephemeral=True)
                return
            items = lst.get("items", [])
            embeds = build_separate_embeds(name, items)
            view  = ListView(name, items, can_manage(interaction.user), self.list_names, data["lists"])
            await interaction.response.edit_message(embeds=embeds, view=view)
        return callback

async def return_to_main_panel(interaction: discord.Interaction):
    data       = load_data()
    list_names = list(data["lists"].keys())
    if list_names:
        lines = "\n".join(f"🔴 **{k.upper()}** —  `{len(v.get('items', []))} Entries`" for k, v in data["lists"].items())
    else:
        lines = "لا توجد قوائم متوفرة حالياً."

    embed = discord.Embed(title="Wonderland Lists", description=f"\n{lines}\n", color=0x1a1a1a)
    view = PanelView(list_names, data["lists"])
    await interaction.response.edit_message(embeds=[embed], view=view)

async def refresh_panel(guild: discord.Guild, channel: discord.TextChannel):
    data       = load_data()
    list_names = list(data["lists"].keys())
    if list_names:
        lines = "\n".join(f"🔴 **{k.upper()}** —  `{len(v.get('items', []))} Entries`" for k, v in data["lists"].items())
    else:
        lines = "لا توجد قوائم متوفرة حالياً."

    embed = discord.Embed(title="Wonderland Lists", description=f"\n{lines}\n", color=0x1a1a1a)
    panel_info = data.get("panel_message", {})
    guild_key  = str(guild.id)
    old_msg_id = panel_info.get(guild_key)
    view       = PanelView(list_names, data["lists"])

    if old_msg_id:
        try:
            old_msg = await channel.fetch_message(old_msg_id)
            await old_msg.edit(embeds=[embed], view=view)
            return
        except discord.NotFound:
            pass

    msg = await channel.send(embed=embed, view=view)
    data.setdefault("panel_message", {})[guild_key] = msg.id
    save_data(data)

# ─── Bot setup ────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True
bot  = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    await tree.sync()

@tree.command(name="panel", description="Post/refresh the main dashboard.")
async def cmd_panel(interaction: discord.Interaction):
    if not can_manage(interaction.user):
        await interaction.response.send_message("⚠️ خطأ: هذا الأمر مخصص للإدارة فقط.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    await refresh_panel(interaction.guild, interaction.channel)
    await interaction.followup.send("تم تحديث الواجهة الرسمية بنجاح.", ephemeral=True)

@tree.command(name="list_create", description="Create a new category.")
@app_commands.describe(name="Category name")
async def cmd_list_create(interaction: discord.Interaction, name: str):
    if not can_manage(interaction.user):
        await interaction.response.send_message("⚠️ خطأ: ليس لديك صلاحية إنشاء قوائم جديدة.", ephemeral=True)
        return
    data = load_data()
    if name in data["lists"]:
        await interaction.response.send_message("القائمة موجودة مسبقاً.", ephemeral=True)
        return
    data["lists"][name] = {"description": "", "items": []}
    save_data(data)
    await interaction.response.send_message(f"تم إنشاء القائمة **{name}** بنجاح!", ephemeral=True)

TOKEN = os.environ.get("DISCORD_TOKEN")
bot.run(TOKEN)

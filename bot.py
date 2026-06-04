import discord
from discord.ext import commands
from discord import app_commands
import json
import os
import urllib.parse
import aiohttp
from pathlib import Path
import traceback

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
        print(f"🚨 [Data Error] فشل قراءة الملف، تم إرجاع هيكل نظيف: {e}")
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

def get_title(item) -> str:
    return item.get("title", "—") if isinstance(item, dict) else str(item)

def get_poster(item) -> str:
    return item.get("poster", "") if isinstance(item, dict) else ""

def get_desc(item) -> str:
    return item.get("desc", "") if isinstance(item, dict) else ""

def get_ratings(item) -> dict:
    return item.get("ratings", {}) if isinstance(item, dict) else {}

def get_year(item) -> str:
    return item.get("year", "") if isinstance(item, dict) else ""

def get_watched_users(item) -> list:
    """جلب قائمة معرفات المستخدمين الذين شاهدوا العمل"""
    return item.get("watched", []) if isinstance(item, dict) else []

# ─── OMDB Async Fetcher ───────────────────────────────────
async def fetch_official_theatrical_details(query: str) -> dict:
    try:
        encoded_query = urllib.parse.quote(query.strip())
        url = f"https://www.omdbapi.com/?apikey={OMDB_API_KEY}&t={encoded_query}"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=6) as response:
                if response.status == 200:
                    res_body = await response.text()
                    data = json.loads(res_body)
                    
                    if data.get("Response") == "True":
                        title = data.get("Title", query)
                        poster = data.get("Poster") if data.get("Poster") != "N/A" else ""
                        year = data.get("Year", "")
                        return {"title": title, "poster": poster, "year": year, "ratings": {}, "watched": []}
    except Exception as e:
        print(f"🚨 [OMDb API Async Error]: {e}")
        
    return {"title": query, "poster": "", "year": "", "ratings": {}, "watched": []}

# ─── Clean Natural Embeds Builder ─────────────────────────
def build_separate_embeds(list_name: str, items: list, current_user_id: int = None) -> list[discord.Embed]:
    if not items:
        embed = discord.Embed(
            title=f"Wonderland • {list_name.upper()}", 
            description="هذه القائمة فارغة حالياً.", 
            color=0xd3beab
        )
        return [embed]
    
    embeds = []
    for i, item in enumerate(items[:10]):
        title = get_title(item)
        desc = get_desc(item).strip()
        poster = get_poster(item)
        ratings = get_ratings(item)
        year = get_year(item)
        watched_list = get_watched_users(item)
        
        embed = discord.Embed(color=0xd3beab)
        
        # إضافة علامة صح بجانب العنوان إذا كان المستخدم الحالي قد شاهد العمل
        is_watched = current_user_id in watched_list if current_user_id else False
        status_prefix = "✅ " if is_watched else ""
        
        embed.title = f"{status_prefix}{i+1:02d}. {title} ({year})" if year else f"{status_prefix}{i+1:02d}. {title}"
        
        content = f"{desc}" if desc else ""
        
        # عرض عدد الأشخاص الذين شاهدوا العمل لزيادة التفاعل
        if watched_list:
            if content: content += "\n\n"
            content += f"👁️ **شاهده:** `{len(watched_list)}` من الأعضاء"

        if ratings:
            if content: content += "\n\n"
            content += "**👥 تقييمات الأعضاء:**"
            for user_name, star_count in ratings.items():
                try:
                    stars_display = "⭐" * int(star_count)
                except ValueError:
                    stars_display = "⭐"
                content += f"\n▫️ {user_name}: {stars_display}"
                
        embed.description = content if content else None
        if poster and poster.startswith("http"):
            embed.set_thumbnail(url=poster)
            
        embeds.append(embed)
    return embeds

# ─── Modals ───────────────────────────────────────────────
class RenameListModal(discord.ui.Modal):
    def __init__(self, current_list_name: str):
        super().__init__(title="تغيير اسم اللستة")
        self.current_list_name = current_list_name
        self.new_name = discord.ui.TextInput(label="اسم اللستة الجديد", placeholder="مثال: MARVEL", required=True)
        self.add_item(self.new_name)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        new_list_name = self.new_name.value.strip()
        
        if not new_list_name:
            await interaction.followup.send("❌ الاسم لا يمكن أن يكون فارغاً.", ephemeral=True)
            return

        data = load_data()
        if new_list_name in data["lists"]:
            await interaction.followup.send("❌ يوجد قائمة أخرى تحمل هذا الاسم بالفعل.", ephemeral=True)
            return

        if self.current_list_name in data["lists"]:
            data["lists"][new_list_name] = data["lists"].pop(self.current_list_name)
            save_data(data)
            await return_to_main_panel(interaction)
            await interaction.followup.send(f"✅ تم تغيير اسم اللستة بنجاح إلى **{new_list_name}**!", ephemeral=True)

class RateItemModal(discord.ui.Modal):
    def __init__(self, list_name: str, list_names: list[str]):
        super().__init__(title="تقييم العمل بالنجوم")
        self.list_name = list_name
        self.list_names = list_names
        
        self.item_number = discord.ui.TextInput(label="رقم الفيلم المراد تقييمه", placeholder="مثال: 1", required=True)
        self.user_rating = discord.ui.TextInput(label="التقييم (أدخل رقم من 1 إلى 5 فقط)", placeholder="1 أو 2 أو 3 أو 4 أو 5", min_length=1, max_length=1, required=True)
        self.add_item(self.item_number)
        self.add_item(self.user_rating)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            num = int(self.item_number.value)
            stars = int(self.user_rating.value)
            if stars < 1 or stars > 5:
                raise ValueError
        except ValueError:
            await interaction.followup.send("❌ يرجى إدخل أرقام صحيحة، والتقييم بين 1 و 5 نجوم.", ephemeral=True)
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
        
        embeds = build_separate_embeds(self.list_name, items, interaction.user.id)
        view = ListView(self.list_name, items, can_manage(interaction.user), self.list_names, data["lists"])
        await update_global_panel(interaction, embeds, view)
        await interaction.followup.send(f"✅ تم تسجيل تقييمك بنجاح!", ephemeral=True)

class AddItemModal(discord.ui.Modal):
    def __init__(self, list_name: str, list_names: list[str]):
        super().__init__(title="إضافة عمل للستة")
        self.list_name = list_name
        self.list_names = list_names
        
        self.item_title = discord.ui.TextInput(label="اسم الفيلم أو المسلسل (للبحث)", placeholder="مثال: Iron Man", required=True)
        self.item_desc = discord.ui.TextInput(label="الوصف أو تقييمك الخاص", style=discord.TextStyle.paragraph, required=False, placeholder="يمكنك ترك هذا الحقل فارغاً تماماً...")
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
            
            items = data["lists"][self.list_name]["items"]
            embeds = build_separate_embeds(self.list_name, items, interaction.user.id)
            view = ListView(self.list_name, items, can_manage(interaction.user), self.list_names, data["lists"])
            await update_global_panel(interaction, embeds, view)
            await interaction.followup.send(f"✅ تمت إضافة العمل بنجاح وبسرعة فائقة عبر OMDB!", ephemeral=True)

class EditItemDetailsModal(discord.ui.Modal):
    def __init__(self, list_name: str, list_names: list[str], index: int, item: dict):
        super().__init__(title="تعديل تفاصيل العمل واختيار مكان الترتيب")
        self.list_name = list_name
        self.list_names = list_names
        self.index = index
        self.item = item
        
        self.new_title = discord.ui.TextInput(label="اسم الفيلم الجديد", default=get_title(item), required=True)
        self.new_desc = discord.ui.TextInput(label="الوصف الجديد (اتركه فارغاً لإلغائه)", style=discord.TextStyle.paragraph, default=get_desc(item), required=False)
        self.new_order = discord.ui.TextInput(label="الترتيب الجديد في القائمة (رقم)", default=str(index + 1), required=True)
        self.new_year = discord.ui.TextInput(label="السنة (مثال: 2008)", default=get_year(item), required=False)
        
        self.add_item(self.new_title)
        self.add_item(self.new_desc)
        self.add_item(self.new_order)
        self.add_item(self.new_year)

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
        curr_item["desc"] = self.new_desc.value.strip() if self.new_desc.value else ""
        curr_item["year"] = self.new_year.value.strip()
        
        items.insert(target_pos - 1, curr_item)
        save_data(data)

        embeds = build_separate_embeds(self.list_name, items, interaction.user.id)
        view = ListView(self.list_name, items, can_manage(interaction.user), self.list_names, data["lists"])
        await update_global_panel(interaction, embeds, view)
        
        await interaction.followup.send("✅ تم تعديل البيانات وإعادة الترتيب بنجاح!", ephemeral=True)
        
        mgr_embed = discord.Embed(
            title=f"إدارة — {self.list_name}",
            description="التحكم الكامل والذكي بمحتوى وتعديل القائمة، ترتيب الأعمال، تغيير اسم اللستة أو حذفها.",
            color=0xd3beab
        )
        await interaction.message.edit(embeds=[mgr_embed], view=ManageDashboardView(self.list_name, self.list_names))

class WatchItemModal(discord.ui.Modal):
    def __init__(self, list_name: str, list_names: list[str]):
        super().__init__(title="تحديث حالة المشاهدة")
        self.list_name = list_name
        self.list_names = list_names
        self.item_number = discord.ui.TextInput(label="رقم الفيلم / المسلسل", placeholder="مثال: 1", required=True)
        self.add_item(self.item_number)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            num = int(self.item_number.value)
        except ValueError:
            await interaction.followup.send("❌ يرجى إدخال رقم صحيح.", ephemeral=True)
            return

        data = load_data()
        items = data["lists"].get(self.list_name, {}).get("items", [])
        if num < 1 or num > len(items):
            await interaction.followup.send("❌ رقم العمل غير موجود بالقائمة.", ephemeral=True)
            return

        target_item = items[num - 1]
        if "watched" not in target_item or not isinstance(target_item["watched"], list):
            target_item["watched"] = []

        user_id = interaction.user.id
        if user_id in target_item["watched"]:
            target_item["watched"].remove(user_id)
            msg = "📥 تم إزالة العمل من قائمة مشاهداتك (لم تشاهده)."
        else:
            target_item["watched"].append(user_id)
            msg = "✅ تم إضافة العمل إلى قائمة مشاهداتك بنجاح!"

        save_data(data)
        
        embeds = build_separate_embeds(self.list_name, items, user_id)
        view = ListView(self.list_name, items, can_manage(interaction.user), self.list_names, data["lists"])
        await interaction.response.edit_message(embeds=embeds, view=view)
        await interaction.followup.send(msg, ephemeral=True)

# ─── Specialized Item Editor Dashboard ────────────────────
class ItemEditorDashboard(discord.ui.View):
    def __init__(self, list_name: str, list_names: list[str], num: int, item: dict):
        super().__init__(timeout=120)
        self.list_name = list_name
        self.list_names = list_names
        self.index = num - 1
        self.item = item

    @discord.ui.button(label="✏️ تعديل (الاسم / الوصف / الترتيب / السنة)", style=discord.ButtonStyle.primary, row=0)
    async def edit_fields(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(EditItemDetailsModal(self.list_name, self.list_names, self.index, self.item))

    @discord.ui.button(label="🗑️ حذف هذا العمل نهائياً", style=discord.ButtonStyle.danger, row=0)
    async def delete_item(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        data = load_data()
        items = data["lists"].get(self.list_name, {}).get("items", [])
        if 0 <= self.index < len(items):
            items.pop(self.index)
            save_data(data)
        
        embeds = build_separate_embeds(self.list_name, items, interaction.user.id)
        view = ListView(self.list_name, items, can_manage(interaction.user), self.list_names, data["lists"])
        await update_global_panel(interaction, embeds, view)
        
        await interaction.followup.send("✅ تم حذف العمل بنجاح وتحديث اللستة!", ephemeral=True)
        
        mgr_embed = discord.Embed(
            title=f"إدارة — {self.list_name}",
            description="التحكم الكامل والذكي بمحتوى وتعديل القائمة، ترتيب الأعمال، تغيير اسم اللستة أو حذفها.",
            color=0xd3beab
        )
        await interaction.message.edit(embeds=[mgr_embed], view=ManageDashboardView(self.list_name, self.list_names))

    @discord.ui.button(label="⬅️ عودة للوحة التحكم", style=discord.ButtonStyle.secondary, row=1)
    async def back_to_mgr(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title=f"إدارة — {self.list_name}",
            description="التحكم الكامل والذكي بمحتوى وتعديل القائمة، ترتيب الأعمال، تغيير اسم اللستة أو حذفها.",
            color=0xd3beab
        )
        await interaction.response.edit_message(embeds=[embed], view=ManageDashboardView(self.list_name, self.list_names))

# ─── Dropdown Component ───────────────────────────────────
class ItemDropdownSelector(discord.ui.Select):
    def __init__(self, list_name: str, list_names: list[str], options: list):
        super().__init__(
            placeholder="🎯 اختر فيلماً أو مسلسلاً للتحكم به مباشرة...",
            min_values=1,
            max_values=1,
            options=options,
            row=2
        )
        self.list_name = list_name
        self.list_names = list_names

    async def callback(self, interaction: discord.Interaction):
        index = int(self.values[0])
        data = load_data()
        items = data["lists"].get(self.list_name, {}).get("items", [])
        
        if index >= len(items):
            await interaction.response.send_message("❌ حدث خطأ، لم يتم العثور على العمل المختار.", ephemeral=True)
            return
        
        item = items[index]
        embed = discord.Embed(
            title=f"🛠️ التحكم بالعمل: {get_title(item)}",
            description=f"**الترتيب الحالي:** {index + 1}\n"
                        f"**السنة:** {get_year(item) or 'غير محددة'}\n"
                        f"**الوصف الحالي:** {get_desc(item) or 'لا يوجد وصف حالي لهذا العمل.'}",
            color=0xd3beab
        )
        await interaction.response.edit_message(embeds=[embed], view=ItemEditorDashboard(self.list_name, self.list_names, index + 1, item))

# ─── Unified Management Dashboard View ────────────────────
class ManageDashboardView(discord.ui.View):
    def __init__(self, list_name: str, list_names: list[str]):
        super().__init__(timeout=120)
        self.list_name = list_name
        self.list_names = list_names
        
        data = load_data()
        items = data["lists"].get(list_name, {}).get("items", [])
        
        options = []
        for i, item in enumerate(items[:25]):
            title = get_title(item)
            year = get_year(item)
            label = f"{i+1:02d}. {title}" + (f" ({year})" if year else "")
            if len(label) > 100:
                label = label[:97] + "..."
            options.append(discord.SelectOption(label=label, value=str(i)))
        
        if options:
            self.add_item(ItemDropdownSelector(list_name, list_names, options))
        else:
            disabled_select = discord.ui.Select(
                placeholder="❌ اللستة فارغة حالياً، لا توجد أعمال لتعديلها.", 
                disabled=True, 
                options=[discord.SelectOption(label="قائمة الأفلام فارغة تماماً", value="empty_fallback")],
                row=2
            )
            self.add_item(disabled_select)

    @discord.ui.button(label="➕ إضافة عمل جديد", style=discord.ButtonStyle.primary, row=0)
    async def add_item_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AddItemModal(self.list_name, self.list_names))

    @discord.ui.button(label="📝 تعديل اسم اللستة", style=discord.ButtonStyle.secondary, row=0)
    async def rename_list_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RenameListModal(self.list_name))

    @discord.ui.button(label="❌ حذف اللستة بالكامل", style=discord.ButtonStyle.danger, row=0)
    async def delete_list_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        data = load_data()
        if self.list_name in data["lists"]:
            del data["lists"][self.list_name]
            save_data(data)
        await return_to_main_panel(interaction)

    @discord.ui.button(emoji="🏠", label="العودة للستة", style=discord.ButtonStyle.success, row=1)
    async def back_to_view(self, interaction: discord.Interaction, button: discord.ui.Button):
        data = load_data()
        items = data["lists"].get(self.list_name, {}).get("items", [])
        embeds = build_separate_embeds(self.list_name, items, interaction.user.id)
        view = ListView(self.list_name, items, can_manage(interaction.user), self.list_names, data["lists"])
        await interaction.response.edit_message(embeds=embeds, view=view)

# ─── Dynamic List View ────────────────────────────────────
class ListView(discord.ui.View):
    def __init__(self, current_list_name: str, items: list, is_manager: bool, list_names: list[str], all_lists_data: dict):
        super().__init__(timeout=None)
        self.current_list_name = current_list_name
        self.list_names = list_names
        self.all_lists_data = all_lists_data
        
        self.add_item(ManageButton(current_list_name, list_names))
        self.add_item(HomeButton())
        self.add_item(RateButton(current_list_name, list_names))
        self.add_item(WatchButton(current_list_name, list_names))  # الزر الجديد الخاص بالمشاهدة لكل مستخدم

        for name in list_names:
            btn = discord.ui.Button(
                label=f"{name}",
                custom_id=f"quick_nav_{name}",
                style=discord.ButtonStyle.danger,
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
            embeds = build_separate_embeds(name, items, interaction.user.id)
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
            msg = await interaction.channel.fetch_message(int(msg_id))
            await msg.edit(embeds=embeds, view=view)
        except Exception:
            pass

class RateButton(discord.ui.Button):
    def __init__(self, list_name: str, list_names: list[str]):
        super().__init__(emoji="⭐", style=discord.ButtonStyle.success, row=0)
        self.list_name = list_name
        self.list_names = list_names

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(RateItemModal(self.list_name, self.list_names))

class WatchButton(discord.ui.Button):
    def __init__(self, list_name: str, list_names: list[str]):
        super().__init__(emoji="✅", label="شاهدته", style=discord.ButtonStyle.primary, row=0)
        self.list_name = list_name
        self.list_names = list_names

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(WatchItemModal(self.list_name, self.list_names))

class ManageButton(discord.ui.Button):
    def __init__(self, list_name: str, list_names: list[str]):
        super().__init__(emoji="⚙️", style=discord.ButtonStyle.success, row=0)
        self.list_name = list_name
        self.list_names = list_names

    async def callback(self, interaction: discord.Interaction):
        if not can_manage(interaction.user):
            await interaction.response.send_message("⚠️ عذراً، لوحة الإدارة مخصصة للمشرفين فقط!", ephemeral=True)
            return
        try:
            embed = discord.Embed(
                title=f"إدارة — {self.list_name}",
                description="التحكم الكامل والذكي بمحتوى وتعديل القائمة، ترتيب الأعمال، تغيير اسم اللستة أو حذفها.",
                color=0xd3beab
            )
            await interaction.response.edit_message(embeds=[embed], view=ManageDashboardView(self.list_name, self.list_names))
        except Exception as e:
            print(f"🚨 خطأ أثناء فتح لوحة التحكم: {e}")
            traceback.print_exc()

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
            embeds = build_separate_embeds(name, items, interaction.user.id)
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

    embed = discord.Embed(title="Wonderland Lists", description=f"\n{lines}\n", color=0xd3beab)
    view = PanelView(list_names, data["lists"])
    await interaction.response.edit_message(embeds=[embed], view=view)

async def refresh_panel(interaction: discord.Interaction, channel: discord.TextChannel):
    data       = load_data()
    list_names = list(data["lists"].keys())
    if list_names:
        lines = "\n".join(f"🔴 **{k.upper()}** —  `{len(v.get('items', []))} Entries`" for k, v in data["lists"].items())
    else:
        lines = "لا توجد قوائم متوفرة حالياً."

    embed = discord.Embed(title="Wonderland Lists", description=f"\n{lines}\n", color=0xd3beab)
    panel_info = data.get("panel_message", {})
    guild_key  = str(interaction.guild.id)
    old_msg_id = panel_info.get(guild_key)
    view       = PanelView(list_names, data["lists"])

    if old_msg_id:
        try:
            old_msg = await channel.fetch_message(int(old_msg_id))
            await old_msg.edit(embeds=[embed], view=view)
            await interaction.followup.send("🔄 تم تحديث لوحة التحكم القديمة بنجاح!", ephemeral=True)
            return
        except discord.NotFound:
            pass
        except Exception as e:
            print(f"🚨 Error updating old message: {e}")

    msg = await channel.send(embed=embed, view=view)
    data.setdefault("panel_message", {})[guild_key] = msg.id
    save_data(data)
    await interaction.followup.send("✅ تم إنشاء لوحة تحكم جديدة بنجاح!", ephemeral=True)

# ─── Bot Core Setup ───────────────────────────────────────
class WonderlandBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        print("✨ [Bot] تم تشغيل البوت بنجاح واستقرار فوري!")

bot = WonderlandBot()
tree = bot.tree

@bot.command(name="sync")
async def manual_sync(ctx):
    if ctx.author.guild_permissions.administrator:
        await ctx.send("⏳ جاري مزامنة أوامر الـ Slash Commands...")
        try:
            synced = await bot.tree.sync()
            await ctx.send(f"✅ تم تحديث ومزامنة {len(synced)} أمر بنجاح!")
        except Exception as e:
            await ctx.send(f"❌ فشلت المزامنة: {e}")
    else:
        await ctx.send("❌ هذا الأمر للمشرفين فقط.")

@tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    print("🚨 [Slash Command Error Error]:")
    traceback.printExc()
    try:
        if interaction.response.is_done():
            await interaction.followup.send(f"❌ حدث خطأ داخلي: {error}", ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ حدث خطأ داخلي: {error}", ephemeral=True)
    except Exception:
        pass

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")

# ─── Slash Commands ───────────────────────────────────────
@tree.command(name="panel", description="Post/refresh the main dashboard.")
@app_commands.guild_only()
async def cmd_panel(interaction: discord.Interaction):
    if not can_manage(interaction.user):
        await interaction.response.send_message("⚠️ خطأ: هذا الأمر مخصص للإدارة فقط.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    try:
        await refresh_panel(interaction, interaction.channel)
    except Exception as e:
        print(f"🚨 Error in panel command: {e}")
        traceback.print_exc()
        await interaction.followup.send("❌ حدث خطأ غير متوقع أثناء تحديث اللوحة.", ephemeral=True)

@tree.command(name="list_create", description="Create a new category.")
@app_commands.guild_only()
@app_commands.describe(name="Category name")
async def cmd_list_create(interaction: discord.Interaction, name: str):
    if not can_manage(interaction.user):
        await interaction.response.send_message("⚠️ خطأ: ليس لديك صلاحية إنشاء قوائم جديدة.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    name = name.strip()
    data = load_data()
    if name in data["lists"]:
        await interaction.followup.send("القائمة موجودة مسبقاً.", ephemeral=True)
        return
    data["lists"][name] = {"description": "", "items": []}
    save_data(data)
    await interaction.followup.send(f"تم إنشاء القائمة **{name}** بنجاح!", ephemeral=True)

TOKEN = os.environ.get("DISCORD_TOKEN")
bot.run(TOKEN)

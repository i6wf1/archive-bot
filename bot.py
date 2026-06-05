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

# ─── OMDB Async Fetcher ───────────────────────────────────
async def fetch_official_theatrical_details(query: str) -> dict:
    try:
        encoded_query = urllib.parse.quote(query.strip())
        url = f"https://www.omdbapi.com/?apikey={OMDB_API_KEY}&t={encoded_query}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=6) as response:
                if response.status == 200:
                    data = json.loads(await response.text())
                    if data.get("Response") == "True":
                        return {
                            "title": data.get("Title", query),
                            "poster": data.get("Poster") if data.get("Poster") != "N/A" else "",
                            "year": data.get("Year", ""),
                            "ratings": {}
                        }
    except Exception as e:
        print(f"🚨 [OMDb Error]: {e}")
    return {"title": query, "poster": "", "year": "", "ratings": {}}

# ─── Embeds Builder ───────────────────────────────────────
def build_separate_embeds(list_name: str, items: list) -> list[discord.Embed]:
    if not items:
        return [discord.Embed(
            title=f"Wonderland • {list_name.upper()}",
            description="هذه القائمة فارغة حالياً.",
            color=0xd3beab
        )]
    embeds = []
    for i, item in enumerate(items[:10]):
        embed = discord.Embed(color=0xd3beab)
        year = get_year(item)
        embed.title = f"{i+1:02d}. {get_title(item)} ({year})" if year else f"{i+1:02d}. {get_title(item)}"
        desc = get_desc(item).strip()
        ratings = get_ratings(item)
        content = desc if desc else ""
        if ratings:
            if content:
                content += "\n\n"
            content += "**👥 تقييمات الأعضاء:**"
            for user_name, star_count in ratings.items():
                try:
                    stars_display = "⭐" * int(star_count)
                except ValueError:
                    stars_display = "⭐"
                content += f"\n▫️ {user_name}: {stars_display}"
        embed.description = content if content else None
        poster = get_poster(item)
        if poster and poster.startswith("http"):
            embed.set_thumbnail(url=poster)
        embeds.append(embed)
    return embeds

def build_panel_embed(data: dict) -> discord.Embed:
    list_names = list(data["lists"].keys())
    if list_names:
        lines = "\n".join(
            f"🔴 **{k.upper()}** —  `{len(v.get('items', []))} Entries`"
            for k, v in data["lists"].items()
        )
    else:
        lines = "لا توجد قوائم متوفرة حالياً."
    return discord.Embed(title="🌿 Wonderland Lists", description=f"\n{lines}\n", color=0xd3beab)

# ─── Silent acknowledge helper ────────────────────────────
async def silent_defer(interaction: discord.Interaction):
    """Acknowledge interaction silently with no visible response."""
    try:
        await interaction.response.defer(ephemeral=True)
    except Exception:
        pass

# ─── Modals ───────────────────────────────────────────────
class RenameListModal(discord.ui.Modal):
    def __init__(self, current_list_name: str):
        super().__init__(title="تغيير اسم اللستة")
        self.current_list_name = current_list_name
        self.new_name = discord.ui.TextInput(label="اسم اللستة الجديد", placeholder="مثال: MARVEL", required=True)
        self.add_item(self.new_name)

    async def on_submit(self, interaction: discord.Interaction):
        new_list_name = self.new_name.value.strip()
        if not new_list_name:
            await interaction.response.defer(ephemeral=True)
            return
        data = load_data()
        if new_list_name in data["lists"]:
            await interaction.response.defer(ephemeral=True)
            return
        if self.current_list_name in data["lists"]:
            data["lists"][new_list_name] = data["lists"].pop(self.current_list_name)
            save_data(data)
        list_names = list(data["lists"].keys())
        embed = build_panel_embed(data)
        view = PanelView(list_names, data["lists"])
        await interaction.response.edit_message(embeds=[embed], view=view)


# ─── Rating: Step 1 — اختيار العمل ───────────────────────
class RateItemSelectView(discord.ui.View):
    """الخطوة الأولى: اختيار الفيلم/المسلسل من dropdown"""
    def __init__(self, list_name: str, list_names: list[str], items: list):
        super().__init__(timeout=120)
        self.list_name = list_name
        self.list_names = list_names
        self.items = items

        options = []
        for i, item in enumerate(items[:25]):
            title = get_title(item)
            year = get_year(item)
            label = f"{i+1:02d}. {title}" + (f" ({year})" if year else "")
            if len(label) > 100:
                label = label[:97] + "..."
            options.append(discord.SelectOption(label=label, value=str(i)))

        select = discord.ui.Select(
            placeholder="اختر العمل المراد تقييمه...",
            min_values=1, max_values=1,
            options=options, row=0
        )
        select.callback = self.on_select
        self.add_item(select)

        # زر إلغاء
        cancel_btn = discord.ui.Button(label="إلغاء", style=discord.ButtonStyle.secondary, row=1)
        cancel_btn.callback = self.on_cancel
        self.add_item(cancel_btn)

    async def on_select(self, interaction: discord.Interaction):
        index = int(interaction.data["values"][0])
        item = self.items[index]
        # الخطوة الثانية: اختيار عدد النجوم
        view = RateStarsView(self.list_name, self.list_names, index, item)
        embed = discord.Embed(
            title=f"⭐ تقييم العمل",
            description=f"**{get_title(item)}**\nاختر عدد النجوم:",
            color=0xd3beab
        )
        await interaction.response.edit_message(embeds=[embed], view=view)

    async def on_cancel(self, interaction: discord.Interaction):
        data = load_data()
        items = data["lists"].get(self.list_name, {}).get("items", [])
        embeds = build_separate_embeds(self.list_name, items)
        view = ListView(self.list_name, items, can_manage(interaction.user), self.list_names, data["lists"])
        await interaction.response.edit_message(embeds=embeds, view=view)


# ─── Rating: Step 2 — اختيار النجوم ──────────────────────
class RateStarsView(discord.ui.View):
    """الخطوة الثانية: اختيار عدد النجوم"""
    def __init__(self, list_name: str, list_names: list[str], index: int, item: dict):
        super().__init__(timeout=120)
        self.list_name = list_name
        self.list_names = list_names
        self.index = index
        self.item = item

        stars_options = [
            discord.SelectOption(label="⭐ نجمة واحدة", value="1"),
            discord.SelectOption(label="⭐⭐ نجمتان", value="2"),
            discord.SelectOption(label="⭐⭐⭐ ثلاث نجوم", value="3"),
            discord.SelectOption(label="⭐⭐⭐⭐ أربع نجوم", value="4"),
            discord.SelectOption(label="⭐⭐⭐⭐⭐ خمس نجوم", value="5"),
        ]
        select = discord.ui.Select(
            placeholder="اختر عدد النجوم...",
            min_values=1, max_values=1,
            options=stars_options, row=0
        )
        select.callback = self.on_stars_select
        self.add_item(select)

        back_btn = discord.ui.Button(label="⬅️ رجوع", style=discord.ButtonStyle.secondary, row=1)
        back_btn.callback = self.on_back
        self.add_item(back_btn)

    async def on_stars_select(self, interaction: discord.Interaction):
        stars = int(interaction.data["values"][0])
        data = load_data()
        items = data["lists"].get(self.list_name, {}).get("items", [])
        if 0 <= self.index < len(items):
            if "ratings" not in items[self.index] or not isinstance(items[self.index]["ratings"], dict):
                items[self.index]["ratings"] = {}
            items[self.index]["ratings"][interaction.user.display_name] = stars
            save_data(data)
        embeds = build_separate_embeds(self.list_name, items)
        view = ListView(self.list_name, items, can_manage(interaction.user), self.list_names, data["lists"])
        await interaction.response.edit_message(embeds=embeds, view=view)
        await update_global_panel_msg(interaction, embeds, view)

    async def on_back(self, interaction: discord.Interaction):
        data = load_data()
        items = data["lists"].get(self.list_name, {}).get("items", [])
        embed = discord.Embed(
            title="⭐ تقييم العمل",
            description="اختر العمل المراد تقييمه:",
            color=0xd3beab
        )
        await interaction.response.edit_message(embeds=[embed], view=RateItemSelectView(self.list_name, self.list_names, items))


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
            embeds = build_separate_embeds(self.list_name, items)
            view = ListView(self.list_name, items, can_manage(interaction.user), self.list_names, data["lists"])
            await update_global_panel_msg(interaction, embeds, view)
        # Return to manage dashboard silently
        mgr_embed = discord.Embed(
            title=f"إدارة — {self.list_name}",
            description="التحكم الكامل والذكي بمحتوى وتعديل القائمة، ترتيب الأعمال، تغيير اسم اللستة أو حذفها.",
            color=0xd3beab
        )
        await interaction.message.edit(embeds=[mgr_embed], view=ManageDashboardView(self.list_name, self.list_names))


class EditItemDetailsModal(discord.ui.Modal):
    def __init__(self, list_name: str, list_names: list[str], index: int, item: dict):
        super().__init__(title="تعديل تفاصيل العمل")
        self.list_name = list_name
        self.list_names = list_names
        self.index = index
        self.new_title = discord.ui.TextInput(label="اسم الفيلم الجديد", default=get_title(item), required=True)
        self.new_desc = discord.ui.TextInput(label="الوصف الجديد (اتركه فارغاً لإلغائه)", style=discord.TextStyle.paragraph, default=get_desc(item), required=False)
        self.new_order = discord.ui.TextInput(label="الترتيب الجديد في القائمة (رقم)", default=str(index + 1), required=True)
        self.new_year = discord.ui.TextInput(label="السنة (مثال: 2008)", default=get_year(item), required=False)
        self.add_item(self.new_title)
        self.add_item(self.new_desc)
        self.add_item(self.new_order)
        self.add_item(self.new_year)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            target_pos = int(self.new_order.value)
        except ValueError:
            await interaction.response.defer(ephemeral=True)
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
        embeds = build_separate_embeds(self.list_name, items)
        view = ListView(self.list_name, items, can_manage(interaction.user), self.list_names, data["lists"])
        await update_global_panel_msg(interaction, embeds, view)
        mgr_embed = discord.Embed(
            title=f"إدارة — {self.list_name}",
            description="التحكم الكامل والذكي بمحتوى وتعديل القائمة، ترتيب الأعمال، تغيير اسم اللستة أو حذفها.",
            color=0xd3beab
        )
        await interaction.response.edit_message(embeds=[mgr_embed], view=ManageDashboardView(self.list_name, self.list_names))


class ReorderListsModal(discord.ui.Modal):
    def __init__(self, list_names: list[str]):
        super().__init__(title="تغيير ترتيب اللستات")
        self.list_names = list_names
        current_order = "\n".join(f"{i+1}. {name}" for i, name in enumerate(list_names))
        self.new_order_input = discord.ui.TextInput(
            label="الترتيب الجديد (اكتب أسماء اللستات)",
            style=discord.TextStyle.paragraph,
            placeholder=current_order,
            default=current_order,
            required=True
        )
        self.add_item(self.new_order_input)

    async def on_submit(self, interaction: discord.Interaction):
        raw_lines = self.new_order_input.value.strip().splitlines()
        new_order = []
        for line in raw_lines:
            line = line.strip()
            if not line:
                continue
            if line[0].isdigit():
                parts = line.split(".", 1)
                if len(parts) == 2:
                    line = parts[1].strip()
            new_order.append(line)
        data = load_data()
        existing = list(data["lists"].keys())
        invalid = [n for n in new_order if n not in existing]
        if invalid:
            await interaction.response.defer(ephemeral=True)
            return
        missing = [n for n in existing if n not in new_order]
        new_order += missing
        data["lists"] = {name: data["lists"][name] for name in new_order}
        save_data(data)
        list_names = list(data["lists"].keys())
        embed = build_panel_embed(data)
        view = PanelView(list_names, data["lists"])
        await interaction.response.edit_message(embeds=[embed], view=view)
        # تحديث رسالة الباول الأصلية
        panel_info = data.get("panel_message", {})
        guild_key = str(interaction.guild.id)
        msg_id = panel_info.get(guild_key)
        if msg_id:
            try:
                msg = await interaction.channel.fetch_message(int(msg_id))
                await msg.edit(embeds=[embed], view=view)
            except Exception:
                pass

# ─── Item Editor Dashboard ────────────────────────────────
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
        data = load_data()
        items = data["lists"].get(self.list_name, {}).get("items", [])
        if 0 <= self.index < len(items):
            items.pop(self.index)
            save_data(data)
        embeds = build_separate_embeds(self.list_name, items)
        view = ListView(self.list_name, items, can_manage(interaction.user), self.list_names, data["lists"])
        await update_global_panel_msg(interaction, embeds, view)
        mgr_embed = discord.Embed(
            title=f"إدارة — {self.list_name}",
            description="التحكم الكامل والذكي بمحتوى وتعديل القائمة، ترتيب الأعمال، تغيير اسم اللستة أو حذفها.",
            color=0xd3beab
        )
        await interaction.response.edit_message(embeds=[mgr_embed], view=ManageDashboardView(self.list_name, self.list_names))

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
            placeholder="✏️ تعديل محتويات اللستة...",
            min_values=1, max_values=1,
            options=options, row=2
        )
        self.list_name = list_name
        self.list_names = list_names

    async def callback(self, interaction: discord.Interaction):
        index = int(self.values[0])
        data = load_data()
        items = data["lists"].get(self.list_name, {}).get("items", [])
        if index >= len(items):
            await interaction.response.defer(ephemeral=True)
            return
        item = items[index]
        embed = discord.Embed(
            title=f"🛠️ التحكم بالعمل: {get_title(item)}",
            description=(
                f"**الترتيب الحالي:** {index + 1}\n"
                f"**السنة:** {get_year(item) or 'غير محددة'}\n"
                f"**الوصف الحالي:** {get_desc(item) or 'لا يوجد وصف حالي لهذا العمل.'}"
            ),
            color=0xd3beab
        )
        await interaction.response.edit_message(embeds=[embed], view=ItemEditorDashboard(self.list_name, self.list_names, index + 1, item))

# ─── Customize List View ──────────────────────────────────
class CustomizeListView(discord.ui.View):
    def __init__(self, list_name: str, list_names: list[str]):
        super().__init__(timeout=120)
        self.list_name = list_name
        self.list_names = list_names

    @discord.ui.button(label="📝 تعديل اسم اللستة", style=discord.ButtonStyle.blurple, row=0)
    async def rename_list_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RenameListModal(self.list_name))

    @discord.ui.button(label="❌ حذف اللستة بالكامل", style=discord.ButtonStyle.danger, row=0)
    async def delete_list_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        data = load_data()
        if self.list_name in data["lists"]:
            del data["lists"][self.list_name]
            save_data(data)
        list_names = list(data["lists"].keys())
        embed = build_panel_embed(data)
        view = PanelView(list_names, data["lists"])
        await interaction.response.edit_message(embeds=[embed], view=view)

    @discord.ui.button(label="🔀 تغيير ترتيب اللستات", style=discord.ButtonStyle.secondary, row=1)
    async def reorder_lists_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        data = load_data()
        list_names = list(data["lists"].keys())
        await interaction.response.send_modal(ReorderListsModal(list_names))

    @discord.ui.button(emoji="⬅️", style=discord.ButtonStyle.secondary, row=1)
    async def back_to_mgr(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title=f"إدارة — {self.list_name}",
            description="التحكم الكامل والذكي بمحتوى وتعديل القائمة، ترتيب الأعمال، تغيير اسم اللستة أو حذفها.",
            color=0xd3beab
        )
        await interaction.response.edit_message(embeds=[embed], view=ManageDashboardView(self.list_name, self.list_names))

# ─── Manage Dashboard View ────────────────────────────────
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
            self.add_item(discord.ui.Select(
                placeholder="❌ اللستة فارغة حالياً، لا توجد أعمال لتعديلها.",
                disabled=True,
                options=[discord.SelectOption(label="قائمة الأفلام فارغة تماماً", value="empty_fallback")],
                row=2
            ))

    @discord.ui.button(emoji="➕", style=discord.ButtonStyle.primary, row=0)
    async def add_item_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AddItemModal(self.list_name, self.list_names))

    @discord.ui.button(emoji="🎨", style=discord.ButtonStyle.blurple, row=0)
    async def customize_list_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title=f"تخصيص اللستة — {self.list_name}",
            description="اختر الإجراء المطلوب:\n\n🗑️ **حذف اللستة بالكامل**\n📝 **تعديل اسم اللستة**\n🔀 **تغيير ترتيب اللستات**",
            color=0x5865F2
        )
        await interaction.response.edit_message(embeds=[embed], view=CustomizeListView(self.list_name, self.list_names))

    @discord.ui.button(emoji="⬅️", style=discord.ButtonStyle.success, row=1)
    async def back_to_view(self, interaction: discord.Interaction, button: discord.ui.Button):
        data = load_data()
        items = data["lists"].get(self.list_name, {}).get("items", [])
        embeds = build_separate_embeds(self.list_name, items)
        view = ListView(self.list_name, items, can_manage(interaction.user), self.list_names, data["lists"])
        await interaction.response.edit_message(embeds=embeds, view=view)

# ─── Buttons ──────────────────────────────────────────────
class RateButton(discord.ui.Button):
    def __init__(self, list_name: str, list_names: list[str]):
        super().__init__(emoji="⭐", style=discord.ButtonStyle.success, row=0)
        self.list_name = list_name
        self.list_names = list_names

    async def callback(self, interaction: discord.Interaction):
        data = load_data()
        items = data["lists"].get(self.list_name, {}).get("items", [])
        if not items:
            await interaction.response.defer(ephemeral=True)
            return
        embed = discord.Embed(
            title="⭐ تقييم العمل",
            description="اختر العمل المراد تقييمه:",
            color=0xd3beab
        )
        await interaction.response.edit_message(embeds=[embed], view=RateItemSelectView(self.list_name, self.list_names, items))


class ManageButton(discord.ui.Button):
    def __init__(self, list_name: str, list_names: list[str]):
        super().__init__(emoji="⚙️", style=discord.ButtonStyle.success, row=0)
        self.list_name = list_name
        self.list_names = list_names

    async def callback(self, interaction: discord.Interaction):
        if not can_manage(interaction.user):
            await interaction.response.defer(ephemeral=True)
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
        data = load_data()
        list_names = list(data["lists"].keys())
        embed = build_panel_embed(data)
        view = PanelView(list_names, data["lists"])
        await interaction.response.edit_message(embeds=[embed], view=view)

# ─── Panel View (with pagination for lists) ───────────────
class PanelView(discord.ui.View):
    def __init__(self, list_names: list[str], all_lists_data: dict, page: int = 0):
        super().__init__(timeout=None)
        self.list_names = list_names
        self.all_lists_data = all_lists_data
        self.page = page

        # Discord: max 5 rows, row 0 for list buttons, row 1 for pagination (if needed)
        LISTS_PER_PAGE = 20  # max buttons per page (rows 0–3, up to 5 per row)
        total_pages = max(1, (len(list_names) + LISTS_PER_PAGE - 1) // LISTS_PER_PAGE)
        start = page * LISTS_PER_PAGE
        page_lists = list_names[start:start + LISTS_PER_PAGE]

        for i, name in enumerate(page_lists):
            row = i // 5  # 5 buttons per row, rows 0-3
            btn = discord.ui.Button(
                label=name,
                custom_id=f"archive_list_{name}_{page}",
                style=discord.ButtonStyle.danger,
                row=row
            )
            btn.callback = self.make_callback(name)
            self.add_item(btn)

        # Pagination buttons on row 4
        if total_pages > 1:
            if page > 0:
                prev_btn = discord.ui.Button(label="◀", style=discord.ButtonStyle.secondary, row=4, custom_id=f"panel_prev_{page}")
                prev_btn.callback = self.make_page_callback(page - 1)
                self.add_item(prev_btn)

            page_indicator = discord.ui.Button(
                label=f"{page + 1} / {total_pages}",
                style=discord.ButtonStyle.secondary,
                row=4,
                disabled=True,
                custom_id="panel_page_indicator"
            )
            self.add_item(page_indicator)

            if page < total_pages - 1:
                next_btn = discord.ui.Button(label="▶", style=discord.ButtonStyle.secondary, row=4, custom_id=f"panel_next_{page}")
                next_btn.callback = self.make_page_callback(page + 1)
                self.add_item(next_btn)

    def make_callback(self, name: str):
        async def callback(interaction: discord.Interaction):
            data = load_data()
            lst = data["lists"].get(name)
            if not lst:
                await interaction.response.defer(ephemeral=True)
                return
            items = lst.get("items", [])
            embeds = build_separate_embeds(name, items)
            view = ListView(name, items, can_manage(interaction.user), self.list_names, data["lists"])
            await interaction.response.edit_message(embeds=embeds, view=view)
        return callback

    def make_page_callback(self, new_page: int):
        async def callback(interaction: discord.Interaction):
            data = load_data()
            list_names = list(data["lists"].keys())
            embed = build_panel_embed(data)
            view = PanelView(list_names, data["lists"], page=new_page)
            await interaction.response.edit_message(embeds=[embed], view=view)
        return callback

# ─── List View ────────────────────────────────────────────
class ListView(discord.ui.View):
    def __init__(self, current_list_name: str, items: list, is_manager: bool, list_names: list[str], all_lists_data: dict):
        super().__init__(timeout=None)
        self.current_list_name = current_list_name
        self.list_names = list_names
        self.all_lists_data = all_lists_data

        self.add_item(ManageButton(current_list_name, list_names))
        self.add_item(HomeButton())
        self.add_item(RateButton(current_list_name, list_names))

        # زر اللستة الحالية كـ indicator — disabled ومضيء يوضح للمستخدم وين هو
        current_btn = discord.ui.Button(
            label=current_list_name,
            style=discord.ButtonStyle.primary,
            disabled=True,
            row=1
        )
        self.add_item(current_btn)

# ─── Global Panel Message Updater ─────────────────────────
async def update_global_panel_msg(interaction: discord.Interaction, embeds, view):
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

async def refresh_panel_silent(bot: commands.Bot):
    """Called on bot ready: re-registers views and edits existing panel messages silently."""
    data = load_data()
    list_names = list(data["lists"].keys())
    embed = build_panel_embed(data)
    view = PanelView(list_names, data["lists"])

    panel_info = data.get("panel_message", {})
    for guild_id_str, msg_id in panel_info.items():
        try:
            guild = bot.get_guild(int(guild_id_str))
            if not guild:
                continue
            # Search all text channels for the message
            for channel in guild.text_channels:
                try:
                    msg = await channel.fetch_message(int(msg_id))
                    await msg.edit(embeds=[embed], view=view)
                    print(f"✅ [Panel] تم تحديث الباول في #{channel.name}")
                    break
                except discord.NotFound:
                    continue
                except discord.Forbidden:
                    continue
                except Exception:
                    continue
        except Exception as e:
            print(f"🚨 [Panel Restore] خطأ: {e}")

async def refresh_panel_interaction(interaction: discord.Interaction, channel: discord.TextChannel):
    """Called by /panel command."""
    data = load_data()
    list_names = list(data["lists"].keys())
    embed = build_panel_embed(data)
    view = PanelView(list_names, data["lists"])
    panel_info = data.get("panel_message", {})
    guild_key = str(interaction.guild.id)
    old_msg_id = panel_info.get(guild_key)

    if old_msg_id:
        try:
            old_msg = await channel.fetch_message(int(old_msg_id))
            await old_msg.edit(embeds=[embed], view=view)
            return
        except discord.NotFound:
            pass
        except Exception as e:
            print(f"🚨 Error updating panel: {e}")

    msg = await channel.send(embed=embed, view=view)
    data.setdefault("panel_message", {})[guild_key] = msg.id
    save_data(data)

# ─── Bot Core ─────────────────────────────────────────────
class WonderlandBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        print("✨ [Bot] setup_hook تم تشغيله")

bot = WonderlandBot()
tree = bot.tree

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    await refresh_panel_silent(bot)

@bot.command(name="sync")
async def manual_sync(ctx):
    if ctx.author.guild_permissions.administrator:
        await ctx.send("⏳ جاري مزامنة الأوامر...")
        try:
            synced = await bot.tree.sync()
            await ctx.send(f"✅ تم تحديث {len(synced)} أمر بنجاح!")
        except Exception as e:
            await ctx.send(f"❌ فشلت المزامنة: {e}")
    else:
        await ctx.send("❌ هذا الأمر للمشرفين فقط.")

@tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    print("🚨 [Slash Command Error]:")
    traceback.print_exc()
    try:
        if not interaction.response.is_done():
            await interaction.response.send_message(".", ephemeral=True, delete_after=0)
    except Exception:
        pass

# ─── Slash Commands ───────────────────────────────────────
@tree.command(name="panel", description="Post/refresh the main dashboard.")
@app_commands.guild_only()
async def cmd_panel(interaction: discord.Interaction):
    await interaction.response.send_message(".", ephemeral=True, delete_after=0)
    try:
        await refresh_panel_interaction(interaction, interaction.channel)
    except Exception as e:
        print(f"🚨 Error in panel command: {e}")
        traceback.print_exc()

@tree.command(name="list_create", description="Create a new category.")
@app_commands.guild_only()
@app_commands.describe(name="Category name")
async def cmd_list_create(interaction: discord.Interaction, name: str):
    await interaction.response.send_message(".", ephemeral=True, delete_after=0)
    if not can_manage(interaction.user):
        return
    name = name.strip()
    data = load_data()
    if name not in data["lists"]:
        data["lists"][name] = {"description": "", "items": []}
        save_data(data)

TOKEN = os.environ.get("DISCORD_TOKEN")
bot.run(TOKEN)

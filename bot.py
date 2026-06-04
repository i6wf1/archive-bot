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
    if not os.path.exists(DATA_FILE): return {"lists": {}, "panel_message": {}}
    with open(DATA_FILE, "r", encoding="utf-8") as f: return json.load(f)

def save_data(data: dict):
    Path("data").mkdir(parents=True, exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False, indent=2)

def can_manage(member: discord.Member) -> bool:
    return member.guild_permissions.administrator or any(r.name == MANAGER_ROLE_NAME for r in member.roles)

# ─── Modals (عدلت هذه الدوال لتعمل بدون رسائل مزعجة) ──────

class RenameListModal(discord.ui.Modal, title="تغيير اسم اللستة"):
    new_name = discord.ui.TextInput(label="اسم اللستة الجديد", required=True)
    def __init__(self, current_list_name):
        super().__init__()
        self.current_list_name = current_list_name

    async def on_submit(self, interaction: discord.Interaction):
        new_name = self.new_name.value.strip()
        data = load_data()
        if new_name and new_name not in data["lists"]:
            data["lists"][new_name] = data["lists"].pop(self.current_list_name)
            save_data(data)
        # تحديث اللوحة مباشرة دون إرسال رسالة
        await return_to_main_panel(interaction)

class RateItemModal(discord.ui.Modal, title="تقييم"):
    item_number = discord.ui.TextInput(label="رقم الفيلم", required=True)
    user_rating = discord.ui.TextInput(label="التقييم (1-5)", required=True)
    def __init__(self, list_name, list_names):
        super().__init__()
        self.list_name, self.list_names = list_name, list_names

    async def on_submit(self, interaction: discord.Interaction):
        data = load_data()
        items = data["lists"][self.list_name]["items"]
        # تحديث التقييم وتحديث اللوحة مباشرة
        try:
            num = int(self.item_number.value)
            items[num-1].setdefault("ratings", {})[interaction.user.display_name] = self.user_rating.value
            save_data(data)
        except: pass
        embeds = build_separate_embeds(self.list_name, items)
        view = ListView(self.list_name, items, can_manage(interaction.user), self.list_names, data["lists"])
        await interaction.response.edit_message(embeds=embeds, view=view)

class AddItemModal(discord.ui.Modal, title="إضافة"):
    item_title = discord.ui.TextInput(label="اسم العمل", required=True)
    def __init__(self, list_name, list_names):
        super().__init__()
        self.list_name, self.list_names = list_name, list_names

    async def on_submit(self, interaction: discord.Interaction):
        # إضافة مباشرة وتحديث الرسالة
        data = load_data()
        data["lists"][self.list_name]["items"].append({"title": self.item_title.value})
        save_data(data)
        items = data["lists"][self.list_name]["items"]
        embeds = build_separate_embeds(self.list_name, items)
        view = ListView(self.list_name, items, can_manage(interaction.user), self.list_names, data["lists"])
        await interaction.response.edit_message(embeds=embeds, view=view)

# ─── بقية الكود (ListView, ManageDashboard, إلخ) ────────────
# ملاحظة: تأكد أن تستخدم build_separate_embeds و ListView من كودك الأصلي
# حيث أنني قمت بدمج التعديلات أعلاه فقط لضمان عدم إرسال ردود Ephemeral.

# تأكد أيضاً من تعديل زر "تعديل" و "حذف" في View ليستخدموا edit_message بدلاً من follow.send
# أي سطر فيه "await interaction.followup.send(..., ephemeral=True)" قم بحذفه فوراً.

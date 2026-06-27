import discord, sys, os, asyncio, io, time, re, aiohttp, random
from dotenv import load_dotenv
from collections import defaultdict
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timedelta
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))
from database.db_logic import DB_Manager
from PIL import Image, ImageDraw, ImageFont, ImageOps
from discord.errors import HTTPException, Forbidden, NotFound
from discord import Interaction, Message

env_path = Path(__file__).parent.parent / "shared.env"
load_dotenv(env_path)
PREFIX = os.getenv('COMMAND_PREFIX')
COMMANDS_CHANNEL, MOD_COMMANDS_CHANNEL = int(os.getenv('COMMANDS_CHANNEL_ID')), int(os.getenv('MOD_COMMANDS_CHANNEL_ID'))
WELCOME_CHANNEL, COUNT_CHANNEL, MOD_LOGS, MOD_LOGS_COMMANDS = int(os.getenv('WELCOME_CHANNEL_ID')), int(os.getenv('COUNT_CHANNEL_ID')), int(os.getenv('MOD_LOGS_CHANNEL_ID')), int(os.getenv('MOD_LOGS_CHANNEL_ID2'))
CATEGORY_TICKET_ID = int(os.getenv('CATEGORY_TICKETS_ID'))
TEMP_CATEGORY_ID = int(os.getenv('TEMP_CATEGORY_ID'))
TRIGGER_CHANNEL_ID = int(os.getenv('TRIGGER_CHANNEL_ID'))
COUNT_ROLE = int(os.getenv('COUNT_BAD_ROLE'))
MUTED_ROLE = int(os.getenv('MUTED_ROLE'))
FIRST_WARN_ROLE, SECOND_WARN_ROLE, THIRD_WARN_ROLE, WARNINGS_CATEGORY_ROLE = int(os.getenv('FIRST_WARN_ROLE')), int(os.getenv('SECOND_WARN_ROLE')), int(os.getenv('THIRD_WARN_ROLE')), int(os.getenv('WARNINGS_CATEGORY_ROLE'))
JOIN_ROLE1, JOIN_ROLE2, JOIN_ROLE3 = int(os.getenv('JOIN_ROLE1')), int(os.getenv('JOIN_ROLE2')), int(os.getenv('JOIN_ROLE3'))
GUILD_ID, DEVELOPER_ID = int(os.getenv('GUILD_ID')),int(os.getenv('DEVELOPER_ID'))
URL_REGEX = r"https?://[^\s]+"
AVAILABLE_PATTERNS = [
    r"\.gif($|\?)",
    r"tenor\.com/view",
    r"giphy\.com/gifs",
    r"klipy\.com/gifs",
    r"gif(s)?\.",
    r"roblox\.com/users/",
    r"steamcommunity\.com/profiles/"
]
SUPPORT_ROLES = [1513487279749074994, 1513487556887449692, 1513487970127183912, 1515424488014221524, 1513261409209811055, 1513271328512147696, 1417895449272258730]
PANEL_CONFIGS = {}
FONT_PATH = "UNCAGE-Regular.ttf"
LEVEL_ROLES = {
    1: 1516414618212503632,
    5: 1513266642988171304,
    10: 1512913425519345674,
}
trusted_bots = {1514273648364753016, 1513553810369417216, 1512556017492295851, 1515369279724195891, 302050872383242240, 575776004233232386, 315926021457051650}

# Настройки бота
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.moderation = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents)

# ========== КЛАССЫ ДЛЯ КНОПОК ==========

class AntiSpam:
    def __init__(self, max_messages=4, time_window=5):
        self.message_history = defaultdict(list)
        self.spam_warnings = defaultdict(int)
        self.muted_users = {}
        self.max_messages = max_messages
        self.time_window = time_window
    
    def is_spam(self, user_id, current_time=None):
        if current_time is None:
            current_time = time.time()
        history = self.message_history[user_id]
        while history and history[0] < current_time - self.time_window:
            history.pop(0)
        history.append(current_time)
        return len(history) > self.max_messages
    
    def add_spam_warning(self, user_id):
        """Добавляет предупреждение за спам"""
        self.spam_warnings[user_id] += 1
        return self.spam_warnings[user_id]
    
    async def is_muted(self, member):
        muted_role = member.guild.get_role(MUTED_ROLE)
        if muted_role:
            return muted_role in member.roles
        return False

    async def mute_user(self, member, duration_seconds):
        muted_role = member.guild.get_role(MUTED_ROLE)
        if not muted_role:
            print("Роль Muted не найдена!")
            return
        await member.add_roles(muted_role, reason=f"Мут на {duration_seconds // 60} минут")
        await asyncio.sleep(duration_seconds)
        await member.remove_roles(muted_role, reason="Окончание мута")
    
    def reset_warnings(self, user_id):
        self.message_history[user_id] = []
        self.spam_warnings[user_id] = 0
        self.muted_users.pop(user_id, None)
    
    def get_spam_warning_count(self, user_id):
        return self.spam_warnings[user_id]
anti_spam = AntiSpam()

# --- 1. Кнопка управления внутри созданного чата тикета ---
class CloseTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    @discord.ui.button(label="зᴀᴋᴩыᴛь ᴛиᴋᴇᴛ", style=discord.ButtonStyle.danger, custom_id="close_channel_btn")
    async def close_channel(self, interaction: discord.Interaction, button: discord.ui.Button):
        is_support = any(r.id in SUPPORT_ROLES or r.name in SUPPORT_ROLES for r in interaction.user.roles)
        if not interaction.user.guild_permissions.administrator and not is_support:
            await safe_send(interaction, "<:warningemoji:1515756604178305054> У вас нет прав для закрытия этого тикета.", ephemeral=True)
            return
        # Отключаем кнопку, чтобы избежать спама кликами
        self.clear_items()
        await safe_edit(interaction, view=self)
        await safe_send(interaction, "<:warningemoji:1515756604178305054> **ᴛиᴋᴇᴛ зᴀᴋᴩыᴛ ᴀдʍиниᴄᴛᴩᴀциᴇй.**\n<:forbiddenemoji:1515780232404144279> ϶ᴛоᴛ ᴋᴀнᴀᴧ будᴇᴛ ᴨоᴧноᴄᴛью удᴀᴧᴇн чᴇᴩᴇз **1 ʍинуᴛу**.")
        await asyncio.sleep(60)
        try:
            await interaction.channel.delete(reason="Тикет закрыт и удален по истечении 1 минуты.")
        except discord.NotFound:
            pass  

# --- 2. Модальное окно анкеты для пользователя (Строго до 5 строк) ---
class DynamicUserModal(discord.ui.Modal):
    def __init__(self, title: str, fields_list: list):
        super().__init__(title=title[:45])
        self.fields_list = fields_list
        self.inputs = []
        # Берем только первые 5 элементов на случай, если админ указал больше
        for label in fields_list[:5]:
            text_input = discord.ui.TextInput(
                label=label[:45],
                placeholder="Введите ответ...",
                required=True,
                max_length=200
            )
            self.add_item(text_input)
            self.inputs.append(text_input)

    async def on_submit(self, interaction: discord.Interaction):
        # Откладываем ответ, чтобы Discord не выдал ошибку из-за создания канала
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        member = interaction.user
        # Настройка приватности для нового канала
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False), # Закрываем для всех
            member: discord.PermissionOverwrite(read_messages=True, send_messages=True, read_message_history=True) # Открываем автору
        }

        # Выдаем доступ ролям тех. поддержки
        for role_id_or_name in SUPPORT_ROLES:
            role = None
            if isinstance(role_id_or_name, int):
                role = guild.get_role(role_id_or_name)
            else:
                role = discord.utils.get(guild.roles, name=role_id_or_name)
            
            if role:
                overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True, read_message_history=True)

        # Получаем указанную категорию
        category = guild.get_channel(CATEGORY_TICKET_ID)
        channel_name = f"╠ticket {member.name}"
        
        # Создаем приватный текстовый канал
        ticket_channel = await guild.create_text_channel(
            name=channel_name,
            category=category,
            overwrites=overwrites,
            reason=f"Тикет для {member}"
        )

        # Формируем красивый эмбед с дубликатом анкеты
        embed = discord.Embed(
            title=f"<:unbanemoji:1515696568156557433> ноʙоᴇ ᴩᴀзобᴧᴀчᴇниᴇ оᴛ {member}",
            description=f"<:successemoji:1515691944460685372> добᴩо ᴨожᴀᴧоʙᴀᴛь ʙ ᴨоддᴇᴩжᴋу, {member.mention}!\n<:techicalemoji:1515678259767939262> оᴨиɯиᴛᴇ ʙᴀɯу ᴨᴩобᴧᴇʍу, ᴇᴄᴧи ϶ᴛо нᴇобходиʍо. ᴀдʍиниᴄᴛᴩᴀция ᴄᴋоᴩо оᴛʙᴇᴛиᴛ ʙᴀʍ.",
            color=discord.Color.darker_grey()
        )
        
        # Заполняем эмбед ответами пользователя
        for text_input in self.inputs:
            if isinstance(text_input, discord.ui.TextInput):
                embed.add_field(name=text_input.label, value=text_input.value, inline=False)

        embed.set_footer(text=f"ID пользователя: {member.id}")

        # Отправляем анкету и кнопку закрытия в САМОЕ НАЧАЛО нового приватного чата
        await safe_send(
            ticket_channel,
            content=f"{member.mention} | ᴀᴅᴍɪɴɪsᴛʀᴀᴛɪᴏɴ",
            embed=embed,
            view=CloseTicketView()
        )
        
        # Сообщаем пользователю (скрыто в системном окне), что чат создан
        await safe_send(interaction, f"Приватный чат успешно создан: {ticket_channel.mention}", ephemeral=True)

# --- 3. Кнопка «Открыть тикет» на главной панели ---
class DynamicUserView(discord.ui.View):
    def __init__(self, custom_id: str):
        super().__init__(timeout=None)
        self.open_ticket_btn.custom_id = custom_id

    @discord.ui.button(label="оᴛᴋᴩыᴛь ᴛиᴋᴇᴛ", style=discord.ButtonStyle.green)
    async def open_ticket_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        fields = PANEL_CONFIGS.get(button.custom_id)
        if not fields:
            await safe_send(interaction, "Ошибка: Настройки панели сброшены.", ephemeral=True)
            return
        await interaction.response.send_modal(DynamicUserModal(title="Заполнение тикета", fields_list=fields))

# --- 4. Конструктор панели для администратора ---
class AdminSetupModal(discord.ui.Modal, title="Конструктор анкеты тикетов"):
    panel_text = discord.ui.TextInput(
        label="Текст над кнопкой в чате",
        style=discord.TextStyle.paragraph,
        max_length=500
    )
    fields_input = discord.ui.TextInput(
        label="Названия строк (ЧЕРЕЗ ЗАПЯТУЮ, МАКСИМУМ 5)",
        placeholder="Имя, Возраст, Ваш вопрос, Игровой ник, Дискорд",
        style=discord.TextStyle.paragraph,
        max_length=250
    )

    def __init__(self, channel: discord.TextChannel):
        super().__init__()
        self.channel = channel

    async def on_submit(self, interaction: discord.Interaction):
        # Парсим вопросы через запятую
        raw_fields = self.fields_input.value.split(",")
        fields = [f.strip() for f in raw_fields if f.strip()]

        if not fields:
            await safe_send(interaction, "Укажите хотя бы один вопрос!", ephemeral=True)
            return

        if len(fields) > 5:
            await safe_send(interaction, "В одном окне Discord поддерживает строго до 5 строк! Сократите количество вопросов.", ephemeral=True)
            return

        panel_id = f"ticket_panel_{interaction.id}"
        PANEL_CONFIGS[panel_id] = fields

        embed = discord.Embed(
            title="<:warnemoji:1515687856549658774> ᴄоздᴀᴛь обᴩᴀщᴇниᴇ",
            description=self.panel_text.value,
            color=discord.Color.darker_grey()
        )
        await safe_send(self.channel, embed=embed, view=DynamicUserView(custom_id=panel_id))
        await safe_send(interaction, "Панель успешно создана!", ephemeral=True)

class TempVoice(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if member.bot:
            return
        # 1. Пользователь ЗАШЁЛ в голосовой канал-триггер
        if after.channel and after.channel.id == TRIGGER_CHANNEL_ID:
            category = await safe_fetch_channel(self.bot, TEMP_CATEGORY_ID)
            if not category:
                print(f"Категория с ID {TEMP_CATEGORY_ID} не найдена!")
                return
            new_channel = await member.guild.create_voice_channel(
                name=f"╠ {member.display_name}'s 𝙘𝙝𝙖𝙣𝙣𝙚𝙡",
                category=category,
                reason=f"Создание временного канала для {member}")
            await new_channel.set_permissions(member, 
                connect=True, 
                manage_channels=True,
                move_members=True)
            await new_channel.set_permissions(member.guild.default_role, connect=True)
            await member.move_to(new_channel)
        # 2. Проверяем ВСЕ временные каналы на пустоту (включая те, откуда пользователь вышел)
        await self.check_empty_temp_channels(member.guild)
    
    async def check_empty_temp_channels(self, guild):
        category = await safe_fetch_channel(self.bot, TEMP_CATEGORY_ID)
        if not category:
            return
        for channel in category.voice_channels:
            if channel.id == TRIGGER_CHANNEL_ID:
                continue
            if len(channel.members) == 0:
                try:
                    await channel.delete(reason="Канал пуст, удаляю.")
                except discord.NotFound:
                    pass
                except discord.Forbidden:
                    print(f"Нет прав для удаления {channel.name}")
                except Exception as e:
                    print(f"Ошибка при удалении {channel.name}: {e}")

class WarningView(discord.ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=10)
        self.user_id = user_id

    @discord.ui.button(label="ᴨочᴇʍу ʍоё ᴄообщᴇниᴇ удᴀᴧᴇно?", style=discord.ButtonStyle.gray)
    async def button_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await safe_send(interaction, "<:forbiddenemoji:1515780232404144279> Это уведомление предназначено не для вас.", ephemeral=True)
        else:
            await safe_send(interaction, "<:grantedemoji:1520173483299049623> В этом канале разрешено отправлять только ссылки на GIF-анимации!", ephemeral=True)

# class ConfirmAction(discord.ui.View):
#     def __init__(self, user_id, action, target):
#         super().__init__(timeout=30)
#         self.user_id = user_id
#         self.action = action
#         self.target = target
#         self.value = None

#     @discord.ui.button(label="✅ Подтвердить", style=discord.ButtonStyle.danger)
#     async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
#         if interaction.user.id != self.user_id:
#             await safe_send(interaction, "<:forbbiden2emoji:1517479332866429008> Это не ваше действие!", ephemeral=True)
#             return
#         self.value = True
#         self.stop()
#     @discord.ui.button(label="❌ Отмена", style=discord.ButtonStyle.secondary)
#     async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
#         if interaction.user.id != self.user_id:
#             await safe_send(interaction, "<:forbbiden2emoji:1517479332866429008> Это не ваше действие!", ephemeral=True)
#             return
#         self.value = False
#         self.stop()

# class ModPanel(discord.ui.View):
#     def __init__(self, moderator, target):
#         super().__init__(timeout=60)
#         self.moderator = moderator
#         self.target = target
    
#     @discord.ui.button(label="Варн", style=discord.ButtonStyle.primary, emoji="⚠️")
#     async def warn_button(self, interaction: discord.Interaction, button: discord.ui.Button):
#         if interaction.user != self.moderator:
#             await safe_send(interaction, "<:forbbiden2emoji:1517479332866429008> Эта панель не для вас!", ephemeral=True)
#             return
#         await interaction.response.send_modal(WarnModal(self.target))
#     @discord.ui.button(label="Мут", style=discord.ButtonStyle.primary, emoji="🔇")
#     async def mute_button(self, interaction: discord.Interaction, button: discord.ui.Button):
#         if interaction.user != self.moderator:
#             await safe_send(interaction, "<:forbbiden2emoji:1517479332866429008> Эта панель не для вас!", ephemeral=True)
#             return
#         await interaction.response.send_modal(MuteModal(self.target))
#     @discord.ui.button(label="Кик", style=discord.ButtonStyle.danger, emoji="👢")
#     async def kick_button(self, interaction: discord.Interaction, button: discord.ui.Button):
#         if interaction.user != self.moderator:
#             await safe_send(interaction, "<:forbbiden2emoji:1517479332866429008> Эта панель не для вас!", ephemeral=True)
#             return
#         view = ConfirmAction(interaction.user.id, "kick", self.target)
#         await safe_send(interaction, f"<:warningemoji:1515756604178305054> Вы уверены, что хотите кикнуть {self.target.mention}?", view=view, ephemeral=True)
#         await view.wait()
#         if view.value:
#             try:
#                 await self.target.kick(reason=f"Кикнут {self.moderator.name}")
#                 await safe_edit(interaction, content=f"<:grantedemoji:1520173483299049623> {self.target.mention} был кикнут!", view=None)
#             except:
#                 await safe_edit(interaction, content="<:forbbiden2emoji:1517479332866429008> Не удалось кикнуть пользователя!", view=None)
#         else:
#             await safe_edit(interaction, content="<:grantedemoji:1520173483299049623> Действие отменено", view=None)
    
#     @discord.ui.button(label="Бан", style=discord.ButtonStyle.danger, emoji="🔨")
#     async def ban_button(self, interaction: discord.Interaction, button: discord.ui.Button):
#         if interaction.user != self.moderator:
#             await interaction.response.send_message("<:forbbiden2emoji:1517479332866429008> Эта панель не для вас!", ephemeral=True)
#             return
        
#         view = ConfirmAction(interaction.user.id, "ban", self.target)
#         await interaction.response.send_message(f"⚠️ Вы уверены, что хотите забанить {self.target.mention}?", view=view, ephemeral=True)
        
#         await view.wait()
#         if view.value:
#             try:
#                 await self.target.ban(reason=f"Забанен {self.moderator.name}")
#                 await interaction.edit_original_response(content=f"✅ {self.target.mention} был забанен!", view=None)
#             except:
#                 await interaction.edit_original_response(content="<:forbbiden2emoji:1517479332866429008> Не удалось забанить пользователя!", view=None)
#         else:
#             await interaction.edit_original_response(content="✅ Действие отменено", view=None)

# class WarnModal(discord.ui.Modal):
#     def __init__(self, target):
#         super().__init__(title="Выдача варна")
#         self.target = target
    
#         reason = discord.ui.TextInput(
#             label="Причина варна",
#             placeholder="Укажите причину...",
#             required=True,
#             max_length=500
#         )
#         self.add_item(self.reason)
    
#     async def on_submit(self, interaction: discord.Interaction):
#         await interaction.response.send_message(f"⚠️ Варн выдан {self.target.mention} по причине: {self.reason.value}", ephemeral=False)
#         # Здесь можно добавить логирование варнов в БД

# class MuteModal(discord.ui.Modal, title="Выдача мута"):
#     def __init__(self, target):
#         super().__init__()
#         self.target = target
    
#         duration = discord.ui.TextInput(
#             label="Длительность (в минутах)",
#             placeholder="10, 30, 60...",
#             required=True
#         )
        
#         reason = discord.ui.TextInput(
#             label="Причина мута",
#             placeholder="Укажите причину...",
#             required=True,
#             max_length=500
#         )

#         self.add_item(self.duration)
#         self.add_item(self.reason)
    
#     async def on_submit(self, interaction: discord.Interaction):
#         try:
#             minutes = int(self.duration.value)
#             duration_seconds = minutes * 60
            
#             # Создаем роль Muted если её нет
#             mute_role = interaction.guild.get_role(MUTED_ROLE)
#             if not mute_role:
#                 mute_role = await interaction.guild.create_role(name="Muted")
#                 for channel in interaction.guild.channels:
#                     await channel.set_permissions(mute_role, send_messages=False, add_reactions=False)
            
#             await self.target.add_roles(mute_role, reason=f"Мут на {minutes} мин. Причина: {self.reason.value}")
#             await interaction.response.send_message(f"🔇 {self.target.mention} получил мут на {minutes} минут. Причина: {self.reason.value}")
            
#             # Авто-снятие мута
#             await asyncio.sleep(duration_seconds)
#             await self.target.remove_roles(mute_role)
            
#         except ValueError:
#             await interaction.response.send_message("<:forbbiden2emoji:1517479332866429008> Неправильный формат времени! Используйте число (минуты)", ephemeral=True)

# ========== ДЕКОРАТОР ==========

def guild_only():
    async def predicate(interaction: discord.Interaction):
        if not interaction.guild:
            await safe_send(interaction, "<:deniedemoji:1519737463126360294> Только на сервере!", ephemeral=True)
            return False
        return True
    return app_commands.check(predicate)

# ========== БЕЗОПАСНАЯ ОТПРАВКА СООБЩЕНИЙ ==========

async def safe_delete(message, delay=0, max_retries=3):
    if delay > 0:
        await asyncio.sleep(delay)
    
    for attempt in range(max_retries):
        try:
            await message.delete()
            return True
        except HTTPException as e:
            if e.status == 429:  # Rate limit
                retry_after = float(e.response.headers.get('Retry-After', 1))
                await asyncio.sleep(retry_after)
                continue
            elif e.status == 403:  # Forbidden - нет прав
                return False
            elif e.status == 404:  # Not Found - уже удалено
                return True
            else:
                return False
        except (Forbidden, NotFound):
            return False
        except:
            return False
    return False

async def safe_reply(message, content=None, max_retries=3, **kwargs):
    if content is None and not kwargs.get('embed') and not kwargs.get('file'):
        return None
    
    for attempt in range(max_retries):
        try:
            return await message.reply(content, **kwargs)
        except HTTPException as e:
            if e.status == 429:  # Rate limit
                retry_after = float(e.response.headers.get('Retry-After', 1))
                await asyncio.sleep(retry_after)
                continue
            else:
                return None
        except:
            return None
    return None

async def safe_send(destination, content=None, max_retries=3, **kwargs):
    if content is None and not kwargs.get('embed') and not kwargs.get('file'):
        return None
    
    # Определяем объект для отправки
    send_target = None
    
    # Проверяем, является ли destination Interaction
    if isinstance(destination, Interaction):
        # Для Interaction используем response или followup
        if not destination.response.is_done():
            # Если ответ еще не отправлен
            for attempt in range(max_retries):
                try:
                    if kwargs.get('ephemeral'):
                        await destination.response.send_message(content, **kwargs)
                    else:
                        await destination.response.send_message(content, **kwargs)
                    return True
                except HTTPException as e:
                    if e.status == 429:
                        retry_after = float(e.response.headers.get('Retry-After', 1))
                        await asyncio.sleep(retry_after)
                        continue
                    else:
                        return None
                except:
                    return None
        else:
            # Если ответ уже отправлен, используем followup
            for attempt in range(max_retries):
                try:
                    return await destination.followup.send(content, **kwargs)
                except HTTPException as e:
                    if e.status == 429:
                        retry_after = float(e.response.headers.get('Retry-After', 1))
                        await asyncio.sleep(retry_after)
                        continue
                    else:
                        return None
                except:
                    return None
        return None
    
    # Для остальных объектов
    if hasattr(destination, 'send'):
        send_target = destination
    elif hasattr(destination, 'channel') and hasattr(destination.channel, 'send'):
        # Для контекста команд
        send_target = destination.channel
    elif hasattr(destination, 'message') and hasattr(destination.message, 'channel'):
        # Для некоторых объектов
        send_target = destination.message.channel
    else:
        return None
    
    for attempt in range(max_retries):
        try:
            return await send_target.send(content, **kwargs)
        except HTTPException as e:
            if e.status == 429:  # Rate limit
                retry_after = float(e.response.headers.get('Retry-After', 1))
                await asyncio.sleep(retry_after)
                continue
            else:
                return None
        except:
            return None
    return None

async def safe_dm_send(user_or_id, content=None, embed=None, view=None, max_retries=3):
    # Получаем пользователя, если передан ID
    if isinstance(user_or_id, int):
        user = await safe_fetch_user(bot, user_or_id)
        if not user:
            print(f"❌ Пользователь {user_or_id} не найден!")
            return False
    else:
        user = user_or_id
    
    # Проверяем, что пользователь существует
    if not user:
        print("❌ Пользователь не указан!")
        return False
    
    # Отправляем с повторными попытками
    for attempt in range(max_retries):
        try:
            await user.send(content=content, embed=embed, view=view)
            return True
            
        except discord.Forbidden:
            print(f"❌ Нет доступа к ЛС {user.name} (закрытые DM или бот заблокирован)")
            return False
            
        except discord.HTTPException as e:
            if e.status == 429:  # Rate Limit
                retry_after = float(e.response.headers.get('Retry-After', 1))
                wait_time = retry_after * (attempt + 1)
                print(f"⏳ Rate limit, ждем {wait_time} сек...")
                await asyncio.sleep(wait_time)
                continue
            else:
                print(f"❌ HTTP ошибка: {e.status}")
                return False
                

async def safe_edit(interaction_or_message, content=None, max_retries=3, **kwargs):
    if content is None and not kwargs.get('embed') and not kwargs.get('view'):
        return None
    if isinstance(interaction_or_message, Interaction):
        interaction = interaction_or_message
        
        for attempt in range(max_retries):
            try:
                # Проверяем, был ли уже ответ
                if interaction.response.is_done():
                    # Если ответ уже отправлен - используем edit_original_response
                    await interaction.edit_original_response(content=content, **kwargs)
                else:
                    # Если ответа еще не было - отправляем новый
                    await interaction.response.send_message(content=content, **kwargs)
                return True
                
            except HTTPException as e:
                if e.status == 429:  # Rate Limit
                    retry_after = float(e.response.headers.get('Retry-After', 1))
                    await asyncio.sleep(retry_after * (attempt + 1))
                    continue
                else:
                    print(f"HTTP ошибка при редактировании Interaction: {e.status}")
                    return False
                    
            except Forbidden:
                print("Нет прав для редактирования Interaction")
                return False
                
            except NotFound:
                print("Interaction или сообщение не найдены")
                return False
                
            except Exception as e:
                print(f"Ошибка при редактировании Interaction: {e}")
                return False
        
        print(f"Не удалось отредактировать Interaction после {max_retries} попыток")
        return False
    
    # ====== РЕДАКТИРОВАНИЕ MESSAGE ======
    elif isinstance(interaction_or_message, Message):
        message = interaction_or_message
        
        for attempt in range(max_retries):
            try:
                return await message.edit(content=content, **kwargs)
                
            except HTTPException as e:
                if e.status == 429:  # Rate Limit
                    retry_after = float(e.response.headers.get('Retry-After', 1))
                    await asyncio.sleep(retry_after * (attempt + 1))
                    continue
                else:
                    print(f"HTTP ошибка при редактировании Message: {e.status}")
                    return None
                    
            except Forbidden:
                print("Нет прав для редактирования Message")
                return None
                
            except NotFound:
                print("Message не найдено")
                return None
                
            except Exception as e:
                print(f"Ошибка при редактировании Message: {e}")
                return None
        
        print(f"Не удалось отредактировать Message после {max_retries} попыток")
        return None
    
    else:
        print("Ошибка: передан не Interaction и не Message")
        return None


async def safe_fetch_channel(bot, channel_id, max_retries=3):
    for attempt in range(max_retries):
        try:
            return await bot.fetch_channel(channel_id)
        except HTTPException as e:
            if e.status == 429:  # Rate Limit
                retry_after = float(e.response.headers.get('Retry-After', 1))
                await asyncio.sleep(retry_after * (attempt + 1))  # Экспоненциальная задержка
                continue
            else:
                print(f"HTTP ошибка при получении канала {channel_id}: {e}")
                return None
                
        except Forbidden:
            print(f"Нет доступа к каналу {channel_id}")
            return None
            
        except NotFound:
            print(f"Канал {channel_id} не найден")
            return None
            
        except Exception as e:
            print(f"Неизвестная ошибка при получении канала {channel_id}: {e}")
            return None
    
    print(f"Не удалось получить канал {channel_id} после {max_retries} попыток")
    return None


async def safe_fetch_user(bot, user_id, max_retries=3):
    for attempt in range(max_retries):
        try:
            return await bot.fetch_user(user_id)
        except HTTPException as e:
            if e.status == 429:
                retry_after = float(e.response.headers.get('Retry-After', 1))
                await asyncio.sleep(retry_after)
                continue
            else:
                return None
        except:
            return None
    return None

# === ГЕНЕРАЦИЯ КАРТИНКИ (Pillow) ===
async def generate_level_card(username: str, avatar_url: str, level: int, current_xp: int, next_level_xp: int, role_name: str) -> io.BytesIO:
    width, height = 600, 200
    card = Image.new("RGBA", (width, height), (24, 25, 28, 255))
    draw = ImageDraw.Draw(card)
    
    async with aiohttp.ClientSession() as session:
        async with session.get(avatar_url) as response:
            if response.status == 200:
                avatar_bytes = await response.read()
                avatar_img = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA")
            else:
                avatar_img = Image.new("RGBA", (120, 120), (100, 100, 100, 255))

    avatar_img = avatar_img.resize((120, 120))
    mask = Image.new("L", (120, 120), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.ellipse((0, 0, 120, 120), fill=255)
    avatar_rounded = ImageOps.fit(avatar_img, (120, 120), centering=(0.5, 0.5))
    avatar_rounded.putalpha(mask)
    
    card.paste(avatar_rounded, (40, 40), avatar_rounded)
    
    try:
        font_name = ImageFont.truetype(FONT_PATH, 28)
        font_info = ImageFont.truetype(FONT_PATH, 22)
        font_sub = ImageFont.truetype(FONT_PATH, 16)
    except IOError:
        font_name = font_info = font_sub = ImageFont.load_default()

    draw.text((190, 35), username, font=font_name, fill=(255, 255, 255, 255))
    draw.text((190, 75), f"Уровень: {level}", font=font_info, fill=(114, 137, 218, 255))
    draw.text((190, 110), f"Роль по лвлу: {role_name}", font=font_sub, fill=(185, 187, 190, 255))
    
    xp_text = f"{current_xp} / {next_level_xp} XP"
    draw.text((560, 125), xp_text, font=font_sub, fill=(185, 187, 190, 255), anchor="ra")

    bar_x, bar_y = 190, 150
    bar_width, bar_height = 370, 16
    
    draw.rounded_rectangle([bar_x, bar_y, bar_x + bar_width, bar_y + bar_height], radius=8, fill=(47, 49, 54, 255))
    
    xp_percentage = min(current_xp / next_level_xp, 1.0)
    if xp_percentage > 0:
        current_bar_width = int(bar_width * xp_percentage)
        draw.rounded_rectangle([bar_x, bar_y, bar_x + current_bar_width, bar_y + bar_height], radius=8, fill=(114, 137, 218, 255))

    image_binary = io.BytesIO()
    card.save(image_binary, "PNG")
    image_binary.seek(0)
    return image_binary

def warn_text(num):
    return {1: "ⲡⲉⲣⲃыⲙ", 2: "ⲃⲧⲟⲣыⲙ", 3: "ⲧⲣⲉⲧьⲉⲙ"}.get(num, "очᴇᴩᴇдныʍ")

async def warn_user(interaction: discord.Interaction, member: discord.Member = None, reason: str ="Не указана"):
    global warns
    if not member:
        await safe_send(interaction, "<:forbiddenemoji:1515780232404144279> Укажите пользователя!", ephemeral=True)
        return
    roles = {
        'category': member.guild.get_role(WARNINGS_CATEGORY_ROLE),
        1: member.guild.get_role(FIRST_WARN_ROLE),
        2: member.guild.get_role(SECOND_WARN_ROLE),
        3: member.guild.get_role(THIRD_WARN_ROLE)
    }
    for key, role in roles.items():
        if not role:
            await safe_send(interaction, f"<:forbiddenemoji:1515780232404144279> Роль {key} не найдена!", ephemeral=True)
            return

    user_id = member.id
    user_data = await manager.get_user_ruler(user_id)
    if not user_data:
        await safe_send(interaction, "<:forbiddenemoji:1515780232404144279> Пользователь не найден в базе данных!", ephemeral=True)
        return
    current_warns = user_data.get("warnings", 0)
    next_warn = current_warns + 1
    if next_warn <= 3:
        # Убираем старую роль
        if current_warns > 0 and roles.get(current_warns):
            try:
                await member.remove_roles(roles[current_warns])
            except discord.NotFound:
                pass
            except Exception as e:
                print(f"Ошибка снятия роли: {e}")
        # Добавляем новую роль
        try:
            await member.add_roles(roles[next_warn], reason=f"Предупреждение #{next_warn}. Причина: {reason}")
        except discord.NotFound:
            await safe_send(interaction, "<:forbiddenemoji:1515780232404144279> Роль не найдена!", ephemeral=True)
            return
        except Exception as e:
            await safe_send(interaction, f"<:forbiddenemoji:1515780232404144279> Ошибка: {e}", ephemeral=True)
            return
        
        await safe_send(
            interaction,
            f"<:warnemoji:1515687856549658774> {member.mention} нᴀᴋᴀзᴀн **{warn_text(next_warn)}** ᴨᴩᴇдуᴨᴩᴇждᴇниᴇʍ! ᴨᴩичинᴀ: {reason}",
            ephemeral=False)
        
        # ✅ Бан при 3 предупреждениях
        if next_warn == 3:
            try:
                await member.ban(reason=f"3 предупреждения. {reason} (Модератор: {interaction.user})")
                await safe_send(
                    interaction,
                    f"<:neutralizeemoji:1515694760990347325> {member.mention} **быᴧ нᴇйᴛᴩᴀᴧизоʙᴀн** зᴀ ᴨᴧохоᴇ ᴨоʙᴇдᴇниᴇ...")
            except discord.Forbidden:
                await safe_send(interaction, "<:forbiddenemoji:1515780232404144279> Нет прав для бана пользователя!", ephemeral=True)
            except Exception as e:
                await safe_send(interaction, f"<:forbiddenemoji:1515780232404144279> Ошибка при бане: {e}", ephemeral=True)
    
    # ✅ Добавляем категорию предупреждений
    if not any(role.id == WARNINGS_CATEGORY_ROLE for role in member.roles):
        try:
            await member.add_roles(roles['category'])
        except Exception as e:
            print(f"Ошибка добавления категории: {e}")
    
    # ✅ Обновляем данные в базе данных
    try:
        await manager.update_user_ruler(user_id, next_warn, user_data.get('reputation', 0), user_data.get('last_time_reputation', 0.0))
    except Exception as e:
        print(f"Ошибка обновления данных: {e}")
    return next_warn

async def send_dm_welcome(member: discord.Member):
    try:
        dm_embed = discord.Embed(
        title=f"Добро пожаловать в {member.guild.name}!",
        description="Спасибо, что присоединились к нашему сообществу!\n\n"
                    "📖 Ознакомьтесь с правилами в канале #rules \n"
                    "🎉 Представьтесь в канале #chat \n"
                    "❓ Если есть вопросы, пишите в #вопросы",
        color=discord.Color.darker_grey()
        )
        dm_embed.set_image(url='https://aniyuki.com/wp-content/uploads/2022/08/aniyuki-hello-19.gif')
        await safe_dm_send(member, embed=dm_embed)
    except discord.Forbidden:
        print(f"Не могу отправить DM пользователю {member.name} (закрытые ЛС)")
    except discord.HTTPException as e:
        print(f"Ошибка при отправке DM: {e}")
    except Exception as e:
        print(f"Неизвестная ошибка: {e}")

# ========== КОМАНДЫ НАСТРОЙКИ ==========

@bot.tree.command(name='sync', description='Синхронизировать команды.')
@app_commands.guild_only()
@app_commands.default_permissions(administrator=True)
async def sync(interaction: discord.Interaction):
    if interaction.user.id != DEVELOPER_ID:
        await safe_send(interaction, "<:forbbiden2emoji:1517479332866429008> У тебя нет прав для этой команды.", ephemeral=True)
        return
    bot.tree.clear_commands(guild=None)
    await bot.tree.sync(guild=None)
    await safe_send(interaction, "✅ Команды синхронизированы для текущего сервера.", ephemeral=False)

@bot.tree.command(name='update', description='Обновить текстовые каналы.')
@app_commands.guild_only()
@app_commands.default_permissions(administrator=True)
async def update_command_chats(interaction: discord.Interaction):
    if interaction.user.id != DEVELOPER_ID:
        await safe_send(interaction, "<:forbbiden2emoji:1517479332866429008> У тебя нет прав для этой команды.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    mute_role = interaction.guild.get_role(MUTED_ROLE)
    count_role = interaction.guild.get_role(COUNT_ROLE)
    special_role = interaction.guild.get_role(LEVEL_ROLES["1"])
    if not mute_role or not count_role:
        await safe_send(interaction, "<:forbbiden2emoji:1517479332866429008> Роли не найдены!", ephemeral=True)
        return
    text_count = 0
    voice_count = 0
    errors = []    
    # Текстовые каналы
    for channel in interaction.guild.channels:
        # Пропускаем категории
        if isinstance(channel, discord.CategoryChannel):
            continue
        try:
            # ✅ Используем safe_fetch_channel для безопасности
            safe_channel = await safe_fetch_channel(interaction.client, channel.id, max_retries=2)
            if not safe_channel:
                errors.append(f"❌ Не удалось получить канал {channel.name}")
                continue
            # Устанавливаем права для MUTE роли
            await safe_channel.set_permissions(
                mute_role,
                send_messages=False,
                add_reactions=False)
            default_role = interaction.guild.default_role
            await channel.set_permissions(
                default_role,
                send_messages=False,
                attach_files=False,
                embed_links=False)
            channel1 = await safe_fetch_channel(bot, 1468672431144173834)
            channel2 = await safe_fetch_channel(bot, 1513070963955335238)
            for special_channel in [channel1, channel2]:
                await special_channel.set_permissions(
                    special_role,
                    send_messages=True,
                    attach_files=True,
                    embed_links=True)
            # Специальные права для COUNT_CHANNEL
            if channel.id == COUNT_CHANNEL:
                await safe_channel.set_permissions(
                    count_role,
                    send_messages=False,
                    add_reactions=False)
            text_count += 1
        except discord.Forbidden:
            errors.append(f"❌ Нет прав для канала {channel.name}")
        except discord.HTTPException as e:
            if e.status == 429:  # Rate Limit
                await asyncio.sleep(1)
                continue
            errors.append(f"❌ Ошибка в канале {channel.name}: {e}")
        except Exception as e:
            errors.append(f"❌ Ошибка в канале {channel.name}: {e}")
    
    # ✅ Голосовые каналы
    for voice_channel in interaction.guild.voice_channels:
        try:
            # ✅ Используем safe_fetch_channel
            safe_channel = await safe_fetch_channel(interaction.client, voice_channel.id, max_retries=2)
            if not safe_channel:
                errors.append(f"❌ Не удалось получить голосовой канал {voice_channel.name}")
                continue
            await safe_channel.set_permissions(
                mute_role,
                connect=False,
                speak=False)
            voice_count += 1
        except discord.Forbidden:
            errors.append(f"❌ Нет прав для голосового канала {voice_channel.name}")
        except discord.HTTPException as e:
            if e.status == 429:
                await asyncio.sleep(1)
                continue
            errors.append(f"❌ Ошибка в голосовом канале {voice_channel.name}: {e}")
        except Exception as e:
            errors.append(f"❌ Ошибка в голосовом канале {voice_channel.name}: {e}")
    result_message = f"✅ Обновление прав завершено!\n"
    result_message += f"📝 Текстовых каналов: {text_count}\n"
    result_message += f"🎤 Голосовых каналов: {voice_count}"
    if errors:
        result_message += f"\n\n⚠️ Ошибок: {len(errors)}"
        if len(errors) > 5:
            result_message += f"\nПервые 5 ошибок:\n" + "\n".join(errors[:5])
        else:
            result_message += f"\n" + "\n".join(errors)
    await safe_send(interaction, result_message, ephemeral=True)

# ========== КОМАНДЫ МОДЕРАЦИИ ==========

@bot.tree.command(name="create_ticket", description="Создать панель тикета.")
@app_commands.guild_only()
@app_commands.default_permissions(administrator=True)
async def create_ticket(interaction: discord.Interaction):
    await interaction.response.send_modal(AdminSetupModal(channel=interaction.channel))

@bot.tree.command(name='удалить_сообщения', description='Очистить чат.')
@app_commands.guild_only()
@app_commands.default_permissions(administrator=True)
async def clear_messages(interaction: discord.Interaction, amount: int = None):
    if amount is None:
        amount = 10
    elif amount > 100:
        amount = 100
    elif amount < 0:
        await safe_send(interaction, "<:forbbiden2emoji:1517479332866429008> Количество должно быть больше 0!", ephemeral=True)
        return
    safe_user = await safe_fetch_user(interaction.client, interaction.user.id)
    if safe_user:
        user_mention = safe_user.mention
        user_avatar = safe_user.display_avatar.url if safe_user.display_avatar else None
    log_channel = await safe_fetch_channel(interaction.client, MOD_LOGS_COMMANDS)
    await safe_send(interaction, f"<:clearemoji:1515691240476377218> удᴀᴧᴇниᴇ {amount} ᴄообщᴇний...", ephemeral=True)
    try:
        deleted = await interaction.channel.purge(limit=amount)
        await safe_edit(interaction, content=f"<:successemoji:1515691944460685372> удᴀᴧᴇно {len(deleted)} ᴄообщᴇний")
        if log_channel:
            try:
                embed = discord.Embed(
                    title="<:clearemoji:1515691240476377218> /удалить_сообщения",
                    description=f"`ʍодᴇᴩᴀᴛоᴩ`: {user_mention} <:forbbiden2emoji:1517479332866429008>\n"
                                f"`удᴀᴧиᴧ ᴄообщᴇний`: {amount} <:successemoji:1515691944460685372>\n"
                                f"`ᴋᴀнᴀᴧ`: {interaction.channel.mention} <:clearemoji:1515691240476377218>",
                    color=discord.Color.darker_grey(),
                    timestamp=interaction.created_at
                )
                if user_avatar:
                    embed.set_thumbnail(url=user_avatar)
                await safe_send(log_channel, embed=embed)
            except Exception as e:
                print(f"Ошибка отправки лога: {e}")
    except discord.Forbidden:
        await safe_edit(
            interaction,
            content="<:forbbiden2emoji:1517479332866429008> Нет прав на удаление сообщений!")
    except discord.HTTPException as e:
        await safe_edit(
            interaction,
            content=f"<:forbbiden2emoji:1517479332866429008> Ошибка: {e}")
    except Exception as e:
        await safe_edit(
            interaction,
            content=f"<:forbbiden2emoji:1517479332866429008> Ошибка при удалении: {e}")

@bot.tree.command(name='выгнать', description='Выгнать пользователя.')
@app_commands.guild_only()
@app_commands.default_permissions(kick_members=True)
async def kick_member(interaction: discord.Interaction, member: discord.Member, reason: str = "Не указана"):
    """Кикает участника"""
    if not interaction.user.guild_permissions.kick_members:
        await safe_send(interaction, "<:forbbiden2emoji:1517479332866429008> У вас нет прав на кик!", ephemeral=True)
        return
    if member == interaction.user:
        await safe_send(interaction, "<:forbbiden2emoji:1517479332866429008> Нельзя кикнуть самого себя!", ephemeral=True)
        return
    if member.guild_permissions.administrator:
        await safe_send(interaction, "<:forbbiden2emoji:1517479332866429008> Нельзя кикнуть администратора!", ephemeral=True)
        return
    if member.bot:
        await safe_send(interaction, "🤖 Нельзя модерировать бота!", ephemeral=True)
        return
    # ✅ Проверяем, что пользователь на сервере
    if not interaction.guild.get_member(member.id):
        await safe_send(interaction, "<:forbbiden2emoji:1517479332866429008> Пользователь не на сервере!", ephemeral=True)
        return
    safe_user = await safe_fetch_user(interaction.client, member.id)
    if safe_user:
        user_mention = safe_user.mention
        user_avatar = safe_user.display_avatar.url if safe_user.display_avatar else None
    # ✅ Получаем канал логов
    log_channel = await safe_fetch_channel(interaction.client, MOD_LOGS_COMMANDS)
    try:
        await member.kick(reason=f"{reason} (Модератор: {interaction.user})")
        
        # ✅ Отправляем сообщение
        await safe_send(interaction, f"<:kickemoji:1515693208783425617> {user_mention} **ʙᴩᴇʍᴇнно оᴛᴄᴛᴩᴀнён**. ᴨᴩичинᴀ: {reason}", ephemeral=False)
        # ✅ Отправляем лог
        if log_channel:
            try:
                embed = discord.Embed(
                    title="<:kickemoji:1515693208783425617> /выгнать",
                    description=f"`ʍодᴇᴩᴀᴛоᴩ`: {interaction.user.mention} <:forbbiden2emoji:1517479332866429008>\n"
                                f"`ᴨоᴧьзоʙᴀᴛᴇᴧь`: {user_mention} <:reputationemoji:1517480379286556832>\n"
                                f"`ᴨᴩичинᴀ`: {reason} <:clearemoji:1515691240476377218>",
                    color=discord.Color.brand_red(),
                    timestamp=interaction.created_at
                )
                if user_avatar:
                    embed.set_thumbnail(url=user_avatar)
                await safe_send(log_channel, embed=embed)
            except Exception as e:
                print(f"Ошибка отправки лога: {e}")
    except discord.Forbidden:
        await safe_send(
            interaction,
            "<:forbbiden2emoji:1517479332866429008> Нет прав для кика этого пользователя!",
            ephemeral=True)
    except discord.HTTPException as e:
        await safe_send(
            interaction,
            f"<:forbbiden2emoji:1517479332866429008> Ошибка: {e}",
            ephemeral=True)
    except Exception as e:
        await safe_send(
            interaction,
            f"<:forbbiden2emoji:1517479332866429008> Ошибка при кике: {e}",
            ephemeral=True)

@bot.tree.command(name='нейтрализовать', description='Забанить пользователя.')
@app_commands.guild_only()
@app_commands.default_permissions(ban_members=True)
async def ban_member(interaction: discord.Interaction, member: discord.Member, reason: str ="Не указана"):
    """Банит участника"""
    if not interaction.user.guild_permissions.ban_members:
        await safe_send(interaction, "<:forbbiden2emoji:1517479332866429008> У вас нет прав на кик!", ephemeral=True)
        return
    if member == interaction.user:
        await safe_send(interaction, "<:forbbiden2emoji:1517479332866429008> Нельзя кикнуть самого себя!", ephemeral=True)
        return
    if member.guild_permissions.administrator:
        await safe_send(interaction, "<:forbbiden2emoji:1517479332866429008> Нельзя кикнуть администратора!", ephemeral=True)
        return
    if member.bot:
        await safe_send(interaction, "🤖 Нельзя модерировать бота!", ephemeral=True)
        return
    # ✅ Проверка, что пользователь на сервере
    if not interaction.guild.get_member(member.id):
        await safe_send(interaction, "<:forbbiden2emoji:1517479332866429008> Пользователь не на сервере!", ephemeral=True)
        return
    # ✅ Проверка ролей (нельзя банить выше своей роли)
    if member.top_role >= interaction.user.top_role and interaction.user.id != interaction.guild.owner_id:
        await safe_send(interaction, "<:forbbiden2emoji:1517479332866429008> Нельзя забанить пользователя с ролью выше или равной вашей!", ephemeral=True)
        return
    safe_user = await safe_fetch_user(interaction.client, member.id)
    if safe_user:
        user_mention = safe_user.mention
        user_avatar = safe_user.display_avatar.url if safe_user.display_avatar else None
    # ✅ Получаем канал логов
    log_channel = await safe_fetch_channel(interaction.client, MOD_LOGS_COMMANDS)
    try:
        await member.ban(reason=f"{reason} (Модератор: {interaction.user})", delete_message_seconds=60)
        # ✅ Отправляем сообщение
        await safe_send(interaction, f"<:banemoji:1515689296118677534> {user_mention} **быᴧ уᴄᴛᴩᴀнён** <:neutralizeemoji:1515694760990347325>. ᴨᴩичинᴀ: {reason}", ephemeral=False)
        if log_channel:
            try:
                embed = discord.Embed(
                    title="<:banemoji:1515689296118677534> /нейтрализовать",
                    description=f"`ʍодᴇᴩᴀᴛоᴩ`: {interaction.user.mention} <:forbbiden2emoji:1517479332866429008>\n"
                                f"`ᴨоᴧьзоʙᴀᴛᴇᴧь`: {user_mention} <:reputationemoji:1517480379286556832>\n"
                                f"`ᴨᴩичинᴀ`: {reason} <:clearemoji:1515691240476377218>",
                    color=discord.Color.brand_red(),
                    timestamp=interaction.created_at
                )
                if user_avatar:
                    embed.set_thumbnail(url=user_avatar)
                await safe_send(log_channel, embed=embed)
            except Exception as e:
                print(f"Ошибка отправки лога: {e}")
                
    except discord.Forbidden:
        await safe_send(
            interaction,
            "<:forbbiden2emoji:1517479332866429008> Нет прав для бана этого пользователя!",
            ephemeral=True)
    except discord.HTTPException as e:
        if e.status == 429:
            await safe_send(
                interaction,
                "⏳ Слишком много запросов. Подождите немного.",
                ephemeral=True)
        else:
            await safe_send(
                interaction,
                f"<:forbbiden2emoji:1517479332866429008> Ошибка: {e}",
                ephemeral=True)
    except Exception as e:
        await safe_send(
            interaction,
            f"<:forbbiden2emoji:1517479332866429008> Ошибка при бане: {e}",
            ephemeral=True)

@bot.tree.command(name='аппелировать', description='Разбанить пользователя.')
@app_commands.guild_only()
@app_commands.default_permissions(ban_members=True)
async def unban_member(interaction: discord.Interaction, name_or_id: str):
    if not interaction.user.guild_permissions.ban_members:
        await safe_send(interaction, "<:forbbiden2emoji:1517479332866429008> У вас нет прав на разбан!", ephemeral=True)
        return
    # ✅ Получаем канал логов
    log_channel = await safe_fetch_channel(interaction.client, MOD_LOGS_COMMANDS)
    # ✅ Получаем список забаненных
    try:
        banned_users = [entry async for entry in interaction.guild.bans()]
    except discord.Forbidden:
        await safe_send(
            interaction,
            "<:forbbiden2emoji:1517479332866429008> Нет прав на просмотр банов!",
            ephemeral=True)
        return
    except Exception as e:
        await safe_send(
            interaction,
            f"<:forbbiden2emoji:1517479332866429008> Ошибка получения бан-листа: {e}",
            ephemeral=True)
        return
    if not banned_users:
        await safe_send(
            interaction,
            "<:forbbiden2emoji:1517479332866429008> Бан-лист пуст!",
            ephemeral=True)
        return
    # ✅ Ищем пользователя
    user = None
    # Поиск по ID
    if name_or_id.isdigit():
        user_id = int(name_or_id)
        for entry in banned_users:
            if entry.user.id == user_id:
                user = entry.user
                break
    else:
        # Поиск по имени (без учета регистра)
        name_lower = name_or_id.lower()
        for entry in banned_users:
            if name_lower in entry.user.name.lower():
                user = entry.user
                break
    
    # ✅ Если не нашли - пробуем по display_name
    if not user:
        name_lower = name_or_id.lower()
        for entry in banned_users:
            if entry.user.display_name and name_lower in entry.user.display_name.lower():
                user = entry.user
                break
    if not user:
        await safe_send(
            interaction,
            f"<:forbbiden2emoji:1517479332866429008> Пользователь **{name_or_id}** не найден в бан-листе!",
            ephemeral=True)
        return
    # ✅ Получаем безопасные данные пользователя
    safe_user = await safe_fetch_user(interaction.client, user.id)
    # ✅ Сохраняем данные ДО разбана
    if safe_user:
        user_mention = safe_user.mention
        user_id = safe_user.id
        user_avatar = safe_user.display_avatar.url if safe_user.display_avatar else None
    else:
        # Если safe_fetch_user не сработал - используем данные из бан-листа
        user_mention = f"<@{user.id}>"
        user_id = user.id
        user_avatar = None
    # ✅ Разбаниваем
    try:
        await interaction.guild.unban(user)
        # ✅ Отправляем сообщение
        await safe_send(interaction, f"<:unbanemoji:1515696568156557433> ᴨоᴧьзоʙᴀᴛᴇᴧь {user_mention} **нᴇ ʙиноʙᴇн**!", ephemeral=False)
        # ✅ Отправляем лог
        if log_channel:
            try:
                embed = discord.Embed(
                    title="<:unbanemoji:1515696568156557433> /аппелировать",
                    description=f"`ʍодᴇᴩᴀᴛоᴩ`: {interaction.user.mention} <:forbbiden2emoji:1517479332866429008>\n"
                                f"`ᴨоᴧьзоʙᴀᴛᴇᴧь`: {user_mention} <:reputationemoji:1517480379286556832>\n"
                                f"`ᴀйди`: {user_id} <:peopleemoji:1517486620939649044>",
                    color=discord.Color.brand_green(),
                    timestamp=interaction.created_at
                )
                if user_avatar:
                    embed.set_thumbnail(url=user_avatar)
                await safe_send(log_channel, embed=embed)
            except Exception as e:
                print(f"Ошибка отправки лога: {e}")
        
    except discord.Forbidden:
        await safe_send(
            interaction,
            "<:forbbiden2emoji:1517479332866429008> Нет прав для разбана!",
            ephemeral=True)
    except discord.HTTPException as e:
        await safe_send(
            interaction,
            f"<:forbbiden2emoji:1517479332866429008> Ошибка: {e}",
            ephemeral=True)
    except Exception as e:
        await safe_send(
            interaction,
            f"<:forbbiden2emoji:1517479332866429008> Ошибка при разбане: {e}",
            ephemeral=True)

@bot.tree.command(name='арестовать', description='Ограничить пользователю право общаться.')
@app_commands.guild_only()
@app_commands.default_permissions(moderate_members=True)
async def mute_member(interaction: discord.Interaction, member: discord.Member, minutes: int = None, reason: str = "Не указана"):
    if not interaction.user.guild_permissions.moderate_members:
        await safe_send(interaction, "<:forbbiden2emoji:1517479332866429008> У вас нет прав на мут!", ephemeral=True)
        return
    if member == interaction.user:
        await safe_send(interaction, "<:forbbiden2emoji:1517479332866429008> Нельзя замутить самого себя!", ephemeral=True)
        return
    if member.bot:
        await safe_send(interaction, "🤖 Нельзя модерировать бота!", ephemeral=True)
        return
    if member.guild_permissions.administrator:
        await safe_send(interaction, "<:forbbiden2emoji:1517479332866429008> Нельзя замутить администратора!", ephemeral=True)
        return
    if member.top_role >= interaction.user.top_role and interaction.user.id != interaction.guild.owner_id:
        await safe_send(interaction, "<:forbbiden2emoji:1517479332866429008> Нельзя замутить пользователя с ролью выше вашей!", ephemeral=True)
        return
    # ✅ Проверка времени
    if minutes is None:
        minutes = 60
    elif minutes > 1440:
        minutes = 1440
    elif minutes < 1:
        await safe_send(interaction, "<:forbbiden2emoji:1517479332866429008> Время должно быть больше 0 минут!", ephemeral=True)
        return
    end_time = datetime.now() + timedelta(minutes=minutes)
    end_timestamp = int(end_time.timestamp())
    # ✅ Получаем роль
    mute_role = interaction.guild.get_role(MUTED_ROLE)
    if not mute_role:
        await safe_send(interaction, "<:forbbiden2emoji:1517479332866429008> Роль MUTED_ROLE не найдена!", ephemeral=True)
        return
    # ✅ Получаем канал логов
    log_channel = await safe_fetch_channel(interaction.client, MOD_LOGS_COMMANDS)
    
    # ✅ Получаем безопасные данные пользователя
    user = await safe_fetch_user(interaction.client, member.id)
    user_mention = user.mention if user else member.mention
    user_avatar = user.display_avatar.url if user.display_avatar else None
    try:
        # ✅ Выдаем мут
        await member.add_roles(mute_role, reason=f"Мут на {minutes} минут. Причина: {reason}")
        # ✅ Отправляем сообщение
        await safe_send(interaction, f"<:muteemoji:1515688038867538000> {user_mention} **ᴀᴩᴇᴄᴛоʙᴀн**. оᴄʙобождᴇниᴇ ʙ <t:{end_timestamp}:T>. ᴨᴩичинᴀ: {reason}", ephemeral=False)
        if log_channel:
            try:
                embed = discord.Embed(
                    title="<:muteemoji:1515688038867538000> /арестовать",
                    description=f"`ʍодᴇᴩᴀᴛоᴩ`: {interaction.user.mention} <:forbbiden2emoji:1517479332866429008>\n"
                                f"`ᴨоᴧьзоʙᴀᴛᴇᴧь`: {user_mention} <:reputationemoji:1517480379286556832>\n"
                                f"`оᴄʙобождᴇниᴇ`: <t:{end_timestamp}:T> <:unmuteemoji:1515698075367112857>\n"
                                f"`ᴨᴩичинᴀ`: {reason} <:clearemoji:1515691240476377218>",
                    color=discord.Color.brand_red(),
                    timestamp=interaction.created_at
                )
                if user_avatar:
                    embed.set_thumbnail(url=user_avatar)
                await safe_send(log_channel, embed=embed)
            except Exception as e:
                print(f"Ошибка отправки лога: {e}")
        
        # ✅ Авто-снятие мута
        await asyncio.sleep(minutes * 60)
        
        # ✅ Проверяем, что пользователь все еще на сервере
        try:
            # Обновляем объект member
            fresh_member = interaction.guild.get_member(member.id)
            if fresh_member and mute_role in fresh_member.roles:
                await fresh_member.remove_roles(mute_role)
                # ✅ Отправляем сообщение о размуте
                try:
                    await safe_send(interaction,
                        f"<:unmuteemoji:1515698075367112857> {user_mention} **зᴀᴋончиᴧ** ᴛюᴩᴇʍный **ᴄᴩоᴋ** ᴀʙᴛоʍᴀᴛичᴇᴄᴋи!",
                        ephemeral=False)
                except Exception as e:
                    print(f"Ошибка при отправке сообщения о размуте: {e}")
            else:
                print(f"Пользователь {member.id} уже не на сервере или не имеет роли мута")
                
        except Exception as e:
            print(f"Ошибка при снятии мута: {e}")
            
    except discord.Forbidden:
        await safe_send(
            interaction,
            "<:forbbiden2emoji:1517479332866429008> Нет прав для мута этого пользователя!",
            ephemeral=True)
    except discord.HTTPException as e:
        await safe_send(
            interaction,
            f"<:forbbiden2emoji:1517479332866429008> Ошибка: {e}",
            ephemeral=True)
    except Exception as e:
        await safe_send(
            interaction,
            f"<:forbbiden2emoji:1517479332866429008> Ошибка при муте: {e}",
            ephemeral=True)

@bot.tree.command(name='освободить', description='Вернуть пользователю право общения.')
@app_commands.guild_only()
@app_commands.default_permissions(moderate_members=True)
async def unmute_member(interaction: discord.Interaction, member: discord.Member):
    if not interaction.user.guild_permissions.moderate_members:
        await safe_send(interaction, "<:forbbiden2emoji:1517479332866429008> У вас нет прав на снятие мута!", ephemeral=True)
        return
    mute_role = interaction.guild.get_role(MUTED_ROLE)
    if not mute_role:
        await safe_send(
            interaction,
            "<:forbbiden2emoji:1517479332866429008> Роль MUTED_ROLE не найдена!",
            ephemeral=True)
        return
    # ✅ Получаем канал логов
    log_channel = await safe_fetch_channel(interaction.client, MOD_LOGS_COMMANDS)

    # ✅ Получаем безопасные данные пользователя
    user = await safe_fetch_user(interaction.client, member.id)
    user_mention = user.mention if user else member.mention
    user_avatar = user.display_avatar.url if user.display_avatar else None
    # ✅ Проверяем, есть ли мут
    if mute_role not in member.roles:
        await safe_send(
            interaction,
            "<:forbbiden2emoji:1517479332866429008> У этого пользователя нет мута!",
            ephemeral=True)
        return
    try:
        # ✅ Снимаем мут
        await member.remove_roles(mute_role, reason=f"Досрочное снятие мута (Модератор: {interaction.user})")
        # ✅ Отправляем сообщение
        await safe_send(interaction, f"<:unmuteemoji:1515698075367112857> {user_mention} **зᴀᴋончиᴧ ᴄᴩоᴋ** доᴄᴩочно!", ephemeral=False)
        if log_channel:
            try:
                embed = discord.Embed(
                    title="<:unmuteemoji:1515698075367112857> /освободить",
                    description=f"`ʍодᴇᴩᴀᴛоᴩ`: {interaction.user.mention} <:forbbiden2emoji:1517479332866429008>\n"
                                f"`ᴨоᴧьзоʙᴀᴛᴇᴧь`: {user_mention} <:reputationemoji:1517480379286556832>",
                    color=discord.Color.brand_green(),
                    timestamp=interaction.created_at
                )
                if user_avatar:
                    embed.set_thumbnail(url=user_avatar)
                await safe_send(log_channel, embed=embed)
            except Exception as e:
                print(f"Ошибка отправки лога: {e}")
                
    except discord.Forbidden:
        await safe_send(
            interaction,
            "<:forbbiden2emoji:1517479332866429008> Нет прав для снятия мута с этого пользователя!",
            ephemeral=True)
    except discord.HTTPException as e:
        await safe_send(
            interaction,
            f"<:forbbiden2emoji:1517479332866429008> Ошибка: {e}",
            ephemeral=True)
    except Exception as e:
        await safe_send(
            interaction,
            f"<:forbbiden2emoji:1517479332866429008> Ошибка при снятии мута: {e}",
            ephemeral=True)

@bot.tree.command(name='выдать_предупреждение', description='Выдать предупреждение пользователю.')
@app_commands.guild_only()
@app_commands.default_permissions(moderate_members=True, ban_members=True)
async def warn_member(interaction: discord.Interaction, member: discord.Member, reason: str ="Не указана"):
    """Выдает предупреждение"""
    if not interaction.user.guild_permissions.moderate_members or not interaction.user.guild_permissions.ban_members:
        await safe_send(interaction, "<:forbbiden2emoji:1517479332866429008> У вас нет прав на выдачу предупреждений!", ephemeral=True)
        return
    if member.bot:
        await safe_send(interaction, "🤖 Нельзя модерировать бота!", ephemeral=True)
        return
    if member == interaction.user:
        await safe_send(interaction, "<:forbbiden2emoji:1517479332866429008> Нельзя модерировать самого себя!", ephemeral=True)
        return
    if member.guild_permissions.administrator:
        await safe_send(interaction, "<:forbbiden2emoji:1517479332866429008> Нельзя выдавать предупреждение администратору!", ephemeral=True)
        return
    if member.top_role >= interaction.user.top_role and interaction.user.id != interaction.guild.owner_id:
        await safe_send(
            interaction,
            "<:forbbiden2emoji:1517479332866429008> Нельзя выдать предупреждение пользователю с ролью выше вашей!",
            ephemeral=True)
        return
    
    # ✅ Получаем канал логов
    log_channel = await safe_fetch_channel(interaction.client, MOD_LOGS_COMMANDS)
    
    # ✅ Получаем безопасные данные пользователя
    user = await safe_fetch_user(interaction.client, member.id)
    user_mention = user.mention if user else member.mention
    user_avatar = user.display_avatar.url if user.display_avatar else None
    try:
        # ✅ Выдаем предупреждение
        new_warns = await warn_user(interaction, member, reason)
        if log_channel:
            try:
                embed = discord.Embed(
                    title="<:warnemoji:1515687856549658774> /выдать_предупреждение",
                    description=f"`ʍодᴇᴩᴀᴛоᴩ`: {interaction.user.mention} <:forbbiden2emoji:1517479332866429008>\n"
                                f"`ᴨоᴧьзоʙᴀᴛᴇᴧь`: {user_mention} <:reputationemoji:1517480379286556832>\n"
                                f"`ʙᴀᴩноʙ ᴛᴇᴨᴇᴩь`: {new_warns} <:warningemoji:1515756604178305054>\n"
                                f"`ᴨᴩичинᴀ`: {reason} <:clearemoji:1515691240476377218>",
                    color=discord.Color.brand_red(),
                    timestamp=interaction.created_at
                )
                if user_avatar:
                    embed.set_thumbnail(url=user_avatar)
                await safe_send(log_channel, embed=embed)
            except Exception as e:
                print(f"Ошибка отправки лога: {e}")
                
    except discord.Forbidden:
        await safe_send(
            interaction,
            "<:forbbiden2emoji:1517479332866429008> Нет прав для выдачи предупреждения этому пользователю!",
            ephemeral=True)
    except discord.HTTPException as e:
        await safe_send(
            interaction,
            f"<:forbbiden2emoji:1517479332866429008> Ошибка: {e}",
            ephemeral=True)
    except Exception as e:
        await safe_send(
            interaction,
            f"<:forbbiden2emoji:1517479332866429008> Ошибка при выдаче предупреждения: {e}",
            ephemeral=True)

@bot.tree.command(name='снять_предупреждение', description='Снять предупреждение с пользователя.')
@app_commands.guild_only()
@app_commands.default_permissions(moderate_members=True, ban_members=True)
async def unwarn_member(interaction: discord.Interaction, member: discord.Member):
    if not interaction.user.guild_permissions.moderate_members or not interaction.user.guild_permissions.ban_members:
        await safe_send(interaction, "<:forbbiden2emoji:1517479332866429008> У вас нет прав на выдачу предупреждений!", ephemeral=True)
        return
    if member.bot:
        await safe_send(interaction, "🤖 Нельзя модерировать бота!", ephemeral=True)
        return
    if member == interaction.user:
        await safe_send(interaction, "<:forbbiden2emoji:1517479332866429008> Нельзя модерировать самого себя!", ephemeral=True)
        return
    if member.top_role >= interaction.user.top_role and interaction.user.id != interaction.guild.owner_id:
        await safe_send(
            interaction,
            "<:forbbiden2emoji:1517479332866429008> Нельзя убирать предупреждение пользователю с ролью выше вашей!",
            ephemeral=True)
        return
    # ✅ Получаем данные пользователя
    try:
        user_data = await manager.get_user_ruler(member.id)
    except Exception as e:
        await safe_send(interaction, f"<:forbbiden2emoji:1517479332866429008> Ошибка получения данных: {e}", ephemeral=True)
        return
    if not user_data:
        await safe_send(interaction, f"<:forbbiden2emoji:1517479332866429008> Пользователь {member.mention} не найден в базе!", ephemeral=True)
        return
    current_warns = user_data.get("warnings", 0)
    if current_warns <= 0:
        await safe_send(
            interaction,
            f"<:forbbiden2emoji:1517479332866429008> {member.mention} не имеет предупреждений.",
            ephemeral=True)
        return
    # ✅ Получаем канал логов
    log_channel = await safe_fetch_channel(interaction.client, MOD_LOGS_COMMANDS)
    
    # ✅ Получаем безопасные данные пользователя
    user = await safe_fetch_user(interaction.client, member.id)
    user_mention = user.mention if user else member.mention
    user_avatar = user.display_avatar.url if user.display_avatar else None
    # ✅ Роли
    roles = {
        1: FIRST_WARN_ROLE,
        2: SECOND_WARN_ROLE,
        3: THIRD_WARN_ROLE}
    try:
        # ✅ Снимаем текущую роль предупреждения
        current_role_id = roles.get(current_warns)
        if current_role_id:
            current_role = interaction.guild.get_role(current_role_id)
            if current_role and current_role in member.roles:
                await member.remove_roles(current_role)
        new_warns = current_warns - 1
        
        if new_warns > 0:
            prev_role_id = roles.get(new_warns)
            if prev_role_id:
                prev_role = interaction.guild.get_role(prev_role_id)
                if prev_role:
                    await member.add_roles(prev_role)
        else:
            # ✅ Снимаем категорию предупреждений
            category_role = interaction.guild.get_role(WARNINGS_CATEGORY_ROLE)
            if category_role and category_role in member.roles:
                await member.remove_roles(category_role)
        
        # ✅ Обновляем данные в базе
        await manager.update_user_ruler(
            member.id,
            new_warns,
            user_data.get('reputation', 0),
            user_data.get('last_time_reputation', None))
        
        # ✅ Отправляем сообщение
        await safe_send(interaction, f"<:unbanemoji:1515696568156557433> {user_mention} **ᴀᴨᴨᴇᴧᴧиᴩоʙᴀн**. оᴄᴛᴀᴧоᴄь ᴨᴩᴇдуᴨᴩᴇждᴇний: **{new_warns}** <:warningemoji:1515756604178305054>", ephemeral=False)
        if log_channel:
            try:
                embed = discord.Embed(
                    title="<:unbanemoji:1515696568156557433> /снять_предупреждение",
                    description=f"`ʍодᴇᴩᴀᴛоᴩ`: {interaction.user.mention} <:forbbiden2emoji:1517479332866429008>\n"
                                f"`ᴨоᴧьзоʙᴀᴛᴇᴧь`: {user_mention} <:reputationemoji:1517480379286556832>\n"
                                f"`ʙᴀᴩноʙ оᴄᴛᴀᴧоᴄь`: {new_warns} <:warningemoji:1515756604178305054>",
                    color=discord.Color.brand_green(),
                    timestamp=interaction.created_at
                )
                if user_avatar:
                    embed.set_thumbnail(url=user_avatar)
                await safe_send(log_channel, embed=embed)
            except Exception as e:
                print(f"Ошибка отправки лога: {e}")
                
    except discord.Forbidden:
        await safe_send(
            interaction,
            "<:forbbiden2emoji:1517479332866429008> Нет прав для снятия предупреждения с этого пользователя!",
            ephemeral=True)
    except discord.HTTPException as e:
        await safe_send(
            interaction,
            f"<:forbbiden2emoji:1517479332866429008> Ошибка: {e}",
            ephemeral=True)
    except Exception as e:
        await safe_send(
            interaction,
            f"<:forbbiden2emoji:1517479332866429008> Ошибка при снятии предупреждения: {e}",
            ephemeral=True)

# @bot.tree.command(name='modpanel', description='Панель модерации.')
# @app_commands.default_permissions(administrator=True)
# async def mod_panel(interaction: discord.Interaction, member: discord.Member = None):
#     """Открывает панель модерации для участника"""
#     if member is None:
#         await interaction.response.send_message("<:forbbiden2emoji:1517479332866429008> Укажите участника: `/modpanel @user`", ephemeral=True)
#         return
#     if member.bot:
#         await interaction.response.send_message("🤖 Нельзя модерировать бота!", ephemeral=True)
#         return
#     if member == interaction.user:
#         await interaction.response.send_message("<:forbbiden2emoji:1517479332866429008> Нельзя модерировать самого себя!", ephemeral=True)
#         return
#     if member.guild_permissions.administrator:
#         await interaction.response.send_message("<:forbbiden2emoji:1517479332866429008> Нельзя модерировать администратора!", ephemeral=True)
#         return
#     joined_timestamp = int(member.joined_at.timestamp())
#     embed = discord.Embed(
#         title="🛡️ The moderation panel",
#         description=f"Действия для {member.mention}",
#         color=discord.Color.blue()
#     )
#     embed.add_field(name="ID", value=member.id, inline=True)
#     embed.add_field(name="Имя", value=member.display_name, inline=True)
#     embed.add_field(name="Дата присоединения", value=f'<t:{joined_timestamp}:F>', inline=True)
    
#     view = ModPanel(interaction.user, member)
#     await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

# ========== КОМАНДЫ ДЛЯ ИНФОРМАЦИИ ==========

@bot.tree.command(name='userinfo', description='Узнайте информацию об пользователи.')
@app_commands.guild_only()
async def user_info(interaction: discord.Interaction, member: discord.Member = None):
    if interaction.channel.id != COMMANDS_CHANNEL and interaction.channel.id != MOD_COMMANDS_CHANNEL:
        await safe_send(interaction, f"<:forbbiden2emoji:1517479332866429008> Эта команда работает только в канале <#{COMMANDS_CHANNEL}>!", ephemeral=True)
        return
    if member is not None and member.bot:
        await safe_send(interaction, "🤖 Нельзя использовать команду на боте!", ephemeral=True)
        return
    target_member = member or interaction.user
    # Получаем UNIX timestamp (секунды, а не миллисекунды)
    user_data = await manager.get_user_ruler(target_member.id)
    joined_timestamp = int(target_member.joined_at.timestamp())
    created_timestamp = int(target_member.created_at.timestamp())
    embed = discord.Embed(
        title=f"<:techicalemoji:1515678259767939262> ɪɴꜰᴏʀᴍᴀᴛɪᴏɴ ᴀʙᴏᴜᴛ {target_member.display_name}",
        color=discord.Color.darker_grey())
    embed.set_thumbnail(url=target_member.avatar.url if target_member.avatar else target_member.default_avatar.url)
    embed.add_field(name="ɪᴅ <:peopleemoji:1517486620939649044>", value=target_member.id, inline=True)
    embed.add_field(name="иʍя ᴨоᴧьзоʙᴀᴛᴇᴧя <:coolemoji:1517487042018410577>", value=target_member.name, inline=True)
    embed.add_field(name="ʀᴇᴘᴜᴛᴀᴛɪᴏɴ <:reputationemoji:1517480379286556832>", value=user_data.get("reputation", 0), inline=True)
    embed.add_field(name="ᴀᴋᴋᴀунᴛ ᴄоздᴀн", value=f'<t:{created_timestamp}:f>', inline=True)
    embed.add_field(name="ᴨᴩиᴄоᴇдиниᴧᴄя", value=f'<t:{joined_timestamp}:f>', inline=True)
    
    await safe_send(interaction, embed=embed, ephemeral=False)

@bot.tree.command(name='serverinfo', description='Узнайте информацию о сервере.')
@app_commands.guild_only()
async def server_info(interaction: discord.Interaction):
    """Показывает информацию о сервере"""
    if interaction.channel.id != COMMANDS_CHANNEL and interaction.channel.id != MOD_COMMANDS_CHANNEL:
        await safe_send(interaction, f"<:forbbiden2emoji:1517479332866429008> Эта команда работает только в канале <#{COMMANDS_CHANNEL}>!", ephemeral=True)
        return
    created_timestamp = int(interaction.guild.created_at.timestamp())
    guild = interaction.guild
    embed = discord.Embed(
        title=f'<:techicalemoji:1515678259767939262> {guild.name}',
        description=guild.description or "Нет описания",
        color=discord.Color.darker_grey()
    )
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    embed.add_field(name="ɪᴅ <:peopleemoji:1517486620939649044>", value=guild.id, inline=True)
    embed.add_field(name="ʙᴧᴀдᴇᴧᴇц <:owneremoji:1517494149119611063", value=guild.owner.mention, inline=True)
    embed.add_field(name="учᴀᴄᴛниᴋоʙ <:coolemoji:1517487042018410577>", value=guild.member_count, inline=True)
    embed.add_field(name="ᴋᴀнᴀᴧоʙ <:clearemoji:1515691240476377218>", value=len(guild.channels), inline=True)
    embed.add_field(name="ᴩоᴧᴇй <:rolesemoji:1517494151086866522>", value=len(guild.roles), inline=True)
    embed.add_field(name="дᴀᴛᴀ ᴄоздᴀния <:techicalemoji:1515678259767939262>", value=f"<t:{created_timestamp}:D>", inline=True)
    
    await safe_send(interaction, embed=embed, ephemeral=False)

@bot.tree.command(name='репутация', description='Узнайте репутацию пользователя.')
@app_commands.guild_only()
async def user_info(interaction: discord.Interaction, member: discord.Member = None):
    if interaction.channel.id != COMMANDS_CHANNEL and interaction.channel.id != MOD_COMMANDS_CHANNEL:
        await safe_send(interaction, f"<:forbbiden2emoji:1517479332866429008> Эта команда работает только в канале <#{COMMANDS_CHANNEL}>!", ephemeral=True)
        return
    if member is not None and member.bot:
        await safe_send(interaction, "🤖 Нельзя использовать команду на боте!", ephemeral=True)
        return
    target_member = member or interaction.user
    user_data = await manager.get_user_ruler(target_member.id)
    reputation = user_data.get("reputation", 0)
    embed = discord.Embed(
        title=f"<:peopleemoji:1517486620939649044> {target_member.display_name}'s ʀᴇᴘᴜᴛᴀᴛɪᴏɴ",
        description=f"у ᴨоᴧьзоʙᴀᴛᴇᴧя **{reputation} очᴋоʙ ᴩᴇᴨуᴛᴀции** <:reputationemoji:1517480379286556832>\nдᴧя уʙᴇᴧичᴇния чьᴇй-ᴛо ᴩᴇᴨуᴛᴀции иᴄᴨоᴧьзуйᴛᴇ `+rep @User`",
        color=discord.Color.darker_grey()
    )
    embed.set_thumbnail(url=target_member.avatar.url if target_member.avatar else target_member.default_avatar.url)
    
    await safe_send(interaction, embed=embed, ephemeral=False)

@bot.tree.command(name="левел", description="Показать карточку уровня и опыта участника.")
@app_commands.guild_only()
@app_commands.describe(member="Выберите участника сервера, чтобы посмотреть его уровень (необязательно)")
async def level_command(interaction: discord.Interaction, member: discord.Member = None):
    if interaction.channel.id != COMMANDS_CHANNEL and interaction.channel.id != MOD_COMMANDS_CHANNEL:
        await safe_send(interaction, f"<:forbbiden2emoji:1517479332866429008> Эта команда работает только в канале <#{COMMANDS_CHANNEL}>!", ephemeral=True)
        return
    if member is not None and member.bot:
        await safe_send(interaction, "🤖 Нельзя использовать команду на боте!", ephemeral=True)
        return
    await interaction.response.defer()
    
    target_member = member or interaction.user
    
    data = await manager.get_user_data(target_member.id)
    user_level = data.get("level", 0)
    current_xp = data.get("xp", 0)
    role_name = data.get("role", None)
    next_level_xp = await manager.get_xp_needed(user_level)
    
    if role_name == "Нет роли" or not role_name:
        for lvl, r_id in sorted(LEVEL_ROLES.items(), reverse=True):
            if user_level >= lvl:
                role = interaction.guild.get_role(r_id)
                if role:
                    role_name = role.name
                    break

    avatar_url = target_member.display_avatar.url
    
    try:
        image_buf = await generate_level_card(
            username=target_member.display_name,
            avatar_url=avatar_url,
            level=user_level,
            current_xp=current_xp,
            next_level_xp=next_level_xp,
            role_name=role_name)
        discord_file = discord.File(fp=image_buf, filename="level_card.png")
        await safe_send(interaction, file=discord_file)
        
    except Exception as e:
        # Если что-то сломается внутри генерации картинки, бот сообщит об этом, а не зависнет
        print(f"Ошибка при отправке карточки уровня: {e}")
        await safe_send(interaction, "Произошла ошибка при генерации карточки уровня.", ephemeral=True)

# ========== ТЕКСТОВЫЕ СОБЫТИЕ ==========

@bot.event
async def on_message(message):
    user_id = message.author.id
    # ПРОВЕРКА БОТОВ
    if message.author.bot:
        if user_id not in trusted_bots:
            user = await safe_fetch_user(bot, user_id)
            if user:
                user_name = user.name
            else:
                user_name = message.author.name
            try:
                await message.author.ban(reason=f"Неавторизованный бот (Автоматический бан)")
            except discord.Forbidden:
                print(f"❌ Нет прав для бана бота {user_name}")
            except discord.HTTPException as e:
                print(f"❌ Ошибка при бане бота: {e}")
            except Exception as e:
                print(f"❌ Неизвестная ошибка: {e}")
        return
    # СОСТОЯНИЕ БОТОВ
    if bot.user in message.mentions and user_id == DEVELOPER_ID:
        await safe_send(message, f"{message.author.mention}, бот ещё жив! ✅")
    # +REP СИСТЕМА
    if message.content == "+rep":
        if message.mentions:
            target_user = message.mentions[0]
            if target_user.id == user_id:
                await safe_reply(message, "<:forbbiden2emoji:1517479332866429008> Вы не можете дать репутацию самому себе!", delete_after=5)
                await safe_delete(message, delay=2)
                return
            user_data = await manager.get_user_ruler(target_user.id)
            current_time = time.time()
    
            time_passed = current_time - user_data["last_time_reputation"]
            if time_passed < 21600:
                seconds_left = int(21600 - time_passed)
                hours = seconds_left // 3600
                minutes = (seconds_left % 3600) // 60
                await safe_reply(message, f"**<:forbbiden2emoji:1517479332866429008> {message.author.mention}, вы не можете часто использовать эту команду!**\n⌛ Осталось: **{hours} ч. {minutes} мин.**", delete_after=5)
                return
            new_reputation = int(user_data["reputation"]+1)
            await manager.update_user_ruler(target_user.id, user_data["warnings"], new_reputation, current_time)
            await safe_reply(message, f"{message.author.mention} ʙыдᴀᴧ ᴩᴇᴨуᴛᴀцию {target_user.mention}! <:reputationemoji:1517480379286556832>", delete_after=60)
            return
        else:
            await safe_reply(message, "<:forbbiden2emoji:1517479332866429008> Укажите пользователя! Пример: `+rep @User`", delete_after=5)
            await safe_delete(message, delay=2)
            return
    # LEVEL UP СИСТЕМА
    data = await manager.get_user_data(user_id)

    current_xp = int(data.get("xp", 0) + random.randint(5, 10))
    current_level = data.get("level", 0)
    current_role = data.get("role", None)

    xp_needed = await manager.get_xp_needed(current_level)

    leveled_up = False
    while current_xp >= xp_needed:
        current_xp -= xp_needed
        current_level += 1
        xp_needed = await manager.get_xp_needed(current_level)
        leveled_up = True

    if leveled_up:
        await safe_send(message, f"<:congrantemoji:1517514349965475954> {message.author.mention}, ʙы доᴄᴛиᴦᴧи **{current_level}** уᴩоʙня!", delete_after=10)
        if current_level in LEVEL_ROLES:
            target_role_id = LEVEL_ROLES[current_level]
            guild = message.guild
            role = guild.get_role(target_role_id)
            
            if role:
                current_role = role.name
                try:
                    await message.author.add_roles(role)
                except discord.Forbidden:
                    print(f"Ошибка: Проверьте иерархию ролей! Бот не может выдать роль '{role.name}'")
    await manager.update_user_data(user_id, current_xp, current_level, current_role)
    # ПРОВЕРКА НА АДМИНИСТРАТОРА
    if message.guild and message.author.guild_permissions.administrator:
        await bot.process_commands(message)
        return
    # ПРОВЕРКА НА ССЫЛКИ
    content_lower = message.content.lower()
    match = re.search(URL_REGEX, content_lower)  # URL_REGEX должен быть строкой паттерна
    if match:  # Проверяем, что URL найден
        is_gif = any(re.search(pattern, match.group()) for pattern in AVAILABLE_PATTERNS)
        if not is_gif:
            try:
                await safe_delete(message)
                view = WarningView(user_id=user_id)
                await safe_send(message, 
                    f"<:clearemoji:1515691240476377218> {message.author.mention}, ʙᴀɯᴇ ᴄообщᴇниᴇ удᴀᴧᴇно.", 
                    view=view, 
                    delete_after=10)
            except (discord.Forbidden, discord.NotFound):
                pass
    # ПРОВЕРКА НА СПАМ
    if await anti_spam.is_muted(message.author):
        await safe_delete(message)
        return
    current_time = time.time()
    if anti_spam.is_spam(user_id, current_time):
        await safe_delete(message)
        warnings = anti_spam.add_spam_warning(user_id)
        if warnings == 1:
            await safe_send(message.author, "<:warningemoji:1515756604178305054> **ᴨᴩᴇдуᴨᴩᴇждᴇниᴇ!** нᴇ ᴄᴨᴀʍьᴛᴇ ʙ чᴀᴛᴇ!\nᴄᴧᴇдующᴇᴇ нᴀᴩуɯᴇниᴇ - ʍуᴛ нᴀ 5 ʍинуᴛ.")
            await safe_send(message.channel, f"<:warningemoji:1515756604178305054> {message.author.mention}, нᴇ ᴄᴨᴀʍьᴛᴇ ʙ чᴀᴛᴇ! ", delete_after=5)
        elif warnings == 2:
            await anti_spam.mute_user(message.author, 300)
            await safe_send(message.author, "<:muteemoji:1515688038867538000> ʙы **зᴀдᴇᴩжᴀны** нᴀ 5 ʍинуᴛ зᴀ ᴄᴨᴀʍ!")
            await safe_send(message.channel, f"<:muteemoji:1515688038867538000> {message.author.mention} **зᴀдᴇᴩжᴀн** нᴀ 5 ʍинуᴛ зᴀ ᴄᴨᴀʍ!")
        elif warnings == 3:
            await anti_spam.mute_user(message.author, 1800)
            await safe_send(message.author, "<:muteemoji:1515688038867538000> ʙы **зᴀдᴇᴩжᴀны** нᴀ 30 ʍинуᴛ зᴀ ᴨоʙᴛоᴩный ᴄᴨᴀʍ!")
            await safe_send(message.channel, f"<:muteemoji:1515688038867538000> {message.author.mention} **зᴀдᴇᴩжᴀн** нᴀ 30 ʍинуᴛ зᴀ ᴨоʙᴛоᴩный ᴄᴨᴀʍ!")
        elif warnings == 4:
            await message.author.kick(reason="Спам после нескольких предупреждений")
            await safe_send(message.channel, f"<:kickemoji:1515693208783425617> {message.author.mention} **ʙᴩᴇʍᴇнно оᴛᴄᴛᴩᴀнён** зᴀ ᴄᴨᴀʍ!")
        elif warnings >= 5:
            await message.author.ban(reason="Многократный спам")
            await safe_send(message.channel, f"<:neutralizeemoji:1515694760990347325> {message.author.mention} **быᴧ нᴇйᴛᴩᴀᴧизоʙᴀн** зᴀ ʍноᴦоᴋᴩᴀᴛный ᴄᴨᴀʍ!")
        return
    if anti_spam.message_history.get(user_id) and time.time() - anti_spam.message_history[user_id][-1] > 30:
        anti_spam.reset_warnings(user_id)
    await bot.process_commands(message)

@bot.event
async def on_member_remove(member):
    if member.bot:
        return
    user = await safe_fetch_user(bot, member.id)
    if not user:
        print(f"⚠️ Не удалось получить данные пользователя {member.id} при выходе")
    current_roles = [role.id for role in member.roles if role.name != "@everyone"]
    try:
        await manager.update_user_roles_ruler(member.id, current_roles)
    except Exception as e:
        print(f"❌ Ошибка сохранения ролей для {member.id}: {e}")

@bot.event
async def on_member_join(member):
    if member.bot:
        # ✅ Проверяем, разрешен ли этот бот
        trusted_set = getattr(bot, 'trusted_set', trusted_bots)
        if member.id not in trusted_set:
            user = await safe_fetch_user(bot, member.id)
            if user:
                user_name = user.name
            else:
                user_name = member.name
            welcome_channel = await safe_fetch_channel(bot, WELCOME_CHANNEL)
            if welcome_channel:
                try:
                    await safe_send(welcome_channel, f"<:neutralizeemoji:1515694760990347325> ʙᴩᴀжᴇᴄᴋоᴇ уᴄᴛᴩойᴄᴛʙо, {member.mention}, **быᴧо нᴇйᴛᴩᴀᴧизоʙᴀно** ᴧучɯиʍи ᴄᴨᴇц-оᴛᴩядᴀʍи.")
                except Exception as e:
                    print(f"❌ Ошибка отправки сообщения в канал: {e}")
            try:
                await member.ban(reason="Неавторизованный бот (Автоматическая нейтрализация)")
            except discord.Forbidden:
                print(f"❌ Нет прав для бана бота {user_name}")
            except Exception as e:
                print(f"❌ Ошибка при бане бота {user_name}: {e}")
            return
    try:
        roles_to_restore = await manager.get_user_roles_ruler(member.id)
    except Exception as e:
        print(f"❌ Ошибка получения ролей: {e}")
        roles_to_restore = []
    roles_objects = []
    for role_id in roles_to_restore:
        role = member.guild.get_role(role_id)
        if role is not None and role.name != "@everyone":
            roles_objects.append(role)    
    # ✅ Создаем список задач
    tasks = []
    # ✅ Восстановление сохраненных ролей
    if roles_objects:
        tasks.append(
            member.add_roles(
                *roles_objects, 
                reason="Восстановление ролей после возвращения"
            )
        )
    welcome_channel = await safe_fetch_channel(bot, WELCOME_CHANNEL)
    if welcome_channel:
        tasks.append(safe_send(welcome_channel, embed=discord.Embed(title="👋 Welcome!", description=f"Привет, {member.mention}!\nРады видеть тебя на **{member.guild.name}**", color=discord.Color.dark_grey()).add_field(name="📅 Присоединился", value=f"<t:{int(member.joined_at.timestamp())}:R>", inline=True).add_field(name="👤 Участников", value=member.guild.member_count, inline=True).set_thumbnail(url=member.display_avatar.url)))
    join_roles = []
    for role_id in [JOIN_ROLE1, JOIN_ROLE2, JOIN_ROLE3]:
        role = member.guild.get_role(role_id)
        if role is not None:
            join_roles.append(role)
    if join_roles:
        tasks.append(
            member.add_roles(
                *join_roles, 
                reason="Выдача стандартных ролей при входе"
            )
        )
    if not member.bot:
        tasks.append(send_dm_welcome(member))
    if tasks:
        try:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            # ✅ Проверяем результаты
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    print(f"❌ Ошибка в задаче {i}: {result}")
                    
        except Exception as e:
            print(f"❌ Ошибка при выполнении задач: {e}")

# ========== ЛОГИРОВАНИЕ СОБЫТИЙ ==========

@bot.event
async def on_message_delete(message):
    if message.author.bot or not message.content:
        return
    log_channel = await safe_fetch_channel(bot, MOD_LOGS)
    if not log_channel:
        return
    user = await safe_fetch_user(bot, message.author.id)
    user_mention = user.mention if user else f"<@{message.author.id}>"
    embed = discord.Embed(
        title="🗑️ The message deleted",
        description=f"**ᴀʙᴛоᴩ:** {user_mention}\n**ᴋᴀнᴀᴧ:** {message.channel.mention}",
        color=discord.Color.red(),
        timestamp=datetime.now()
    )
    content = message.content[:1000] + ('...' if len(message.content) > 1000 else '')
    embed.add_field(
        name="Содержание", 
        value=f'```{content}```', 
        inline=False
    )
    if message.attachments:
        attachment_texts = []
        total_size = 0
        for i, att in enumerate(message.attachments[:10], 1):
            is_image = att.content_type and att.content_type.startswith('image/')
            is_video = att.content_type and att.content_type.startswith('video/')
            is_audio = att.content_type and att.content_type.startswith('audio/')
            # Размер файла
            size_kb = att.size / 1024
            if size_kb > 1024:
                size_str = f"{size_kb/1024:.1f} MB"
            else:
                size_str = f"{size_kb:.1f} KB"
            # Иконка
            if is_image:
                icon = "🖼️"
            elif is_video:
                icon = "🎬"
            elif is_audio:
                icon = "🎵"
            else:
                icon = "📎"
            
            attachment_texts.append(f"{icon} [{att.filename}]({att.url}) ({size_str})")
        if len(message.attachments) > 10:
            attachment_texts.append(f"... и еще {len(message.attachments) - 10} файлов")
        
        attachments_text = '\n'.join(attachment_texts)

        if len(attachments_text) > 1024:
            attachments_text = attachments_text[:1021] + "..."
        
        embed.add_field(
            name=f"📎 Вложения ({len(message.attachments)})",
            value=attachments_text,
            inline=False
        )
    try:
        await safe_send(log_channel, embed=embed)
    except Exception as e:
        print(f"Ошибка при отправке лога удаления: {e}")

@bot.event
async def on_message_edit(before, after):
    if before.author.bot or before.content == after.content:
        return
    log_channel = await safe_fetch_channel(bot, MOD_LOGS)
    if not log_channel:
        return
    user = await safe_fetch_user(bot, before.author.id)
    user_mention = user.mention if user else f"<@{before.author.id}>"
    if before.guild:
        channel_name = before.channel.mention
    else:
        channel_name = "Личные сообщения"
    embed = discord.Embed(
        title="✏️ The message redacted",
        description=f"**ᴀʙᴛоᴩ:** {user_mention}\n**ᴋᴀнᴀᴧ:** {channel_name}",
        color=discord.Color.orange(),
        timestamp=datetime.now()
    )
    jump_url = before.jump_url if hasattr(before, 'jump_url') else None
    if jump_url:
        embed.description += f"\n[Перейти к сообщению]({jump_url})"
    old_content = before.content[:400] + ('...' if len(before.content) > 400 else '') if before.content else "*Пусто*"
    embed.add_field(
        name="Было", 
        value=f"```{old_content}```", 
        inline=False
    )
    new_content = after.content[:400] + ('...' if len(after.content) > 400 else '') if after.content else "*Пусто*"
    embed.add_field(
        name="Стало", 
        value=f"```{new_content}```", 
        inline=False
    )
    if before.attachments or after.attachments:
        before_count = len(before.attachments)
        after_count = len(after.attachments)
        
        if before_count != after_count:
            embed.add_field(
                name="📎 Вложения изменены",
                value=f"**Было:** {before_count} файлов\n**Стало:** {after_count} файлов",
                inline=False
            )
        elif before.attachments and after.attachments:
            before_names = {att.filename for att in before.attachments}
            after_names = {att.filename for att in after.attachments}
            if before_names != after_names:
                embed.add_field(
                    name="📎 Вложения изменены",
                    value="**Имена файлов изменились**",
                    inline=False
                )
    try:
        await safe_send(log_channel, embed=embed)
    except Exception as e:
        print(f"Ошибка при отправке лога редактирования: {e}")

# ========== ОБРАБОТКА ОШИБОК ==========

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    error_messages = {
        commands.MissingPermissions: "<:forbbiden2emoji:1517479332866429008> У вас недостаточно прав для выполнения этой команды!",
        commands.MissingRequiredArgument: f"<:forbbiden2emoji:1517479332866429008> Не хватает аргументов! Используйте `!help {ctx.command.name}`",
        commands.BadArgument: "<:forbbiden2emoji:1517479332866429008> Неверный аргумент! Укажите существующего пользователя.",
        commands.NotOwner: "<:forbbiden2emoji:1517479332866429008> Эта команда доступна только владельцу бота!",
        commands.CommandOnCooldown: f"⏰ Подождите {error.retry_after:.1f} секунд перед повторным использованием!",
        commands.BotMissingPermissions: f"<:forbbiden2emoji:1517479332866429008> У бота недостаточно прав! Нужны: {', '.join(error.missing_permissions)}",
        commands.MaxConcurrencyReached: "<:forbbiden2emoji:1517479332866429008> Команда уже выполняется! Подождите.",
        commands.MemberNotFound: "<:forbbiden2emoji:1517479332866429008> Участник не найден на сервере!",
        commands.UserNotFound: "<:forbbiden2emoji:1517479332866429008> Пользователь не найден!",
        commands.ChannelNotFound: "<:forbbiden2emoji:1517479332866429008> Канал не найден!",
        commands.RoleNotFound: "<:forbbiden2emoji:1517479332866429008> Роль не найдена!",
        commands.NoPrivateMessage: "<:forbbiden2emoji:1517479332866429008> Эта команда недоступна в личных сообщениях!",
        commands.PrivateMessageOnly: "<:forbbiden2emoji:1517479332866429008> Эта команда доступна только в личных сообщениях!",
        commands.DisabledCommand: "<:forbbiden2emoji:1517479332866429008> Эта команда отключена!",
        commands.CheckFailure: "<:forbbiden2emoji:1517479332866429008> У вас нет доступа к этой команде!",
    }
    # ✅ Проверяем известные ошибки
    for error_type, message in error_messages.items():
        if isinstance(error, error_type):
            await safe_send(ctx, message)
            return
    # ✅ Обработка ошибок Discord
    if isinstance(error, discord.Forbidden):
        await safe_send(ctx, "<:forbbiden2emoji:1517479332866429008> У бота нет прав для выполнения этого действия!")
        return
    if isinstance(error, discord.NotFound):
        await safe_send(ctx, "<:forbbiden2emoji:1517479332866429008> Ресурс не найден!")
        return
    if isinstance(error, discord.HTTPException):
        if error.status == 429:
            await safe_send(ctx, "⏰ Слишком много запросов! Подождите немного.")
            return
        else:
            await safe_send(ctx, f"<:forbbiden2emoji:1517479332866429008> Ошибка соединения: {error.status}")
            return
    # ✅ Неизвестная ошибка - логируем в консоль и сообщаем
    print(f"⚠️ Неизвестная ошибка: {error}")
    print(f"📚 Тип ошибки: {type(error).__name__}")
    
    # ✅ Отправляем в лог-канал (если есть)
    log_channel = await safe_fetch_channel(bot, MOD_LOGS_COMMANDS)
    if log_channel:
        try:
            embed = discord.Embed(
                title="❌ Ошибка команды",
                description=f"**Команда:** `{ctx.command.name}`\n"
                            f"**Пользователь:** {ctx.author.mention}\n"
                            f"**Канал:** {ctx.channel.mention}\n"
                            f"**Ошибка:** {type(error).__name__}\n"
                            f"**Детали:** {error}",
                color=discord.Color.red(),
                timestamp=datetime.now()
            )
            embed.set_footer(text=f"ID: {ctx.author.id}")
            await log_channel.send(embed=embed)
        except Exception as e:
            print(f"❌ Ошибка отправки лога: {e}")
    
    # ✅ Сообщение пользователю
    await safe_send(ctx, "⚠️ Произошла неизвестная ошибка. Разработчик уже уведомлён.")

# ========== ЗАПУСК БОТА ==========

@bot.event
async def on_ready():
    bot.trusted_set = set(trusted_bots)
    try:
        await bot.tree.sync(guild=None) 
    except Exception as e:
        print(f"❌ Ошибка: {e}")
    print(f"✅ Бот {bot.user} запущен!")
    print(f"📊 На серверах: {len(bot.guilds)}")
    print(f"🔧 Команд: {len(bot.commands)}")
    await bot.change_presence(
        activity=discord.CustomActivity(
            name="Слежу за порядком 🛡️",
        )
    )
    await bot.add_cog(TempVoice(bot))

# Запуск бота
if __name__ == "__main__":
    TOKEN = os.getenv('BOT_TOKEN_RULER')
    manager = DB_Manager('/app/database/fg_db.db')
    if TOKEN:
        bot.run(TOKEN)
    else:
        print("❌ Токен не найден! Создайте .env файл с BOT_TOKEN")
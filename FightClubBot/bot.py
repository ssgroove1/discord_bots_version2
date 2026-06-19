import discord, sys, os, asyncio, io, time, re, aiohttp, random
from dotenv import load_dotenv
from collections import defaultdict
from discord.ext import commands
from discord import app_commands
from datetime import datetime
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))
from database.db_logic import DB_Manager
from PIL import Image, ImageDraw, ImageFont, ImageOps
from discord.errors import HTTPException, Forbidden, NotFound
from discord import Interaction

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
GIF_PATTERNS = [
    r"\.gif($|\?)",       
    r"tenor\.com/view",   
    r"giphy\.com/gifs"    
]
SUPPORT_ROLES = [1513487279749074994, 1513487556887449692, 1513487970127183912, 1513268159598166127, 1515424488014221524, 1513261409209811055]
PANEL_CONFIGS = {}
LEVEL_ROLES = {
    1: 1516414618212503632,  # ID роли за 1 уровень
    5: 1513266642988171304,  # ID роли за 5 уровень
    10: 1512913425519345674,  # ID роли за 10 уровень
}

# Настройки бота
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.moderation = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents)

# ========== КЛАССЫ ДЛЯ КНОПОК ==========

class AntiSpam:
    def __init__(self, max_messages=5, time_window=5):
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
            await interaction.response.send_message("<:warningemoji:1515756604178305054> У вас нет прав для закрытия этого тикета.", ephemeral=True)
            return
        # Отключаем кнопку, чтобы избежать спама кликами
        self.clear_items()
        await interaction.message.edit(view=self)
        await interaction.response.send_message("<:warningemoji:1515756604178305054> **ᴛиᴋᴇᴛ зᴀᴋᴩыᴛ ᴀдʍиниᴄᴛᴩᴀциᴇй.**\n<:forbiddenemoji:1515780232404144279> ϶ᴛоᴛ ᴋᴀнᴀᴧ будᴇᴛ ᴨоᴧноᴄᴛью удᴀᴧᴇн чᴇᴩᴇз **1 ʍинуᴛу**.")
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
        await ticket_channel.send(
            content=f"{member.mention} | ᴀᴅᴍɪɴɪsᴛʀᴀᴛɪᴏɴ", 
            embed=embed, 
            view=CloseTicketView()
        )
        
        # Сообщаем пользователю (скрыто в системном окне), что чат создан
        await interaction.followup.send(f"Приватный чат успешно создан: {ticket_channel.mention}", ephemeral=True)

# --- 3. Кнопка «Открыть тикет» на главной панели ---
class DynamicUserView(discord.ui.View):
    def __init__(self, custom_id: str):
        super().__init__(timeout=None)
        self.open_ticket_btn.custom_id = custom_id

    @discord.ui.button(label="оᴛᴋᴩыᴛь ᴛиᴋᴇᴛ", style=discord.ButtonStyle.green)
    async def open_ticket_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        fields = PANEL_CONFIGS.get(button.custom_id)
        if not fields:
            await interaction.response.send_message("Ошибка: Настройки панели сброшены.", ephemeral=True)
            return
        
        # Открываем форму с вопросами
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
            await interaction.response.send_message("Укажите хотя бы один вопрос!", ephemeral=True)
            return

        if len(fields) > 5:
            await interaction.response.send_message("В одном окне Discord поддерживает строго до 5 строк! Сократите количество вопросов.", ephemeral=True)
            return

        panel_id = f"ticket_panel_{interaction.id}"
        PANEL_CONFIGS[panel_id] = fields

        embed = discord.Embed(
            title="<:warnemoji:1515687856549658774> ᴄоздᴀᴛь обᴩᴀщᴇниᴇ",
            description=self.panel_text.value,
            color=discord.Color.darker_grey()
        )
        await self.channel.send(embed=embed, view=DynamicUserView(custom_id=panel_id))
        await interaction.response.send_message("Панель успешно создана!", ephemeral=True)

class TempVoice(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        # Игнорируем ботов
        if member.bot:
            return
        # 1. Пользователь ЗАШЁЛ в голосовой канал-триггер
        if after.channel and after.channel.id == TRIGGER_CHANNEL_ID:
            # Находим категорию для временных каналов
            category = discord.utils.get(member.guild.categories, id=TEMP_CATEGORY_ID)
            if not category:
                print(f"❌ Категория с ID {TEMP_CATEGORY_ID} не найдена!")
                return

            # Создаём новый канал
            new_channel = await member.guild.create_voice_channel(
                name=f"╠ {member.display_name}'s 𝙘𝙝𝙖𝙣𝙣𝙚𝙡",
                category=category,
                reason=f"Создание временного канала для {member}"
            )

            # Настраиваем права
            await new_channel.set_permissions(member, 
                connect=True, 
                manage_channels=True,
                move_members=True
            )
            await new_channel.set_permissions(member.guild.default_role, connect=True)
            
            # Перемещаем пользователя
            await member.move_to(new_channel)

        # 2. Проверяем ВСЕ временные каналы на пустоту (включая те, откуда пользователь вышел)
        await self.check_empty_temp_channels(member.guild)
    
    async def check_empty_temp_channels(self, guild):
        category = guild.get_channel(TEMP_CATEGORY_ID)
        if not category:
            return
        
        # Проходим по всем голосовым каналам в категории
        for channel in category.voice_channels:
            # Пропускаем триггерный канал
            if channel.id == TRIGGER_CHANNEL_ID:
                continue
            
            # Если в канале никого нет - удаляем
            if len(channel.members) == 0:
                try:
                    await channel.delete(reason="Канал пуст, удаляю.")
                except discord.NotFound:
                    pass  # Канал уже удалён
                except discord.Forbidden:
                    print(f"❌ Нет прав для удаления {channel.name}")
                except Exception as e:
                    print(f"❌ Ошибка при удалении {channel.name}: {e}")

class ConfirmAction(discord.ui.View):
    """Кнопки подтверждения действия"""
    def __init__(self, user_id, action, target):
        super().__init__(timeout=30) # Какое время существуют кнопки
        self.user_id = user_id
        self.action = action
        self.target = target
        self.value = None
    
    @discord.ui.button(label="✅ Подтвердить", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Это не ваше действие!", ephemeral=True)
            return
        self.value = True
        self.stop()
    
    @discord.ui.button(label="❌ Отмена", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Это не ваше действие!", ephemeral=True)
            return
        self.value = False
        self.stop()

class ModPanel(discord.ui.View):
    """Панель модерации с кнопками"""
    def __init__(self, moderator, target):
        super().__init__(timeout=60)
        self.moderator = moderator
        self.target = target
    
    @discord.ui.button(label="Варн", style=discord.ButtonStyle.primary, emoji="⚠️")
    async def warn_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.moderator:
            await interaction.response.send_message("❌ Эта панель не для вас!", ephemeral=True)
            return
        await interaction.response.send_modal(WarnModal(self.target))

    @discord.ui.button(label="Мут", style=discord.ButtonStyle.primary, emoji="🔇")
    async def mute_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.moderator:
            await interaction.response.send_message("❌ Эта панель не для вас!", ephemeral=True)
            return
        await interaction.response.send_modal(MuteModal(self.target))
    
    @discord.ui.button(label="Кик", style=discord.ButtonStyle.danger, emoji="👢")
    async def kick_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.moderator:
            await interaction.response.send_message("❌ Эта панель не для вас!", ephemeral=True)
            return
        
        view = ConfirmAction(interaction.user.id, "kick", self.target)
        await interaction.response.send_message(f"⚠️ Вы уверены, что хотите кикнуть {self.target.mention}?", view=view, ephemeral=True)
        
        await view.wait()
        if view.value:
            try:
                await self.target.kick(reason=f"Кикнут {self.moderator.name}")
                await interaction.edit_original_response(content=f"✅ {self.target.mention} был кикнут!", view=None)
            except:
                await interaction.edit_original_response(content="❌ Не удалось кикнуть пользователя!", view=None)
        else:
            await interaction.edit_original_response(content="✅ Действие отменено", view=None)
    
    @discord.ui.button(label="Бан", style=discord.ButtonStyle.danger, emoji="🔨")
    async def ban_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.moderator:
            await interaction.response.send_message("❌ Эта панель не для вас!", ephemeral=True)
            return
        
        view = ConfirmAction(interaction.user.id, "ban", self.target)
        await interaction.response.send_message(f"⚠️ Вы уверены, что хотите забанить {self.target.mention}?", view=view, ephemeral=True)
        
        await view.wait()
        if view.value:
            try:
                await self.target.ban(reason=f"Забанен {self.moderator.name}")
                await interaction.edit_original_response(content=f"✅ {self.target.mention} был забанен!", view=None)
            except:
                await interaction.edit_original_response(content="❌ Не удалось забанить пользователя!", view=None)
        else:
            await interaction.edit_original_response(content="✅ Действие отменено", view=None)

class WarningView(discord.ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=60)
        self.user_id = user_id

    @discord.ui.button(label="ᴨочᴇʍу ʍоё ᴄообщᴇниᴇ удᴀᴧᴇно?", style=discord.ButtonStyle.gray)
    async def button_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id == self.user_id:
            await interaction.response.send_message("В этом канале разрешено отправлять только ссылки на GIF-анимации!", ephemeral=True)
        else:
            await interaction.response.send_message("Это уведомление предназначено не для вас.", ephemeral=True)

class WarnModal(discord.ui.Modal):
    def __init__(self, target):
        super().__init__(title="Выдача варна")
        self.target = target
    
        reason = discord.ui.TextInput(
            label="Причина варна",
            placeholder="Укажите причину...",
            required=True,
            max_length=500
        )
        self.add_item(self.reason)
    
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.send_message(f"⚠️ Варн выдан {self.target.mention} по причине: {self.reason.value}", ephemeral=False)
        # Здесь можно добавить логирование варнов в БД

class MuteModal(discord.ui.Modal, title="Выдача мута"):
    def __init__(self, target):
        super().__init__()
        self.target = target
    
        duration = discord.ui.TextInput(
            label="Длительность (в минутах)",
            placeholder="10, 30, 60...",
            required=True
        )
        
        reason = discord.ui.TextInput(
            label="Причина мута",
            placeholder="Укажите причину...",
            required=True,
            max_length=500
        )

        self.add_item(self.duration)
        self.add_item(self.reason)
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            minutes = int(self.duration.value)
            duration_seconds = minutes * 60
            
            # Создаем роль Muted если её нет
            mute_role = interaction.guild.get_role(MUTED_ROLE)
            if not mute_role:
                mute_role = await interaction.guild.create_role(name="Muted")
                for channel in interaction.guild.channels:
                    await channel.set_permissions(mute_role, send_messages=False, add_reactions=False)
            
            await self.target.add_roles(mute_role, reason=f"Мут на {minutes} мин. Причина: {self.reason.value}")
            await interaction.response.send_message(f"🔇 {self.target.mention} получил мут на {minutes} минут. Причина: {self.reason.value}")
            
            # Авто-снятие мута
            await asyncio.sleep(duration_seconds)
            await self.target.remove_roles(mute_role)
            
        except ValueError:
            await interaction.response.send_message("❌ Неправильный формат времени! Используйте число (минуты)", ephemeral=True)

# ========== НЕКОТОРЫЕ РЕФЕРЕНС ==========

trusted_bots = {1513553810369417216, 1512556017492295851, 1515369279724195891, 302050872383242240, 575776004233232386, 315926021457051650}
FONT_PATH = "UNCAGE-Regular.ttf"

# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ДЛЯ ОБРАБОТКИ RATE LIMIT
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

async def safe_respond(interaction: Interaction, content=None, max_retries=3, **kwargs):
    if content is None and not kwargs.get('embed') and not kwargs.get('file'):
        return None
    # Проверяем, отправлен ли уже ответ
    if interaction.response.is_done():
        # Используем followup
        for attempt in range(max_retries):
            try:
                return await interaction.followup.send(content, **kwargs)
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
        # Отправляем первый ответ
        for attempt in range(max_retries):
            try:
                await interaction.response.send_message(content, **kwargs)
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
    return None

async def safe_edit(interaction_or_message, content=None, max_retries=3, **kwargs):
    if content is None and not kwargs.get('embed'):
        return None
    
    # Если это Interaction
    if isinstance(interaction_or_message, Interaction):
        for attempt in range(max_retries):
            try:
                await interaction_or_message.response.edit_message(content=content, **kwargs)
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
        return None
    
    # Если это Message
    for attempt in range(max_retries):
        try:
            return await interaction_or_message.edit(content=content, **kwargs)
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


async def safe_fetch_channel(bot, channel_id, max_retries=3):
    """
    Безопасное получение канала с обработкой rate limit
    """
    for attempt in range(max_retries):
        try:
            return await bot.fetch_channel(channel_id)
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


async def safe_fetch_user(bot, user_id, max_retries=3):
    """
    Безопасное получение пользователя с обработкой rate limit
    """
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


async def safe_followup(interaction: Interaction, content=None, max_retries=3, **kwargs):
    """
    Безопасная отправка followup сообщения для Interaction
    """
    if content is None and not kwargs.get('embed') and not kwargs.get('file'):
        return None
    
    for attempt in range(max_retries):
        try:
            return await interaction.followup.send(content, **kwargs)
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
    roles = {
        'category': member.guild.get_role(WARNINGS_CATEGORY_ROLE),
        1: member.guild.get_role(FIRST_WARN_ROLE),
        2: member.guild.get_role(SECOND_WARN_ROLE),
        3: member.guild.get_role(THIRD_WARN_ROLE)
    }
    user_id = member.id
    user_data = await manager.get_user_ruler(user_id)
    current_warns = user_data["warnings"]
    next_warn = current_warns + 1
    if next_warn <= 3:
        if current_warns > 0:
            await member.remove_roles(roles[current_warns])
        await member.add_roles(roles[next_warn], reason=f"Предупреждение #{next_warn}. Причина: {reason}")
        
        await interaction.response.send_message(
            f"<:warnemoji:1515687856549658774> {member.mention} нᴀᴋᴀзᴀн **{warn_text(next_warn)}** ᴨᴩᴇдуᴨᴩᴇждᴇниᴇʍ! ᴨᴩичинᴀ: {reason}",
            ephemeral=False
        )
        if next_warn == 3:
            await member.ban(reason=f"3 предупреждения. {reason} (Модератор: {interaction.user})")
            await interaction.followup.send(f"<:neutralizeemoji:1515694760990347325> {member.mention} **быᴧ нᴇйᴛᴩᴀᴧизоʙᴀн** зᴀ ᴨᴧохоᴇ ᴨоʙᴇдᴇниᴇ...")
    if not any(role.id == WARNINGS_CATEGORY_ROLE for role in member.roles):
        await member.add_roles(roles['category'])
    
    await manager.update_user_ruler(user_id, next_warn, user_data['reputation'], user_data['last_time_reputation'])

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
        await member.send(embed=dm_embed)
    except:
        pass  # Если у пользователя закрыты ЛС

async def get_user_id_by_nickname(guild: discord.Guild, nickname: str) -> int:
    for member in guild.members:
        if member.display_name == nickname or member.name == nickname:
            return member.id
    return None

# ========== КОМАНДЫ НАСТРОЙКИ ==========

@bot.tree.command(name='sync', description='Синхронизировать команды.')
@app_commands.default_permissions(administrator=True)
async def sync(interaction: discord.Interaction):
    if interaction.user.id != DEVELOPER_ID:
        await interaction.response.send_message("❌ У тебя нет прав для этой команды.", ephemeral=True)
        return
    bot.tree.clear_commands(guild=None)
    await bot.tree.sync(guild=None)
    await interaction.response.send_message("✅ Команды синхронизированы для текущего сервера.", ephemeral=False)

@bot.tree.command(name='update', description='Обновить текстовые каналы.')
@app_commands.default_permissions(administrator=True)
async def update_command_chats(interaction: discord.Interaction):
    if interaction.user.id != DEVELOPER_ID:
        await interaction.response.send_message("❌ У тебя нет прав для этой команды.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    mute_role, count_role = interaction.guild.get_role(MUTED_ROLE), interaction.guild.get_role(COUNT_ROLE)
    if not mute_role or not count_role:
        await interaction.followup.send("❌ Роли не найдены!", ephemeral=True)
        return
    count = 0
    for channel in interaction.guild.channels:
        if isinstance(channel, discord.CategoryChannel):
            continue
        try:
            await channel.set_permissions(mute_role, send_messages=False, add_reactions=False)
            if channel.id == COUNT_CHANNEL:
                await channel.set_permissions(count_role, send_messages=False, add_reactions=False)
            count += 1
        except Exception as e:
            print(f"Ошибка в канале {channel.name}: {e}")
    for voice_channel in interaction.guild.voice_channels:
        try:
            await voice_channel.set_permissions(mute_role, send_messages=False, connect=False)
        except Exception as e:
            print(f"Ошибка в канале {voice_channel.name}: {e}")
    
    await interaction.followup.send(f"✅ Обновление прав завершено. Обработано {count} каналов.", ephemeral=True)

# ========== КОМАНДЫ МОДЕРАЦИИ ==========

@bot.tree.command(name="create_ticket", description="Создать панель тикета.")
@app_commands.checks.has_permissions(administrator=True)
async def create_ticket(interaction: discord.Interaction):
    await interaction.response.send_modal(AdminSetupModal(channel=interaction.channel))

@bot.tree.command(name='clear', description='Очистить чат.')
@app_commands.default_permissions(manage_messages=True)
async def clear_messages(interaction: discord.Interaction, amount: int = None):
    channel = bot.get_channel(MOD_LOGS_COMMANDS)
    if amount is None:
        amount = 10
    elif amount > 100:
        amount = 100
    elif amount < 0:
        await interaction.response.send_message("❌ Количество должно быть больше 0!", ephemeral=True)
        return
    await interaction.response.send_message(f"<:clearemoji:1515691240476377218> удᴀᴧᴇниᴇ {amount} ᴄообщᴇний...", ephemeral=True)
    try:
        deleted = await interaction.channel.purge(limit=amount)
        await interaction.edit_original_response(content=f"<:successemoji:1515691944460685372> удᴀᴧᴇно {len(deleted)} ᴄообщᴇний")
        await channel.send(f"[<:clearemoji:1515691240476377218>] Пользователь {interaction.user.mention} использовал команду **/clear** с удалением {amount} сообщений в канале {interaction.channel.mention}.")
    except Exception as e:
        await interaction.edit_original_response(content=f"❌ Ошибка при удалении: {e}")

@bot.tree.command(name='kick', description='Выгнать пользователя.')
@app_commands.default_permissions(kick_members=True)
async def kick_member(interaction: discord.Interaction, member: discord.Member, reason: str = "Не указана"):
    """Кикает участника"""
    if member == interaction.user:
        await interaction.response.send_message("❌ Нельзя кикнуть самого себя!", ephemeral=True)
        return
    if member.guild_permissions.administrator:
        await interaction.response.send_message("❌ Нельзя кикнуть администратора!", ephemeral=True)
        return
    if member.bot:
        await interaction.response.send_message("🤖 Нельзя модерировать бота!", ephemeral=True)
        return
    if not member in member.guild.members:
        await interaction.response.send_message("❌ Нельзя кикнуть несуществующего пользователя!", ephemeral=True)
        return
    channel = bot.get_channel(MOD_LOGS_COMMANDS)
    user_id_int = await get_user_id_by_nickname(interaction.guild, member.name)
    user_id = interaction.guild.get_member(user_id_int)
    if user_id:
        await user_id.kick(reason=f"{reason} (Модератор: {interaction.user})")
        await interaction.response.send_message(f"<:kickemoji:1515693208783425617> {member.mention} **ʙᴩᴇʍᴇнно оᴛᴄᴛᴩᴀнён**. ᴨᴩичинᴀ: {reason}", ephemeral=False)
        await channel.send(f"[<:kickemoji:1515693208783425617>] Пользователь {interaction.user.mention} использовал команду **/kick** на игроке {member.mention}, причина: {reason}")
    else:
        await interaction.response.send_message(f"⚠️ Пользователь не найден.", ephemeral=True)

@bot.tree.command(name='ban', description='Забанить пользователя.')
@app_commands.default_permissions(ban_members=True)
async def ban_member(interaction: discord.Interaction, member: discord.Member, reason: str ="Не указана"):
    """Банит участника"""
    if member == interaction.user:
        await interaction.response.send_message("❌ Нельзя забанить самого себя!", ephemeral=True)
        return
    if member.bot:
        await interaction.response.send_message("🤖 Нельзя модерировать бота!", ephemeral=True)
        return
    if member.guild_permissions.administrator:
        await interaction.response.send_message("❌ Нельзя забанить администратора!", ephemeral=True)
        return
    if not member in member.guild.members:
        await interaction.response.send_message("❌ Нельзя забанить несуществующего пользователя!", ephemeral=True)
        return
    channel = bot.get_channel(MOD_LOGS_COMMANDS)
    user_id_int = await get_user_id_by_nickname(interaction.guild, member.name)
    user_id = interaction.guild.get_member(user_id_int)
    if user_id:
        await member.ban(reason=f"{reason} (Модератор: {interaction.user})")
        await interaction.response.send_message(f"<:banemoji:1515689296118677534> {member.mention} **быᴧ уᴄᴛᴩᴀнён** <:neutralizeemoji:1515694760990347325>. ᴨᴩичинᴀ: {reason}", ephemeral=False)
        await channel.send(f"[<:banemoji:1515689296118677534>] Пользователь {interaction.user.mention} использовал команду **/ban** на игроке {member.mention}, причина: {reason}")
    else:
        await interaction.response.send_message(f"⚠️ Пользователь не найден.", ephemeral=True)

@bot.tree.command(name='unban', description='Разбанить пользователя.')
@app_commands.default_permissions(ban_members=True)
async def unban_member(interaction: discord.Interaction, name_or_id: str):
    """Разбанивает пользователя"""
    channel = bot.get_channel(MOD_LOGS_COMMANDS)
    banned_users = [entry async for entry in interaction.guild.bans()]
    user = None
    if name_or_id.isdigit():
        user_id = int(name_or_id)
        user = discord.Object(id=user_id)
    else:
        for ban_entry in banned_users:
            if name_or_id.lower() in ban_entry.user.name.lower():
                user = ban_entry.user
                break
    if user:
        await interaction.guild.unban(user)
        # Правильная проверка
        if hasattr(user, 'mention'):
            user_mention = user.mention
        else:
            # Если user - это discord.Object, получаем реального пользователя
            if hasattr(user, 'id'):
                real_user = bot.get_user(user.id)
                if real_user:
                    user_mention = real_user.mention
                else:
                    user_mention = f"<@{user.id}>"  # Ручное упоминание через ID
            else:
                user_mention = str(user)
        await interaction.response.send_message(f"<:unbanemoji:1515696568156557433> ᴨоᴧьзоʙᴀᴛᴇᴧь {user_mention} **нᴇ ʙиноʙᴇн**!", ephemeral=False)
        await channel.send(f"[<:unbanemoji:1515696568156557433>] Пользователь {interaction.user.mention} использовал команду **/unban** на игроке {user_mention}")
    else:
        await interaction.response.send_message("❌ Пользователь не найден в бан-листе!", ephemeral=True)

@bot.tree.command(name='mute', description='Ограничить пользователю право голоса.')
@app_commands.default_permissions(moderate_members=True)
async def mute_member(interaction: discord.Interaction, member: discord.Member, minutes: int = None, reason: str = "Не указана"):
    """Выдает мут участнику"""
    if member == interaction.user:
        await interaction.response.send_message("❌ Нельзя замутить самого себя!", ephemeral=True)
        return
    if member.bot:
        await interaction.response.send_message("🤖 Нельзя модерировать бота!", ephemeral=True)
        return
    if member.guild_permissions.administrator:
        await interaction.response.send_message("❌ Нельзя замутить администратора!", ephemeral=True)
        return
    channel = bot.get_channel(MOD_LOGS_COMMANDS)
    if minutes is None:
        minutes = 10
    if minutes > 1440:
        minutes = 1440
    mute_role = interaction.guild.get_role(MUTED_ROLE)
    await member.add_roles(mute_role, reason=f"Мут на {minutes} минут. Причина: {reason}")
    await interaction.response.send_message(f"<:muteemoji:1515688038867538000> {member.mention} **ᴀᴩᴇᴄᴛоʙᴀн** нᴀ {minutes} ʍинуᴛ. ᴨᴩичинᴀ: {reason}", ephemeral=False)
    await channel.send(f"[<:muteemoji:1515688038867538000>] Пользователь {interaction.user.mention} использовал команду **/mute** на игроке {member.mention}, мут на {minutes} минут, причина: {reason}")
    # Авто-снятие мута
    await asyncio.sleep(minutes * 60)
    await member.remove_roles(mute_role)
    try:
        await interaction.response.send_message(f"<:unmuteemoji:1515698075367112857> {member.mention} **зᴀᴋончиᴧ** ᴛюᴩᴇʍный **ᴄᴩоᴋ** ᴀʙᴛоʍᴀᴛичᴇᴄᴋи!", ephemeral=True)
    except discord.HTTPException:
        try:
            await interaction.followup.send(f"<:unmuteemoji:1515698075367112857> {member.mention} **зᴀᴋончиᴧ** ᴛюᴩᴇʍный **ᴄᴩоᴋ** ᴀʙᴛоʍᴀᴛичᴇᴄᴋи!", ephemeral=True)
        except Exception as e:
            print(f"Ошибка при отправке сообщения о размуте: {e}")

@bot.tree.command(name='unmute', description='Вернуть пользователю право голоса.')
@app_commands.default_permissions(moderate_members=True)
async def unmute_member(interaction: discord.Interaction, member: discord.Member):
    """Снимает мут с участника"""
    mute_role = interaction.guild.get_role(MUTED_ROLE)
    if mute_role in member.roles:
        channel = bot.get_channel(MOD_LOGS_COMMANDS)
        await member.remove_roles(mute_role)
        await interaction.response.send_message(f"<:unmuteemoji:1515698075367112857> {member.mention} **зᴀᴋончиᴧ ᴄᴩоᴋ** доᴄᴩочно!", ephemeral=False)
        await channel.send(f"[<:unmuteemoji:1515698075367112857>] Пользователь {interaction.user.mention} использовал команду **/umnute** на игроке {member.mention}")
    else:
        await interaction.response.send_message("❌ У этого пользователя нет мута!", ephemeral=True)

@bot.tree.command(name='warn', description='Выдать предупреждение пользователю.')
@app_commands.default_permissions(moderate_members=True, ban_members=True)
async def warn_member(interaction: discord.Interaction, member: discord.Member, reason: str ="Не указана"):
    """Выдает предупреждение"""
    if member.bot:
        await interaction.response.send_message("🤖 Нельзя модерировать бота!", ephemeral=True)
        return
    if member == interaction.user:
        await interaction.response.send_message("❌ Нельзя модерировать самого себя!", ephemeral=True)
        return
    if member.guild_permissions.administrator:
        await interaction.response.send_message("❌ Нельзя выдавать предупреждение администратору!", ephemeral=True)
        return
    await warn_user(interaction, member, reason)
    channel = bot.get_channel(MOD_LOGS_COMMANDS)
    await channel.send(f"[<:warnemoji:1515687856549658774>] Пользователь {interaction.user.mention} использовал команду **/warn** на игроке {member.mention}, причина: {reason}")

@bot.tree.command(name='unwarn', description='Снять предупреждение с пользователя.')
@app_commands.default_permissions(moderate_members=True, ban_members=True)
async def unwarn_member(interaction: discord.Interaction, member: discord.Member):
    user_data = await manager.get_user_ruler(member.id)
    if user_data["warnings"] <= 0:
        return await interaction.response.send_message(f"❌ {member.mention} нᴇ иʍᴇᴇᴛ ᴨᴩᴇдуᴨᴩᴇждᴇний.", ephemeral=True)
    
    roles = {1: FIRST_WARN_ROLE, 2: SECOND_WARN_ROLE, 3: THIRD_WARN_ROLE}
    await member.remove_roles(interaction.guild.get_role(roles[user_data["warnings"]]))
    if user_data["warnings"] - 1 > 0:
        await member.add_roles(interaction.guild.get_role(roles[user_data["warnings"] - 1]))
    else:
        await member.remove_roles(interaction.guild.get_role(WARNINGS_CATEGORY_ROLE))
    new_warns = user_data["warnings"] - 1
    await manager.update_user_ruler(member.id, new_warns, user_data['reputation'], user_data['last_time_reputation'])
    await interaction.response.send_message(f"<:unbanemoji:1515696568156557433> {member.mention} ᴀᴨᴇᴧᴧиᴩоʙᴀн, ᴄняᴛо 1 ᴨᴩᴇдуᴨᴩᴇждᴇниᴇ.")
    channel = bot.get_channel(MOD_LOGS_COMMANDS)
    if channel:
        await channel.send(f"[<:unbanemoji:1515696568156557433>] Пользователь {interaction.user.mention} использовал команду **/unwarn** на игроке {member.mention}.")

@bot.tree.command(name='modpanel', description='Панель модерации.')
@app_commands.default_permissions(administrator=True)
async def mod_panel(interaction: discord.Interaction, member: discord.Member = None):
    """Открывает панель модерации для участника"""
    if member is None:
        await interaction.response.send_message("❌ Укажите участника: `/modpanel @user`", ephemeral=True)
        return
    if member.bot:
        await interaction.response.send_message("🤖 Нельзя модерировать бота!", ephemeral=True)
        return
    if member == interaction.user:
        await interaction.response.send_message("❌ Нельзя модерировать самого себя!", ephemeral=True)
        return
    if member.guild_permissions.administrator:
        await interaction.response.send_message("❌ Нельзя модерировать администратора!", ephemeral=True)
        return
    joined_timestamp = int(member.joined_at.timestamp())
    embed = discord.Embed(
        title="🛡️ The moderation panel",
        description=f"Действия для {member.mention}",
        color=discord.Color.blue()
    )
    embed.add_field(name="ID", value=member.id, inline=True)
    embed.add_field(name="Имя", value=member.display_name, inline=True)
    embed.add_field(name="Дата присоединения", value=f'<t:{joined_timestamp}:F>', inline=True)
    
    view = ModPanel(interaction.user, member)
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

# ========== КОМАНДЫ ДЛЯ ИНФОРМАЦИИ ==========

@bot.tree.command(name='userinfo', description='Узнайте информацию об пользователи.')
async def user_info(interaction: discord.Interaction, member: discord.Member = None):
    if interaction.channel.id != COMMANDS_CHANNEL and interaction.channel.id != MOD_COMMANDS_CHANNEL:
        await interaction.response.send_message(f"<:forbbiden2emoji:1517479332866429008> Эта команда работает только в канале <#{COMMANDS_CHANNEL}>!", ephemeral=True)
        return
    if member is None:
        member = interaction.user
    # Получаем UNIX timestamp (секунды, а не миллисекунды)
    user_data = await manager.get_user_ruler(member.id)
    joined_timestamp = int(member.joined_at.timestamp())
    created_timestamp = int(member.created_at.timestamp())
    embed = discord.Embed(
        title=f"<:techicalemoji:1515678259767939262> ɪɴꜰᴏʀᴍᴀᴛɪᴏɴ ᴀʙᴏᴜᴛ {member.display_name}",
        color=discord.Color.darker_grey()
    )
    
    embed.set_thumbnail(url=member.avatar.url if member.avatar else member.default_avatar.url)
    embed.add_field(name="ɪᴅ <:peopleemoji:1517486620939649044>", value=member.id, inline=True)
    embed.add_field(name="иʍя ᴨоᴧьзоʙᴀᴛᴇᴧя <:coolemoji:1517487042018410577>", value=member.name, inline=True)
    embed.add_field(name="ʀᴇᴘᴜᴛᴀᴛɪᴏɴ <:reputationemoji:1517480379286556832>", value=user_data["reputation"], inline=True)
    embed.add_field(name="ᴀᴋᴋᴀунᴛ ᴄоздᴀн", value=f'<t:{created_timestamp}:f>', inline=True)
    embed.add_field(name="ᴨᴩиᴄоᴇдиниᴧᴄя", value=f'<t:{joined_timestamp}:f>', inline=True)
    
    await interaction.response.send_message(embed=embed, ephemeral=False)

@bot.tree.command(name='serverinfo', description='Узнайте информацию о сервере.')
async def server_info(interaction: discord.Interaction):
    """Показывает информацию о сервере"""
    if interaction.channel.id != COMMANDS_CHANNEL and interaction.channel.id != MOD_COMMANDS_CHANNEL:
        await interaction.response.send_message(f"<:forbbiden2emoji:1517479332866429008> Эта команда работает только в канале <#{COMMANDS_CHANNEL}>!", ephemeral=True)
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
    embed.add_field(name="ʙᴧᴀдᴇᴧᴇц <:owneremoji:1517494149119611063>", value=guild.owner.mention, inline=True)
    embed.add_field(name="учᴀᴄᴛниᴋоʙ <:coolemoji:1517487042018410577>", value=guild.member_count, inline=True)
    embed.add_field(name="ᴋᴀнᴀᴧоʙ <:clearemoji:1515691240476377218>", value=len(guild.channels), inline=True)
    embed.add_field(name="ᴩоᴧᴇй <:rolesemoji:1517494151086866522>", value=len(guild.roles), inline=True)
    embed.add_field(name="дᴀᴛᴀ ᴄоздᴀния <:techicalemoji:1515678259767939262>", value=f"<t:{created_timestamp}:D>", inline=True)
    
    await interaction.response.send_message(embed=embed, ephemeral=False)

@bot.tree.command(name='reputation', description='Узнайте репутацию пользователя.')
async def user_info(interaction: discord.Interaction, member: discord.Member = None):
    if interaction.channel.id != COMMANDS_CHANNEL and interaction.channel.id != MOD_COMMANDS_CHANNEL:
        await interaction.response.send_message(f"<:forbbiden2emoji:1517479332866429008> Эта команда работает только в канале <#{COMMANDS_CHANNEL}>!", ephemeral=True)
        return
    if member is None:
        member = interaction.user
    user_data = await manager.get_user_ruler(member.id)
    embed = discord.Embed(
        title=f"<:peopleemoji:1517486620939649044> {member.display_name}'s ʀᴇᴘᴜᴛᴀᴛɪᴏɴ",
        description=f"у ᴨоᴧьзоʙᴀᴛᴇᴧя **{user_data['reputation']} очᴋоʙ ᴩᴇᴨуᴛᴀции** <:reputationemoji:1517480379286556832>\nдᴧя уʙᴇᴧичᴇния чьᴇй-ᴛо ᴩᴇᴨуᴛᴀции иᴄᴨоᴧьзуйᴛᴇ `+rep @User`",
        color=discord.Color.darker_grey()
    )
    embed.set_thumbnail(url=member.avatar.url if member.avatar else member.default_avatar.url)
    
    await interaction.response.send_message(embed=embed, ephemeral=False)

@bot.tree.command(name="level", description="Показать карточку уровня и опыта участника.")
@app_commands.describe(member="Выберите участника сервера, чтобы посмотреть его уровень (необязательно)")
async def level_command(interaction: discord.Interaction, member: discord.Member = None):
    await interaction.response.defer()
    
    target_member = member or interaction.user
    
    data = await manager.get_user_data(target_member.id)
    user_level = data["level"]
    current_xp = data["xp"]
    role_name = data["role"]
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
            role_name=role_name
        )
        discord_file = discord.File(fp=image_buf, filename="level_card.png")
        await interaction.followup.send(file=discord_file)
        
    except Exception as e:
        # Если что-то сломается внутри генерации картинки, бот сообщит об этом, а не зависнет
        print(f"Ошибка при отправке карточки уровня: {e}")
        await interaction.followup.send("Произошла ошибка при генерации карточки уровня.", ephemeral=True)

# ========== ТЕКСТОВЫЕ СОБЫТИЕ ==========

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    user_id = message.author.id
    if message.author.bot and user_id not in trusted_bots:
        try:
            await message.author.ban(reason="Неавторизованный бот")
        except:
            pass
        return
    if bot.user in message.mentions and user_id == DEVELOPER_ID:
        await safe_send(message.channel, f"{message.author.mention}, бот ещё жив! ✅")
    if message.content == "+rep" and not message.author.bot:
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
    data = await manager.get_user_data(user_id)

    current_xp = int(data["xp"] + random.randint(5, 10))
    current_level = data["level"]
    current_role = data["role"]

    xp_needed = await manager.get_xp_needed(current_level)

    leveled_up = False
    while current_xp >= xp_needed:
        current_xp -= xp_needed
        current_level += 1
        xp_needed = await manager.get_xp_needed(current_level)
        leveled_up = True

    if leveled_up:
        await safe_send(message.channel, f"<:congrantemoji:1517514349965475954> {message.author.mention}, ʙы доᴄᴛиᴦᴧи **{current_level}** уᴩоʙня!", delete_after=10)
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
    if message.author.guild_permissions.administrator:
        await bot.process_commands(message)
        return
    content_lower = message.content.lower()
    match = re.search(URL_REGEX, content_lower)  # URL_REGEX должен быть строкой паттерна
    if match:  # Проверяем, что URL найден
        is_gif = any(re.search(pattern, match.group()) for pattern in GIF_PATTERNS)
        if not is_gif:
            try:
                await safe_delete(message)
                view = WarningView(user_id=user_id)
                await safe_send(message.channel, 
                    f"<:clearemoji:1515691240476377218> {message.author.mention}, ʙᴀɯᴇ ᴄообщᴇниᴇ удᴀᴧᴇно.", 
                    view=view, 
                    delete_after=10
                )
            except (discord.Forbidden, discord.NotFound):  # Объединение исключений
                pass
            return
    if await anti_spam.is_muted(message.author):
        await safe_delete(message)
        return
    current_time = time.time()
    if anti_spam.is_spam(user_id, current_time):
        await safe_delete(message)
        warnings = anti_spam.add_spam_warning(user_id)
        
        # Оптимизированная структура действий
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
    """Сохраняем роли пользователя при выходе"""
    if member.bot:
        return
    current_roles = [role.id for role in member.roles if role.name != "@everyone"]
    await manager.update_user_roles_ruler(member.id, current_roles)

@bot.event
async def on_member_join(member):
    if member.bot and member.id not in getattr(bot, 'trusted_set', trusted_bots):
        channel = bot.get_channel(WELCOME_CHANNEL)
        await channel.send(f"<:neutralizeemoji:1515694760990347325> ʙᴩᴀжᴇᴄᴋоᴇ уᴄᴛᴩойᴄᴛʙо, {member.mention}, **быᴧо нᴇйᴛᴩᴀᴧизоʙᴀно** ᴧучɯиʍи ᴄᴨᴇц-оᴛᴩядᴀʍи.")
        return await member.ban(reason="Неавторизованный бот")
    
    roles_to_restore = await manager.get_user_roles_ruler(member.id)
    roles_objects = []
    for role_id in roles_to_restore:
        role = member.guild.get_role(role_id)
        if role is not None and role.name != "@everyone":
            roles_objects.append(role)

    tasks = []
    if roles_objects:
        tasks.append(member.add_roles(*roles_objects, reason="Восстановление ролей"))
    if ch := bot.get_channel(WELCOME_CHANNEL):
        tasks.append(ch.send(embed=discord.Embed(title="👋 Welcome!", description=f"Привет, {member.mention}!\nРады видеть тебя на **{member.guild.name}**", color=discord.Color.dark_grey()).add_field(name="📅 Присоединился", value=f"<t:{int(member.joined_at.timestamp())}:R>", inline=True).add_field(name="👤 Участников", value=member.guild.member_count, inline=True).set_thumbnail(url=member.display_avatar.url)))
    if roles := [r for r in map(member.guild.get_role, [JOIN_ROLE1, JOIN_ROLE2, JOIN_ROLE3]) if r]:
        tasks.append(member.add_roles(*roles, reason="Авто-роли"))
    if not member.bot:
        tasks.append(send_dm_welcome(member))
    tasks and await asyncio.gather(*tasks, return_exceptions=True)

# ========== ЛОГИРОВАНИЕ СОБЫТИЙ ==========

@bot.event
async def on_message_delete(message):
    if message.author.bot or not message.content:
        return
    log_channel = bot.get_channel(MOD_LOGS)
    if not log_channel:
        return
    embed = discord.Embed(
        title="🗑️ The message deleted",
        description=f"**ᴀʙᴛоᴩ:** {message.author.mention}\n**ᴋᴀнᴀᴧ:** {message.channel.mention}",
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

            size_kb = att.size / 1024
            if size_kb > 1024:
                size_str = f"{size_kb/1024:.1f} MB"
            else:
                size_str = f"{size_kb:.1f} KB"
            icon = "🖼️" if is_image else "🎬" if is_video else "📎"
            
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
    """Логирует изменения сообщений"""
    if before.author.bot or before.content == after.content:
        return
    log_channel = bot.get_channel(MOD_LOGS)
    if not log_channel:
        return
    if before.guild:
        channel_name = before.channel.mention
    else:
        channel_name = "Личные сообщения"
    embed = discord.Embed(
        title="✏️ The message redacted",
        description=f"**ᴀʙᴛоᴩ:** {before.author.mention}\n**ᴋᴀнᴀᴧ:** {channel_name}",
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
    # Игнорируем неизвестные команды
    if isinstance(error, commands.CommandNotFound):
        return
    # Словарь с сообщениями об ошибках
    error_messages = {
        commands.MissingPermissions: "❌ У вас недостаточно прав для выполнения этой команды!",
        commands.MissingRequiredArgument: f"❌ Не хватает аргументов! Используйте `!help {ctx.command.name}`",
        commands.BadArgument: "❌ Неверный аргумент! Укажите существующего пользователя.",
        commands.NotOwner: "❌ Эта команда доступна только владельцу бота!",
        commands.CommandOnCooldown: f"⏰ Подождите {error.retry_after:.1f} секунд перед повторным использованием!",
        commands.BotMissingPermissions: f"❌ У бота недостаточно прав! Нужны: {', '.join(error.missing_permissions)}",
        commands.MaxConcurrencyReached: "❌ Команда уже выполняется! Подождите."
    }
    # Проверяем известные ошибки
    for error_type, message in error_messages.items():
        if isinstance(error, error_type):
            await ctx.send(message)
            return
    
    # Неизвестная ошибка - логируем в консоль и сообщаем
    print(f"⚠️ Неизвестная ошибка: {error}")
    await ctx.send(f"⚠️ Произошла неизвестная ошибка. Разработчик уже уведомлён.")

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
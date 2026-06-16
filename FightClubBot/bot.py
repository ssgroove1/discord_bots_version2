import discord, sys, os, asyncio, json, time, re
from dotenv import load_dotenv
from collections import defaultdict
from discord.ext import commands
from discord import app_commands
from datetime import datetime
from pathlib import Path
parent_dir = os.path.dirname(os.path.dirname(__file__))
sys.path.append(parent_dir)
from db_logic import DB_Manager

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
                mute_members=True,
                deafen_members=True,
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
ROLES_FILE = "user_roles.json"

def load_roles():
    if not os.path.exists(ROLES_FILE):
        return {}
    with open(ROLES_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_roles(roles_data):
    with open(ROLES_FILE, 'w', encoding='utf-8') as f:
        json.dump(roles_data, f, indent=4, ensure_ascii=False)

def warn_text(num):
    return {1: "ⲡⲉⲣⲃыⲙ", 2: "ⲃⲧⲟⲣыⲙ", 3: "ⲧⲣⲉⲧьⲉⲙ"}.get(num, "очᴇᴩᴇдныʍ")

async def warn_user(interaction: discord.Interaction, member: discord.Member = None, reason: str ="Не указана"):
    global warns
    roles = {
        'category': member.guild.get_role(WARNINGS_CATEGORY_ROLE),
        1: member.guild.get_role(FIRST_WARN_ROLE),
        2: member.guild.get_role(SECOND_WARN_ROLE),
        3: member.guild.get_role(THIRD_WARN_ROLE)
    }
    user_id = interaction.user.id
    user_data = manager.get_user_ruler(user_id)
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
    
    manager.update_user_ruler(user_id, next_warn, user_data['reputation'])

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
    await interaction.followup.send(f"<:unmuteemoji:1515698075367112857> {member.mention} **зᴀᴋончиᴧ** ᴛюᴩᴇʍный **ᴄᴩоᴋ** ᴀʙᴛоʍᴀᴛичᴇᴄᴋи!", ephemeral=True)

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

@bot.tree.command(name='warn', description='Выдать предупреждение пользователю.') # IN PROGRESS
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
    """Показывает информацию о пользователе"""
    if interaction.channel.id != COMMANDS_CHANNEL and interaction.channel.id != MOD_COMMANDS_CHANNEL:
        await interaction.response.send_message(f"❌ Эта команда работает только в канале <#{COMMANDS_CHANNEL}>!", ephemeral=True)
        return
    if member is None:
        member = interaction.user
    # Получаем UNIX timestamp (секунды, а не миллисекунды)
    joined_timestamp = int(member.joined_at.timestamp())
    created_timestamp = int(member.created_at.timestamp())
    embed = discord.Embed(
        title=f"<:techicalemoji:1515678259767939262> Информация о {member.display_name}",
        color=member.color if member.color != discord.Color.default() else discord.Color.darker_grey()
    )
    
    embed.set_thumbnail(url=member.avatar.url if member.avatar else member.default_avatar.url)
    embed.add_field(name="ɪᴅ", value=member.id, inline=True)
    embed.add_field(name="иʍя ᴨоᴧьзоʙᴀᴛᴇᴧя", value=member.name, inline=True)
    embed.add_field(name="ниᴋнᴇйʍ", value=member.nick or "Нет", inline=True)
    embed.add_field(name="ᴀᴋᴋᴀунᴛ ᴄоздᴀн", value=f'<t:{created_timestamp}:f>', inline=True)
    embed.add_field(name="ᴨᴩиᴄоᴇдиниᴧᴄя", value=f'<t:{joined_timestamp}:f>', inline=True)
    embed.add_field(name="ᴩоᴧи", value=", ".join([role.mention for role in member.roles[1:10]]) or "Нет", inline=False)
    
    await interaction.response.send_message(embed=embed, ephemeral=False)

@bot.tree.command(name='serverinfo', description='Узнайте информацию о сервере.')
async def server_info(interaction: discord.Interaction):
    """Показывает информацию о сервере"""
    if interaction.channel.id != COMMANDS_CHANNEL and interaction.channel.id != MOD_COMMANDS_CHANNEL:
        await interaction.response.send_message(f"❌ Эта команда работает только в канале <#{COMMANDS_CHANNEL}>!", ephemeral=True)
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
    embed.add_field(name="ɪᴅ", value=guild.id, inline=True)
    embed.add_field(name="ʙᴧᴀдᴇᴧᴇц", value=guild.owner.mention, inline=True)
    embed.add_field(name="учᴀᴄᴛниᴋоʙ", value=guild.member_count, inline=True)
    embed.add_field(name="ᴋᴀнᴀᴧоʙ", value=len(guild.channels), inline=True)
    embed.add_field(name="ᴩоᴧᴇй", value=len(guild.roles), inline=True)
    embed.add_field(name="дᴀᴛᴀ ᴄоздᴀния", value=f"<t:{created_timestamp}:D>", inline=True)
    
    await interaction.response.send_message(embed=embed, ephemeral=False)

# ========== ТЕКСТОВЫЕ СОБЫТИЕ ==========

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    if message.author.bot and message.author.id not in trusted_bots:
        await message.author.ban(reason="Неавторизованный бот")
        return
    urls = re.findall(URL_REGEX, message.content.lower())
    for url in urls:
        is_gif = any(re.search(pattern, url) for pattern in GIF_PATTERNS)
        if not is_gif:
            try:
                await message.delete()
                view = WarningView(user_id=message.author.id)
                await message.channel.send(
                    f"<:clearemoji:1515691240476377218> {message.author.mention}, ʙᴀɯᴇ ᴄообщᴇниᴇ удᴀᴧᴇно.", 
                    view=view, 
                    delete_after=10
                )
            except discord.Forbidden:
                print("Ошибка: У бота нет прав на удаление сообщений.")
            except discord.NotFound:
                pass
            break  
    if bot.user in message.mentions and message.author.id == DEVELOPER_ID:
        await message.channel.send(f"{message.author.mention}, бот ещё жив! ✅")
    if message.author.guild_permissions.administrator:
        await bot.process_commands(message)
        return
    if await anti_spam.is_muted(message.author):
        await message.delete()
        return
    current_time = time.time()
    if anti_spam.is_spam(message.author.id, current_time):
        await message.delete()
        warnings = anti_spam.add_spam_warning(message.author.id)
        actions = {
            1: (lambda: (message.author.send("<:warningemoji:1515756604178305054> **ᴨᴩᴇдуᴨᴩᴇждᴇниᴇ!** нᴇ ᴄᴨᴀʍьᴛᴇ ʙ чᴀᴛᴇ!\nᴄᴧᴇдующᴇᴇ нᴀᴩуɯᴇниᴇ - ʍуᴛ нᴀ 5 ʍинуᴛ."), 
                        message.channel.send(f"<:warningemoji:1515756604178305054> {message.author.mention}, нᴇ ᴄᴨᴀʍьᴛᴇ ʙ чᴀᴛᴇ! ", delete_after=5))),
            2: (lambda: (anti_spam.mute_user(message.author, 300),
                        message.author.send("<:muteemoji:1515688038867538000> ʙы **зᴀдᴇᴩжᴀны** нᴀ 5 ʍинуᴛ зᴀ ᴄᴨᴀʍ!"),
                        message.channel.send(f"<:muteemoji:1515688038867538000> {message.author.mention} **зᴀдᴇᴩжᴀн** нᴀ 5 ʍинуᴛ зᴀ ᴄᴨᴀʍ!"))),
            3: (lambda: (anti_spam.mute_user(message.author, 1800),
                        message.author.send("<:muteemoji:1515688038867538000> ʙы **зᴀдᴇᴩжᴀны** нᴀ 30 ʍинуᴛ зᴀ ᴨоʙᴛоᴩный ᴄᴨᴀʍ!"),
                        message.channel.send(f"<:muteemoji:1515688038867538000> {message.author.mention} **зᴀдᴇᴩжᴀн** нᴀ 30 ʍинуᴛ зᴀ ᴨоʙᴛоᴩный ᴄᴨᴀʍ!"))),
        }
        if warnings in actions:
            await asyncio.gather(*[task for task in actions[warnings]() if task])
        elif warnings == 4:
            await message.author.kick(reason="Спам после нескольких предупреждений")
            await message.channel.send(f"<:kickemoji:1515693208783425617> {message.author.mention} **ʙᴩᴇʍᴇнно оᴛᴄᴛᴩᴀнён** зᴀ ᴄᴨᴀʍ!")
        elif warnings >= 5:
            await message.author.ban(reason="Многократный спам")
            await message.channel.send(f"<:neutralizeemoji:1515694760990347325> {message.author.mention} **быᴧ нᴇйᴛᴩᴀᴧизоʙᴀн** зᴀ ʍноᴦоᴋᴩᴀᴛный ᴄᴨᴀʍ!")
        return
    # Автосброс предупреждений (одной строкой)
    if anti_spam.get_spam_warning_count(message.author.id) and anti_spam.message_history[message.author.id] and time.time() - anti_spam.message_history[message.author.id][-1] > 30:
        anti_spam.reset_warnings(message.author.id)
    await bot.process_commands(message)

@bot.event
async def on_member_remove(member):
    """Сохраняем роли пользователя при выходе"""
    if member.bot:
        return
    current_roles = [role.id for role in member.roles if role.name != "@everyone"]
    manager.update_user_roles_ruler(member.id, current_roles)

@bot.event
async def on_member_join(member):
    if member.bot and member.id not in getattr(bot, 'trusted_set', trusted_bots):
        channel = bot.get_channel(WELCOME_CHANNEL)
        await channel.send(f"<:neutralizeemoji:1515694760990347325> ʙᴩᴀжᴇᴄᴋоᴇ уᴄᴛᴩойᴄᴛʙо, {member.mention}, **быᴧо нᴇйᴛᴩᴀᴧизоʙᴀно** ᴧучɯиʍи ᴄᴨᴇц-оᴛᴩядᴀʍи.")
        return await member.ban(reason="Неавторизованный бот")
    
    roles_to_restore = manager.get_user_roles_ruler(member.id)
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
    """Логирует удаленные сообщения"""
    if message.author.bot or not message.content:
        return
    if not (channel := bot.get_channel(MOD_LOGS)):
        return
    channel = bot.get_channel(MOD_LOGS)
    if channel and message.content:
        embed = discord.Embed(
            title="🗑️ The message deleted",
            description=f"**ᴀʙᴛоᴩ:** {message.author.mention}\n**ᴋᴀнᴀᴧ:** {message.channel.mention}",
            color=discord.Color.red(),
            timestamp=datetime.now()
        )
        embed.add_field(name="Содержание", value=f'```{message.content[:1000]}```', inline=False)
        await channel.send(embed=embed)

@bot.event
async def on_message_edit(before, after): # сообщение до, после
    """Логирует изменения сообщений"""
    if before.author.bot or before.content == after.content:
        return
    if not (channel := bot.get_channel(MOD_LOGS)):
        return
    channel = bot.get_channel(MOD_LOGS)
    if channel:
        embed = discord.Embed(
            title="✏️ The message redacted",
            description=f"**ᴀʙᴛоᴩ:** {before.author.mention}\n**ᴋᴀнᴀᴧ:** {before.channel.mention}",
            color=discord.Color.orange(),
            timestamp=datetime.now()
        )
        embed.add_field(name="Было", value=f"```{before.content[:400]}```" if before.content else "*Пусто*", inline=False)
        embed.add_field(name="Стало", value=f"```{after.content[:400]}```" if after.content else "*Пусто*", inline=False)
        await channel.send(embed=embed)

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
    manager = DB_Manager('"/data/fg_db.db"')
    if TOKEN:
        bot.run(TOKEN)
    else:
        print("❌ Токен не найден! Создайте .env файл с BOT_TOKEN")
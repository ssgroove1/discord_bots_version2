import discord, os, asyncio, aiohttp, random, re, sys, time
from dotenv import load_dotenv
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))
from database.db_logic import DB_Manager
from discord.errors import HTTPException, Forbidden, NotFound
from discord import Interaction, Message

env_path = Path(__file__).parent.parent / "shared.env"
load_dotenv(env_path)
PREFIX = os.getenv('COMMAND_PREFIX')
COUNT_ROLE = int(os.getenv('COUNT_BAD_ROLE'))
COMMANDS_CHANNEL = int(os.getenv('COMMANDS_CHANNEL_ID'))
MOD_COMMANDS_CHANNEL = int(os.getenv('MOD_COMMANDS_CHANNEL_ID'))
RADIO_COMMANDS_CHANNEL = int(os.getenv('RADIO_COMMANDS_CHANNEL_ID'))
COUNT_CHANNEL = int(os.getenv('COUNT_CHANNEL_ID'))
GUILD_ID = int(os.getenv('GUILD_ID'))
DEVELOPER_ID = int(os.getenv('DEVELOPER_ID'))

# Настройки бота
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.moderation = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents)

# ========== КЛАССЫ КНОПОК ==========

RADIO_CONFIG = {
    "public": {"name": "общий", "emoji": "📻", "range": 100},
    "emergency": {"name": "϶ᴋᴄᴛᴩᴇнный", "emoji": "🚨", "range": 50},
    "umbrella": {"name": "ᴜᴍʙʀᴇʟʟᴀ", "emoji": "🩸", "range": 30},
    "stars": {"name": "s.ᴛ.ᴀ.ʀ.s.", "emoji": "🌟", "range": 75},
    "bsaa": {"name": "ʙsᴀᴀ", "emoji": "🧪", "range": 80}
}
RADIO_SOUNDS = ["պⲉⲗɥⲟⲕ.", "ⲏⲁⲥⲧⲣⲟύⲕⲁ.", "ⲥυⲅⲏⲁⲗ ⲡⲣυⲏяⲧ.", "ⲡⲉⲣⲉⲇⲁю...", "ⲡⲣυⲉⲙ..."]
RADIO_NOISES = ["шшш...", "треск...", "шум ветра...", "помехи...", "потеря сигнала..."]
CIPHER = {'а':'α','б':'β','в':'ν','г':'γ','д':'δ','е':'ε','ё':'ε','ж':'ζ','з':'ζ','и':'ι',
          'й':'ι','к':'κ','л':'λ','м':'μ','н':'ν','о':'ο','п':'π','р':'ρ','с':'σ','т':'τ',
          'у':'υ','ф':'φ','х':'χ','ц':'ψ','ч':'ω','ш':'ω','щ':'ω','ъ':'ʏ','ы':'ʏ','ь':'ʏ',
          'э':'ε','ю':'υ','я':'α'}
CHANNELS = [app_commands.Choice(name=f"{v['emoji']} {v['name']}", value=k) for k,v in RADIO_CONFIG.items()]
ENCRYPTS = [app_commands.Choice(name=n, value=str(i)) for i,n in enumerate(["❌ Нет", "🔒 Базовое", "🔐 Полное"])]
NOISES = [app_commands.Choice(name=n, value=str(i)) for i,n in enumerate(["📡 Без помех", "📡 Легкие", "📡 Средние", "📡 Сильные"])]

# --- РАДИО КОНТРОЛЛЕР ---
class RadioManager:
    def __init__(self): self.active = {}
    def encrypt(self, text, level=1):
        if not level: return text
        enc = ''.join(CIPHER.get(c, c) for c in text.lower())
        return ''.join(c + random.choice('*&#@!?') if random.random() > .7 and level == 2 else c for c in enc)
    def decrypt(self, text):
        rev = {v:k for k,v in CIPHER.items()}
        return ''.join(rev.get(c, c) for c in re.sub(r'[*&#@!?]', '', text))
    def add_noise(self, text, level):
        if not level: return text
        words = text.split()
        if level >= 1:
            for _ in range(random.randint(0, len(words)//4)):
                i = random.randint(0, len(words)-1)
                words[i] = words[i] + '...' if random.random()>.5 else '...' + words[i]
        if level >= 2:
            for _ in range(random.randint(len(words)//3, len(words)//2)):
                i = random.randint(0, len(words)-1)
                words[i] = f"[{random.choice(RADIO_NOISES)}] {words[i]}"
        if level >= 3:
            for _ in range(random.randint(len(words)//2, len(words))):
                i = random.randint(0, len(words)-1)
                w = list(words[i])
                if len(w) > 1:
                    for j in range(random.randint(1, len(w)//2)):
                        if random.random()>.5: w[j] = random.choice('*?!')
                    words[i] = ''.join(w)
        return ' '.join(words)
    
class RadioView(discord.ui.View):
    def __init__(self, recipient, sender, channel, msg, enc):
        super().__init__(timeout=300)
        self.recipient, self.sender, self.channel, self.msg, self.enc = recipient, sender, channel, msg, enc
    
    @discord.ui.button(label="📨 Ответить", style=discord.ButtonStyle.primary)
    async def reply(self, inter: discord.Interaction, button: discord.ui.Button):
        if inter.user.id != self.recipient.id:
            return await safe_send(inter, "<:deniedemoji:1519737463126360294> Не для вас!", ephemeral=True)
        await inter.response.send_modal(RadioModal(self.sender, self.recipient, self.channel, self.msg, self.enc))
    @discord.ui.button(label="🔊 Повтор", style=discord.ButtonStyle.secondary)
    async def repeat(self, inter: discord.Interaction, button: discord.ui.Button):
        if inter.user.id not in [self.recipient.id, self.sender.id]:
            return await safe_send(inter, "<:deniedemoji:1519737463126360294> Нет доступа!", ephemeral=True)
        await safe_send(inter, f"```\n{self.msg}\n```", ephemeral=True)

class RadioModal(discord.ui.Modal, title="Ответ"):
    reply = discord.ui.TextInput(label="Сообщение", style=discord.TextStyle.paragraph, max_length=200)
    
    def __init__(self, sender, recipient, channel, orig, enc):
        super().__init__()
        self.sender, self.recipient, self.channel, self.orig, self.enc = sender, recipient, channel, orig, enc
    
    async def on_submit(self, inter):
        msg = self.reply.value
        if self.enc: msg = radio_mgr.encrypt(msg, self.enc)
        embed = discord.Embed(
            title="<:radioemoji:1519767792193110086> оᴛʙᴇᴛ",
            description=f"📡 {inter.user.mention} → {self.sender.mention}",
            color=discord.Color.gold()
        )
        embed.add_field(name="<:messageemoji:1519990110882496705> ᴄообщᴇниᴇ", value=f"```\n{msg}\n```", inline=False)
        try:
            if self.channel == "public" or self.channel == "emergency":
                await safe_send(inter, embed=embed)
            else:
                await safe_send(self.sender, embed=embed)
            await safe_send(inter, "<:confirmedemoji:1519738036936638474> Отправлено!", ephemeral=True)
        except discord.Forbidden:
            await safe_send(inter, f"<:deniedemoji:1519737463126360294> Не могу отправить ЛС {self.sender.mention} — пользователь закрыл ЛС", ephemeral=True)
        except Exception as e:
            await safe_send(inter, f"<:deniedemoji:1519737463126360294> Ошибка: {e}", ephemeral=True)
radio_mgr = RadioManager()

# --- КНОПКА УЧАСТИЯ (Для публичного сообщения) ---
class PublicGiveawayView(discord.ui.View):
    def __init__(self, manager):
        super().__init__(timeout=None)
        self.manager = manager

    @discord.ui.button(label="учᴀᴄᴛʙоʙᴀᴛь (0)", style=discord.ButtonStyle.green, custom_id="public_join")
    async def join_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.manager.is_ended or self.manager.is_cancelled:
            return await safe_send(interaction, "Розыгрыш уже завершен или отменен.", ephemeral=True)
        user_id = interaction.user.id
        if user_id in self.manager.participants:
            self.manager.participants.remove(user_id)
            await safe_send(interaction, "Вы вышли из розыгрыша.", ephemeral=True)
        else:
            self.manager.participants.add(user_id)
            await safe_send(interaction, "Вы успешно зарегистрировались в розыгрыше!", ephemeral=True)
        button.label = f"учᴀᴄᴛʙоʙᴀᴛь ({len(self.manager.participants)})"
        await interaction.message.edit(view=self)

# --- КНОПКИ УПРАВЛЕНИЯ (Для скрытого сообщения) ---
class AdminControlView(discord.ui.View):
    def __init__(self, manager):
        super().__init__(timeout=None)
        self.manager = manager

    @discord.ui.button(label="оᴛʍᴇниᴛь ᴩозыᴦᴩыɯ", style=discord.ButtonStyle.red, custom_id="admin_cancel")
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            return safe_send(interaction, "У вас нет прав для отмены этого розыгрыша.", ephemeral=True)
        if self.manager.is_ended or self.manager.is_cancelled:
            return safe_send(interaction, "Этот розыгрыш уже нельзя отменить.", ephemeral=True)
        self.manager.is_cancelled = True
        self.manager.event.set()
        for child in self.children:
            child.disabled = True
        for child in self.manager.public_view.children:
            child.disabled = True
        self.manager.public_embed.description = f"{self.manager.description}\n\n<:forbiddenemoji:1515790567555203123> **ᴩозыᴦᴩыɯ быᴧ оᴛʍᴇнᴇн ᴀдʍиниᴄᴛᴩᴀᴛоᴩоʍ.**"
        self.manager.public_embed.color = discord.Color.red()
        await self.manager.public_message.edit(embed=self.manager.public_embed, view=self.manager.public_view)
        await interaction.response.edit_message(view=self)
        
        await safe_send(interaction, "Вы успешно отменили розыгрыш.", ephemeral=True)

    @discord.ui.button(label="зᴀʙᴇᴩɯиᴛь доᴄᴩочно", style=discord.ButtonStyle.blurple, custom_id="admin_end_fast")
    async def end_fast_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            return await safe_send(interaction, "У вас нет прав для досрочного завершения.", ephemeral=True)
        if self.manager.is_ended or self.manager.is_cancelled:
            return await safe_send(interaction, "Розыгрыш нельзя завершить.", ephemeral=True)
        self.manager.is_ended = True
        self.manager.event.set() 
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)
        
        await safe_send(interaction, "Розыгрыш завершается досрочно...", ephemeral=True)

# --- ГЛАВНЫЙ КОНТРОЛЛЕР РОЗЫГРЫША ---
class GiveawayManager:
    def __init__(self, description, prize_text_after, mention_role):
        self.description = description
        self.prize_text_after = prize_text_after
        self.mention_role = mention_role
        self.participants = set()
        self.is_cancelled = False
        self.is_ended = False
        self.event = asyncio.Event()
        
        self.public_message = None
        self.public_embed = None
        self.public_view = None

# --- КНОПКА ДЛЯ ПОЛУЧЕНИЯ ЦВЕТОВ ---
class get_flower(discord.ui.View):
    def __init__(self, user, target, text):
        super().__init__(timeout=300)
        self.user = user
        self.target = target
        self.text = text
    
    @discord.ui.button(label="ᴨоᴧучиᴛь цʙᴇᴛы", style=discord.ButtonStyle.primary, emoji="💐")
    async def get_flower_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user == self.user:
            await safe_send(interaction, f"🤗 Вы не можете отменить действие!", ephemeral=True)
            return
        elif interaction.user != self.target:
            await safe_send(interaction, f"😡 Цветы не для вас!", ephemeral=True)
            return
        button.disabled = True
        await safe_edit(interaction, view=self)
        await safe_send(interaction, f"🌹 {self.user.mention} дарит вам цветы!\n💌 С пожеланиями: {self.text}", ephemeral=True)

# --- КНОПКА ПОЖЕНИТЬСЯ ---
class MarriageView(discord.ui.View):
    def __init__(self, proposer_id: int, target_id: int):
        super().__init__(timeout=300)
        self.proposer_id = proposer_id
        self.target_id = target_id
        self.message = None
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.target_id:
            await safe_send(interaction, "<:deniedemoji:1519737463126360294> Это предложение не для вас!", ephemeral=True)
            return False
        return True
    
    @discord.ui.button(label="💍 Принять", style=discord.ButtonStyle.success)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        if manager.is_married(self.proposer_id):
            await safe_send(interaction, "<:deniedemoji:1519737463126360294> Вы уже состоите в браке!", ephemeral=True)
            for child in self.children:
                child.disabled = True
            await interaction.response.edit_message(view=self)
            return
        
        if manager.is_married(self.target_id):
            await safe_send(interaction, "<:deniedemoji:1519737463126360294> Этот пользователь уже в браке!", ephemeral=True)
            for child in self.children:
                child.disabled = True
            await interaction.response.edit_message(view=self)
            return

        result = manager.create_marriage_funbot(self.proposer_id, self.target_id)
        
        for child in self.children:
            child.disabled = True
        try:
            await interaction.response.edit_message(view=self)
        except:
            await interaction.edit_original_response(view=self)
        
        if "✅" in result:
            embed = discord.Embed(
                title="<:ringemoji:1523657901569212426> бᴩᴀᴋ зᴀᴋᴧючᴇн!",
                description=f"<@{self.proposer_id}> и <@{self.target_id}> ᴛᴇᴨᴇᴩь ʍуж и жᴇнᴀ! <:giveawayemoji:1515792000279121930>",
                color=discord.Color.pink(),
                timestamp=discord.utils.utcnow()
            )
            await safe_send(interaction, embed=embed,
            )
        else:
            await safe_send(interaction,
                content=f"<:deniedemoji:1519737463126360294> {result}",
            )
    
    @discord.ui.button(label="❌ Отказать", style=discord.ButtonStyle.danger)
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        for child in self.children:
            child.disabled = True
        try:
            await interaction.response.edit_message(view=self)
        except:
            await interaction.edit_original_response(view=self)
        
        await safe_send(interaction,
            content=f"<:deniedemoji:1519737463126360294> <@{self.target_id}> оᴛᴋᴀзᴀᴧ(ᴀ) ʙ бᴩᴀᴋᴇ.",
        )
        
    
    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except:
                pass

# Создаем кнопку подтверждения развода
class DivorceView(discord.ui.View):
    def __init__(self, user_id: int, spouse_id: int):
        super().__init__(timeout=30)
        self.user_id = user_id
        self.spouse_id = spouse_id
        self.message = None
    
    @discord.ui.button(label="💔 Подтвердить развод", style=discord.ButtonStyle.danger)
    async def confirm_divorce(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await safe_send(interaction, "<:deniedemoji:1519737463126360294> Это не ваш развод!", ephemeral=True)
            return
        
        # Расторгаем брак
        success, message = manager.divorce_simple(self.user_id)
        
        # Отключаем кнопки
        for child in self.children:
            child.disabled = True
        try:
            await interaction.response.edit_message(view=self)
        except:
            await interaction.edit_original_response(view=self)
        
        if success:
            embed = discord.Embed(
                title="<:brokenheartemoji:1523753728375656588> бᴩᴀᴋ ᴩᴀᴄᴛоᴩᴦнуᴛ",
                description=f"<@{self.user_id}> ᴩᴀзʙᴇᴧᴄя(ᴀᴄь) ᴄ <@{self.spouse_id}>.",
                color=discord.Color.red(),
                timestamp=discord.utils.utcnow()
            )
            embed.set_image(url='https://i.pinimg.com/originals/5c/3f/d0/5c3fd04b1e985a8bddd87ae3c7e58827.gif')
            await safe_send(interaction, embed=embed, ephemeral=False)
            
            # Уведомляем супруга
            try:
                spouse = await bot.fetch_user(self.spouse_id)
                await interaction.channel.send(
                    f"{spouse.mention}, ваш брак был расторгнут. <:brokenheartemoji:1523753728375656588>")
            except:
                pass
        else:
            await safe_send(interaction, 
                content=f"<:deniedemoji:1519737463126360294> {message}",
                ephemeral=True)
    
    @discord.ui.button(label="❌ Отмена", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await safe_send(interaction, "<:deniedemoji:1519737463126360294> Это не ваш развод!", ephemeral=True)
            return
        
        for child in self.children:
            child.disabled = True
        
        await safe_edit(interaction,
            content="<:heartemoji:1516740800518557696> ᴩᴀзʙод оᴛʍᴇнᴇн.", view=self)
    
    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        # ✅ Проверяем, что self.message - это Message, а не bool
        if self.message and isinstance(self.message, discord.Message):
            try:
                await self.message.edit(view=self)
            except Exception as e:
                print(f"⚠️ Ошибка при обновлении сообщения по таймауту: {e}")
        else:
            print("ℹ️ Нет сообщения для обновления или это не Message объект")

# ========== ДЕКОРАТОР ==========

def guild_only():
    async def predicate(interaction: discord.Interaction):
        if not interaction.guild:
            await safe_send(interaction, "<:deniedemoji:1519737463126360294> Только на сервере!", ephemeral=True)
            return False
        return True
    return app_commands.check(predicate)

# ========== БЕЗОПАСНАЯ ОТПРАВКА СООБЩЕНИЙ ==========

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

async def send_with_view(interaction, embed, view, content=None, ephemeral=False):
    try:
        if interaction.response.is_done():
            # Если уже отвечали - используем followup
            message = await interaction.followup.send(
                content=content,
                embed=embed,
                view=view,
                ephemeral=ephemeral
            )
        else:
            # Отправляем новый ответ
            await interaction.response.send_message(
                content=content,
                embed=embed,
                view=view,
                ephemeral=ephemeral
            )
            message = await interaction.original_response()
        
        # ✅ Сохраняем сообщение в view
        if isinstance(message, discord.Message):
            view.message = message
        else:
            print(f"⚠️ Получен не-Message объект: {type(message)}")
        
        return message
    except Exception as e:
        print(f"❌ Ошибка при отправке: {e}")
        return None

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

# ========== НЕКОТОРЫЙ РЕФЕРЕНС ==========

herbs = {
    "зеленая": "ʙᴀɯ ᴨᴇᴩᴄонᴀж иᴄцᴇᴧён. <:plantemoji:1516711202544422932>",
    "красная": "ʙы ᴨоᴧучиᴧи ʙᴩᴇʍᴇнный бᴀɸɸ ᴋ уᴩону. <:swordsemoji:1516712211563810836>",
    "синяя": "ᴄниʍᴀᴇᴛ оᴛᴩᴀʙᴧᴇниᴇ. (и ᴦᴧуᴨыᴇ ϶ɸɸᴇᴋᴛы) <:poisonemoji:1516712752352202862>",
    "зеленая+красная": "иᴄцᴇᴧᴇниᴇ <:plantemoji:1516711202544422932> + ʙᴩᴇʍᴇнный бᴀɸɸ. <:swordsemoji:1516712211563810836>",
    "зеленая+синяя": "иᴄцᴇᴧᴇниᴇ <:plantemoji:1516711202544422932> + ᴨоᴧучиᴧ ᴀнᴛидоᴛ. <:antidotemoji:1516713811393118278>",
    "красная+синяя": "ʙᴩᴇʍᴇнный бᴀɸɸ ᴋ уᴩону <:swordsemoji:1516712211563810836> + ᴀнᴛидоᴛ. <:antidotemoji:1516713811393118278>",
    "зеленая+красная+синяя": "ᴨоᴧноᴇ иᴄцᴇᴧᴇниᴇ <:plantemoji:1516711202544422932> + ʙᴩᴇʍᴇнный бᴀɸɸ <:swordsemoji:1516712211563810836> + ᴀнᴛидоᴛ. <:antidotemoji:1516713811393118278>",
    "зеленая+зеленая": "ʙы ᴨоᴧноᴄᴛью ʙоᴄᴄᴛᴀноʙиᴧиᴄь! <:heartemoji:1516740800518557696>",
    "зеленая+зеленая+зеленая": "ᴛᴩᴇбуᴇʍᴀя ноᴩʍᴀ нᴇ быᴧᴀ ʙыᴨоᴧнᴇнᴀ... (ɯᴀнᴄ 20%) <:brokenglassemoji:1516742443104731136>",
    "красная+красная": "ʙы ᴨоᴧучᴀᴇᴛᴇ ᴄиᴧу ᴛиᴩᴀнᴀ нᴀ нᴇᴋоᴛоᴩоᴇ ʙᴩᴇʍя! <:tiranemoji:1516747539918098432>",
    "красная+красная+красная": "ᴛᴩᴇбуᴇʍᴀя ноᴩʍᴀ нᴇ быᴧᴀ ᴄобᴧюдᴇнᴀ... (ɯᴀнᴄ 10%) <:brokenglassemoji:1516742443104731136>",
    "синяя+синяя": ": ''϶ᴛоᴛ ᴀнᴛидоᴛ ʍожᴇᴛ ʙыᴧᴇчиᴛь ʙᴄё!'' <:antidotemoji:1516713811393118278>",
    "синяя+синяя+синяя": "ʙᴀɯ ᴀнᴛидоᴛ ᴨᴩизнᴀн оᴨᴀᴄныʍ и нᴇᴄᴛᴀбиᴧьныʍ... (ɯᴀнᴄ 15%) <:brokenglassemoji:1516742443104731136>"
}
special_combos = {
    "красная+красная+красная": (1516766412981403669, 0.1, "ʙы ᴨоᴧучᴀᴇᴛᴇ ᴄиᴧу ᴛиᴩᴀнᴀ из ʀᴇsɪᴅᴇɴᴛ ᴇᴠɪʟ! <:tiranemoji:1516747539918098432>"),
    "зеленая+зеленая+зеленая": (1513501866250604569, 0.2, "ʙы ᴄоздᴀᴇᴛᴇ ноʙый ʙиᴩуᴄ, нᴀзыʙᴀя ᴇᴦо ᴛ-ᴠɪʀᴜs! <:tvirusemoji:1516761340579020910>"),
    "синяя+синяя+синяя": (1516779985338368061, 0.15, "ʙы ʙᴄᴛуᴨᴀᴇᴛᴇ ʙ ᴩяды ϶ᴧиᴛы, 𝗕𝗦𝗔𝗔! <:soldieremoji:1516779793624993843>")
}
role_checks = [
    (5, 1516767047701237870, "<:giveawayemoji:1515792000279121930> ᴨоздᴩᴀʙᴧяю! ʙы ᴨоᴧучиᴧи ᴩоᴧь {}!"),
    (10, 1513494417040867358, "<:umbrellaemoji:1516757365800833146> ᴜᴍʙʀᴇʟʟᴀ ᴄᴏʀᴘᴏʀᴀᴛɪᴏɴ ᴦоᴩдиᴛᴄя ʙᴀʍи, ʙы ᴨоᴧучиᴧи ᴩоᴧь {}!"),
    (25, 1516781259206951104, "<:d0cabb52b2db458489ad66afc62fc0ec:1516782385566449674> ʙы ᴄᴛᴀᴧи оᴄноʙоᴨоᴧожниᴋоʍ ᴜᴍʙʀᴇʟʟᴀ ᴄᴏʀᴘᴏʀᴀᴛɪᴏɴ и ᴨоᴧучᴀᴇᴛᴇ ᴩоᴧь {}!")
]
herb_cooldown = 10800

masked_user = None
mask_time = None
cooldown_mask = None
SCP_035_webhook = None
MASK_ROLE_ID = 1520061586650173591

next_number_in_count_channel = 1

with open('gifs/hug_gifs.txt', 'r', encoding='utf-8') as f:
    hug_gifs = f.readlines()
with open('gifs/kiss_gifs.txt', 'r', encoding='utf-8') as f:
    kiss_gifs = f.readlines()
with open('gifs/hello_gifs.txt', 'r', encoding='utf-8') as f:
    hello_gifs = f.readlines()
with open('gifs/flower_gifs.txt', 'r', encoding='utf-8') as f:
    flower_gifs = f.readlines()
with open('gifs/pat_gifs.txt', 'r', encoding='utf-8') as f:
    pat_gifs = f.readlines()
with open('gifs/slap_gifs.txt', 'r', encoding='utf-8') as f:
    slap_gifs = f.readlines()
with open('gifs/bite_gifs.txt', 'r', encoding='utf-8') as f:
    bite_gifs = f.readlines()
with open('gifs/cry_gifs.txt', 'r', encoding='utf-8') as f:
    cry_gifs = f.readlines()

async def remove_role_at_time(member: discord.Member, role: discord.Role, minutes: int):
    remove_time = datetime.now() + timedelta(minutes=minutes)
    await discord.utils.sleep_until(remove_time)
    
    if role in member.roles:
        await member.remove_roles(role, reason="Автоматическое снятие роли")

async def mask_death_check():
    await bot.wait_until_ready()
    global masked_user, mask_time, cooldown_mask
    
    while not bot.is_closed():
        if masked_user and (datetime.now() - mask_time).total_seconds() >= 3600:
            user = bot.get_user(masked_user)
            if user:
                for g in bot.guilds:
                    member = g.get_member(masked_user)
                    if member:
                        if "[𝙎𝘾𝙋 035]" in member.display_name:
                            try: await member.edit(nick=member.display_name.replace("[𝙎𝘾𝙋 035] ", ""))
                            except: pass
                        role = g.get_role(MASK_ROLE_ID)
                        if role and role in member.roles:
                            try: await member.remove_roles(role, reason="Умер от маски SCP-035")
                            except: pass
                        channel = bot.get_channel(1468672223564005649)
                        if channel:
                            await channel.send(f"<:SCP035_2emoji:1520066884920410311> {user.mention} ᴨоᴦибᴀᴇᴛ оᴛ ʍᴀᴄᴋи одᴇᴩжиʍоᴄᴛи!")
            
            masked_user = None
            mask_time = None
            cooldown_mask = None
        
        await asyncio.sleep(30)

def make_interaction_command(gifs_list: list, embed_title: str, action_verb: str, color: discord.Color, self_error: str, no_gifs_error: str = "<:deniedemoji:1519737463126360294> Нет доступных гифок! Проверьте файл"):
    async def command_func(interaction: discord.Interaction, member: discord.Member):
        if not gifs_list:
            await safe_send(interaction, no_gifs_error, ephemeral=True)
            return
        if member.bot:
            await safe_send(interaction, "🤖 Нельзя выполнить действия на боте!", ephemeral=True)
            return
        if member == interaction.user:
            await safe_send(interaction, self_error, ephemeral=True)
            return
        random_gif = random.choice(gifs_list)
        embed = discord.Embed(
            title=embed_title,
            description=f"{interaction.user.mention} {action_verb} {member.mention}!",
            color=color
        )
        embed.set_image(url=random_gif)
        await safe_send(interaction, embed=embed, ephemeral=False)
    
    return command_func

def parse_duration(duration_str: str) -> int:
    match = re.match(r"^(\d+)([smhd])$", duration_str.lower())
    if not match:
        return 0
    amount, unit = match.groups()
    amount = int(amount)
    units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    return amount * units[unit]

# ========== КОМАНДА ДЛЯ РЕГУЛИРОВКИ ==========

@bot.tree.command(name='sync', description='Синхронизировать команды.')
@app_commands.guild_only()
@app_commands.default_permissions(administrator=True)
async def sync_command(interaction: discord.Interaction):
    if interaction.user.id != DEVELOPER_ID:
        await safe_send(interaction, "<:deniedemoji:1519737463126360294> У тебя нет прав для этой команды.", ephemeral=True)
        return
    bot.tree.clear_commands(guild=None)
    await bot.tree.sync(guild=None)
    await safe_send(interaction, "<:confirmedemoji:1519738036936638474> Команды синхронизированы для текущего сервера.", ephemeral=False)

@bot.tree.command(name='set', description='Техническая команда.')
@app_commands.guild_only()
@app_commands.default_permissions(administrator=True)
async def set_count(interaction: discord.Interaction, last_count: int = 0):
    global next_number_in_count_channel
    if interaction.user.id != DEVELOPER_ID:
        await safe_send(interaction, "<:deniedemoji:1519737463126360294> У тебя нет прав для этой команды.", ephemeral=True)
        return
    next_number_in_count_channel = int(last_count+1)
    await safe_send(interaction, f"<:confirmedemoji:1519738036936638474> Счетчик в подсчетах изменен. Следующее число {int(next_number_in_count_channel)}", ephemeral=True)

# ========== КОМАНДЫ РАЗВЛЕЧЕНИЯ ==========

@bot.tree.command(name='обнять', description='Обнимите дорогого вам человека!')
@app_commands.guild_only()
async def hug_command(interaction: discord.Interaction, member: discord.Member):
    await make_interaction_command(
        hug_gifs,
        "🤗 Обнимашки!",
        "обнимает",
        discord.Color.pink(),
        "😥 Простите, вы не можете обнять самого себя!"
    )(interaction, member)

@bot.tree.command(name='поцеловать', description='Поцелуйте дорогого вам человека!')
@app_commands.guild_only()
async def kiss_command(interaction: discord.Interaction, member: discord.Member):
    await make_interaction_command(
        kiss_gifs,
        "🤗 Поцелуйчики!",
        "поцеловал",
        discord.Color.brand_red(),
        "😥 Простите, вы не можете поцеловать самого себя!"
    )(interaction, member)

@bot.tree.command(name='погладить', description='Погладить пользователя!')
@app_commands.guild_only()
async def pat_command(interaction: discord.Interaction, member: discord.Member):
    await make_interaction_command(
        pat_gifs,
        "🤗 Прижимашки!",
        "погладил",
        discord.Color.purple(),
        "😥 Простите, вы не можете погладить себя!"
    )(interaction, member)

@bot.tree.command(name='поздароваться', description='Поздаровайтесь с пользователем!')
@app_commands.guild_only()
async def hello_command(interaction: discord.Interaction, member: discord.Member):
    await make_interaction_command(
        hello_gifs,
        "🤗 Приветствие!",
        "поздаровался с",
        discord.Color.gold(),
        "😥 Простите, вы не можете поздароваться с собой!"
    )(interaction, member)

@bot.tree.command(name='ударить', description='Дать леща пользователю!')
@app_commands.guild_only()
async def slap_command(interaction: discord.Interaction, member: discord.Member):
    await make_interaction_command(
        slap_gifs,
        "😨 Рукоприкладство!",
        "дал леща",
        discord.Color.darker_grey(),
        "😏 Вы не можете ударить себя самого!"
    )(interaction, member)

@bot.tree.command(name='укусить', description='Укусить пользователя!')
@app_commands.guild_only()
async def bite_command(interaction: discord.Interaction, member: discord.Member):
    await make_interaction_command(
        bite_gifs,
        "😨 Укусики!",
        "кусает",
        discord.Color.darker_grey(),
        "😱 Вы не можете кусать себя самого!"
    )(interaction, member)

@bot.tree.command(name='заплакать', description='Заплакать в чате.')
@app_commands.guild_only()
async def cry_func(interaction: discord.Interaction):
    if not cry_gifs:
        await safe_send(interaction, "<:deniedemoji:1519737463126360294> Нет доступных гифок! Проверьте файл cry_gifs.txt", ephemeral=True)
        return
    random_gif = random.choice(cry_gifs)
    embed = discord.Embed(
        title="😭 Слезки!",
        description=f"{interaction.user.mention} плачет. 😢",
        color=discord.Color.blue()
    )
    embed.set_image(url=random_gif)
    await safe_send(interaction, embed=embed, ephemeral=False)

@bot.tree.command(name='цветы', description='Подарить пользователю записку с цветами!')
@app_commands.guild_only()
async def gift_user(interaction: discord.Interaction, member: discord.Member, text: str = "Всего самого наилучшего! 🤗"):
    if not flower_gifs:
        await safe_send(interaction, "<:deniedemoji:1519737463126360294> Нет доступных гифок! Проверьте файл flower_gifs.txt", ephemeral=True)
        return
    if member == interaction.user:
        await safe_send(interaction, "😥 Простите, вы не можете подарить цветы себе!", ephemeral=True)
        return
    if member.bot:
        await safe_send(interaction, "🤖 Нельзя подарить цветы боту!", ephemeral=True)
        return
    if len(text) > 150:
        await safe_send(interaction, "<:deniedemoji:1519737463126360294> Пожелание не может быть длиннее 150 символов!", ephemeral=True)
        return
    view = get_flower(user=interaction.user, target=member, text=text)
    random_gif = random.choice(flower_gifs)
    embed = discord.Embed(
        title="🤗 Цветочки, подарочки!",
        description=f"{interaction.user.mention} подарил {member.mention} цветы! 💕",
        color=discord.Color.brand_red()
    )
    embed.set_image(url=random_gif)
    await safe_send(interaction, embed=embed, view=view, ephemeral=False)

@bot.tree.command(name="мой_брак", description="Показать информацию о вашем браке.")
@app_commands.describe(user="Пользователь, информацию о браке которого вы хотите узнать.")
async def marriage_info(interaction: discord.Interaction, user: discord.Member = None):
    if user is None:
        user = interaction.user
    if not manager.is_married(user.id):
        if user.id == interaction.user.id:
            await safe_send(interaction, "<:deniedemoji:1519737463126360294> Вы не состоите в браке.", ephemeral=True)
        else:
            await safe_send(interaction, f"<:deniedemoji:1519737463126360294> {user.mention} не состоит в браке.", ephemeral=True)
        return
    spouse_id = manager.get_spouse(user.id)
    if spouse_id is None:
        await safe_send(interaction, "<:deniedemoji:1519737463126360294> Не удалось найти данные о браке.", ephemeral=True)
        return
    marriage_data = manager.get_information_marry(user.id)
    if marriage_data is None:
        await safe_send(interaction, "<:deniedemoji:1519737463126360294> Не удалось найти данные о браке.", ephemeral=True)
        return
    try:
        spouse = await bot.fetch_user(spouse_id)
        spouse_name = spouse.mention
        spouse_avatar = spouse.display_avatar.url if spouse.display_avatar else None
    except:
        spouse_name = f"<@{spouse_id}>"
        spouse_avatar = None
    created_at = marriage_data['created_at']
    created_dt = discord.utils.format_dt(
        datetime.fromtimestamp(created_at, tz=timezone.utc), 
        'f')
    relative_dt = discord.utils.format_dt(
        datetime.fromtimestamp(created_at, tz=timezone.utc),
        'R')
    
    # Вычисляем длительность брака
    days = int((time.time() - created_at) // 86400)
    hours = int(((time.time() - created_at) % 86400) // 3600)
    minutes = int(((time.time() - created_at) % 3600) // 60)
    
    if days > 0:
        duration = f"{days} дн. {hours} ч. {minutes} мин."
    elif hours > 0:
        duration = f"{hours} ч. {minutes} мин."
    else:
        duration = f"{minutes} мин."

    embed = discord.Embed(
        title="<:ringemoji:1523657901569212426> инɸоᴩʍᴀция о бᴩᴀᴋᴇ",
        color=discord.Color.pink(),
        timestamp=discord.utils.utcnow()
    )
    embed.add_field(
        name="<:smilefaceemoji:1524123343370977448> ᴄуᴨᴩуᴦ(ᴀ)",
        value=f"{spouse_name}",
        inline=False
    )
    embed.add_field(
        name="<:starsemoji:1519768273925705749> дᴀᴛᴀ зᴀᴋᴧючᴇния",
        value=f"{created_dt}\n({relative_dt})",
        inline=False
    )
    embed.add_field(
        name="<:timeemoji:1524124492236980316> дᴧиᴛᴇᴧьноᴄᴛь",
        value=f"`{duration}`",
        inline=True
    )
    if spouse_avatar:
        embed.set_thumbnail(url=spouse_avatar)
    
    embed.set_footer(
        text=f"Запросил: {interaction.user.display_name}",
        icon_url=interaction.user.display_avatar.url if interaction.user.display_avatar else None)
    await safe_send(interaction, embed=embed, ephemeral=False)

@bot.tree.command(name="заключить_брак", description="Предложить брак пользователю.")
@app_commands.describe(user="Пользователь, которому вы предлагаете брак")
async def propose_marriage(interaction: discord.Interaction, user: discord.Member):
    if user.id == interaction.user.id:
        await safe_send(interaction, "<:deniedemoji:1519737463126360294> Нельзя жениться на самом себе!", ephemeral=True)
        return
    if user.bot:
        await safe_send(interaction, "🤖 Нельзя жениться на боте!", ephemeral=True)
        return
    if manager.is_married(interaction.user.id):
        await safe_send(interaction, "<:deniedemoji:1519737463126360294> Вы уже состоите в браке!", ephemeral=True)
        return
    if manager.is_married(user.id):
        await safe_send(interaction, f"<:deniedemoji:1519737463126360294> {user.mention} уже состоит в браке!", ephemeral=True)
        return
    
    view = MarriageView(interaction.user.id, user.id)
    
    embed = discord.Embed(
        title="<:ringemoji:1523657901569212426> ᴨᴩᴇдᴧожᴇниᴇ бᴩᴀᴋᴀ",
        description=f"{interaction.user.mention} ᴨᴩᴇдᴧᴀᴦᴀᴇᴛ бᴩᴀᴋ {user.mention}!",
        color=discord.Color.pink(),
        timestamp=discord.utils.utcnow())
    embed.add_field(
        name="<:clockemoji:1523658304281116672> ʙᴩᴇʍя нᴀ оᴛʙᴇᴛ",
        value="300 ᴄᴇᴋунд",
        inline=True)
    embed.set_image(url='https://i.pinimg.com/originals/f9/ab/3f/f9ab3f93ea21d12d5a0363262a4b8802.gif')
    embed.set_footer(text="Нажмите кнопку для ответа")
    
    await send_with_view(interaction, 
        content=f"{user.mention}, у ʙᴀᴄ ᴇᴄᴛь ᴨᴩᴇдᴧожᴇниᴇ!",
        embed=embed,
        view=view)

@bot.tree.command(name="развод", description="Расторгнуть брак.")
async def divorce_command(interaction: discord.Interaction):
    if not manager.is_married(interaction.user.id):
        await safe_send(interaction, "<:deniedemoji:1519737463126360294> Вы не состоите в браке!", ephemeral=True)
        return
    
    spouse_id = manager.get_spouse(interaction.user.id)
    if spouse_id is None:
        await safe_send(interaction, "<:deniedemoji:1519737463126360294> Не удалось найти данные о браке.", ephemeral=True)
        return
    
    try:
        spouse = await bot.fetch_user(spouse_id)
        spouse_name = spouse.mention
    except:
        spouse_name = f"<@{spouse_id}>"
    
    view = DivorceView(interaction.user.id, spouse_id)
    
    embed = discord.Embed(
        title="<:brokenheartemoji:1523753728375656588> ᴨодᴛʙᴇᴩждᴇниᴇ ᴩᴀзʙодᴀ",
        description=f"ʙы уʙᴇᴩᴇны, чᴛо хоᴛиᴛᴇ ᴩᴀзʙᴇᴄᴛиᴄь ᴄ {spouse_name}?",
        color=discord.Color.red(),
        timestamp=discord.utils.utcnow()
    )
    embed.add_field(
        name="<:cautionemoji:1520064481357598770> ʙниʍᴀниᴇ",
        value="϶ᴛо дᴇйᴄᴛʙиᴇ нᴇᴧьзя оᴛʍᴇниᴛь!",
        inline=False
    )
    embed.add_field(
        name="<:clockemoji:1523658304281116672> ʙᴩᴇʍя нᴀ оᴛʙᴇᴛ",
        value="30 ᴄᴇᴋунд",
        inline=True)
    embed.set_image(url='https://i.pinimg.com/originals/81/cc/04/81cc045c3e66f8b54c71a2a85a64cc9d.gif')
    embed.set_footer(text="Нажмите кнопку для подверждение")
    
    await send_with_view(interaction, embed=embed, view=view, ephemeral=False)

@bot.tree.command(name="надеть_маску", description="Надеть маску")
@app_commands.guild_only()
async def mask(inter: discord.Interaction):
    if inter.channel.id != COMMANDS_CHANNEL and inter.channel.id != MOD_COMMANDS_CHANNEL:
        await safe_send(inter, f"<:accessdeniedemoji:1517986918573408318> Эта команда работает только в канале <#{COMMANDS_CHANNEL}>!", ephemeral=True)
        return
    global masked_user, mask_time, masked_by, cooldown_mask
    if masked_user: return await safe_send(inter, f"<:deniedemoji:1519737463126360294> Маска уже на {inter.guild.get_member(masked_user).mention}!", ephemeral=True)
    if cooldown_mask and datetime.now() < cooldown_mask:
        remain = (cooldown_mask - datetime.now()).total_seconds()
        return await safe_send(inter, f"<:deniedemoji:1519737463126360294> Ждите {int(remain//60)} мин.", ephemeral=True)
    masked_user = inter.user.id
    mask_time = datetime.now()
    cooldown_mask = datetime.now() + timedelta(hours=1, minutes=30)
    try:
        await inter.user.edit(nick=f"[𝙎𝘾𝙋 035] {inter.user.display_name}")
    except discord.Forbidden:
        pass
    role = inter.guild.get_role(MASK_ROLE_ID)
    if role:
        try:
            await inter.user.add_roles(role, reason="Надел маску SCP-035")
        except:
            pass
    embed = discord.Embed(title="<:SCP035emoji:1520063257325473913> 𝙎𝙤𝙢𝙚𝙗𝙤𝙙𝙮 𝙪𝙨𝙚𝙙 𝙖 𝙢𝙖𝙨𝙠!", description=f"<:emergencyemoji:1519769135767228576> {inter.user.mention} ᴄᴛᴀᴧ одᴇᴩжиʍ sᴄᴘ 035", color=discord.Color.light_grey())
    embed.add_field(name="<:cautionemoji:1520064481357598770> 𝑾𝒂𝒓𝒏𝒊𝒏𝒈:", value="чᴇᴩᴇз 10 ʍинуᴛ одᴇᴩжиʍоᴄᴛь! чᴇᴩᴇз чᴀᴄ - ᴄʍᴇᴩᴛь.")
    embed.set_image(url='https://i.pinimg.com/1200x/ed/6d/a0/ed6da036c1394a0333c4a0470d87ba50.jpg')
    await safe_send(inter, embed=embed)

@bot.tree.command(name="радио", description="Отправить сообщение по рации.")
@app_commands.describe(user="Кому", message="Сообщение (текст)", channel="Канал", encrypt="Шифрование", noise="Помехи")
@app_commands.choices(channel=CHANNELS, encrypt=ENCRYPTS, noise=NOISES)
@app_commands.guild_only()
async def radio(interaction: discord.Interaction, user: discord.Member, message: str,
                channel: app_commands.Choice[str] = None, encrypt: app_commands.Choice[str] = None,
                noise: app_commands.Choice[str] = None):
    if interaction.channel.id != RADIO_COMMANDS_CHANNEL and interaction.channel.id != MOD_COMMANDS_CHANNEL:
        await safe_send(interaction, f"<:deniedemoji:1519737463126360294> Эта команда работает только в канале <#{RADIO_COMMANDS_CHANNEL}>!", ephemeral=True)
        return
    if len(message) > 200:
        return await safe_send(interaction, "<:deniedemoji:1519737463126360294> Сообщение должно быть меньше 200 символов!", ephemeral=True)
    if user.bot:
        return await safe_send(interaction, "<:deniedemoji:1519737463126360294> Нельзя отправлять сообщение боту!", ephemeral=True)
    if user.id == interaction.user.id:
        return await safe_send(interaction, "<:deniedemoji:1519737463126360294> Нельзя отправить сообщение самому себе!", ephemeral=True)
    
    ch = channel.value if channel else "public"
    enc = int(encrypt.value) if encrypt else 0
    ns = int(noise.value) if noise else 0
    if enc and ch == "emergency":
        return await safe_send(interaction, "<:deniedemoji:1519737463126360294> Шифрование не может быть использовано в **экстренном канале**!", ephemeral=True)
    
    info = RADIO_CONFIG[ch]
    msg = message
    if enc: msg = radio_mgr.encrypt(msg, enc)
    if ns: msg = radio_mgr.add_noise(msg, ns)
    
    embed = discord.Embed(
        title=f"{info['emoji']} {info['name']}",
        description=f"**{random.choice(RADIO_SOUNDS)}**\n📡 {interaction.user.mention} → {user.mention}",
        color=discord.Color.darker_grey() if ch != "umbrella" else discord.Color.dark_red(),
        timestamp=datetime.now()
    )
    embed.add_field(name="ᴄообщᴇниᴇ", value=f"```\n{msg}\n```", inline=False)
    if ns: embed.add_field(name="ᴨоʍᴇхи", value=["", "<:goodconnectionemoji:1519985770750808134> Легкие", "<:mediumconnectionemoji:1519986766499811428> Средние", "<:badconnectionemoji:1519985656305291325> Сильные"][ns], inline=True)
    if enc: embed.add_field(name="ɯиɸᴩоʙᴀниᴇ", value=["", "<:lockemoji:1519992045152899072> Базовое", "<:fulllockemoji:1519992041986064506> Полное"][enc], inline=True)
    embed.add_field(name="ᴄᴛᴀᴛуᴄ", value=f"{'<:excelentconnectionemoji:1519985715977523350>' if random.random()>.2 else '<:goodconnectionemoji:1519985770750808134>'} {'Стабильна' if random.random()>.2 else 'Нестабильна'}", inline=True)
    embed.add_field(name="ᴩᴀдиуᴄ", value=f"<:radiowavesemoji:1519988737579286659> {info['range']} км", inline=True)
    
    try:
        if ch == "public" or ch == "emergency":
            await safe_send(interaction, embed=embed, view=RadioView(user, interaction.user, ch, msg, enc))
        else:
            await user.send(embed=embed, view=RadioView(user, interaction.user, ch, msg, enc))
        await safe_send(interaction, f"<:confirmedemoji:1519738036936638474> Отправлено {user.mention}", ephemeral=True)
    except discord.Forbidden:
        await safe_send(interaction, f"<:deniedemoji:1519737463126360294> Не могу отправить ЛС {user.mention} — пользователь закрыл ЛС", ephemeral=True)
    except Exception as e:
        await safe_send(interaction, f"<:deniedemoji:1519737463126360294> Ошибка: {e}", ephemeral=True)

@bot.tree.command(name="расшифровать", description="Расшифровать сообщение с радио.")
@app_commands.describe(message="Сообщение")
async def decrypt(inter: discord.Interaction, message: str):
    dec = radio_mgr.decrypt(message)
    embed = discord.Embed(title="<:keysemoji:1519980356260860066> ᴩᴀᴄɯиɸᴩоʙᴋᴀ", color=discord.Color.purple())
    embed.add_field(name="<:messageemoji:1519990110882496705> оᴩиᴦинᴀᴧ", value=f"```\n{message[:200]}```", inline=False)
    embed.add_field(name="<:unlockemoji:1519992043751997440> ᴩᴀᴄɯиɸᴩоʙᴀно", value=f"```\n{dec[:200]}```", inline=False)
    await safe_send(inter, embed=embed)

@bot.tree.command(name='8ball', description="Получить предсказание.")
@app_commands.guild_only()
async def eight_ball(interaction: discord.Interaction, question: str = None):
    if question == None:
        await safe_send(interaction, "<:deniedemoji:1519737463126360294> Вы должны написать вопрос!", ephemeral=True)
        return
    if len(question) < 5:
        await safe_send(interaction, "<:deniedemoji:1519737463126360294> Чуть длинее, пожалуйста!", ephemeral=True)
        return
    responses = ["Определённо да!", "Будьте в этом уверены!", "Нет, даже не думай...", "Мой источник говорит, что нет.", "Это запретные знания!", "Ответ неоднозначен..."]
    embed = discord.Embed(
        title=f"🔮 Гадание для {interaction.user.display_name}!",
        description=f"಄ **Вопрос:** {question}\n✘ **Ответ:** {random.choice(responses)}",
        color=discord.Color.darker_grey()
    )
    await safe_send(interaction, embed=embed, ephemeral=False)

@bot.tree.command(name="травы", description="Смешать травы для получения разных комбинаций (Resident Evil)")
@app_commands.guild_only()
@app_commands.describe(color="Выберите цвет, примеры: зеленая, красная, синяя, зеленая+красная")
async def herb(interaction: discord.Interaction, color: str):
    if interaction.channel.id != COMMANDS_CHANNEL and interaction.channel.id != MOD_COMMANDS_CHANNEL:
        await safe_send(interaction, f"<:deniedemoji:1519737463126360294> Эта команда работает только в канале <#{COMMANDS_CHANNEL}>!", ephemeral=True)
        return
    key = '+'.join(sorted(color.lower().replace(' ', '').split('+')))
    result = herbs.get(key, None)
    if result is None:
        await safe_send(interaction, f"{interaction.user.mention}, 🧪 ᴛᴩᴀʙы нᴇ ᴄочᴇᴛᴀюᴛᴄя... ᴨоᴨᴩобуй ᴇщᴇ ᴩᴀз. (Иᴄᴨоᴧьзуй: зᴇᴧᴇнᴀя, ᴋᴩᴀᴄнᴀя, зеленая+красная)")
        return
    user_id = interaction.user.id
    user_info = await manager.get_user_funbot(user_id)
    current_time = time.time()
    
    time_passed = current_time - user_info["last_time_herb"]
    if time_passed < herb_cooldown:
        seconds_left = int(herb_cooldown - time_passed)
        hours = seconds_left // 3600
        minutes = (seconds_left % 3600) // 60
        await safe_send(interaction, f"**<:deniedemoji:1519737463126360294> {interaction.user.mention}, вы уже смешивали травы!**\n⌛ Осталось: **{hours} ч. {minutes} мин.**", ephemeral=True)
        return
    
    if key in special_combos:
        role_id, chance, success_msg = special_combos[key]
        if random.random() < chance:
            role = interaction.guild.get_role(role_id)
            await interaction.user.add_roles(role, reason="🧪 Заслужил роль")
            result = success_msg  
    
    new_count = user_info["count_herb"] + 1
    await safe_send(interaction, f"{interaction.user.mention}, {result}")
    
    for count, role_id, message_template in role_checks:
        if new_count == count:
            role = interaction.guild.get_role(role_id)
            await interaction.user.add_roles(role, reason="🧪 Заслужил роль")
            await safe_send(interaction, message_template.format(role.mention), ephemeral=True)
            break
    await manager.update_user_funbot(user_id, user_info["current_aura"], new_count, current_time)

@bot.tree.command(name="giveaway", description="Запустить новый розыгрыш")
@app_commands.describe(
    описание="Текст самого розыгрыша (что происходит)",
    приз_после_выигрыша="Текст, который пишется при победе",
    время="Через сколько итоги? (Пример: 10m, 2h, 1d)",
    количество_победителей="Сколько человек должно выиграть?",
    роль_для_упоминания="Какую роль пингануть при победе (необязательно)",
    канал="Канал, куда отправить розыгрыш (необязательно)")
@app_commands.guild_only()
@app_commands.default_permissions(manage_events=True)
async def giveaway(
    interaction: discord.Interaction,
    описание: str,
    приз_после_выигрыша: str,
    время: str,
    количество_победителей: int,
    роль_для_упоминания: discord.Role = None,
    канал: discord.TextChannel = None):
    if количество_победителей <= 0:
        return await safe_send(interaction, "Количество победителей должно быть больше 0!", ephemeral=True)
    seconds = parse_duration(время)
    if seconds <= 0:
        return await safe_send(interaction, "Неверный формат времени! Используйте например: 30s, 15m, 2h, 1d.", ephemeral=True)
    target_channel = канал if канал else interaction.channel
    end_time = datetime.now(timezone.utc) + timedelta(seconds=seconds)
    timestamp = int(end_time.timestamp())

    manager = GiveawayManager(описание, приз_после_выигрыша, роль_для_упоминания)

    manager.public_embed = discord.Embed(
        title="<:giveawayemoji:1515792000279121930> ⲏⲟⲃыύ ⲣⲟⳅыⲅⲣыɯ! <:giveawayemoji:1515792000279121930>",
        description=f"{описание}\n\n<:luckyemoji:1515790408922173450> **ᴨобᴇдиᴛᴇᴧᴇй:** {количество_победителей}\n⏳ **зᴀʙᴇᴩɯиᴛᴄя:** <t:{timestamp}:R>",
        color=discord.Color.gold(),
    )
    manager.public_embed.set_footer(text="нᴀжʍиᴛᴇ нᴀ ᴋноᴨᴋу нижᴇ, чᴛобы ᴨᴩиняᴛь учᴀᴄᴛиᴇ!")
    manager.public_view = PublicGiveawayView(manager)

    manager.public_message = await safe_send(target_channel, embed=manager.public_embed, view=manager.public_view)
    
    admin_view = AdminControlView(manager)
    await safe_send(interaction, 
        f"<:confirmedemoji:1519738036936638474> Розыгрыш успешно запущен в канале {target_channel.mention}!\nПанель управления доступна только вам ниже:", 
        view=admin_view,
        ephemeral=True
    )
    try:
        await asyncio.wait_for(manager.event.wait(), timeout=float(seconds))
    except asyncio.TimeoutError:
        pass

    if manager.is_cancelled:
        return

    for child in manager.public_view.children:
        child.disabled = True
    
    manager.public_embed.description = f"{описание}\n\n<:luckyemoji:1515790408922173450> **ᴨобᴇдиᴛᴇᴧᴇй:** {количество_победителей}\n<:forbiddenemoji:1515790567555203123> **ᴩозыᴦᴩыɯ зᴀʙᴇᴩɯᴇн!**"
    await manager.public_message.edit(embed=manager.public_embed, view=manager.public_view)

    if not manager.participants:
        await safe_send(target_channel, f"ʙ ᴩозыᴦᴩыɯᴇ **'{описание}'** ниᴋᴛо нᴇ ᴨᴩиняᴧ учᴀᴄᴛиᴇ. ᴨобᴇдиᴛᴇᴧи нᴇ ʙыбᴩᴀны. <:forbiddenemoji:1515790567555203123>")
    else:
        participants_list = list(manager.participants)
        actual_winners_count = min(количество_победителей, len(participants_list))
        winners_ids = random.sample(participants_list, k=actual_winners_count)
        
        winners_mentions = [f"<@{w_id}>" for w_id in winners_ids]
        winners_text = ", ".join(winners_mentions)
        mention_str = f"\n🔔 Уведомление для роли: {manager.mention_role.mention}" if manager.mention_role else ""
        title_text = "<:giveawayemoji:1515792000279121930> ⲣⲉⳅⲩⲗьⲧⲁⲧы ⲣⲟⳅыⲅⲣыɯⲁ! <:giveawayemoji:1515792000279121930>" if actual_winners_count > 1 else "<:giveawayemoji:1515792000279121930> ⲣⲉⳅⲩⲗьⲧⲁⲧ ⲣⲟⳅыⲅⲣыɯⲁ! <:giveawayemoji:1515792000279121930>"

        success_embed = discord.Embed(
            title=title_text,
            description=f"ʙ ᴩозыᴦᴩыɯᴇ **'{описание}'\n**<:luckyemoji:1515790408922173450> ᴨобᴇждᴀюᴛ: {winners_text}!\n\n**<:treasureemoji:1515794261839188199> Ваш выигрыш:** {manager.prize_text_after}{mention_str}",
            color=discord.Color.green(),
        )
        await safe_send(target_channel, content=winners_text, embed=success_embed)

# ========== ТЕКСТОВЫЕ СОБЫТИЕ ==========

@bot.event
async def on_message(message):
    global next_number_in_count_channel
    if not message.guild:
        return
    if message.author == bot.user:
        return
    if bot.user in message.mentions and message.author.id == DEVELOPER_ID:
        await safe_send(message, f"{message.author.mention}, бот ещё жив! <:confirmedemoji:1519738036936638474>", delete_after=5)
    if message.author.id == masked_user and not message.channel.id == COUNT_CHANNEL:
        if (datetime.now() - mask_time).total_seconds() >= 600:
            new = random.choice([
                "*ʍᴀᴄᴋᴀ ᴦоʙоᴩиᴛ:* {}",
                "{} *- ᴄниʍиᴛᴇ ʍᴇня!*",
                "*я ʙᴀᴄ ʙижу...* {}",
                "*ʍᴀᴄᴋᴀ ɯᴇᴨчᴇᴛ:* {}",
                "{} *- ᴛы ужᴇ ʍой!*",
                "*ᴄᴧиɯᴋоʍ ᴨоздно...* {}",
                "{} *- я знᴀю ᴛʙои ᴄᴛᴩᴀхи*",
                "*ʍᴀᴄᴋᴀ ᴄʍᴇᴇᴛᴄя:* {}",
                "{} *- оᴄᴛᴀноʙиᴛᴇ ϶ᴛо!*",
                "*ᴛʙой ᴦоᴧоᴄ ᴨᴩинᴀдᴧᴇжиᴛ ʍнᴇ:* {}",
                "{} *- ʍы ᴄᴛᴀнᴇʍ одниʍ цᴇᴧыʍ*",
                "*ʍᴀᴄᴋᴀ ʙᴄᴇᴦдᴀ ᴄ ᴛобой:* {}"
            ]).format(message.content)
        else:
            if random.random() > 0.7: 
                return await bot.process_commands(message)
            new = random.choice([
                "*ʍᴀᴄᴋᴀ ᴦоʙоᴩиᴛ:* {}",
                "{}*... ᴨоʍоᴦиᴛᴇ...*",
                "*я чуʙᴄᴛʙую ᴄᴛᴩᴀнноᴇ...* {}",
                "*ʍᴀᴄᴋᴀ ᴄжиʍᴀᴇᴛᴄя:* {}",
                "{}*... чᴛо-ᴛо нᴇ ᴛᴀᴋ...*",
                "*ᴦоᴧоᴄᴀ ʙ ᴦоᴧоʙᴇ:* {}",
                "*ᴄниʍиᴛᴇ ϶ᴛо ᴄ ʍᴇня...* {}",
                "*ʍᴀᴄᴋᴀ ᴨуᴧьᴄиᴩуᴇᴛ:* {}",
                "*ʍнᴇ ᴄᴛᴩᴀɯно...* {}",
                "{}*... оно ʙнуᴛᴩи ʍᴇня...*",
                "*ᴄᴧыɯиᴛᴇ? ʍᴀᴄᴋᴀ ɯᴇᴨчᴇᴛ:* {}",
                "{} - *я ᴛᴇᴩяю ᴋонᴛᴩоᴧь...*"
            ]).format(message.content)
        await message.delete()
        if SCP_035_webhook:
            await SCP_035_webhook.send(new, username=f"{message.author.display_name}", avatar_url='https://i.pinimg.com/1200x/dd/bb/e8/ddbbe8338846172fd52739ee99a12436.jpg')
        else:
            await message.channel.send(new)
    if message.channel.id == COUNT_CHANNEL:
        role = message.guild.get_role(COUNT_ROLE)
        try:
            user_number = int(message.content.strip())
            if user_number != next_number_in_count_channel:
                raise ValueError("Не по порядку")
            elif user_number % 250 == 0:
                await safe_send(message, f"**ⲡⲟⲗьⳅⲟⲃⲁⲧⲉⲗυ, ⲕⲁⲕ ⲿⲉ я ⲃⲁⲙυ ⲅⲟⲣⲿⲩⲥь! <a:animegirl:1523642604124897340>**\nᴋᴀждый ʙᴀɯ ɯᴀᴦ дᴇᴧᴀᴇᴛ ʍᴇня ᴩᴀдоᴄᴛнᴇᴇ! ᴛᴇᴋущᴇᴇ чиᴄᴧо — {user_number}, нᴇ оᴄᴛᴀнᴀʙᴧиʙᴀйᴛᴇᴄь и нᴇ ᴄдᴀʙᴀйᴛᴇᴄь! <a:akirakogami:1523644045832880218>")
            elif user_number % 100 == 0:
                await safe_send(message, f"**ⲡⲟⲗьⳅⲟⲃⲁⲧⲉⲗυ, ⲃы ⲇⲟⲥⲧυⲅⲁⲉⲧⲉ ⲃⲉⲣɯυⲏ! ⲅⲟⲣⲿⲩⲥь ⲃⲁⲙυ! <a:yuik:1514940189988880507>**\nʙы ᴨᴩᴇодоᴧᴇʙᴀᴇᴛᴇ оᴛʍᴇᴛᴋу ʙ {user_number}, нᴇ оᴨуᴄᴋᴀйᴛᴇ ᴩуᴋи нᴀ доᴄᴛиᴦнуᴛоʍ! <a:oshimai:1514940166626742382>")
            elif user_number % 50 == 0:
                await safe_send(message, f"**ⲡⲟⲗьⳅⲟⲃⲁⲧⲉⲗυ, ⲡⲟⳅⲇⲣⲁⲃⲗяю! <a:makise:1514939694624800818>**\nʙы доɯᴧи до {user_number}, ᴨᴩодоᴧжᴀйᴛᴇ ʙ ᴛоʍ жᴇ духᴇ! <a:oshimai:1514940166626742382>")
            next_number_in_count_channel += 1
        except (ValueError, TypeError):
            await safe_delete(message)
            if role:
                await message.author.add_roles(role, reason="<:deniedemoji:1519737463126360294> Не число в канале счёта")
            asyncio.create_task(remove_role_at_time(message.author, role, 10))
            await safe_send(message, f"😡 {message.author.mention}, балбес, соблюдай порядок чисел!", delete_after=5)       
    await bot.process_commands(message)

# ========== ОБРАБОТКА ОШИБОК ==========

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await safe_send(ctx, f"<:deniedemoji:1519737463126360294> У вас недостаточно прав для выполнения команды!")
    elif isinstance(error, commands.MissingRequiredArgument):
        await safe_send(ctx, f"<:deniedemoji:1519737463126360294> Не хватает аргументов! Используйте `!help {ctx.command.name}`")
    elif isinstance(error, commands.BadArgument):
        await safe_send(ctx, f"<:deniedemoji:1519737463126360294> Неверный аргумент! Укажите существующего пользователя.")
    elif isinstance(error, commands.CommandNotFound):
        pass  # Игнорируем неизвестные команды
    else:
        await safe_send(ctx, f"⚠️ Произошла ошибка: {error}")

# ========== ЗАПУСК БОТА ==========

@bot.event
async def on_ready():
    global SCP_035_webhook
    SCP_035_webhook = discord.Webhook.from_url(os.getenv('SCP_WEBHOOK_URL'), session=aiohttp.ClientSession())
    try:
        await bot.tree.sync(guild=None)
    except Exception as e:
        print(f"Ошибка: {e}")
    print(f"✅ Бот {bot.user} запущен!")
    print(f"📊 На серверах: {len(bot.guilds)}")
    print(f"🔧 Команд: {len(bot.commands)}")
    await bot.change_presence(
        activity=discord.CustomActivity(
            name="Отвечаю за актив 🍀",
        )
    )
    bot.loop.create_task(mask_death_check())
# Запуск бота
if __name__ == "__main__":
    # Загружаем токен из .env файла 
    TOKEN = os.getenv('BOT_TOKEN_FUNBOT')
    manager = DB_Manager('/app/database/fg_db.db')
    if TOKEN:
        bot.run(TOKEN)
    else:
        print("❌ Токен не найден! Создайте .env файл с BOT_TOKEN")
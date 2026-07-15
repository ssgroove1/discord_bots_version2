import discord, sys, os, asyncio, time, re, random, traceback, difflib
from dotenv import load_dotenv
from collections import defaultdict
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))
from database.db_logic import DB_Manager
from discord import Interaction
from config import BotConfig
from FightClubBot.logic_ruler import ModerationFunc
from FightClubBot.logic_ticket import *
from safe_commands import *

env_path = Path(__file__).parent.parent / "shared.env"
load_dotenv(env_path)
VERIFICATION_MESSAGES = {}
XP_COOLDOWNS = {}

# Настройки бота
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.members = True
intents.moderation = True
bot = commands.Bot(command_prefix=BotConfig.COMMAND_PREFIX, intents=intents, max_messages=10000)

init_safe(bot) # safe_send, safe_reply...

# ========== СИСТЕМЫ ==========

class AntiSpam(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

        self.message_history = defaultdict(list)
        self.spam_warnings = {}
        self.spam_warnings = {}
        self.text_warnings = {}
        self.last_purge_time = {}
        self.warned_users = set()

        self.processing_users = set()
        self.processing_lock = asyncio.Lock()
        self.last_process_time = {}

        self.max_messages = 5
        self.time_window = 4
        self.purge_delay = 2.0
        self.min_process_interval = 1.0

        # 📌 Настройки фильтров КАПСА и символов
        self.min_caps_length = 7  # Длина сообщения, начиная с которой проверяется капс
        self.caps_threshold = 0.70  # Порог капса (70% и более заглавных букв)
        self.max_emoji_count = 4  # Максимум эмодзи в одном сообщении
        self.max_repeated_chars = 5  # Максимум одинаковых символов подряд (например, "ааааааа")

        self.bot.loop.create_task(self._auto_reset_warnings())
        self.bot.loop.create_task(self._cleanup_processing())

    # 🔍 Вспомогательные проверки текста
    def _is_caps(self, text: str) -> bool:
        """Проверяет, превышает ли процент заглавных букв допустимый порог."""
        letters = [char for char in text if char.isalpha()]
        if len(letters) < self.min_caps_length:
            return False

        uppercase_count = sum(1 for char in letters if char.isupper())
        return (uppercase_count / len(letters)) >= self.caps_threshold

    def _is_symbol_spam(self, text: str) -> bool:
        """Проверяет сообщение на спам эмодзи или повторяющимися символами."""
        # 1. Поиск кастомных и стандартных эмодзи Discord
        custom_emojis = re.findall(r"<a?:[a-zA-Z0-9_]+:[0-9]+>", text)
        # Поиск Unicode эмодзи
        unicode_emojis = re.findall(
            r"[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F700-\U0001F77F]",
            text,
        )

        if (len(custom_emojis) + len(unicode_emojis)) > self.max_emoji_count:
            return True

        # 2. Поиск длинных повторяющихся символов подряд (например, "аааааааааа" или "!!!!!!!!")
        if re.search(r"(.)\1{" + str(self.max_repeated_chars) + r",}", text):
            return True

        return False

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return

        if message.author.guild_permissions.administrator:
            return

        support_roles = BotConfig.SUPPORT_ROLES.get(
            "second_order", []
        ) + BotConfig.SUPPORT_ROLES.get("third_order", [])
        if any(role.id in support_roles for role in message.author.roles):
            return

        user_id = message.author.id
        current_time = datetime.now().timestamp()
        content = message.content

        # Блокировка от параллельных срабатываний
        if user_id in self.processing_users:
            return

        # 1. ПРОВЕРКА НА КАПС И СМАЙЛЫ
        if content and (self._is_caps(content) or self._is_symbol_spam(content)):
            self.processing_users.add(user_id)

            try:
                # Мгновенно удаляем сообщение с капсом/смайлами
                try:
                    BotConfig.deleted_by_bot.add(message.id)
                    await safe_delete(message)
                except Exception:
                    pass

                # Увеличиваем счетчик текстовых предупреждений
                self.text_warnings[user_id] = self.text_warnings.get(user_id, 0) + 1
                current_text_warns = self.text_warnings[user_id]

                if current_text_warns < 4:
                # 💬 1, 2, 3 предупреждения — просто предупреждаем в чате
                    await safe_send(
                        message.channel,
                        f"<:warningemoji:1515756604178305054> {message.author.mention},"
                        " прекратите использовать капс / спамить смайлами!"
                        f" **[{current_text_warns}/4]**",
                        delete_after=5,
                    )
                else:
                    # 🚨 4-й раз — сбрасываем мелкий счетчик и выдаем системный warn_count += 1
                    self.text_warnings[user_id] = 0
                    await self._handle_spam(message, reason="нᴇ ᴨᴩᴇʙыɯᴀйᴛᴇ ᴧиʍиᴛ ᴋᴀᴨᴄᴀ/ᴄʍᴀйᴧоᴋ (нᴀᴋᴀзуᴇʍо)")

            finally:
                await asyncio.sleep(1.5)
                self.processing_users.discard(user_id)
            return

        # 2. ПРОВЕРКА НА ЧАСТОТУ СООБЩЕНИЙ (ФЛУД)
        self._clean_old_messages(user_id, current_time)
        self.message_history[user_id].append(current_time)

        if len(self.message_history[user_id]) > self.max_messages:
            self.processing_users.add(user_id)
            try:
                self.last_process_time[user_id] = current_time
                await self._handle_spam(message, reason="Частая отправка сообщений")
            finally:
                await asyncio.sleep(2.0)
                self.processing_users.discard(user_id)

    def _clean_old_messages(self, user_id, current_time):
        if user_id not in self.message_history:
            return
        cutoff = current_time - self.time_window
        self.message_history[user_id] = [
            t for t in self.message_history[user_id] if t > cutoff
        ]
        if not self.message_history[user_id]:
            del self.message_history[user_id]

    async def _handle_spam(
        self, message: discord.Message, reason: str = "Спам в чате"):
        user = message.author
        user_id = user.id
        guild = message.guild

        me = guild.me
        if not me.guild_permissions.manage_messages:
            return

        # Увеличиваем счетчик варнов
        self.spam_warnings[user_id] = self.spam_warnings.get(user_id, 0) + 1
        warn_count = self.spam_warnings[user_id]
        user_mention = user.mention

        # Очищаем чат от сообщений спамера
        await self._purge_user_messages(message.channel, user_id)

        try:
            # 1 ВАРНИНГ: Предупреждение (с авто-удалением сообщения бота через 5 сек)
            if warn_count == 1:
                await safe_send(
                    message.channel,
                    f"<:warningemoji:1515756604178305054> {user_mention},"
                    f" прекратите спам! Причина: **{reason}**.",
                    delete_after=5,)  # 👈 Чтобы бот сам не засорял чат своим предупреждением!

            # 2 ВАРНИНГ: Тайм-аут (Мут)
            elif warn_count == 2:
                if me.guild_permissions.moderate_members:
                    await commands_func.mute_func(
                        target=message.channel,
                        member=message.author,
                        rule="П. 2.4 (Флуд/Спам/Оффтоп)",
                        minutes=10,
                        reason=f"Повторный спам ({reason})",
                    )
                else:
                    await safe_send(
                        message.channel,
                        "<:forbiddenemoji:1515780232404144279> У бота нет прав"
                        " для мута!",
                        delete_after=5,
                    )

            # 3 ВАРНИНГ: Кик
            elif warn_count == 3:
                if me.guild_permissions.kick_members:
                    await commands_func.kick_func(
                        target=message.channel,
                        member=message.author,
                        rule="П. 2.4 (Флуд/Спам/Оффтоп)",
                        reason=f"Мночисленный спам ({reason})",
                    )
                else:
                    await safe_send(
                        message.channel,
                        "<:forbiddenemoji:1515780232404144279> У бота нет прав"
                        " для мута!",
                        delete_after=5,
                    )

            # 4 ВАРНИНГ: Бан
            elif warn_count >= 4:
                if me.guild_permissions.ban_members:
                    await commands_func.ban_func(
                        target=message.channel,
                        user=message.author,
                        rule="П. 2.4 (Флуд/Спам/Оффтоп)",
                        reason=f"Спам-атака ({reason})",
                    )
                    self.spam_warnings[user_id] = 0  # Сбрасываем только при бане
                else:
                    await safe_send(
                        message.channel,
                        "<:forbiddenemoji:1515780232404144279> У бота нет прав"
                        " на бан!",
                        delete_after=5,
                    )

        except discord.Forbidden:
            print(f"❌ Недостаточно прав для наказания {user}")
        except Exception as e:
            print(f"❌ Ошибка при обработке спама: {e}")

    async def _reset_warn_flag(self, user_id, delay):
        await asyncio.sleep(delay)
        self.warned_users.discard(user_id)

    async def _purge_user_messages(self, channel, user_id, limit=15):
        channel_id = channel.id
        now = datetime.now()

        if channel_id in self.last_purge_time:
            elapsed = (now - self.last_purge_time[channel_id]).total_seconds()
            if elapsed < self.purge_delay:
                await asyncio.sleep(
                    self.purge_delay - elapsed + random.uniform(0.1, 0.3)
                )

        def check(msg):
            return msg.author.id == user_id

        try:
            deleted = await channel.purge(limit=min(limit, 10), check=check)
            self.last_purge_time[channel_id] = datetime.now()
            if deleted:
                print(
                    f"🗑️ Удалено {len(deleted)} сообщений пользователя {user_id}")

        except discord.HTTPException as e:
            if e.status == 429:
                retry_after = getattr(e, "retry_after", 5)
                print(f"⏳ Rate limit 429! Ожидание {retry_after:.1f} сек...")
                await asyncio.sleep(retry_after)
            else:
                print(f"❌ Ошибка HTTP при purge: {e}")
        except discord.Forbidden:
            print(f"❌ Нет прав Manage Messages в канале {channel}")
        except Exception as e:
            print(f"❌ Ошибка purge: {e}")

    async def _auto_reset_warnings(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            await asyncio.sleep(3600)  # Каждый час
            for user_id in list(self.spam_warnings.keys()):
                if user_id not in self.message_history:
                    del self.spam_warnings[user_id]

            # Сбрасываем текстовые предупреждения
            self.text_warnings.clear()

    async def _cleanup_processing(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            await asyncio.sleep(30)
        self.processing_users.clear()

# Защита от массового захода для копирования
class ServerProtection(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.join_tracker = {}        # {user_id: [datetime, ...]}
        self.message_warnings = {}     # Единая система предпреждений в чате: {user_id: [datetime, ...]}
        self.quarantined_users = set()
        self.quarantine_role_id = BotConfig.ROLES.get("quarantine")
        
        # Переменные для защиты от рейдов (Anti-Raid)
        self.global_joins = []         # Список временных меток входов всех пользователей за последнее время
        self.lockdown_active = False

        self.blocked_patterns = getattr(BotConfig, 'blocked', [])
        self.compiled_patterns = [re.compile(p, re.IGNORECASE) for p in self.blocked_patterns]
        self.url_pattern = re.compile(r'https?://[^\s]+', re.IGNORECASE)

        # Время жизни предупреждений в чате (в минутах)
        self.warning_lifespan = 15

        # Запуск фоновых задач
        self.bot.loop.create_task(self._auto_cleanup_warnings())

    def is_blocked(self, text: str) -> bool:
        return any(pattern.search(text) for pattern in self.compiled_patterns)

    def _add_message_warning(self, user_id: int, max_age_minutes: int = 60) -> int:
        """Единый метод для добавления и подсчёта предупреждений за любые нарушения в чате."""
        now = datetime.now()
        cutoff = now - timedelta(minutes=max_age_minutes)
        
        if user_id not in self.message_warnings:
            self.message_warnings[user_id] = []
        
        # Очищаем устаревшие записи и добавляем новое предупреждение
        self.message_warnings[user_id] = [t for t in self.message_warnings[user_id] if t > cutoff]
        self.message_warnings[user_id].append(now)
        
        return len(self.message_warnings[user_id])
    
    async def _auto_cleanup_warnings(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            try:
                await asyncio.sleep(60) # Проверка каждую минуту
                now = datetime.now()
                cutoff = now - timedelta(minutes=self.warning_lifespan)

                # Безопасно итерируемся по копии ключей словаря предупреждений
                for user_id in list(self.message_warnings.keys()):
                    # Фильтруем предупреждения, оставляя только те, которые младше 15 минут
                    active_warnings = [t for t in self.message_warnings[user_id] if t > cutoff]
                    
                    if active_warnings:
                        self.message_warnings[user_id] = active_warnings
                    else:
                        # Если все предупреждения пользователя сгорели, полностью удаляем его из памяти
                        del self.message_warnings[user_id]
                        
            except Exception as e:
                print(f"❌ Ошибка во время авто-очистки предупреждений: {e}")

    async def _run_quarantine_tasks(self, tasks):
        try:
            await asyncio.gather(*tasks, return_exceptions=True)
        except Exception as e:
            print(f"❌ Ошибка при массовой выдаче ролей карантина: {e}")

    @app_commands.command(name="lockdown", description="Управление экстренным режимом Lockdown (Защита от рейда)")
    @app_commands.describe(action="Включить (True) или выключить (False) экстренную блокировку входов")
    @app_commands.default_permissions(administrator=True)
    async def lockdown(self, interaction: discord.Interaction, action: bool):
        await interaction.response.defer(ephemeral=True)
        self.lockdown_active = action

        status = "АКТИВИРОВАН <:redalertemoji:1526209446026678413>" if action else "ДЕАКТИВИРОВАН <:verifiedemoji:1525207492928213204>"
        color = discord.Color.brand_red() if action else discord.Color.brand_green()

        await safe_send(interaction, f"ᴩᴇжиʍ Lockdown уᴄᴨᴇɯно {status}!", ephemeral=True)

        log_channel = await safe_fetch_channel(self.bot, BotConfig.CHANNELS.get('emergency_logs'))
        if log_channel:
            embed_log = discord.Embed(
                title=f"<:owneremoji:1517494149119611063> ϶ᴋᴄᴛᴩᴇнный ᴩᴇжиʍ Lockdown {'ʙᴋᴧючᴇн' if action else 'ʙыᴋᴧючᴇн'}",
                description=f"ᴀдʍиниᴄᴛᴩᴀᴛоᴩ {interaction.user.mention} изʍᴇниᴧ ᴦᴧобᴀᴧьный ᴄᴛᴀᴛуᴄ зᴀщиᴛы ᴄᴇᴩʙᴇᴩᴀ.",
                color=color,
                timestamp=datetime.now(timezone.utc))
            embed_log.add_field(
                name="ᴛᴇᴋущᴇᴇ ᴄоᴄᴛояниᴇ ᴄᴇᴩʙᴇᴩᴀ", 
                value="<:redalertemoji:1526209446026678413> **ᴨоᴧнᴀя бᴧоᴋиᴩоʙᴋᴀ (ʟᴏᴄᴋᴅᴏᴡɴ)**\nʙᴄᴇ ноʙыᴇ ᴨоᴧьзоʙᴀᴛᴇᴧи изоᴧиᴩуюᴛᴄя ᴀʙᴛоʍᴀᴛичᴇᴄᴋи." if action else "<:verifiedemoji:1525207492928213204> **обычный ᴩᴇжиʍ**\nзᴀщиᴛᴀ ᴩᴀбоᴛᴀᴇᴛ ᴨо ᴄᴛᴀндᴀᴩᴛныʍ ɸиᴧьᴛᴩᴀʍ ʙозᴩᴀᴄᴛᴀ.")
            
            if interaction.guild and interaction.guild.icon:
                embed_log.set_footer(text=interaction.guild.name, icon_url=interaction.guild.icon.url)
                
            await safe_send(log_channel, embed=embed_log)

    @app_commands.command(name="карантин", description="Отправить пользователя в карантин, сняв с него все роли")
    @app_commands.describe(member="Участник, которого нужно изолировать", reason="Причина отправки в карантин")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def manual_quarantine(self, interaction: discord.Interaction, member: discord.Member, reason: str = "Ручная изоляция модератором"):
        await interaction.response.defer(ephemeral=True)

        # Защита от изоляции самого себя или администратора
        if member.id == interaction.user.id:
            await safe_send(interaction, "<:forbiddenemoji:1515780232404144279> Вы не можете отправить в карантин самого себя!", ephemeral=True)
            return
        if member.guild_permissions.administrator:
            await safe_send(interaction, "<:forbiddenemoji:1515780232404144279> Нельзя отправить в карантин администратора сервера!", ephemeral=True)
            return

        quarantine_role = interaction.guild.get_role(self.quarantine_role_id)

        if not quarantine_role:
            await safe_send(interaction, "<:forbiddenemoji:1515780232404144279> Роль карантина не найдена в настройках сервера!", ephemeral=True)
            return

        # Добавляем в список отслеживания карантина в памяти
        self.quarantined_users.add(member.id)

        # Собираем роли для сохранения в базу данных
        current_roles = [role.id for role in member.roles if role.name != "@everyone" and role.id != self.quarantine_role_id]

        try:
            # Безопасное сохранение ролей в базу данных (если менеджер БД инициализирован)
            try:
                if 'manager' in globals():
                    await globals()['manager'].update_user_roles_ruler(member.id, current_roles)
                elif hasattr(self.bot, 'manager'):
                    await self.bot.manager.update_user_roles_ruler(member.id, current_roles)
            except Exception as db_err:
                print(f"⚠️ Не удалось сохранить роли в БД для {member.id}: {db_err}")

            # Снимаем все роли, кроме @everyone и неуправляемых (managed / бусты)
            roles_to_remove = [role for role in member.roles if role.name != "@everyone" and not role.managed]
            if roles_to_remove:
                await member.remove_roles(*roles_to_remove, reason=f"Карантин: {reason} | Модератор: {interaction.user}")

            # Выдаем роль карантина
            await member.add_roles(quarantine_role, reason=f"Карантин: {reason} | Модератор: {interaction.user}")

            # Ответ модератору
            await safe_send(
                interaction,
                f"<:successemoji:1515691944460685372> {member.mention} успешно отправлен в карантин, его роли сохранены и очищены!",
                ephemeral=True
            )

            # Отправка подробного лога в канал логов
            log_channel = await safe_fetch_channel(self.bot, BotConfig.CHANNELS.get('warning_logs'))
            if log_channel:
                embed_log = discord.Embed(
                    title="<:hazardemoji:1526566003339821207> оᴛᴨᴩᴀʙᴧᴇн нᴀ ᴋᴀᴩᴀнᴛин",
                    description=f"ʍодᴇᴩᴀᴛоᴩ ʙᴩᴇʍᴇнно изоᴧиᴩоʙᴀᴧ ᴨоᴧьзоʙᴀᴛᴇᴧя и очиᴄᴛиᴧ ᴇᴦо ᴩоᴧи.",
                    color=discord.Color.dark_orange(),
                    timestamp=datetime.now(timezone.utc)
                )
                embed_log.add_field(
                    name="<:warningemoji:1515756604178305054> изоᴧиᴩоʙᴀн",
                    value=f"{member.mention}",
                    inline=True
                )
                embed_log.add_field(
                    name="<:verifiedemoji:1525207492928213204> ʍодᴇᴩᴀᴛоᴩ",
                    value=f"{interaction.user.mention}",
                    inline=True
                )
                embed_log.add_field(
                    name="<:pencilemoji:1525177241749950464> ᴨᴩичинᴀ дᴇйᴄᴛʙия",
                    value=f"```\n{reason}```",
                    inline=False
                )
                
                if member.display_avatar:
                    embed_log.set_thumbnail(url=member.display_avatar.url)
                if interaction.guild and interaction.guild.icon:
                    embed_log.set_footer(text=interaction.guild.name, icon_url=interaction.guild.icon.url)

                await safe_send(log_channel, embed=embed_log)

        except discord.Forbidden:
            await safe_send(
                interaction,
                "❌ У бота нет прав на изменение ролей этого пользователя! Убедитесь, что роль бота находится выше остальных.",
                ephemeral=True
            )
        except Exception as e:
            await safe_send(interaction, f"❌ Ошибка при отправке в карантин: {e}", ephemeral=True)

    @app_commands.command(name="верифицировать", description="Снять карантин.")
    @app_commands.describe(member="Участник, которого следует верифицировать")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    async def verify_member(self, interaction: discord.Interaction, member: discord.Member):
        await interaction.response.defer(ephemeral=True)

        quarantine_role = interaction.guild.get_role(self.quarantine_role_id)
        # Проверяем, находится ли пользователь в карантине
        if quarantine_role and quarantine_role not in member.roles:
            await safe_send(
                interaction,
                f"<:forbiddenemoji:1515780232404144279> {member.mention} не находится"
                " в карантине!",
                ephemeral=True,)
            return

        try:
            # Снимаем карантин и выдаем роль игрока
            if quarantine_role and quarantine_role in member.roles:
                await member.remove_roles(
                    quarantine_role,
                    reason=f"Верифицирован модератором {interaction.user.name}",)

            await commands_func.get_base_roles(member=member)

            # Ответ модератору
            await safe_send(
                interaction,
                f"<:successemoji:1515691944460685372> {member.mention} успешно"
                " верифицирован!",
                ephemeral=True,
            )
            self.quarantined_users.discard(member.id)

            # Уведомление пользователю в ЛС
            dm_embed = discord.Embed(
                title="<:successemoji:1515691944460685372> ʙы уᴄᴨᴇɯно ʙᴇᴩиɸициᴩоʙᴀны!",
                description=(
                    f"ᴀдʍиниᴄᴛᴩᴀᴛоᴩ {interaction.user.mention} ᴄняᴧ ᴄ ʙᴀᴄ оᴦᴩᴀничᴇния.\nᴨᴩияᴛноᴦо общᴇния!"
                ),
                color=discord.Color.green(),
                timestamp=datetime.now(timezone.utc),
            )
            try:
                await safe_dm_send(member.id, embed=dm_embed)
            except Exception:
                pass

            # Лог модерации
            log_channel = await safe_fetch_channel(
                interaction.client, BotConfig.CHANNELS.get("mod_logs_commands")
            )
            if log_channel:
                embed_log = discord.Embed(
                    title="<:successemoji:1515691944460685372> уᴄᴨᴇɯнᴀя ʙᴇᴩиɸиᴋᴀция",
                    description=f"ᴨоᴧьзоʙᴀᴛᴇᴧь уᴄᴨᴇɯно ᴨᴩоɯᴇᴧ ᴨᴩоʙᴇᴩᴋу и быᴧ доᴨущᴇн нᴀ ᴄᴇᴩʙᴇᴩ.",
                    color=discord.Color.green(),
                    timestamp=datetime.now(timezone.utc),
                )
                
                embed_log.add_field(
                    name="<:hazardemoji:1526566003339821207> учᴀᴄᴛниᴋ",
                    value=f"{member.mention}\n`ID: {member.id}`",
                    inline=True
                )
                
                embed_log.add_field(
                    name="<:verifiedemoji:1525207492928213204> ʍодᴇᴩᴀᴛоᴩ",
                    value=f"{interaction.user.mention}\n`ID: {interaction.user.id}`",
                    inline=True
                )
                
                # Добавляем аватар верифицированного пользователя в качестве миниатюры
                if member.display_avatar:
                    embed_log.set_thumbnail(url=member.display_avatar.url)
                    
                # Footer с иконкой и названием сервера
                if interaction.guild and interaction.guild.icon:
                    embed_log.set_footer(
                        text=interaction.guild.name, 
                        icon_url=interaction.guild.icon.url
                    )
                    
                await safe_send(log_channel, embed=embed_log)

        except discord.Forbidden:
            await safe_send(
                interaction,
                "<:forbiddenemoji:1515780232404144279> У бота недостаточно прав для"
                " управления ролями!",
                ephemeral=True,
            )
        except Exception as e:
            await safe_send(
                interaction,
                f"<:forbiddenemoji:1515780232404144279> Произошла ошибка: {e}",
                ephemeral=True,
            )

    @app_commands.command(name="нейтрализовать_карантин", description="Экстренная массовая очистка (кик/бан) всех участников в карантине")
    @app_commands.describe(
        action="Что сделать с участниками карантина (kick - исключить, ban - забанить)",
        reason="Укажите причину для модерационных логов")
    @app_commands.choices(action=[
        app_commands.Choice(name="Исключить (Kick)", value="kick"),
        app_commands.Choice(name="Забанить (Ban)", value="ban")])
    @app_commands.checks.has_permissions(administrator=True)
    async def purge_quarantine(self, interaction: discord.Interaction, action: str, reason: str = "Экстренное устранение рейда"):
        await interaction.response.defer(ephemeral=True)

        if not self.quarantined_users:
            await safe_send(
                interaction,
                "⚠️ В карантине сейчас нет пользователей для очистки!",
                ephemeral=True)
            return

        guild = interaction.guild
        user_ids_to_purge = list(self.quarantined_users)
        
        purge_tasks = []
        successful_purges = []
        failed_purges = 0

        # Собираем список пользователей, которые находятся на сервере
        for user_id in user_ids_to_purge:
            member = guild.get_member(user_id)
            if not member:
                # Если пользователя уже нет на сервере, просто удаляем из списка памяти
                self.quarantined_users.discard(user_id)
                continue

            # Защита от случайного удаления модераторов/админов
            if member.guild_permissions.administrator:
                continue

            if action == "kick":
                purge_tasks.append(member.kick(reason=f"{reason} | Администратор: {interaction.user}"))
            elif action == "ban":
                purge_tasks.append(member.ban(reason=f"{reason} | Администратор: {interaction.user}", delete_message_days=1))
            
            successful_purges.append(member)

        if not purge_tasks:
            await safe_send(
                interaction,
                "⚠️ На сервере не найдено участников, подходящих под критерии очистки.",
                ephemeral=True)
            return

        # Запускаем параллельное массовое удаление нарушителей
        results = await asyncio.gather(*purge_tasks, return_exceptions=True)

        # Подсчет успешных и неудавшихся действий
        actual_success_count = 0
        for index, result in enumerate(results):
            if isinstance(result, Exception):
                failed_purges += 1
                print(f"❌ Ошибка очистки пользователя {successful_purges[index].id}: {result}")
            else:
                actual_success_count += 1
                # Удаляем из списка карантинников тех, кого успешно выгнали
                self.quarantined_users.discard(successful_purges[index].id)

        action_name = "исключены (кикнуты)" if action == "kick" else "забанены"
        emoji = "<:kickemoji:1515693208783425617>" if action == "kick" else "<:banemoji:1515689296118677534>"

        # Отвечаем администратору
        await safe_send(
            interaction,
            f"<:hazardemoji:1526566003339821207> оᴨᴇᴩᴀция зᴀʙᴇᴩɯᴇнᴀ!\n"
            f"Успешно {action_name}: **{actual_success_count}** пользователей.\n"
            f"Ошибок выполнения: **{failed_purges}**.",
            ephemeral=True
        )

        # Отправляем подробный отчет в логи модерации
        log_channel = await safe_fetch_channel(self.bot, BotConfig.CHANNELS.get('emergency_logs'))
        if log_channel:
            embed_log = discord.Embed(
                title=f"{emoji} ʍᴀᴄᴄоʙᴀя очиᴄᴛᴋᴀ ᴋᴀᴩᴀнᴛинᴀ",
                description=f"ᴀдʍиниᴄᴛᴩᴀᴛоᴩ {interaction.user.mention} ᴨᴩиʍᴇниᴧ быᴄᴛᴩую очиᴄᴛᴋу нᴀᴩуɯиᴛᴇᴧᴇй.",
                color=discord.Color.brand_red() if action == "ban" else discord.Color.dark_orange(),
                timestamp=datetime.now(timezone.utc)
            )
            embed_log.add_field(name="<:binemoji:1525176536607752202> ʙыбᴩᴀнноᴇ дᴇйᴄᴛʙиᴇ", value=f"**{action.upper()}**", inline=True)
            embed_log.add_field(name="<:pencilemoji:1525177241749950464> ᴨᴩичинᴀ", value=f"{reason}", inline=True)
            embed_log.add_field(
                name="<:successemoji:1515691944460685372> ᴩᴇзуᴧьᴛᴀᴛы", 
                value=f"уᴄᴨᴇɯно очищᴇно: `{actual_success_count}`\nнᴇ удᴀᴧоᴄь иᴄᴋᴧючиᴛь: `{failed_purges}`", 
                inline=False
            )
            
            if guild.icon:
                embed_log.set_footer(text=guild.name, icon_url=guild.icon.url)
                
            await safe_send(log_channel, embed=embed_log)


    # =========================================================================
    # СОБЫТИЯ ВХОДА НА СЕРВЕР (JOIN EVENTS)
    # =========================================================================

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        # ==================== ЛОГИКА ДЛЯ БОТОВ ====================
        if member.bot:
            if member.id == bot.user.id:
                return

            trusted_set = getattr(bot, 'trusted_set', BotConfig.trusted_bots)

            if member.id not in trusted_set:
                welcome_channel = await safe_fetch_channel(bot, BotConfig.CHANNELS['welcome'])
                
                bot_tasks = []
                
                # Задача на отправку сообщения
                if welcome_channel:
                    bot_tasks.append(
                        safe_send(
                            welcome_channel, 
                            f"<:neutralizeemoji:1515694760990347325> ʙᴩᴀжᴇᴄᴋоᴇ уᴄᴛᴩойᴄᴛʙо, {member.mention}, **быᴧо нᴇйᴛᴩᴀᴧизоʙᴀно** ᴧучɯиʍи ᴄᴨᴇц-оᴛᴩядᴀʍи.", delete_after=5
                        ))

                # Задача на бан
                bot_tasks.append(
                    member.ban(
                        reason="Неавторизованный бот (Автоматическая нейтрализация)", 
                        delete_message_days=1))

                # Выполняем действия с неавторизованным ботом параллельно
                results = await asyncio.gather(*bot_tasks, return_exceptions=True)
                for res in results:
                    if isinstance(res, Exception):
                        print(f"❌ Ошибка при нейтрализации бота {member.name}: {res}")
                return
            return
        
        # ==================== ДЕТЕКТОР РЕЙДОВ (ANTI-RAID) ====================
        now = datetime.now()
        # Очищаем из глобального трекера входов всё, что было более 7 секунд назад
        self.global_joins = [(t, m) for t, m in self.global_joins if (now - t).total_seconds() < 7]
        self.global_joins.append((now, member))

        # Если входов за 7 секунд набралось 10 или более, и локдаун еще не активен
        if len(self.global_joins) >= 10 and not self.lockdown_active:
            self.lockdown_active = True
            
            # Получаем роль карантина
            quarantine_role = member.guild.get_role(self.quarantine_role_id)
            
            # Извлекаем всех пользователей, зашедших за последние 5 секунд
            raid_members = [m for t, m in self.global_joins]
            
            # Асинхронно отправляем в карантин всех первых зашедших (включая тех, кто уже прошел)
            quarantine_tasks = []
            for raid_member in raid_members:
                self.quarantined_users.add(raid_member.id)
                if quarantine_role and quarantine_role not in raid_member.roles:
                    quarantine_tasks.append(
                        raid_member.add_roles(
                            quarantine_role, 
                            reason="Изоляция: один из первых участников рейда (Авто-Lockdown)"
                        )
                    )
            
            # Запускаем фоновую выдачу ролей параллельно для предотвращения задержек
            if quarantine_tasks:
                self.bot.loop.create_task(self._run_quarantine_tasks(quarantine_tasks))
            
            # Отправляем критический алерт модераторам
            log_channel = await safe_fetch_channel(self.bot, BotConfig.CHANNELS.get("emergency_logs"))
            if log_channel:
                embed_warn = discord.Embed(
                    title="<:redalertemoji:1526209446026678413> обнᴀᴩужᴇнᴀ ᴀᴛᴀᴋᴀ (ʀᴀɪᴅ ᴅᴇᴛᴇᴄᴛᴇᴅ) <:redalertemoji:1526209446026678413>",
                    description=(
                        f"**϶ᴋᴄᴛᴩᴇнноᴇ дᴇйᴄᴛʙиᴇ:** ᴀʙᴛоʍᴀᴛичᴇᴄᴋи ᴀᴋᴛиʙиᴩоʙᴀн ᴩᴇжиʍ **Lockdown**!\n"
                        f"зᴀɸиᴋᴄиᴩоʙᴀно **{len(self.global_joins)} ʙходоʙ** зᴀ ᴨоᴄᴧᴇдниᴇ 5 ᴄᴇᴋунд.\n\n"
                        f"<:hazardemoji:1526566003339821207> **ᴨᴇᴩʙыᴇ {len(raid_members)} зᴀɯᴇдɯих ᴨоᴧьзоʙᴀᴛᴇᴧᴇй ᴛᴀᴋжᴇ быᴧи уᴄᴨᴇɯно оᴛᴨᴩᴀʙᴧᴇны ʙ ᴋᴀᴩᴀнᴛин**."
                    ),
                    color=discord.Color.brand_red(),
                    timestamp=datetime.now(timezone.utc)
                )
                if member.guild.icon:
                    embed_warn.set_thumbnail(url=member.guild.icon.url)
                    embed_warn.set_footer(text=member.guild.name, icon_url=member.guild.icon.url)
                await safe_send(log_channel, embed=embed_warn)

        # 🛑 1. ПРОВЕРКА LOCKDOWN И ПОВТОРНОГО КАРАНТИНА
        # Если включен Lockdown или пользователь уже был в карантине
        is_lockdown_quarantine = self.lockdown_active
        is_existing_quarantine = member.id in self.quarantined_users

        # 🛑 1. ПРОВЕРКА ПО ID: Если бот уже отправлял этого пользователя в карантин
        if is_existing_quarantine:
            # Выдаем роль карантина повторно (без спама в ЛС и логи)
            quarantine_role = member.guild.get_role(self.quarantine_role_id)
            if quarantine_role:
                try:
                    await member.add_roles(
                        quarantine_role, reason="Повторный вход (уже в карантине)")
                except Exception:
                    pass
                return

        if is_lockdown_quarantine or is_existing_quarantine:
            quarantine_role = member.guild.get_role(self.quarantine_role_id)
            
            if quarantine_role:
                try:
                    reason_text = "Режим Lockdown (Авто-защита от рейда)" if is_lockdown_quarantine else "Повторный вход (уже в карантине)"
                    await member.add_roles(quarantine_role, reason=reason_text)
                except Exception as e:
                    print(f"⚠️ Ошибка выдачи роли карантина в Lockdown: {e}")

            # Если это новый вход во время активного Lockdown, отправляем специальное предупреждение
            if is_lockdown_quarantine and not is_existing_quarantine:
                self.quarantined_users.add(member.id)
                # ЛС пользователю
                dm_embed = discord.Embed(
                    title="<:redalertemoji:1526209446026678413> ᴄᴇᴩʙᴇᴩ нᴀ изоᴧяции",
                    description=(
                        "нᴀ ᴄᴇᴩʙᴇᴩᴇ ᴀᴋᴛиʙиᴩоʙᴀн ᴩᴇжиʍ ᴨоᴧной зᴀщиᴛы оᴛ ᴀʙᴛоʍᴀᴛичᴇᴄᴋих ᴀᴛᴀᴋ (ʟᴏᴄᴋᴅᴏᴡɴ).\n"
                        "доᴄᴛуᴨ ᴋ ᴛᴇᴋᴄᴛоʙыʍ чᴀᴛᴀʍ ʙᴩᴇʍᴇнно оᴦᴩᴀничᴇн. ᴨожᴀᴧуйᴄᴛᴀ, ожидᴀйᴛᴇ ʙᴇᴩиɸиᴋᴀции ᴀдʍиниᴄᴛᴩᴀциᴇй."
                    ),
                    color=discord.Color.brand_red(),
                    timestamp=datetime.now(timezone.utc)
                )
                if member.guild.icon:
                    dm_embed.set_footer(text=member.guild.name, icon_url=member.guild.icon.url)
                try:
                    await safe_dm_send(member.id, embed=dm_embed)
                except Exception:
                    pass

                # Логируем изоляцию рейда
                log_channel = await safe_fetch_channel(self.bot, BotConfig.CHANNELS.get("emergency_logs"))
                if log_channel:
                    embed_quarantine_log = discord.Embed(
                        title="<:owneremoji:1517494149119611063> ᴨᴩоᴛоᴋоᴧ: ʟᴏᴄᴋᴅᴏᴡɴ",
                        description=f"ᴨоᴧьзоʙᴀᴛᴇᴧь {member.mention} ᴀʙᴛоʍᴀᴛичᴇᴄᴋи изоᴧиᴩоʙᴀн ʙо ʙᴩᴇʍя ϶ᴋᴄᴛᴩᴇнноᴦо ᴩᴇжиʍᴀ.",
                        color=discord.Color.dark_orange(),
                        timestamp=datetime.now(timezone.utc)
                    )
                    embed_quarantine_log.add_field(name="<:hazardemoji:1526566003339821207> учᴀᴄᴛниᴋ", value=f"{member.mention}")
                    if member.display_avatar:
                        embed_quarantine_log.set_thumbnail(url=member.display_avatar.url)
                    if member.guild.icon:
                        embed_quarantine_log.set_footer(text=member.guild.name, icon_url=member.guild.icon.url)
                    await safe_send(log_channel, embed=embed_quarantine_log)
            return

        # ==================== ЧАСТЫЕ ПЕРЕЗАХОДЫ ПОЛЬЗОВАТЕЛЕЙ ====================
        if member.id not in self.join_tracker:
            self.join_tracker[member.id] = []

        self.join_tracker[member.id] = [
            t
            for t in self.join_tracker[member.id]
            if (now - t).total_seconds() < 1200
        ]
        self.join_tracker[member.id].append(now)

        recent_joins = len(self.join_tracker[member.id])

        if recent_joins >= 4:
            log_channel = await safe_fetch_channel(
                self.bot, BotConfig.CHANNELS.get("warning_logs")
            )
            if log_channel:
                embed_log = discord.Embed(
                    title="<:warningemoji:1515756604178305054> ᴨодозᴩиᴛᴇᴧьнᴀя ᴀᴋᴛиʙноᴄᴛь",
                    description="зᴀɸиᴋᴄиᴩоʙᴀны чᴀᴄᴛыᴇ ᴨᴇᴩᴇзᴀходы нᴀ ᴄᴇᴩʙᴇᴩ (возможный рейд).",
                    color=discord.Color.dark_orange(),
                    timestamp=datetime.now(timezone.utc),
                )

                embed_log.add_field(
                    name="<:forbbiden2emoji:1517479332866429008> учᴀᴄᴛниᴋ",
                    value=f"{member.mention}",
                    inline=True,
                )

                embed_log.add_field(
                    name="<:pencilemoji:1525177241749950464> ᴄᴛᴀᴛиᴄᴛиᴋᴀ",
                    value=f"**{recent_joins}** входов за **20 мин.**",
                    inline=True,
                )

                embed_log.add_field(
                    name="<:verifiedemoji:1525207492928213204> дᴇйᴄᴛʙиᴇ",
                    value="<:banemoji:1515689296118677534> **Автоматический бан**",
                    inline=False,
                )

                if member.display_avatar:
                    embed_log.set_thumbnail(url=member.display_avatar.url)

                if member.guild.icon:
                    embed_log.set_footer(text=member.guild.name, icon_url=member.guild.icon.url)

                await safe_send(log_channel, embed=embed_log)
            try:
                await member.ban(
                    reason="Подозрительная активность (частые перезаходы)",
                    delete_message_days=1,)
                return
            except Exception as e:
                print(f"⚠️ Ошибка бана за частые перезаходы: {e}")

        # ==================== ЛОГИКА КАРАНТИНА НОВЫХ АККАУНТОВ ====================
        account_age = int((datetime.now(timezone.utc) - member.created_at).days)
        if account_age < 7:
            # 📌 Запоминаем ID пользователя, что он в карантине
            self.quarantined_users.add(member.id)

            quarantine_role = member.guild.get_role(self.quarantine_role_id)

            if quarantine_role:
                try:
                    await member.add_roles(
                        quarantine_role, reason=f"Новый аккаунт ({account_age} дн.)"
                    )
                except Exception as e:
                    print(f"⚠️ Ошибка выдачи роли карантина: {e}")

            # Отправляем ЛС
            dm_embed = discord.Embed(
                title="<:warningemoji:1515756604178305054> ʙᴀɯ ᴀᴋᴋᴀунᴛ нᴀ ᴨᴩоʙᴇᴩᴋᴇ",
                description=(
                    "ʙᴀɯ ᴀᴋᴋᴀунᴛ ʍᴧᴀдɯᴇ 7 днᴇй. ʙᴀʍ ʙыдᴀнᴀ ᴩоᴧь ᴋᴀᴩᴀнᴛинᴀ.\nожидᴀйᴛᴇ,"
                    " ᴨоᴋᴀ ᴀдʍиниᴄᴛᴩᴀция ᴨᴩоʙᴇᴩиᴛ ʙᴀᴄ"
                ),
                color=discord.Color.orange(),
                timestamp=datetime.now(timezone.utc),
            )
            if member.display_avatar:
                dm_embed.set_thumbnail(url=member.display_avatar.url)
            if member.guild.icon:
                dm_embed.set_footer(
                    text="𝐅𝐈𝐆𝐇𝐓 𝐂𝐋𝐔𝐁", icon_url=member.guild.icon.url
                )

            try:
                await safe_dm_send(member.id, embed=dm_embed)
            except Exception:
                pass

            # Лог модераторам
            log_channel = await safe_fetch_channel(
                self.bot, BotConfig.CHANNELS.get("warning_logs")
            )
            if log_channel:
                embed_quarantine = discord.Embed(
                    title="<:hazardemoji:1526566003339821207> ᴨоʍᴇщᴇн ʙ ᴋᴀᴩᴀнᴛин",
                    description="обнᴀᴩужᴇн ноʙый ᴀᴋᴋᴀунᴛ. доᴄᴛуᴨ ᴋ ᴄᴇᴩʙᴇᴩу ʙᴩᴇʍᴇнно оᴦᴩᴀничᴇн.",
                    color=discord.Color.dark_red(),
                    timestamp=datetime.now(timezone.utc),
                )

                embed_quarantine.add_field(
                    name="<:warningemoji:1515756604178305054> учᴀᴄᴛниᴋ",
                    value=f"{member.mention}",
                    inline=True,
                )

                embed_quarantine.add_field(
                    name="<:pencilemoji:1525177241749950464> ʙозᴩᴀᴄᴛ ᴀᴋᴋᴀунᴛᴀ",
                    value=f"**{account_age}** дн.",
                    inline=True,
                )

                embed_quarantine.add_field(
                    name="<:owneremoji:1517494149119611063> инᴄᴛᴩуᴋция дᴧя ʙᴇᴩиɸиᴋᴀции",
                    value=f"Используйте команду:\n`/верифицировать member:{member.id}`",
                    inline=False,
                )

                if member.display_avatar:
                    embed_quarantine.set_thumbnail(url=member.display_avatar.url)

                if member.guild.icon:
                    embed_quarantine.set_footer(
                        text=member.guild.name, icon_url=member.guild.icon.url)

                await safe_send(log_channel, embed=embed_quarantine)
            return

        # ==================== ЛОГИКА ДЛЯ ОБЫЧНЫХ ПОЛЬЗОВАТЕЛЕЙ ====================
        await commands_func.get_base_roles(member=member)

    # =========================================================================
    # СОБЫТИЯ СООБЩЕНИЙ (ЕДИНАЯ ПРОВЕРКА)
    # =========================================================================

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return

        # Игнорируем администраторов и техподдержку
        if message.author.guild_permissions.administrator:
            return

        support_roles = BotConfig.SUPPORT_ROLES.get("second_order", []) + BotConfig.SUPPORT_ROLES.get("third_order", [])
        if any(role.id in support_roles for role in getattr(message.author, 'roles', [])):
            return

        violation_type = None
        log_detail = ""

        # 1. Проверка запрещённых слов (экспорт токенов/спам фразы)
        if self.is_blocked(message.content):
            violation_type = "запрещенный текст"
            log_detail = "`" + message.content.replace('\n', ' ')[:50] + "`"

        # 2. Проверка массовых упоминаний
        if not violation_type:
            user_mentions = len(message.mentions)
            role_mentions = len(message.role_mentions)
            text_mentions = len(re.findall(r'@\S+', message.content))
            id_mentions = len(re.findall(r'<@!?\d+>', message.content))
            
            if (user_mentions + role_mentions + text_mentions + id_mentions) >= 3:
                violation_type = "массовые упоминания"
                log_detail = "`" + message.content.replace('\n', ' ')[:25] + "`"

        # 3. Проверка сторонних ссылок
        if not violation_type:
            urls = self.url_pattern.findall(message.content)
            if urls:
                allowed_domains = getattr(BotConfig, 'allowed_domains', [])
                if any(not any(domain in url for domain in allowed_domains) for url in urls):
                    violation_type = "запрещенные ссылки"
                    log_detail = f"`{urls[0]}`"

        # Если обнаружено любое нарушение в сообщении
        if violation_type:
            BotConfig.deleted_by_bot.add(message.id)
            await safe_delete(message)
            
            # Начисляем 1 предупреждение в единую систему
            warn_count = self._add_message_warning(message.author.id)
            user_mention = message.author.mention

            if warn_count == 4:
                try:
                    await commands_func.kick_func(message.channel, member=message.author, rule="П. 3.3 (Вредоносные ссылки)", reason="Подозрительный формат")
                    log_channel = await safe_fetch_channel(self.bot, BotConfig.CHANNELS.get('mod_logs_commands'))
                    if log_channel:
                        await safe_send(
                            log_channel,
                            f"<:kickemoji:1515693208783425617> **{user_mention} выгнан(а) зᴀ 4 ᴨᴩᴇдуᴨᴩᴇждᴇния ʙ чате (последнее: {violation_type})**"
                        )
                except Exception as e:
                    print(f"⚠️ Ошибка бана за нарушения в чате: {e}")
            if warn_count == 5:
                try:
                    await commands_func.ban_func(message.channel, member=message.author, rule="П. 3.3 (Вредоносные ссылки)", reason="Многочисленный подозрительный формат")
                    log_channel = await safe_fetch_channel(self.bot, BotConfig.CHANNELS.get('mod_logs_commands'))
                    if log_channel:
                        await safe_send(
                            log_channel,
                            f"<:neutralizeemoji:1515694760990347325> **{user_mention} нᴇйᴛᴩᴀᴧизоʙᴀн(а) зᴀ 5 ᴨᴩᴇдуᴨᴩᴇждᴇния ʙ чате (последнее: {violation_type})**"
                        )
                except Exception as e:
                    print(f"⚠️ Ошибка бана за нарушения в чате: {e}")
            else:
                await safe_send(
                    message.channel,
                    f"<:forbiddenemoji:1515780232404144279> {user_mention}, ϶ᴛо зᴀᴨᴩᴇщᴇно! Предупреждений: ({warn_count}/5)",
                    delete_after=5
                )

            # Логирование нарушения
            log_channel = await safe_fetch_channel(self.bot, BotConfig.CHANNELS.get('warning_logs'))
            if log_channel:
                # Создаем стильный Embed золотого цвета для предупреждений
                embed_violation = discord.Embed(
                    title="<:warningemoji:1515756604178305054> Нарушение в чате",
                    color=discord.Color.orange(),
                    timestamp=datetime.now(timezone.utc))

                # Добавляем информацию о нарушителе
                # Примечание: предполагается, что у вас есть доступ к объекту member/user для ID и аватарки
                embed_violation.add_field(
                    name="<:forbbiden2emoji:1517479332866429008> нᴀᴩуɯиᴛᴇᴧь",
                    value=f"{user_mention}",
                    inline=True
                )

                # Добавляем тип нарушения
                embed_violation.add_field(
                    name="<:binemoji:1525176536607752202> ᴛиᴨ нᴀᴩуɯᴇния",
                    value=f"**{violation_type}**",
                    inline=True
                )

                # Безопасно обрезаем детали нарушения до 1000 символов, чтобы не превысить лимиты Discord
                safe_detail = log_detail if len(log_detail) < 1000 else f"{log_detail[:990]}..."
                embed_violation.add_field(
                    name="<:pencilemoji:1525177241749950464> дᴇᴛᴀᴧи нᴀᴩуɯᴇния",
                    value=f"```\n{safe_detail}```",
                    inline=False
                )

                # Если в коде доступен объект сообщения, можно прикрепить ссылку на него и указать канал
                if 'message' in locals() and message:
                    embed_violation.add_field(
                        name="<:clearemoji:1515691240476377218> ᴋонᴛᴇᴋᴄᴛ",
                        value=f"Канал: {message.channel.mention}\n[Перейти к сообщению]({message.jump_url})",
                        inline=False
                    )
                    # Устанавливаем аватарку автора в превью лога
                    if message.author.display_avatar:
                        embed_violation.set_thumbnail(url=message.author.display_avatar.url)

                # Оформляем футер с иконкой сервера
                if 'message' in locals() and message.guild and message.guild.icon:
                    embed_violation.set_footer(
                        text=message.guild.name, 
                        icon_url=message.guild.icon.url)

                # Отправляем оформленный лог в канал
                try:
                    await safe_send(log_channel, embed=embed_violation)
                except Exception as e:
                    print(f"❌ Не удалось отправить лог нарушения: {e}")

# Фильтр матов
# class ProfanityFilter(commands.Cog):
#     def __init__(self, bot):
#         self.bot = bot
#         self.warnings = {}
#         self.messages_count = {}

#         # Базовые корни и основы слов для поиска
#         self.base_words = [
#             # Оскорбления внешности / личности
#             "жиробас", "жирдяй", "жирна", "жирно",
#             "мудак", "мудил", "мудач", "мудел", "мудело",
#             "урод", "мразь", "тварь", "отсталы", "сосунок", "гандон",

#             # Нецензурные корни и их искажения
#             "хуесос", "хуэсос", "хуисос", "ху1сос",
#             "долбоеб", "долбоиб", "долбаеб", "долбаиб",
#             "ебал", "ибал", "ебало", "ебан", "уебан",
#             "пидор", "педор", "пидорас", "педорас", "пидрил", "педрил",
#             "шлюх", "блядин", "бляден", "блядотин", "курв", "проститутка",
#             "сукин", "сучар", "ублюдок", "хуйн", "лесби", "лезби",

#             # Англоязычные
#             "fuck", "shit", "bitch", "asshole", "bastard", "dick", "cunt"
#         ]

#         # Настройки
#         self.max_messages_before_warn = 4
#         self.warning_reset_minutes = 10
#         self.ignore_role_ids = BotConfig.SUPPORT_ROLES.get('second_order', []) + BotConfig.SUPPORT_ROLES.get('third_order', [])

#         # Генерация паттернов
#         self.patterns = self._generate_patterns()

#         # Запуск фоновой задачи очистки
#         self.bot.loop.create_task(self._auto_reset_warnings())

#     def _generate_patterns(self):
#         patterns = []

#         # Завуалированные фразовые проверки
#         extra_patterns = [
#             re.compile(r'сын\s+хорош(ей|еи)\s+матер(и|е)', re.IGNORECASE),
#             re.compile(r'f[\s.,!?;:()\−]*[uу][\s.,!?;:()\−]*c[\s.,!?;:()\−]*k', re.IGNORECASE),
#             re.compile(r's[\s.,!?;:()\−]*h[\s.,!?;:()\−]*[i1][\s.,!?;:()\−]*t', re.IGNORECASE),
#             re.compile(r'b[\s.,!?;:()\−]*[i1][\s.,!?;:()\−]*t[\s.,!?;:()\−]*c[\s.,!?;:()\−]*h', re.IGNORECASE),
#             re.compile(r'a[\s.,!?;:()\−]*s[\s.,!?;:()\−]*s[\s.,!?;:()\−]*h[\s.,!?;:()\−]*o[\s.,!?;:()\−]*l[\s.,!?;:()\−]*e', re.IGNORECASE),
#         ]

#         patterns.extend(extra_patterns)
#         return patterns

#     @staticmethod
#     def _clean_char_map() -> dict:
#         return {
#             # А
#             'a': 'а', '@': 'а', '4': 'а', 'а́': 'а', 'α': 'а', 'ä': 'а', 'а': 'а',
#             # Б
#             'b': 'б', '6': 'б', 'б': 'б',
#             # В
#             'v': 'в', 'w': 'в', 'в': 'в',
#             # Г
#             'g': 'г', 'г': 'г',
#             # Д
#             'd': 'д', 'д': 'д',
#             # Е / Ё / Э
#             'e': 'е', '3': 'е', 'ё': 'е', 'э': 'е', 'е́': 'е', 'є': 'е', '3́': 'е', 'е': 'е',
#             # Ж
#             'zh': 'ж', 'ж': 'ж',
#             # З
#             'z': 'з', 'з': 'з',
#             # И / Й
#             'i': 'и', '1': 'и', '!': 'и', '|': 'и', 'j': 'и', 'й': 'и', 'и́': 'и', 'ы': 'и', 'и': 'и',
#             # К
#             'k': 'к', 'к': 'к',
#             # Л
#             'l': 'л', 'л': 'л',
#             # М
#             'm': 'м', 'µ': 'м', 'м': 'м',
#             # Н
#             'n': 'н', 'н': 'н',
#             # О
#             'o': 'о', '0': 'о', 'о́': 'о', 'ö': 'о', 'о': 'о',
#             # П
#             'p': 'п', 'п': 'п',
#             # Р
#             'r': 'р', 'р': 'р',
#             # С
#             's': 'с', 'c': 'с', '$': 'с', 'с': 'с',
#             # Т
#             't': 'т', '7': 'т', '+': 'т', 'т': 'т',
#             # У
#             'u': 'у', 'y': 'у', 'у́': 'у', 'у': 'у',
#             # Ф
#             'f': 'ф', 'ф': 'ф',
#             # Х
#             'h': 'х', 'x': 'х', 'х': 'х',
#             # Ц
#             'ts': 'ц', 'ц': 'ц',
#             # Ч
#             'ch': 'ч', 'ч': 'ч',
#             # Ш / Щ
#             'sh': 'ш', 'sch': 'щ', 'ш': 'ш', 'щ': 'щ',
#             # Ъ / Ь
#             'b': 'ь', 'ь': 'ь', 'ъ': 'ь'
#         }

#     @classmethod
#     def normalize_text(cls, text: str) -> tuple[str, list[str]]:
#         # 1. Удаление невидимых спецсимволов Unicode
#         text = re.sub(r'[\u200B-\u200D\uFEFF]', '', text)

#         # 2. Приведение к нижнему регистру и NFKC нормализации
#         text = unicodedata.normalize('NFKC', text.lower())

#         char_map = cls._clean_char_map()

#         # 3. Полная замена каждого символа по карте (буквы, цифры, знаки)
#         cleaned_chars = [char_map.get(c, c) for c in text]
#         cleaned_text = "".join(cleaned_chars)

#         # 4. Обработка списка отдельных слов
#         words = cleaned_text.split()
#         normalized_words = []
#         for word in words:
#             # Оставляем только буквы кириллицы/латиницы
#             clean_word = re.sub(r'[^а-яa-z]', '', word)
#             # Схлопываем повторы букв подряд (например, "ппееддоорр" -> "педор")
#             collapsed_word = re.sub(r'(.)\1+', r'\1', clean_word)
#             if collapsed_word:
#                 normalized_words.append(collapsed_word)

#         # 5. Склеивание всего текста в одну строку (для ловли "х.у.1.с.о.с" или "х у 1 с о с")
#         all_words_only = re.sub(r'[^а-яa-z]', '', cleaned_text)
#         collapsed_full_text = re.sub(r'(.)\1+', r'\1', all_words_only)

#         return collapsed_full_text, normalized_words

#     @commands.Cog.listener()
#     async def on_message(self, message: discord.Message):
#         if not message.guild or message.author.bot:
#             return

#         # Игнорирование администраторов
#         if getattr(message.author, 'guild_permissions', None) and message.author.guild_permissions.administrator:
#             return

#         # Игнорирование ролей поддержки
#         if hasattr(message.author, 'roles') and self.ignore_role_ids:
#             if any(r.id in self.ignore_role_ids for r in message.author.roles):
#                 return

#         raw_content = message.content.lower()
#         collapsed_text, normalized_words = self.normalize_text(message.content)

#         # Проверка 1: Завуалированные фразы по исходному тексту
#         matched = [p.pattern for p in self.patterns if p.search(raw_content)]

#         # Проверка 2: Поиск корней в склеенном и пословесном тексте
#         if not matched:
#             for word in self.base_words:
#                 if word in collapsed_text:
#                     matched.append(word)
#                     break
#                 if any(word in norm_word for norm_word in normalized_words):
#                     matched.append(word)
#                     break

#         if matched:
#             await self._handle_profanity(message, matched)

#     async def _handle_profanity(self, message: discord.Message, matched: list):
#         user = message.author
#         now = datetime.now()

#         if 'deleted_by_bot' in globals():
#             BotConfig.deleted_by_bot.add(message.id)

#         self._clean_old_messages(user.id)

#         if user.id not in self.messages_count:
#             self.messages_count[user.id] = {
#                 "count": 0,
#                 "first_time": now,
#                 "messages": []
#             }

#         clean_text = message.content.replace('\n', ' ')[:50]
#         self.messages_count[user.id]["count"] += 1
#         self.messages_count[user.id]["messages"].append({
#             "timestamp": now,
#             "content": clean_text,
#             "matched": matched[:3]
#         })

#         # Удаляем сообщение с нарушением
#         await safe_delete(message)

#         current_count = self.messages_count[user.id]["count"]
#         fake_interaction = self._create_fake_interaction(message)

#         # Выдача варна при достижении лимита
#         if current_count >= self.max_messages_before_warn:
#             self.messages_count[user.id] = {
#                 "count": 0,
#                 "first_time": datetime.now(),
#                 "messages": []
#             }

#             await commands_func.warn_func(
#                 fake_interaction,
#                 user,
#                 "Вы слишком часто используете запрещенный сленг/мат"
#             )
#         else:
#             await safe_send(
#                 fake_interaction,
#                 content=(
#                     f"<:clearemoji:1515691240476377218> **{user.mention}, ʙ ʙᴀɯᴇʍ ᴄообщᴇнии зᴀᴨᴩᴇщᴇнный ᴄᴧᴇнᴦ.**\n"
#                     f"<:warningemoji:1515756604178305054> оᴄᴛᴀᴧоᴄь до ʙᴀᴩнᴀ: {current_count}/{self.max_messages_before_warn}"
#                 ),
#                 delete_after=5
#             )

#     def _clean_old_messages(self, user_id: int):
#         if user_id not in self.messages_count:
#             return

#         cutoff = datetime.now() - timedelta(minutes=self.warning_reset_minutes)

#         if self.messages_count[user_id]["first_time"] < cutoff:
#             self.messages_count[user_id] = {
#                 "count": 0,
#                 "first_time": datetime.now(),
#                 "messages": []
#             }

#     def _create_fake_interaction(self, message: discord.Message):
#         class FakeInteraction:
#             def __init__(self, bot_member, guild, channel, message_id):
#                 self.user = bot_member
#                 self.guild = guild
#                 self.channel = channel
#                 self.id = message_id
#                 self.created_at = datetime.now()
#                 self.response = None

#         bot_member = message.guild.me if message.guild else self.bot.user

#         return FakeInteraction(
#             bot_member=bot_member,
#             guild=message.guild,
#             channel=message.channel,
#             message_id=message.id
#         )

#     async def _auto_reset_warnings(self):
#         await self.bot.wait_until_ready()

#         while not self.bot.is_closed():
#             await asyncio.sleep(60)

#             now = datetime.now()
#             cutoff = now - timedelta(minutes=self.warning_reset_minutes)

#             for user_id, data in list(self.messages_count.items()):
#                 if data["first_time"] < cutoff:
#                     self.messages_count[user_id] = {
#                         "count": 0,
#                         "first_time": now,
#                         "messages": []
#                     }

class RolePermissionDetector(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Список прав, которые считаются критически опасными для обычных ролей
        self.dangerous_permissions = [
            'administrator',
            'manage_guild',
            'manage_roles',
            'manage_webhooks',
            'mention_everyone',
            'kick_members',
            'ban_members',
            'manage_channels',      
            'manage_expressions',   
            'moderate_members'      
        ]
        
        # НАСТРОЙКА МЕЖСЕРВЕРНОЙ ПЕРЕДАЧИ
        self.source_guild_id = BotConfig.GUILD_ID  # ЗАМЕНИТЕ на ID сервера-источника (который сканируем)
        self.log_channel_id = BotConfig.CHANNELS.get("tech_logs")   # ЗАМЕНИТЕ на ID канала на сервере-получателе (куда слать логи)

        # Запуск фонового сканирования каждые 60 минут
        self.audit_roles_task.start()

    def cog_unload(self):
        self.audit_roles_task.cancel()

    def check_dangerous_permissions(self, role: discord.Role):
        """Проверяет роль на наличие опасных прав."""
        found_dangerous = []
        for perm, value in role.permissions:
            if perm in self.dangerous_permissions and value is True:
                found_dangerous.append(perm)
        return found_dangerous

    @tasks.loop(minutes=60)
    async def audit_roles_task(self):
        """Фоновое сканирование ролей на конкретном сервере."""
        await self.bot.wait_until_ready()
        
        # Находим целевой сервер-источник
        guild = self.bot.get_guild(self.source_guild_id)
        if not guild:
            print(f"❌ Не удалось найти сервер-источник с ID {self.source_guild_id}. Убедитесь, что бот присутствует на нем.")
            return

        # Сканируем роли только на найденном сервере-источнике
        for role in guild.roles:
            if role.is_default():  # @everyone
                # Для @everyone проверяем только самые критичные права
                everyone_danger = [p for p in ['administrator', 'mention_everyone', 'manage_roles'] if getattr(role.permissions, p)]
                if everyone_danger:
                    await self.notify_danger(guild, role, everyone_danger, is_everyone=True)
                continue

            # Проверяем обычные роли (пропускаем роли интеграций/ботов)
            if role.is_bot_managed() or role.is_integration():
                continue

            dangerous_perms = self.check_dangerous_permissions(role)
            # Если роль не должна обладать правами администратора, но имеет опасные права
            if dangerous_perms and not role.permissions.administrator:
                # Исключаем доверенные роли модераторов (берем из конфига)
                trusted_role_ids = BotConfig.SUPPORT_ROLES.get("third_order", [])
                if role.id not in trusted_role_ids:
                    await self.notify_danger(guild, role, dangerous_perms)

    async def notify_danger(self, guild, role, dangerous_perms, is_everyone=False):
        """Отправка уведомления об обнаружении опасных прав на другой сервер."""
        # Получаем канал логирования напрямую по его глобальному ID (работает между серверами)
        log_channel = self.bot.get_channel(self.log_channel_id)
        if not log_channel:
            try:
                log_channel = await self.bot.fetch_channel(self.log_channel_id)
            except Exception as e:
                print(f"❌ Не удалось получить межсерверный канал логирования с ID {self.log_channel_id}: {e}")
                return

        formatted_perms = ", ".join([f"`{p}`" for p in dangerous_perms])
        
        embed = discord.Embed(
            title="<:warningemoji:1515756604178305054> обнᴀᴩужᴇны оᴨᴀᴄныᴇ ᴨᴩᴀʙᴀ у ᴩоᴧи!",
            description=(
                f"у ᴩоᴧи **{role.name}** на сервере **{guild.name}** обнаружены опасные привилегии.\n"
                f"`обнᴀᴩужᴇнныᴇ ᴨᴩᴀʙᴀ`: {formatted_perms}"
            ) if not is_everyone else (
                f"<:redalertemoji:1526209446026678413> **ᴋᴩиᴛичᴇᴄᴋᴀя уᴦᴩозᴀ:** у стандартной роли `@everyone` на сервере **{guild.name}** активны опасные права: {formatted_perms}!\n"
                f"Любой зашедший на тот сервер пользователь может использовать их!"
            ),
            color=discord.Color.brand_red() if is_everyone else discord.Color.dark_orange(),
            timestamp=datetime.now(timezone.utc)
        )
        
        # Поскольку role.mention не будет отображаться корректно (не будет кликабельным) на другом сервере,
        # мы отправляем текстовое имя роли и ее ID для удобства модераторов
        embed.add_field(name="<:rolesemoji:1517494151086866522> ᴩоᴧь", value=f"**{role.name}**`", inline=True)
        embed.add_field(name="<:successemoji:1515691944460685372> иᴄᴛочниᴋ", value=f"Сервер: **{guild.name}**", inline=True)
        
        if guild.icon:
            embed.set_footer(text=guild.name, icon_url=guild.icon.url)

        await safe_send(log_channel, embed=embed)

    @audit_roles_task.before_loop
    async def before_audit(self):
        await self.bot.wait_until_ready()                  

class AntiWebhook(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Белый список ID пользователей, которым разрешено создавать вебхуки
        self.allowed_creators = BotConfig.SUPPORT_ROLES.get("third_order", [])
        # FIFO-список для хранения ID уже обработанных событий аудита (чтобы избежать дубликатов)
        self.processed_actions = []

    @commands.Cog.listener()
    async def on_webhooks_update(self, channel: discord.TextChannel):
        """Срабатывает при любом изменении вебхуков в текстовом канале."""
        guild = channel.guild
        
        # Проверяем права бота на управление вебхуками на сервере
        if not guild.me.guild_permissions.view_audit_log or not guild.me.guild_permissions.manage_webhooks:
            return

        try:
            # Получаем последнее действие создания вебхука из Audit Log
            async for entry in guild.audit_logs(action=discord.AuditLogAction.webhook_create, limit=1):
                creator = entry.user
                webhook_target = entry.target # Объект созданного вебхука

                # Если создатель — сам бот, игнорируем
                if creator.id == self.bot.user.id:
                    return

                # ПРОВЕРКА НА ДУБЛИКАТЫ: если это событие уже обрабатывалось, выходим
                if entry.id in self.processed_actions:
                    return

                # Проверяем, находится ли создатель в белом списке
                if creator.id not in self.allowed_creators:
                    # Вносим ID действия в список обработанных, чтобы предотвратить спам-триггер
                    self.processed_actions.append(entry.id)
                    
                    # Запускаем отложенное удаление ID из списка через 10 секунд
                    async def remove_from_cache(action_id):
                        await asyncio.sleep(10)
                        if action_id in self.processed_actions:
                            self.processed_actions.remove(action_id)
                            
                    asyncio.create_task(remove_from_cache(entry.id))

                    # Находим и удаляем этот вебхук
                    webhooks = await channel.webhooks()
                    for webhook in webhooks:
                        if webhook.id == webhook_target.id:
                            await webhook.delete(reason=f"Несанкционированное создание вебхука пользователем {creator.name}")
                            
                            await self.punish_creator(guild, creator, channel)
                            break
        except discord.Forbidden:
            print(f"❌ Нет прав доступа к Audit Logs или Webhooks на сервере {guild.name}.")
        except Exception as e:
            print(f"❌ Ошибка в системе Anti-Webhook: {e}")

    async def punish_creator(self, guild, member, channel):
        """Наказание за несанкционированное создание вебхука."""
        if isinstance(member, discord.Member) and not member.guild_permissions.administrator:
            try:
                # Даем таймаут на 2 часа (120 минут) за попытку саботажа
                await member.timeout(timedelta(minutes=120), reason="Попытка создания вебхука без разрешения (Anti-Nuke)")
                
                # Сообщение в чат (текст остался без изменений)
                await safe_send(
                    channel, 
                    f"<:verifiedemoji:1525207492928213204> **ᴄиᴄᴛᴇʍᴀ ᴀɴᴛɪ-ɴᴜᴋᴇ:** ᴨоᴨыᴛᴋᴀ ᴄоздᴀния ʙᴇбхуᴋᴀ ᴨоᴧьзоʙᴀᴛᴇᴧᴇʍ {member.mention} зᴀбᴧоᴋиᴩоʙᴀнᴀ.\nʙᴇбхуᴋ удᴀᴧᴇн, нᴀᴩуɯиᴛᴇᴧю ʙыдᴀн ᴛᴀйʍᴀуᴛ.",
                    delete_after=15
                )
            except Exception as e:
                print(f"⚠️ Не удалось наказать нарушителя {member.id}: {e}")

            # Логирование события (embed остался без изменений)
            log_channel = await safe_fetch_channel(self.bot, BotConfig.CHANNELS.get('tech_logs'))
            if log_channel:
                embed_log = discord.Embed(
                    title="<:redalertemoji:1526209446026678413> нᴇᴄᴀнᴋциониᴩоʙᴀнный ʙᴇбхуᴋ удᴀᴧᴇн",
                    description=f"ᴨоᴨыᴛᴀᴧᴄя ᴄоздᴀᴛь ʙᴇбхуᴋ ʙ ᴋᴀнᴀᴧᴇ {channel.mention}.",
                    color=discord.Color.brand_red(),
                    timestamp=datetime.now(timezone.utc)
                )
                embed_log.add_field(name="<:smileemoji:1526114626557706252> нᴀᴩуɯиᴛᴇᴧь", value=f"{member.mention}", inline=True)
                embed_log.add_field(name="<:verifiedemoji:1525207492928213204> дᴇйᴄᴛʙиᴇ зᴀщиᴛы", value="Вебхук уничтожен, выдан таймаут на 120 мин.", inline=True)
                
                if guild.icon:
                    embed_log.set_footer(text=guild.name, icon_url=guild.icon.url)
                    
                await safe_send(log_channel, embed=embed_log)

class TempVoice(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.temp_channels = set()
        self.muted_role_id = BotConfig.ROLES.get("muted")
        
        # Блокировка от гонки запросов при создании
        self._creation_lock = asyncio.Lock()
        self._creating_users = set()

    def is_temp_channel(self, channel: discord.abc.GuildChannel) -> bool:
        if not isinstance(channel, discord.VoiceChannel):
            return False
        if channel.id == BotConfig.CHANNELS['trigger_voice']:
            return False
        if channel.category_id != BotConfig.CATEGORIES['temp_voices']:
            return False
            
        # Проверка по ID в памяти или специфичному форматированию названия
        return channel.id in self.temp_channels or channel.name.endswith("𝙘𝙝𝙖𝙣𝙣𝙚𝙡") or "╠" in channel.name

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if member.bot:
            return

        # 1. Если игрок вышел или перешел из одного канала в другой
        if before.channel != after.channel:
            if before.channel and self.is_temp_channel(before.channel):
                await self.check_and_delete_channel(before.channel)

        # 2. Если игрок зашел в триггерный канал
        if after.channel and after.channel.id == BotConfig.CHANNELS['trigger_voice']:
            await self.create_temp_channel(member)

    async def check_and_delete_channel(self, channel: discord.VoiceChannel):
        """Проверяет конкретный канал и удаляет его, если он пуст."""
        try:
            # Получаем актуальное состояние из кэша
            cached_channel = self.bot.get_channel(channel.id) or channel
            
            if len(cached_channel.members) == 0:
                self.temp_channels.discard(channel.id)
                await cached_channel.delete(reason="Временный голосовой канал пуст.")
        except discord.NotFound:
            self.temp_channels.discard(channel.id)
        except discord.Forbidden:
            print(f"❌ Нет прав для удаления канала {channel.name}")
        except Exception as e:
            print(f"❌ Ошибка при удалении канала {channel.name}: {e}")

    async def create_temp_channel(self, member: discord.Member):
        # Защита от спама: если канал для юзера уже создается — выходим
        if member.id in self._creating_users:
            return

        async with self._creation_lock:
            self._creating_users.add(member.id)
            try:
                # Получаем категорию из кэша (без лишних HTTP запросов)
                category = self.bot.get_channel(BotConfig.CATEGORIES['temp_voices'])
                if not category:
                    category = await safe_fetch_channel(self.bot, BotConfig.CATEGORIES['temp_voices'])
                
                if not category:
                    print(f"❌ Категория временных каналов не найдена!")
                    return

                # Проверяем, не находится ли пользователь уже в созданной комнатe
                for channel in category.voice_channels:
                    if channel.id == BotConfig.CHANNELS['trigger_voice']:
                        continue
                    if member in channel.members and self.is_temp_channel(channel):
                        return

                # Формируем права СРАЗУ при создании (1 запрос вместо 4)
                overwrites = {
                    member.guild.default_role: discord.PermissionOverwrite(
                        connect=True,
                        send_messages=True,
                        attach_files=False
                    ),
                    member: discord.PermissionOverwrite(
                        connect=True,
                        manage_channels=True,
                        move_members=True
                    )
                }

                # Добавляем ограничения для Muted роли, если она существует
                if self.muted_role_id:
                    muted_role = member.guild.get_role(self.muted_role_id)
                    if muted_role:
                        overwrites[muted_role] = discord.PermissionOverwrite(
                            connect=False,
                            speak=False,
                            stream=False
                        )

                # Создание канала
                new_channel = await member.guild.create_voice_channel(
                    name=f"╠ {member.display_name}'s 𝙘𝙝𝙖𝙣𝙣𝙚𝙡",
                    category=category,
                    overwrites=overwrites,
                    reason=f"Автоматическое создание временного канала для {member}"
                )
                
                self.temp_channels.add(new_channel.id)

                # Перемещаем пользователя в созданный канал
                await member.move_to(new_channel)

            except discord.Forbidden:
                print(f"❌ Недостаточно прав для создания/перемещения у {member.name}")
            except discord.HTTPException as e:
                print(f"⚠️ Ошибка Discord API при создании канала: {e}")
            except Exception as e:
                print(f"❌ Ошибка в create_temp_channel: {e}")
            finally:
                self._creating_users.remove(member.id)

    async def check_empty_temp_channels(self, guild: discord.Guild):
        """Запускается как сервис/таск для фоновой очистки брошенных каналов."""
        category = self.bot.get_channel(BotConfig.CATEGORIES['temp_voices'])
        if not category:
            return

        for channel in category.voice_channels:
            if channel.id == BotConfig.CHANNELS['trigger_voice']:
                continue
            if len(channel.members) == 0 and self.is_temp_channel(channel):
                await self.check_and_delete_channel(channel)

class VoiceSpamDetector(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Хранилище логов голосовой активности: {user_id: [datetime, datetime, ...]}
        self.voice_tracker = {}
        
        # НАСТРОЙКИ ФИЛЬТРА
        self.max_actions = 5         # Максимальное количество переподключений/смен каналов
        self.time_window = 5         # Временной промежуток (в секундах)
        self.punishment_mute = 15    # Время таймаута за нарушение (в минутах)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        # Игнорируем ботов и администраторов
        if member.bot or member.guild_permissions.administrator:
            return

        # Проверяем, изменился ли голосовой канал (вход, выход, перемещение)
        # Игнорируем системные события типа mute/unmute/deafen
        if before.channel == after.channel:
            return

        now = datetime.now(timezone.utc)
        user_id = member.id

        # Инициализируем список для пользователя, если его нет в трекере
        if user_id not in self.voice_tracker:
            self.voice_tracker[user_id] = []

        # Очищаем историю переподключений от записей старше временного окна
        cutoff = now - timedelta(seconds=self.time_window)
        self.voice_tracker[user_id] = [t for t in self.voice_tracker[user_id] if t > cutoff]

        # Регистрируем текущее действие
        self.voice_tracker[user_id].append(now)

        # Проверяем превышение лимита (наказываем ровно на указанном значении)
        if len(self.voice_tracker[user_id]) >= self.max_actions:
            # Сбрасываем счетчик, чтобы избежать множественных наказаний за один спам-круг
            self.voice_tracker[user_id] = []

            # Переменная для отправки сообщения (пытаемся писать в тот канал, откуда шел спам, либо в общий)
            target_channel = after.channel or before.channel

            # 1. Принудительно отключаем пользователя от любого голосового канала
            if member.voice:
                try:
                    await member.move_to(None, reason="Принудительное отключение за спам голосовыми каналами")
                except discord.Forbidden:
                    print(f"⚠️ Не удалось отключить {member.name} из голосового канала (нет прав).")

            # 2. Выдаем таймаут нарушителю
            try:
                duration = timedelta(minutes=self.punishment_mute)
                await member.timeout(duration, reason=f"Голосовой спам (более {self.max_actions} подключений за {self.time_window} сек.)")
                
                # Отправляем предупреждение в текстовый чат, связанный с голосовым каналом (или текстовый лог)
                if target_channel:
                    await safe_send(
                        target_channel, 
                        f"<:forbiddenemoji:1515780232404144279> {member.mention} оᴛᴨᴩᴀʙᴧᴇн ʙ ᴛᴀйʍᴀуᴛ нᴀ {self.punishment_mute} ʍинуᴛ зᴀ ᴄᴨᴀʍ ᴦоᴧоᴄоʙыʍи ᴋᴀнᴀᴧᴀʍи!",
                        delete_after=10)
            except discord.Forbidden:
                print(f"❌ Недостаточно прав для выдачи таймаута пользователю {member.name}.")
            except Exception as e:
                print(f"❌ Ошибка при попытке выдать таймаут за голосовой спам: {e}")

            # 3. Отправляем красивый лог на ваш технический сервер
            log_channel = await safe_fetch_channel(self.bot, BotConfig.CHANNELS.get('tech_logs'))
            if log_channel:
                guild = member.guild
                embed_log = discord.Embed(
                    title="<:warningemoji:1515756604178305054> ᴦоᴧоᴄоʙой ᴄᴨᴀʍ ᴨᴩᴇᴄᴇчᴇн",
                    description=f"ᴨоᴧьзоʙᴀᴛᴇᴧь {member.mention} уᴄᴛᴩоиᴧ ɸᴧуд ᴨодᴋᴧючᴇнияʍи ʙ ᴦоᴧоᴄоʙых ᴋᴀнᴀᴧᴀх.",
                    color=discord.Color.brand_red(),
                    timestamp=datetime.now(timezone.utc)
                )
                embed_log.add_field(name="<:smileemoji:1526114626557706252> Нарушитель", value=f"{member.mention}", inline=True)
                embed_log.add_field(name="<:verifiedemoji:1525207492928213204> Действие", value=f"Кикнут из голосового канала,\nвыдан таймаут на {self.punishment_mute} мин.", inline=True)
                embed_log.add_field(name="<:successemoji:1515691944460685372> иᴄᴛочниᴋ", value=f"Сервер: **{guild.name}**", inline=False)
                
                if guild.icon:
                    embed_log.set_footer(text=guild.name, icon_url=guild.icon.url)
                    
                await safe_send(log_channel, embed=embed_log)

class ThreadModeration(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Настройка: через сколько часов неактивности архивировать ветку
        self.archive_threshold_hours = 6
        
        # Запуск фоновой задачи
        self.auto_archive_threads.start()

    def cog_unload(self):
        self.auto_archive_threads.cancel()

    @tasks.loop(minutes=30)  # Проверка запускается каждые 30 минут
    async def auto_archive_threads(self):
        """Фоновый цикл для поиска и архивации неактивных веток на серверах."""
        await self.bot.wait_until_ready()
        
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=self.archive_threshold_hours)
        
        # Проходим по всем серверам, где установлен бот
        for guild in self.bot.guilds:
            # Получаем все активные (не архивированные) ветки на сервере
            for thread in guild.threads:
                # Пропускаем приватные ветки, если бот не имеет к ним доступа
                if thread.archived:
                    continue
                
                try:
                    # Пытаемся получить время последнего сообщения в ветке
                    last_message_time = None
                    
                    if thread.last_message_id:
                        # Получаем последнее сообщение из кэша или истории
                        try:
                            last_msg = await thread.fetch_message(thread.last_message_id)
                            last_message_time = last_msg.created_at
                        except discord.NotFound:
                            # Если сообщение удалено, используем время создания самой ветки
                            last_message_time = thread.created_at
                    else:
                        # Если сообщений вообще не было, ориентируемся на время создания
                        last_message_time = thread.created_at

                    # Если время последнего действия старше установленного порога
                    if last_message_time and last_message_time < cutoff:
                        # Отправляем предупреждающее сообщение перед архивацией
                        await safe_send(thread,
                            f"<:sweepemoji:1526652778469003294> ʙᴇᴛᴋᴀ ᴀʙᴛоʍᴀᴛичᴇᴄᴋи ᴀᴩхиʙиᴩоʙᴀнᴀ из-зᴀ нᴇᴀᴋᴛиʙноᴄᴛи ʙ ᴛᴇчᴇниᴇ {self.archive_threshold_hours} ч.\n"
                            f"ᴧюбой учᴀᴄᴛниᴋ ʍожᴇᴛ оᴛᴨᴩᴀʙиᴛь ноʙоᴇ ᴄообщᴇниᴇ, чᴛобы оᴛᴋᴩыᴛь ᴇё ᴄноʙᴀ.")
                        
                        # Удаляем ветку
                        await thread.delete(reason="Авто-удаление по причине неактивности")
                        print(f"📦 Ветка '{thread.name}' (ID: {thread.id}) на сервере {guild.name} успешно архивирована.")
                        
                except discord.Forbidden:
                    # Ошибка, если у бота нет прав на управление ветками в этом канале
                    print(f"⚠️ Нет прав для архивации ветки '{thread.name}' на сервере {guild.name}.")
                except Exception as e:
                    print(f"❌ Ошибка при обработке ветки {thread.id}: {e}")

    @auto_archive_threads.before_loop
    async def before_auto_archive(self):
        await self.bot.wait_until_ready()

class ReactionAntiSpam(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Хранилище логов реакций: {user_id: [datetime, datetime, ...]}
        self.reaction_tracker = {}
        
        # НАСТРОЙКИ ФИЛЬТРА
        self.max_reactions = 5     # Максимальное количество реакций
        self.time_window = 5       # За какой промежуток времени (в секундах)
        self.punishment_mute = 20    # Время таймаута за нарушение (в минутах)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        # Игнорируем действия самого бота
        if payload.user_id == self.bot.user.id:
            return

        # Получаем объект сервера (guild)
        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return

        # Игнорируем администраторов
        member = payload.member or guild.get_member(payload.user_id)
        if not member or member.bot or member.guild_permissions.administrator:
            return

        now = datetime.now(timezone.utc)
        user_id = payload.user_id

        # Инициализируем список для пользователя, если его нет
        if user_id not in self.reaction_tracker:
            self.reaction_tracker[user_id] = []

        # Очищаем историю реакций пользователя от записей старше нашего временного окна
        cutoff = now - timedelta(seconds=self.time_window)
        self.reaction_tracker[user_id] = [t for t in self.reaction_tracker[user_id] if t > cutoff]

        # Добавляем текущую реакцию в историю
        self.reaction_tracker[user_id].append(now)

        # Проверяем превышение лимита
        if len(self.reaction_tracker[user_id]) >= self.max_reactions:
            # Сбрасываем счетчик, чтобы не спамить наказаниями
            self.reaction_tracker[user_id] = []

            channel = self.bot.get_channel(payload.channel_id) or await self.bot.fetch_channel(payload.channel_id)

            # Выдача наказания (Timeout)
            try:
                duration = timedelta(minutes=self.punishment_mute)
                await member.timeout(duration, reason=f"Спам реакциями (более {self.max_reactions} за {self.time_window} сек.)")
                
                # Отправка предупреждения в чат (через safe_send)
                if channel:
                    await safe_send(
                        channel, 
                        f"<:forbiddenemoji:1515780232404144279> {member.mention} оᴛᴨᴩᴀʙᴧᴇн ʙ ᴛᴀйʍᴀуᴛ нᴀ {self.punishment_mute} ʍинуᴛ зᴀ ᴄᴨᴀʍ ᴩᴇᴀᴋцияʍи!",
                        delete_after=10)
            except discord.Forbidden:
                print(f"❌ Нет прав для выдачи таймаута пользователю {member.name} (ID: {member.id})")
            except Exception as e:
                print(f"❌ Ошибка при попытке выдать таймаут за спам реакциями: {e}")

            # Попытка удалить ВСЕ реакции нарушителя с этого сообщения
            if channel:
                try:
                    message = await channel.fetch_message(payload.message_id)
                    # Проходимся по всем реакциям на сообщении и удаляем те, которые оставил нарушитель
                    for reaction in message.reactions:
                        try:
                            # Проверяем, реагировал ли этот пользователь данным эмодзи
                            async for user in reaction.users():
                                if user.id == member.id:
                                    await message.remove_reaction(reaction.emoji, member)
                                    break # Переходим к следующему эмодзи на этом сообщении
                        except Exception as e_single:
                            print(f"⚠️ Не удалось удалить конкретную реакцию {reaction.emoji}: {e_single}")
                except Exception as e:
                    print(f"⚠️ Не удалось получить сообщение для зачистки всех реакций: {e}")

            # Логирование нарушения
            log_channel = await safe_fetch_channel(self.bot, BotConfig.CHANNELS.get('warning_logs'))
            if log_channel:
                embed_log = discord.Embed(
                    title="<:warningemoji:1515756604178305054> ᴄᴨᴀʍ ᴩᴇᴀᴋцияʍи нᴇйᴛᴩᴀᴧизоʙᴀн",
                    description=f"ᴨоᴧьзоʙᴀᴛᴇᴧь {member.mention} ᴨᴩᴇʙыᴄиᴧ ᴧиʍиᴛ уᴄᴛᴀноʙᴋи ᴩᴇᴀᴋций.",
                    color=discord.Color.orange(),
                    timestamp=datetime.now(timezone.utc)
                )
                embed_log.add_field(name="<:smileemoji:1526114626557706252> учᴀᴄᴛниᴋ", value=f"{member.mention}", inline=True)
                embed_log.add_field(name="<:binemoji:1525176536607752202> нᴀᴋᴀзᴀниᴇ", value=f"Таймаут на {self.punishment_mute} мин.", inline=True)
                
                if guild.icon:
                    embed_log.set_footer(text=guild.name, icon_url=guild.icon.url)
                    
                await safe_send(log_channel, embed=embed_log)

class ServerStatsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.cooldown_until = None
        # Запускаем фоновую задачу обновления статистики
        self.update_counters_loop.start()

    def cog_unload(self):
        # Обязательно останавливаем задачу при выгрузке кога
        self.update_counters_loop.cancel()

    # Фоновая задача, работающая каждые 10 минут
    # Discord строго лимитирует переименование каналов (макс. 2 раза в 10 минут),
    # поэтому интервал в 10 минут является идеальным и безопасным стандартом.
    @tasks.loop(minutes=10)
    async def update_counters_loop(self):
        await self.bot.wait_until_ready()

        now = datetime.now(timezone.utc)

        if self.cooldown_until and now < self.cooldown_until:
            remaining = (self.cooldown_until - now).total_seconds()
            print(f"⏳ [Статистика] Обновление пропущено. Кулдаун лимитов Discord активен ещё {remaining:.1f} сек.")
            return

        # 2. Задержка перед первой проверкой при запуске бота
        if self.update_counters_loop.current_loop == 0:
            print("⏳ [Статистика] Ожидаем 15 секунд перед первой проверкой счетчиков при старте...")
            await asyncio.sleep(15)
        
        # Получаем ID сервера и каналов из конфигурации BotConfig
        guild_id = getattr(BotConfig, 'GUILD_ID', None)
        if not guild_id:
            return

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return

        # Получаем настроенные ID голосовых каналов для счётчиков
        stats_config = BotConfig.STATS
        if not stats_config:
            return

        # Подсчитываем количество участников
        total_members = guild.member_count
        bots_count = sum(1 for member in guild.members if member.bot)
        humans_count = total_members - bots_count

        # Словарь соответствия типов счётчиков и их названий
        # Вы можете использовать любые эмодзи и шрифты
        counters_data = {
            'total': (stats_config.get('total_id'), f"╔ⲡⲟⲗьⳅⲟⲃⲁⲧⲉⲗⲉύ — {total_members}"),
            'humans': (stats_config.get('humans_id'), f"╠ⲩɥⲁⲥⲧⲏυⲕⲟⲃ — {humans_count}"),
            'bots': (stats_config.get('bots_id'), f"╚ⳝⲟⲧⲟⲃ — {bots_count}")
        }

        for key, (channel_id, new_name) in counters_data.items():
            if not channel_id:
                continue

            channel = guild.get_channel(channel_id)
            if isinstance(channel, discord.VoiceChannel):
                # Проверяем, изменилось ли значение, чтобы не слать лишние запросы в API
                if channel.name != new_name:
                    try:
                        await channel.edit(name=new_name, reason="Автоматическое обновление счётчиков сервера")
                        print(f"📊 [Статистика] Счётчик {key} успешно обновлен на: '{new_name}'")
                        # Небольшая пауза между запросами для безопасности
                        await asyncio.sleep(2)
                    except discord.Forbidden:
                        print(f"⚠️ Ошибка счетчиков: У бота нет прав на редактирование канала {channel_id}")
                    except discord.HTTPException as e:
                        if e.status == 429:
                            # Красиво обрабатываем лимит запросов, не забивая консоль ошибками
                            print(f"⏰ [Rate Limit] Дискорд временно ограничил изменение канала {channel_id}. Обновим позже.")
                        else:
                            print(f"⚠️ Ошибка обновления счетчика {channel_id}: {e}")

    # =========================================================================
    # АДМИНИСТРАТИВНАЯ СЛЭШ-КОМАНДА ДЛЯ НАСТРОЙКИ СЧЁТЧИКОВ
    # =========================================================================

    @app_commands.command(name="счетчики_обновить", description="Принудительно обновить динамические счётчики сервера прямо сейчас")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(administrator=True)
    async def force_update_stats(self, interaction: discord.Interaction):
        """Ручной запуск обновления счётчиков (доступно только Администраторам)."""
        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild
        stats_config = BotConfig.STATS
        
        if not stats_config:
            await interaction.followup.send(
                content="❌ Счётчики не настроены в BotConfig.CHANNELS['stats']!",
                ephemeral=True
            )
            return

        total_members = guild.member_count
        bots_count = sum(1 for m in guild.members if m.bot)
        humans_count = total_members - bots_count

        counters_data = {
            'total': (stats_config.get('total_id'), f"╔ⲡⲟⲗьⳅⲟⲃⲁⲧⲉⲗⲉύ — {total_members}"),
            'humans': (stats_config.get('humans_id'), f"╠ⲩɥⲁⲥⲧⲏυⲕⲟⲃ — {humans_count}"),
            'bots': (stats_config.get('bots_id'), f"╚ⳝⲟⲧⲟⲃ — {bots_count}")
        }

        updated_count = 0
        for key, (channel_id, new_name) in counters_data.items():
            if not channel_id:
                continue

            channel = guild.get_channel(channel_id)
            if isinstance(channel, discord.VoiceChannel):
                try:
                    await channel.edit(name=new_name, reason=f"Ручное обновление. Инициатор: {interaction.user}")
                    updated_count += 1
                    await asyncio.sleep(1)
                except Exception as e:
                    print(f"❌ Не удалось обновить канал {channel_id}: {e}")

        await interaction.followup.send(
            content=f"✅ Успешно обновлено счётчиков: **{updated_count}** из 3.\n"
                    f"*Обратите внимание: Discord позволяет обновлять названия каналов не чаще 2 раз в 10 минут!*",
            ephemeral=True
        )

# 1. Создаем класс View с кнопкой для разблокировки
class UnlockView(discord.ui.View):
    def __init__(self, duration: int, support_role_ids: list):
        super().__init__(timeout=duration * 60) # Кнопка активна ровно то время, пока идет блокировка
        self.support_role_ids = support_role_ids

    @discord.ui.button(label="Открыть чат", style=discord.ButtonStyle.success, emoji="🔓", custom_id="unlock_channel_btn")
    async def unlock_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        channel = interaction.channel
        user = interaction.user

        # Проверка прав у нажавшего кнопку
        # 1. Проверяем, является ли пользователь администратором
        is_admin = user.guild_permissions.administrator
        
        # 2. Проверяем наличие права управления каналами
        has_manage_channels = user.guild_permissions.manage_channels
        
        # 3. Проверяем, есть ли у пользователя хотя бы одна роль из Support_roles
        has_support_role = any(role.id in self.support_role_ids for role in user.roles)

        # Объединяем все условия в итоговую проверку
        has_perm = is_admin or has_manage_channels or has_support_role

        if not has_perm:
            await safe_send(
                interaction, 
                "<:forbbiden2emoji:1517479332866429008> У вас нет прав для управления блокировкой этого канала!", 
                ephemeral=True)
            return

        # Разблокируем @everyone
        everyone_role = guild.default_role
        everyone_overwrites = channel.overwrites_for(everyone_role)
        everyone_overwrites.send_messages = None
        await channel.set_permissions(everyone_role, overwrite=everyone_overwrites, reason=f"Разблокировка кнопкой модератором {user}")

        # Сбрасываем изменения для ролей поддержки
        for role_id in self.support_role_ids:
            role = guild.get_role(role_id)
            if role:
                role_ow = channel.overwrites_for(role)
                role_ow.send_messages = None
                if role_ow.is_empty():
                    await channel.set_permissions(role, overwrite=None)
                else:
                    await channel.set_permissions(role, overwrite=role_ow)

        # Отключаем кнопку, чтобы ее нельзя было нажать повторно
        self.stop()
        for child in self.children:
            child.disabled = True

        # Отправляем сообщение о разблокировке
        unlock_embed = discord.Embed(
            title="<:verifiedemoji:1525207492928213204> ᴋᴀнᴀᴧ ᴩᴀзбᴧоᴋиᴩоʙᴀн",
            description=f"Модератор {user.mention} оᴛᴋᴩыᴧ чᴀᴛ. ʙы ᴄноʙᴀ ʍожᴇᴛᴇ оᴛᴨᴩᴀʙᴧяᴛь ᴄообщᴇния!",
            color=discord.Color.green(),
            timestamp=discord.utils.utcnow()
        )
        if guild.icon:
            unlock_embed.set_footer(text='𝐅𝐈𝐆𝐇𝐓 𝐂𝐋𝐔𝐁', icon_url=guild.icon.url)
        
        # Обновляем оригинальное сообщение (отключаем кнопку) и отправляем новый эмбед в чат
        await interaction.response.edit_message(view=self)
        await safe_send(interaction, embed=unlock_embed)

class VerificationView(discord.ui.View):
    def __init__(self, role_id: int):
        super().__init__(timeout=None)
        self.role_id = role_id

        # Динамически добавляем кнопку с выданной ролью
        button = discord.ui.Button(
            label="Пройти верификацию",
            style=discord.ButtonStyle.success,
            emoji="<:grantedemoji:1520173483299049623>",
            custom_id=f"verify_btn_{role_id}"
        )
        button.callback = self.verify_callback
        self.add_item(button)

    async def verify_callback(self, interaction: discord.Interaction):
        role_to_remove = interaction.guild.get_role(BotConfig.WELCOME_ROLES.get("join5"))
        if role_to_remove:
            await interaction.user.remove_roles(role_to_remove, reason="Верификация через кнопку")

        role = interaction.guild.get_role(self.role_id)
        if not role:
            await safe_send(interaction, "Ошибка: Роль верификации не найдена на сервере.", ephemeral=True)
            return

        if role in interaction.user.roles:
            await safe_send(interaction, "Вы уже прошли верификацию!", ephemeral=True)
            return

        try:
            await interaction.user.add_roles(role, reason="Верификация через кнопку")
            await safe_send(interaction, "<:grantedemoji:1520173483299049623> Вы успешно получили доступ к серверу!", ephemeral=True)
        except discord.Forbidden:
            await safe_send(interaction, "У бота недостаточно прав для выдачи этой роли.", ephemeral=True)

# ========== ДЕКОРАТОР ==========

def moderation_only(allowed_roles: list = None):
    async def predicate(interaction: discord.Interaction):
        if not interaction.guild or interaction.guild.id != BotConfig.GUILD_ID:
            return False
        if interaction.user.guild_permissions.administrator:
            return True
        if allowed_roles is None:
            all_support_roles = (
                BotConfig.SUPPORT_ROLES.get('first_order', []) +
                BotConfig.SUPPORT_ROLES.get('second_order', []) +
                BotConfig.SUPPORT_ROLES.get('third_order', []))
            roles_to_check = all_support_roles
        else:
            roles_to_check = allowed_roles
        user_roles = [role.id for role in interaction.user.roles]
        
        if not any(role_id in roles_to_check for role_id in user_roles):
            return False
        return True
    return app_commands.check(predicate)

# ========== МОДЕРАЦИОННЫЕ КОМАНДЫ (КЛАСС) ==========

class ModerationCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.last_purge_date = None
        # Запускаем фоновую задачу для автоматической очистки логов раз в 2 дня

    async def cog_load(self):
        self.bot.loop.create_task(self._auto_purge_logs_task())

    async def _auto_purge_logs_task(self):
        # 1. Ждём, пока бот полностью подключится к Discord API
        await self.bot.wait_until_ready()
        
        # 2. Дополнительная задержка в 5 секунд, чтобы кэш каналов успел полностью сформироваться
        # Это гарантирует, что функция safe_fetch_channel мгновенно возьмет каналы из локального кэша
        await asyncio.sleep(5)
        
        while not self.bot.is_closed():
            try:
                now = datetime.now(timezone.utc)
                
                # Если очистка ещё ни разу не проводилась или с момента последней прошло более 2 дней
                if self.last_purge_date is None or (now - self.last_purge_date).days >= 2:
                    
                    # Собираем ID каналов логов, которые подлежат периодической очистке
                    target_channels_keys = ['warning_logs', 'mod_logs_commands', 'mod_logs', 'tech_logs']
                    
                    for key in target_channels_keys:
                        channel_id = BotConfig.CHANNELS.get(key)
                        if not channel_id:
                            continue
                            
                        channel = await safe_fetch_channel(self.bot, channel_id)
                        if isinstance(channel, discord.TextChannel):
                            try:
                                # Удаляем сообщения в канале логов (пропускаем закреплённые сообщения)
                                deleted = await channel.purge(limit=2000, check=lambda m: not m.pinned)
                                deleted_count = len(deleted)
                                
                                # Отправляем информационное сообщение об успешной очистке
                                if deleted_count > 0:
                                    info_embed = discord.Embed(
                                        title="<:sweepemoji:1526652778469003294> ᴨᴧᴀноʙᴀя очиᴄᴛᴋᴀ ᴧоᴦоʙ",
                                        description=(
                                            f"ᴋᴀнᴀᴧ быᴧ ᴀʙᴛоʍᴀᴛичᴇᴄᴋи очищᴇн оᴛ уᴄᴛᴀᴩᴇʙɯих зᴀᴨиᴄᴇй.\n"
                                            f"удᴀᴧᴇно ᴄообщᴇний: **{deleted_count}**.\n"
                                            f"ᴄᴧᴇдующᴀя ᴨᴧᴀноʙᴀя очиᴄᴛᴋᴀ: через **2 дня**."
                                        ),
                                        color=discord.Color.blue(),
                                        timestamp=now
                                    )
                                    info_embed.set_image(url='https://i.pinimg.com/originals/6f/41/1a/6f411aecccd141513e25d6be01e9f59d.gif?nii=t')
                                    info_embed.set_footer(text="(ᴄᴀо) ᴄиᴄᴛᴇʍᴀ ᴀʙᴛоʍᴀᴛичᴇᴄᴋой оᴨᴛиʍизᴀции")
                                    await channel.send(embed=info_embed, delete_after=60) # удалится само через минуту
                                    
                                print(f"🧹 [Авто-очистка] Успешно очищен канал {channel.name} ({key}). Удалено сообщений: {deleted_count}")
                            except Exception as channel_err:
                                print(f"⚠️ Не удалось очистить канал логов {channel_id}: {channel_err}")
                                
                    # Обновляем метку времени последней очистки логов
                    self.last_purge_date = now
                    
            except Exception as task_err:
                print(f"❌ Ошибка в задаче автоматической очистки логов: {task_err}")
                
            # Проверяем условия раз в 1 час, чтобы не грузить процессор
            await asyncio.sleep(3600)

    @app_commands.command(name='удалить_сообщения', description='Очистить чат.')
    @app_commands.guild_only()
    @moderation_only(BotConfig.SUPPORT_ROLES['third_order'])
    async def clear_messages(self, interaction: discord.Interaction, amount: app_commands.Range[int, 1, 100]):
        # Откладываем ответ, так как очистка может занять больше 3 секунд
        await interaction.response.defer(ephemeral=True)

        user = interaction.user
        user_mention = user.mention
        user_avatar = user.display_avatar.url if user.display_avatar else None
        guild = interaction.guild

        try:
            # Выполняем очистку канала
            deleted = await interaction.channel.purge(limit=amount)
            deleted_count = len(deleted)

            # Отправляем подтверждение модератору
            await interaction.followup.send(
                content=f"<:successemoji:1515691944460685372> Успешно удалено {deleted_count} сообщений.",
                ephemeral=True
            )

            # Логирование в модераторский канал
            log_channel_id = BotConfig.CHANNELS.get('mod_logs_commands')
            if log_channel_id:
                log_channel = await safe_fetch_channel(self.bot, log_channel_id)
                if log_channel:
                    embed = discord.Embed(
                        title="<:clearemoji:1515691240476377218> /удалить_сообщения",
                        description=f"`ʍодᴇᴩᴀᴛоᴩ`: {user_mention} <:forbiddenemoji:1515780232404144279>\n"
                                    f"`удᴀᴧиᴧ ᴄообщᴇний`: {deleted_count} <:successemoji:1515691944460685372>\n"
                                    f"`ᴋᴀнᴀᴧ`: {interaction.channel.mention} <:clearemoji:1515691240476377218>",
                        color=discord.Color.darker_grey(),
                        timestamp=datetime.now()
                    )
                    if user_avatar:
                        embed.set_thumbnail(url=user_avatar)
                    if guild and guild.icon:
                        embed.set_footer(text='𝐅𝐈𝐆𝐇𝐓 𝐂𝐋𝐔𝐁', icon_url=guild.icon.url)

                    await safe_send(log_channel, embed=embed)

        except discord.Forbidden:
            await interaction.followup.send(
                content="<:forbiddenemoji:1515780232404144279> У бота нет прав на управление сообщениями в этом канале!",
                ephemeral=True
            )
        except discord.HTTPException as e:
            await interaction.followup.send(
                content=f"<:forbiddenemoji:1515780232404144279> Ошибка Discord API: {e}",
                ephemeral=True
            )
        except Exception as e:
            await interaction.followup.send(
                content=f"<:forbiddenemoji:1515780232404144279> Произошла ошибка при удалении: {e}",
                ephemeral=True
            )

    @app_commands.command(name="lock", description="Заблокировать канал на время")
    @app_commands.guild_only()
    @moderation_only(BotConfig.SUPPORT_ROLES['second_order'] + BotConfig.SUPPORT_ROLES['third_order'])
    @app_commands.describe(duration="Длительность блокировки в минутах (по умолчанию 60)")
    async def lock_command(self, interaction: discord.Interaction, duration: app_commands.Range[int, 10, 1440]):
        guild = interaction.guild
        channel = interaction.channel
        user = interaction.user

        # 1. Проверка типов: команда работает только в обычных текстовых каналах
        if not isinstance(channel, discord.TextChannel):
            await safe_send(interaction, "<:forbiddenemoji:1515780232404144279> Эту команду можно использовать только в текстовых каналах!", ephemeral=True)
            return

        # 2. Список ролей модерации/поддержки из конфига или локальной переменной
        support_role_ids = BotConfig.SUPPORT_ROLES.get("first_order", []) + BotConfig.SUPPORT_ROLES.get("second_order", []) + BotConfig.SUPPORT_ROLES.get("third_order", [])

        # Проверка прав вызова: наличие права manage_channels ИЛИ хотя бы одной роли поддержки
        has_perm = user.guild_permissions.manage_channels or any(r.id in support_role_ids for r in user.roles)
        if not has_perm:
            await safe_send(interaction, "<:forbiddenemoji:1515780232404144279> У вас нет прав для блокировки этого канала!", ephemeral=True)
            return

        # 3. Проверка прав самого бота
        bot_member = guild.me or await guild.fetch_member(self.bot.user.id)
        if not channel.permissions_for(bot_member).manage_channels:
            await safe_send(interaction, "<:forbiddenemoji:1515780232404144279> У бота нет права `Управление каналами` (Manage Channels) в этом канале!", ephemeral=True)
            return

        # 4. Проверка корректности времени (от 1 минуты до 24 часов)
        if duration < 1 or duration > 1440:
            await safe_send(interaction, "<:forbiddenemoji:1515780232404144279> Укажите время от 1 до 1440 минут (24 часа)!", ephemeral=True)
            return

        everyone_role = guild.default_role
        everyone_overwrites = channel.overwrites_for(everyone_role)

        # 5. Проверка: не заблокирован ли уже канал
        if everyone_overwrites.send_messages is False:
            await safe_send(interaction, "<:forbiddenemoji:1515780232404144279> Этот канал уже заблокирован!", ephemeral=True)
            return

        # Откладываем ответ, так как обновление прав нескольких ролей может занять время
        await interaction.response.defer()

        # --- ПРИМЕНЕНИЕ ОГРАНИЧЕНИЙ ---

        # А) Блокируем доступ для @everyone
        everyone_overwrites.send_messages = False
        await channel.set_permissions(
            everyone_role, 
            overwrite=everyone_overwrites, 
            reason=f"Блокировка канала (Модератор: {user})")

        # Б) Явно разрешаем писать ролям поддержки (Support_Roles)
        unlocked_support_roles = []
        for role_id in support_role_ids:
            role = guild.get_role(role_id)
            if role:
                role_overwrites = channel.overwrites_for(role)
                role_overwrites.send_messages = True
                await channel.set_permissions(
                    role, 
                    overwrite=role_overwrites, 
                    reason="Разрешение доступа модераторам во время блокировки"
                )
                unlocked_support_roles.append(role.mention)

        # --- ОТПРАВКА ОБЪЯВЛЕНИЯ ---
        
        unlock_time = int(discord.utils.utcnow().timestamp()) + (duration * 60)
        support_info = ", ".join(unlocked_support_roles) if unlocked_support_roles else "Администрация"

        embed = discord.Embed(
            title="<:owneremoji:1517494149119611063> ᴋᴀнᴀᴧ ʙᴩᴇʍᴇнно оᴦᴩᴀничᴇн",
            description=(
                f"ᴋᴀнᴀᴧ зᴀᴋᴩыᴛ нᴀ **{duration} ʍинуᴛ** дᴧя ᴩᴀзбоᴩᴀ ᴄиᴛуᴀций и уᴩᴇᴦуᴧиᴩоʙᴀния ᴋонɸᴧиᴋᴛоʙ. <:verifiedemoji:1525207492928213204>\n\n"
                f"<:successemoji:1515691944460685372> **ᴨиᴄᴀᴛь ʍоᴦуᴛ:** {support_info}\n"
                f"<:forbiddenemoji:1515780232404144279> **ᴩᴀзбᴧоᴋиᴩоʙᴋᴀ:** <t:{unlock_time}:R> (<t:{unlock_time}:f>)\n\n"
                f"ᴨожᴀᴧуйᴄᴛᴀ, ᴄобᴧюдᴀйᴛᴇ ᴨоᴩядоᴋ и ожидᴀйᴛᴇ ᴩᴇɯᴇния ʍодᴇᴩᴀᴛоᴩоʙ."
            ),
            color=discord.Color.brand_red(),
            timestamp=discord.utils.utcnow()
        )
        embed.set_footer(text=f"Заблокировал: {user.display_name}", icon_url=user.display_avatar.url)

        view = UnlockView(duration=duration, support_role_ids=BotConfig.SUPPORT_ROLES['second_order']+BotConfig.SUPPORT_ROLES['third_order'])
        await safe_send(interaction, embed=embed, view=view)

        # --- ТАЙМЕР АВТО-РАЗБЛОКИРОВКИ ---

        async def auto_unlock():
            await asyncio.sleep(duration * 60)

            # Проверяем, заблокирован ли еще канал
            current_everyone = channel.overwrites_for(everyone_role)
            if current_everyone.send_messages is False:
                # Возвращаем дефолтные права для @everyone
                current_everyone.send_messages = None
                await channel.set_permissions(everyone_role, overwrite=current_everyone, reason="Автоматическая разблокировка по таймеру")

                # Сбрасываем персональные оверрайды для ролей поддержки, если они менялись
                for role_id in support_role_ids:
                    role = guild.get_role(role_id)
                    if role:
                        role_ow = channel.overwrites_for(role)
                        role_ow.send_messages = None
                        # Если у оверрайда больше нет настроек, сбрасываем его полностью
                        if role_ow.is_empty():
                            await channel.set_permissions(role, overwrite=None, reason="Сброс прав после блокировки")
                        else:
                            await channel.set_permissions(role, overwrite=role_ow, reason="Сброс прав после блокировки")

                # Делаем кнопку неактивной, если время вышло
                for child in view.children:
                    child.disabled = True

                unlock_embed = discord.Embed(
                    title="<:verifiedemoji:1525207492928213204> ᴋᴀнᴀᴧ ᴩᴀзбᴧоᴋиᴩоʙᴀн",
                    description="ʙᴩᴇʍя бᴧоᴋиᴩоʙᴋи иᴄᴛᴇᴋᴧо. доᴄᴛуᴨ ᴋ чᴀᴛу ʙоᴄᴄᴛᴀноʙᴧᴇн. ᴨожᴀᴧуйᴄᴛᴀ, ᴄобᴧюдᴀйᴛᴇ ᴨᴩᴀʙиᴧᴀ!",
                    color=discord.Color.green(),
                    timestamp=discord.utils.utcnow()
                )
                if guild.icon:
                    unlock_embed.set_footer(text='𝐅𝐈𝐆𝐇𝐓 𝐂𝐋𝐔𝐁', icon_url=guild.icon.url)
                try:
                    await channel.send(embed=unlock_embed)
                except Exception as e:
                    print(f"❌ Ошибка отправки сообщения об авто-разблокировке: {e}")

        # Запуск таймера в фоновом режиме
        asyncio.create_task(auto_unlock())

    @app_commands.command(name='выгнать', description='Выгнать пользователя.')
    @app_commands.guild_only()
    @app_commands.choices(rule=BotConfig.RULE_CHOICES)
    @app_commands.describe(member="Участник, которого нужно выгнать", rule="Выберите нарушенный пункт правил", reason="Дополнительное примечание")
    @moderation_only(BotConfig.SUPPORT_ROLES['second_order']+BotConfig.SUPPORT_ROLES['third_order'])
    async def kick_member(self, interaction: discord.Interaction, member: discord.Member, rule: app_commands.Choice[str], reason: str = "Не указана"):    
        await commands_func.kick_func(interaction, member, rule.value, reason)

    @app_commands.command(name='нейтрализовать', description='Забанить пользователя.')
    @app_commands.guild_only()
    @app_commands.choices(rule=BotConfig.RULE_CHOICES)
    @app_commands.describe(member="Участник, которого нужно забанить", rule="Выберите нарушенный пункт правил", reason="Дополнительное примечание")
    @moderation_only(BotConfig.SUPPORT_ROLES['second_order']+BotConfig.SUPPORT_ROLES['third_order'])
    async def ban_member(self, interaction: discord.Interaction, member: discord.Member, rule: app_commands.Choice[str], reason: str = "Не указана"):
        await commands_func.ban_func(interaction, member, rule.value, reason)

    @app_commands.command(name='аппелировать', description='Разбанить пользователя.')
    @app_commands.guild_only()
    @app_commands.describe(name_or_id="Айди пользователя")
    @moderation_only(BotConfig.SUPPORT_ROLES['third_order'])
    async def unban_member(self, interaction: discord.Interaction, name_or_id: str):
        await commands_func.unban_func(interaction, name_or_id)
        
    @app_commands.command(name='арестовать', description='Ограничить пользователю право общаться.')
    @app_commands.guild_only()
    @app_commands.choices(rule=BotConfig.RULE_CHOICES)
    @app_commands.describe(member="Участник, которого нужно замутить", minutes="Время мута", rule="Выберите нарушенный пункт правил", reason="Дополнительное примечание")
    @moderation_only()
    async def mute_member(self, interaction: discord.Interaction, member: discord.Member, minutes: app_commands.Range[int, 10, 1440], rule: app_commands.Choice[str], reason: str = "Не указана"):
        await commands_func.mute_func(interaction, member, minutes, rule.value, reason)
        
    @app_commands.command(name='освободить', description='Вернуть пользователю право общения.')
    @app_commands.guild_only()
    @app_commands.describe(member="Участник, которого следует размутить", reason="Причина размута")
    @moderation_only()
    async def unmute_member(self, interaction: discord.Interaction, member: discord.Member, reason: str):
        await commands_func.unmute_func(interaction, member, reason)

    @app_commands.command(name='выдать_предупреждение', description='Выдать предупреждение пользователю.')
    @app_commands.guild_only()
    @app_commands.choices(rule=BotConfig.RULE_CHOICES)
    @app_commands.describe(member="Участник, которому нужно выдать предупреждение", rule="Выберите нарушенный пункт правил", reason="Дополнительное примечание")
    @moderation_only(BotConfig.SUPPORT_ROLES['second_order']+BotConfig.SUPPORT_ROLES['third_order'])
    async def warn_member(self, interaction: discord.Interaction, member: discord.Member, rule: app_commands.Choice[str], reason: str ="Не указана"):
        await commands_func.warn_func(interaction, member, rule.value, reason)

    @app_commands.command(name='снять_предупреждение', description='Снять предупреждение с пользователя.')
    @app_commands.guild_only()
    @app_commands.describe(member="Участник, которому нужно снять предупреждение")
    @moderation_only(BotConfig.SUPPORT_ROLES['second_order']+BotConfig.SUPPORT_ROLES['third_order'])
    async def unwarn_member(self, interaction: discord.Interaction, member: discord.Member):
        await commands_func.unwarn_member(interaction, member)

    # ========== КОМАНДЫ НАСТРОЙКИ ==========

    @app_commands.command(name='sync', description='Синхронизировать команды.')
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    async def clearslash(self, interaction: discord.Interaction):
        # 1. Очищаем локальные команды на этом сервере
        bot.tree.clear_commands(guild=interaction.guild)
        await bot.tree.sync(guild=interaction.guild)
        
        # 2. Очищаем глобальные команды бота
        bot.tree.clear_commands(guild=None)
        await bot.tree.sync()
        
        await safe_send(interaction, "🧹 Все слэш-команды (глобальные и локальные) успешно удалены из Discord! Подождите пару минут, пока Discord обновит интерфейс.")

    @app_commands.command(name='status', description='Статус бота.')
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    async def status_of_bot(self, interaction: discord.Interaction):
        if interaction.user.id != BotConfig.DEVELOPER_ID:
            await safe_send(interaction, "<:forbiddenemoji:1515780232404144279> У тебя нет прав для этой команды.", ephemeral=True)
            return
        await safe_send(Interaction, f"{interaction.user.mention}, бот ещё жив! <:grantedemoji:1520173483299049623>", delete_after=5)

    # ========== КОМАНДЫ ПОМОЩИ ==========

    @app_commands.command(name="create_ticket", description="Создать панель тикета.")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    async def create_ticket(self, interaction: discord.Interaction):
        await interaction.response.send_modal(AdminSetupModal(channel=interaction.channel))

    @app_commands.command(name="verification", description="Создать сообщение для верификации.")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(channel="Канал для отправки", role="Роль для выдачи")
    async def verification_button(self, interaction: discord.Interaction, channel: discord.TextChannel, role: discord.Role):
        if interaction.user.id != BotConfig.DEVELOPER_ID:
            await safe_send(interaction, "<:forbiddenemoji:1515780232404144279> У тебя нет прав.", ephemeral=True)
            return
        embed = discord.Embed(
            title="<:verifiedemoji:1525207492928213204> ʙᴇᴩиɸиᴋᴀция",
            description="**нᴀжʍиᴛᴇ нᴀ ᴋноᴨᴋу ᴄнизу <:grantedemoji:1520173483299049623>**, чᴛобы ᴨоᴧучиᴛь доᴄᴛуᴨ ᴋ ᴄᴇᴩʙᴇᴩу!\n**ᴄᴛᴀндᴀᴩᴛнᴀя ᴨᴩоʙᴇᴩᴋᴀ** нᴀ ᴨоᴧьзоʙᴀᴛᴇᴧя, дᴧя оᴛᴋᴩыᴛия ᴋᴀнᴀᴧоʙ нᴀжʍиᴛᴇ ᴩᴇᴀᴋцию.",
            color=discord.Color.brand_green())
        embed.add_field(name="<:rolesemoji:1517494151086866522> Вы получите роль", value=role.mention, inline=False)
        embed.set_image(url='https://i.pinimg.com/originals/90/9c/40/909c405bc363f250d247f14ac0c89818.gif?nii=t')
        embed.set_footer(text='𝐅𝐈𝐆𝐇𝐓 𝐂𝐋𝐔𝐁 • 𝐕𝐞𝐫𝐢𝐟𝐢𝐜𝐚𝐭𝐢𝐨𝐧', icon_url=interaction.guild.icon.url if interaction.guild.icon else None)
        
        await channel.send(embed=embed, view=VerificationView(role.id))
        await safe_send(interaction, f"Верификация создана в {channel.mention}!", ephemeral=True)

class InfoCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        # Инициализируем контекстные меню через создание объектов ContextMenu
        self.info_context_menu = app_commands.ContextMenu(
            name="информация о пользователе",
            callback=self.show_info_user
        )
        self.reputation_context_menu = app_commands.ContextMenu(
            name="репутация о пользователе",
            callback=self.show_user_reputation
        )
        self.level_context_menu = app_commands.ContextMenu(
            name="уровень/опыт пользователя",
            callback=self.level_command
        )
        self.last_purge_date = None

    async def cog_load(self):
        # Регистрируем меню в дереве команд бота при загрузке Кога
        self.bot.tree.add_command(self.info_context_menu)
        self.bot.tree.add_command(self.reputation_context_menu)
        self.bot.tree.add_command(self.level_context_menu)

    def cog_unload(self):
        # Удаляем контекстные меню при выгрузке кога, чтобы избежать дублирования
        self.bot.tree.remove_command(self.info_context_menu.name, type=self.info_context_menu.type)
        self.bot.tree.remove_command(self.reputation_context_menu.name, type=self.reputation_context_menu.type)
        self.bot.tree.remove_command(self.level_context_menu.name, type=self.level_context_menu.type)
    
    # ========== КОМАНДЫ ДЛЯ ИНФОРМАЦИИ ==========

    @app_commands.command(name='userinfo', description='Узнайте информацию об пользователе.')
    @app_commands.guild_only()
    async def user_info(self, interaction: discord.Interaction, member: discord.Member = None):
        await commands_func.user_info_func(interaction, member)

    @app_commands.command(name="serverinfo", description="Узнайте информацию о сервере.")
    @app_commands.guild_only()
    async def server_info(self, interaction: discord.Interaction):
        # Проверка каналов
        allowed_channels = [
            BotConfig.CHANNELS.get("commands"),
            BotConfig.CHANNELS.get("mod_commands"),
        ]

        if interaction.channel.id not in allowed_channels:
            await safe_send(
                interaction,
                "<:forbiddenemoji:1515780232404144279> Эта команда работает только в"
                f" канале <#{BotConfig.CHANNELS['commands']}>!",
                ephemeral=True,
            )
            return

        guild = interaction.guild

        # 1. Безопасное получение владельца (если нет в кэше)
        owner = guild.owner
        if not owner:
            try:
                owner = await guild.fetch_owner()
            except discord.HTTPException:
                owner = None

        owner_mention = owner.mention if owner else "Неизвестно"

        # 2. Подсчет ботов и обычных участников
        bots_count = sum(1 for m in guild.members if m.bot)
        humans_count = guild.member_count - bots_count

        # 3. Детализация каналов
        text_channels = len(guild.text_channels)
        voice_channels = len(guild.voice_channels)

        # 4. Форматирование времени создания
        created_timestamp = int(guild.created_at.timestamp())

        # 5. Сборка Embed
        embed = discord.Embed(
            title=f"<:techicalemoji:1515678259767939262> {guild.name}",
            description=guild.description or "Описание отсутствует.",
            color=discord.Color.darker_grey(),
        )

        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)

        # Добавляем баннер сервера, если он есть (буст 2+ уровня)
        if guild.banner:
            embed.set_image(url=guild.banner.url)

        embed.add_field(
            name="ɪᴅ <:peopleemoji:1517486620939649044>",
            value=f"`{guild.id}`",
            inline=True,
        )
        embed.add_field(
            name="ʙᴧᴀдᴇᴧᴇц <:owneremoji:1517494149119611063>",
            value=owner_mention,
            inline=True,
        )
        embed.add_field(
            name="дᴀᴛᴀ ᴄоздᴀния <:techicalemoji:1515678259767939262>",
            value=f"<t:{created_timestamp}:D> (<t:{created_timestamp}:R>)",
            inline=True,
        )

        embed.add_field(
            name="учᴀᴄᴛниᴋи <:coolemoji:1517487042018410577>",
            value=(
                f"Всего: **{guild.member_count}**\n👥 Людей:"
                f" **{humans_count}**\n🤖 Ботов: **{bots_count}**"
            ),
            inline=True,
        )
        embed.add_field(
            name="ᴋᴀнᴀᴧы <:clearemoji:1515691240476377218>",
            value=(
                f"Всего: **{len(guild.channels)}**\n💬 Текстовых:"
                f" **{text_channels}**\n🔊 Голосовых: **{voice_channels}**"
            ),
            inline=True,
        )
        embed.add_field(
            name="буᴄᴛы <:insaneemoji:1526218299313098752>",
            value=(
                f"Уровень: **{guild.premium_tier}**\nБустов:"
                f" **{guild.premium_subscription_count or 0}**"
            ),
            inline=True,
        )

        embed.set_footer(
            text=f"𝐅𝐈𝐆𝐇𝐓 𝐂𝐋𝐔𝐁 • Запросил: {interaction.user.display_name}",
            icon_url=interaction.guild.icon.url if interaction.guild.icon else None,)

        await safe_send(interaction, embed=embed, ephemeral=False)

    @app_commands.command(name='репутация', description='Узнайте репутацию пользователя.')
    @app_commands.guild_only()
    async def user_reputation(self, interaction: discord.Interaction, member: discord.Member = None):
        await commands_func.reputation_info_func(interaction, member)

    @app_commands.command(name="левел", description="Показать карточку уровня и опыта участника.")
    @app_commands.guild_only()
    @app_commands.describe(member="Выберите участника сервера, чтобы посмотреть его уровень (необязательно)")
    async def level_command(self, interaction: discord.Interaction, member: discord.Member = None):
        await commands_func.level_info_func(interaction, member)
    
    # ========== БЫСТРЫЕ ДЕЙСТВИЯ ==========

    async def show_info_user(self, interaction: discord.Interaction, member: discord.Member):
        """Внутренний колбэк для контекстного меню информации об участнике."""
        await commands_func.user_info_func(interaction, member)

    async def show_user_reputation(self, interaction: discord.Interaction, member: discord.Member):
        """Внутренний колбэк для контекстного меню репутации."""
        await commands_func.reputation_info_func(interaction, member)

    async def level_command(self, interaction: discord.Interaction, member: discord.Member):
        """Внутренний колбэк для контекстного меню уровней."""
        await commands_func.level_info_func(interaction, member)

# ========== ТЕКСТОВЫЕ СОБЫТИЕ ==========

@bot.event
async def on_message(message: discord.Message):
    # 1. Игнорируем ЛС и ботов (включая самого бота)
    if not message.guild or message.author.bot:
        return

    user_id = message.author.id
    current_time = time.time()

    # 2. СИСТЕМА +REP
    # Используем lower(), чтобы сработало и "+REP", и "+Rep"
    # if message.content.lower().startswith("+rep"):
    #     if message.mentions:
    #         target_user = message.mentions[0]
    #         BotConfig.deleted_by_bot.add(message.id)

    #     # Проверка: нельзя выдавать репутацию самому себе
    #     if target_user.id == user_id:
    #         await safe_reply(
    #             message,
    #             "<:forbiddenemoji:1515780232404144279> Вы не можете дать репутацию"
    #             " самому себе!",
    #             delete_after=5,
    #         )
    #         await safe_delete(message, delay=2)
    #         return

    #     # Проверка: нельзя выдавать репутацию ботам
    #     if target_user.bot:
    #         await safe_reply(
    #             message,
    #             "<:forbiddenemoji:1515780232404144279> Нельзя выдавать репутацию"
    #             " ботам!",
    #             delete_after=5,
    #         )
    #         await safe_delete(message, delay=2)
    #         return

    #     # Проверка кулдауна
    #     author_ruler = await manager.get_user_ruler(user_id)
    #     last_rep_time = author_ruler.get("last_time_reputation", 0)
    #     cooldown_seconds = 21600  # 6 часов
    #     time_passed = current_time - last_rep_time

    #     if time_passed < cooldown_seconds:
    #         seconds_left = int(cooldown_seconds - time_passed)
    #         hours = seconds_left // 3600
    #         minutes = (seconds_left % 3600) // 60
    #         await safe_reply(
    #             message,
    #             f"**<:forbiddenemoji:1515780232404144279> {message.author.mention},"
    #             " вы не можете так часто использовать эту команду!**\n⌛ Осталось:"
    #             f" **{hours} ч. {minutes} мин.**",
    #             delete_after=5,
    #         )
    #         await safe_delete(message, delay=2)
    #         return

    #     # Обновление данных получателя
    #     target_ruler = await manager.get_user_ruler(target_user.id)
    #     new_reputation = int(target_ruler.get("reputation", 0) + 1)

    #     await manager.update_user_ruler(
    #         target_user.id,
    #         target_ruler.get("warnings", 0),
    #         new_reputation,
    #         target_ruler.get("last_time_reputation", 0),
    #     )

    #     # Обновление кулдауна отправителя
    #     await manager.update_user_ruler(
    #         user_id,
    #         author_ruler.get("warnings", 0),
    #         author_ruler.get("reputation", 0),
    #         current_time,
    #     )

    #     await safe_reply(
    #         message,
    #         f"{message.author.mention} ʙыдᴀᴧ ᴩᴇᴨуᴛᴀцию {target_user.mention}!"
    #         " <:reputationemoji:1517480379286556832>",
    #         delete_after=60,
    #     )
    #     return

    # else:
    #     await safe_reply(
    #         message,
    #         "<:forbiddenemoji:1515780232404144279> Укажите пользователя! Пример:"
    #         " `+rep @User`",
    #         delete_after=5,
    #     )
    #     await safe_delete(message, delay=2)
    #     return

    # 3. СИСТЕМА LEVEL UP (с защитой от фарма)
    # Выдаем опыт только если с момента прошлого сообщения прошло больше 60 секунд
    last_xp_time = XP_COOLDOWNS.get(user_id, 0)

    if current_time - last_xp_time >= 30:
        XP_COOLDOWNS[user_id] = current_time

        data = await manager.get_user_data(user_id)

        current_xp = int(data.get("xp", 0) + random.randint(15, 25))
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
            await safe_send(
                message.channel,
                f"<:congrantemoji:1517514349965475954> {message.author.mention}, ʙы"
                f" доᴄᴛиᴦᴧи **{current_level}** уᴩоʙня!",
                delete_after=10,
            )

        # Выдача новой роли и замена старой (при наличии)
        if current_level in BotConfig.LEVEL_ROLES:
            target_role_id = BotConfig.LEVEL_ROLES[current_level]
            new_role = message.guild.get_role(target_role_id)

            if new_role:
                current_role = new_role.name
                try:
                    # Снимаем старые роли за уровни, чтобы не забивать профиль
                    roles_to_remove = [
                        message.guild.get_role(r_id)
                        for lvl, r_id in BotConfig.LEVEL_ROLES.items()
                        if lvl < current_level and message.guild.get_role(r_id)
                    ]
                    roles_to_remove = [
                        r for r in roles_to_remove if r and r in message.author.roles
                    ]

                    if roles_to_remove:
                        await message.author.remove_roles(*roles_to_remove)

                        # Выдаем новую
                        await message.author.add_roles(new_role)
                except discord.Forbidden:
                    print(
                        "❌ Ошибка: Недостаточно прав для управления ролями"
                        f" {message.author.name}"
                    )
                except discord.HTTPException as e:
                    print(f"❌ Ошибка HTTP при управлении ролями: {e}")

        await manager.update_user_data(
            user_id, current_xp, current_level, current_role
        )

    # Не забудьте пробросить обработку команд, если в боте используются префиксные команды
    await bot.process_commands(message)

@bot.event
async def on_member_remove(member: discord.Member):
    if member.bot:
        return

    quarantine_role_id = BotConfig.ROLES.get("quarantine")

    # Фильтруем роли: исключаем @everyone и роль карантина
    current_roles = [
        role.id
        for role in member.roles
        if role.name != "@everyone" and role.id != quarantine_role_id
    ]

    try:
        await manager.update_user_roles_ruler(member.id, current_roles)
    except Exception as e:
        print(f"❌ Ошибка сохранения ролей для {member.id}: {e}")

# ========== ЛОГИРОВАНИЕ СОБЫТИЙ ==========

@bot.event
async def on_raw_message_delete(payload: discord.RawMessageDeleteEvent):
    # Игнорируем ЛС
    if not payload.guild_id:
        return

    # Пропускаем, если удалено самим ботом
    if payload.message_id in BotConfig.deleted_by_bot:
        BotConfig.deleted_by_bot.discard(payload.message_id)
        return

    # Находим глобальный канал логирования
    log_channel_id = BotConfig.CHANNELS.get('mod_logs')
    log_channel = bot.get_channel(log_channel_id)
    if not log_channel:
        try:
            log_channel = await bot.fetch_channel(log_channel_id)
        except Exception:
            return

    message = payload.cached_message

    # === ВОТ ЭТОТ БЛОК: Если сообщения НЕТ в кэше бота ===
    if not message:
        # Пытаемся определить текстовый канал, где произошло удаление
        channel_mention = f"<#{payload.channel_id}>"
        
        embed = discord.Embed(
            title="<:binemoji:1525176536607752202> 𝐃𝐄𝐋𝐄𝐓𝐄𝐃 (Вне кэша)",
            description=(
                f"Было удалено старое сообщение, которого не оказалось в памяти бота.\n"
                f"`ᴋᴀнᴀᴧ:` {channel_mention}\n"
                f"`ID сообщения:` `{payload.message_id}`\n\n"
                f"*Содержимое и автор неизвестны, так как сообщение отправлено до запуска бота или стерлось из памяти.*"
            ),
            color=discord.Color.dark_red(),
            timestamp=datetime.now(timezone.utc)
        )
        
        try:
            await safe_send(log_channel, embed=embed)
        except Exception as e:
            print(f"Ошибка при отправке лога удаления вне кэша: {e}")
        return
    # =====================================================

    # ДАЛЬШЕ ИДЕТ ВАШ СТАНДАРТНЫЙ КОД (когда сообщение НАЙДЕНО в кэше)
    if message.author.bot or (not message.content and not message.attachments):
        return

    author = message.author
    user_avatar = author.display_avatar.url if author.display_avatar else None

    embed = discord.Embed(
        title="<:binemoji:1525176536607752202> 𝐃𝐄𝐋𝐄𝐓𝐄𝐃",
        description=f"`ᴀʙᴛоᴩ:` {author.mention}\n`ᴋᴀнᴀᴧ:` {message.channel.mention}",
        color=discord.Color.red(),
        timestamp=datetime.now(timezone.utc)
    )

    if message.content:
        safe_content = message.content.replace("```", "`\u200b`\u200b`")
        content = safe_content[:1000] + ('...' if len(safe_content) > 1000 else '')
        embed.add_field(name="`ᴄодᴇᴩжᴀниᴇ:`", value=f'```{content}```', inline=False)

    if message.attachments:
        attachment_texts = []
        for att in message.attachments[:10]:
            content_type = att.content_type or ''
            icon = "🖼️" if content_type.startswith('image/') else "🎬" if content_type.startswith('video/') else "🎵" if content_type.startswith('audio/') else "📎"
            size_kb = att.size / 1024
            size_str = f"{size_kb / 1024:.1f} MB" if size_kb > 1024 else f"{size_kb:.1f} KB"
            attachment_texts.append(f"{icon} [{att.filename}]({att.url}) ({size_str})")

        if len(message.attachments) > 10:
            attachment_texts.append(f"... и еще {len(message.attachments) - 10} файлов")

        attachments_text = '\n'.join(attachment_texts)
        if len(attachments_text) > 1024:
            attachments_text = attachments_text[:1021] + "..."
        embed.add_field(name=f"📎 Вложения ({len(message.attachments)})", value=attachments_text, inline=False)

    if user_avatar:
        embed.set_footer(text=author.display_name, icon_url=user_avatar)
    else:
        embed.set_footer(text=author.display_name)

    try:
        await safe_send(log_channel, embed=embed)
    except Exception as e:
        print(f"Ошибка при отправке лога удаления: {e}")


@bot.event
async def on_raw_message_edit(payload: discord.RawMessageUpdateEvent):
    # Игнорируем личные сообщения
    if not payload.guild_id:
        return

    # ГЛОБАЛЬНЫЙ ПОИСК КАНАЛА (для межсерверной отправки)
    log_channel_id = BotConfig.CHANNELS.get('mod_logs')
    log_channel = bot.get_channel(log_channel_id)
    if not log_channel:
        try:
            log_channel = await bot.fetch_channel(log_channel_id)
        except Exception:
            return

    # Получаем обновленное (новое) сообщение из канала
    try:
        channel = bot.get_channel(payload.channel_id) or await bot.fetch_channel(payload.channel_id)
        if not channel:
            return
        after = await channel.fetch_message(payload.message_id)
    except Exception:
        # Если сообщение не удалось получить (например, оно уже удалено)
        return

    # Игнорируем сообщения ботов
    if after.author.bot:
        return

    before = payload.cached_message

    # === БЛОК: Если старого сообщения НЕТ в кэше бота ===
    if not before:
        author = after.author
        user_avatar = author.display_avatar.url if author.display_avatar else None

        embed = discord.Embed(
            title="<:pencilemoji:1525177241749950464> 𝐑𝐄𝐃𝐀𝐂𝐓𝐄𝐃 (Вне кэша)",
            description=(
                f"Было изменено старое сообщение, оригинальный текст которого не сохранен.\n"
                f"`ᴀʙᴛоᴩ:` {author.mention}\n"
                f"`ᴋᴀнᴀᴧ:` {channel.mention}\n"
                f"[Перейти к сообщению]({after.jump_url})"
            ),
            color=discord.Color.dark_orange(),
            timestamp=datetime.now(timezone.utc)
        )

        def format_content(content):
            if not content:
                return "*Пусто*"
            safe_text = content.replace("```", "`\u200b`\u200b`")
            return safe_text[:400] + ("..." if len(safe_text) > 400 else "")

        # Показываем только то, каким сообщение СТАЛО
        embed.add_field(
            name="`ᴄᴛᴀᴧо:`",
            value=f"```{format_content(after.content)}```",
            inline=False,
        )

        if after.attachments:
            embed.add_field(
                name="📎 Вложения",
                value=f"Содержит {len(after.attachments)} файл(ов)",
                inline=False
            )

        if user_avatar:
            embed.set_footer(text=author.display_name, icon_url=user_avatar)
        else:
            embed.set_footer(text=author.display_name)

        try:
            await safe_send(log_channel, embed=embed)
        except Exception as e:
            print(f"Ошибка при отправке лога редактирования вне кэша: {e}")
        return
    # =====================================================

    # ДАЛЬШЕ ИДЕТ ВАШ СТАНДАРТНЫЙ КОД (когда сообщение НАЙДЕНО в кэше)
    
    # 1. Если текст и вложения не изменились (например, подгрузился превью ссылки)
    if (
        before.content == after.content
        and before.attachments == after.attachments
    ):
        return

    # 2. Проверка на незначительные изменения текста
    if before.content and after.content:
        similarity = difflib.SequenceMatcher(
            None, before.content, after.content
        ).ratio()

        char_difference = abs(len(before.content) - len(after.content))

        if similarity >= 0.75 and char_difference <= 3:
            return

    author = before.author
    user_avatar = author.display_avatar.url if author.display_avatar else None

    # Формируем базовый Embed (оригинальное оформление)
    embed = discord.Embed(
        title="<:pencilemoji:1525177241749950464> 𝐑𝐄𝐃𝐀𝐂𝐓𝐄𝐃",
        description=(
            f"`ᴀʙᴛоᴩ:` {author.mention}\n`ᴋᴀнᴀᴧ:`"
            f" {before.channel.mention}\n[Перейти к сообщению]({after.jump_url})"
        ),
        color=discord.Color.orange(),
        timestamp=datetime.now(timezone.utc),
    )

    def format_content(content):
        if not content:
            return "*Пусто*"
        safe_text = content.replace("```", "`\u200b`\u200b`")
        return safe_text[:400] + ("..." if len(safe_text) > 400 else "")

    # Добавляем текстовые поля, только если текст изменился
    if before.content != after.content:
        embed.add_field(
            name="`быᴧо:`",
            value=f"```{format_content(before.content)}```",
            inline=False,
        )
        embed.add_field(
            name="`ᴄᴛᴀᴧо:`",
            value=f"```{format_content(after.content)}```",
            inline=False,
        )

    # Логика проверки изменений во вложениях
    before_count = len(before.attachments)
    after_count = len(after.attachments)

    if before_count != after_count:
        embed.add_field(
            name="📎 Вложения изменены",
            value=(
                f"`быᴧо:` {before_count} файлов\n`ᴄᴛᴀᴧо:` {after_count} файлов"
            ),
            inline=False,
        )
    elif before_count > 0:
        before_names = {att.filename for att in before.attachments}
        after_names = {att.filename for att in after.attachments}
        if before_names != after_names:
            embed.add_field(
                name="📎 Вложения изменены",
                value="**Имена файлов изменились**",
                inline=False,
            )

    if user_avatar:
        embed.set_footer(text=author.display_name, icon_url=user_avatar)
    else:
        embed.set_footer(text=author.display_name)

    try:
        await safe_send(log_channel, embed=embed)
    except Exception as e:
        print(f"Ошибка при отправке лога редактирования: {e}")

# ========== ОБРАБОТКА ОШИБОК ==========

@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    # 1. Извлекаем исходную ошибку, если она обернута во внутренний класс библиотеки
    if isinstance(error, app_commands.CommandInvokeError):
        error = error.original

    # 2. Игнорируем ненайденные команды (обычно это временная рассинхронизация Discord)
    if isinstance(error, app_commands.errors.CommandNotFound):
        return

    # 3. Обработка ошибок прав доступа и проверок
    if isinstance(error, app_commands.errors.CheckFailure):
        await safe_send(interaction, 
            "<:forbiddenemoji:1515780232404144279> у ʙᴀᴄ нᴇᴛ доᴄᴛуᴨᴀ ᴋ ϶ᴛой ᴋоʍᴀндᴇ!",
            ephemeral=True
        )
        return

    if isinstance(error, app_commands.errors.MissingAnyRole):
        roles = [f"<@&{role_id}>" for role_id in error.missing_roles]
        await safe_send(interaction, 
            f"<:forbiddenemoji:1515780232404144279> у ʙᴀᴄ нᴇᴛ нᴇобходиʍых ᴩоᴧᴇй!\n"
            f"Требуются: {', '.join(roles)}",
            ephemeral=True
        )
        return

    if isinstance(error, app_commands.errors.MissingRole):
        await safe_send(interaction, 
            f"<:forbiddenemoji:1515780232404144279> у ʙᴀᴄ нᴇᴛ ᴩоᴧи <@&{error.missing_role}>!",
            ephemeral=True
        )
        return

    if isinstance(error, app_commands.errors.CommandOnCooldown):
        await safe_send(interaction, 
            f"⏰ Подождите {error.retry_after:.1f} ᴄᴇᴋунд ᴨᴇᴩᴇд ᴨоʙᴛоᴩныʍ иᴄᴨоᴧьзоʙᴀниᴇʍ!",
            ephemeral=True
        )
        return

    # Вспомогательная функция для красивого форматирования названий прав
    def format_permissions(permissions):
        return ", ".join(f"`{perm.replace('_', ' ').title()}`" for perm in permissions)

    if isinstance(error, app_commands.errors.BotMissingPermissions):
        await safe_send(interaction, 
            f"<:forbiddenemoji:1515780232404144279> у боᴛᴀ нᴇдоᴄᴛᴀᴛочно ᴨᴩᴀʙ!\n"
            f"Нужны: {format_permissions(error.missing_permissions)}",
            ephemeral=True
        )
        return

    if isinstance(error, app_commands.errors.MissingPermissions):
        await safe_send(interaction, 
            f"<:forbiddenemoji:1515780232404144279> у ʙᴀᴄ нᴇдоᴄᴛᴀᴛочно ᴨᴩᴀʙ!\n"
            f"Нужны: {format_permissions(error.missing_permissions)}",
            ephemeral=True
        )
        return

    if isinstance(error, app_commands.errors.TransformerError):
        await safe_send(interaction, 
            f"<:forbiddenemoji:1515780232404144279> нᴇʙᴇᴩный ɸоᴩʍᴀᴛ ᴀᴩᴦуʍᴇнᴛᴀ: `{error.value}`",
            ephemeral=True
        )
        return

    # 4. Обработка ошибок сети и структуры Discord API
    if isinstance(error, discord.NotFound):
        await safe_send(interaction, 
            "<:forbiddenemoji:1515780232404144279> учᴀᴄᴛниᴋ иᴧи ᴩᴇᴄуᴩᴄ нᴇ нᴀйдᴇны!",
            ephemeral=True
        )
        return

    if isinstance(error, discord.Forbidden):
        await safe_send(interaction, 
            "<:forbiddenemoji:1515780232404144279> у боᴛᴀ нᴇᴛ ᴨᴩᴀʙ дᴧя ʙыᴨоᴧнᴇния ϶ᴛоᴦо дᴇйᴄᴛʙия!",
            ephemeral=True
        )
        return

    if isinstance(error, discord.HTTPException):
        if error.status == 429:
            await safe_send(interaction, 
                "⏰ ᴄᴧиɯᴋоʍ ʍноᴦо зᴀᴨᴩоᴄоʙ! ᴨодождиᴛᴇ нᴇʍноᴦо.",
                ephemeral=True
            )
        else:
            await safe_send(interaction, 
                f"<:forbiddenemoji:1515780232404144279> оɯибᴋᴀ ᴄоᴇдинᴇния: {error.status}",
                ephemeral=True
            )
        return

    # ==================== ОБРАБОТКА НЕИЗВЕСТНОЙ ОШИБКИ ====================
    cmd_name = interaction.command.name if interaction.command else "Неизвестно"
    
    # Выводим в локальную консоль подробности с трассировкой
    print(f"⚠️ Неизвестная ошибка в slash-команде '{cmd_name}':")
    traceback.print_exception(type(error), error, error.__traceback__)

    # Отправляем лог-запись в специальный канал
    log_channel = await safe_fetch_channel(bot, BotConfig.CHANNELS['mod_logs_commands'])
    if log_channel:
        try:
            error_details = str(error)[:1000]
            
            embed = discord.Embed(
                title="❌ Ошибка slash-команды",
                description=(
                    f"**Команда:** `{cmd_name}`\n"
                    f"**Пользователь:** {interaction.user.mention} (ID: {interaction.user.id})\n"
                    f"**Канал:** {interaction.channel.mention if interaction.channel else 'Неизвестно'}\n"
                    f"**Тип ошибки:** `{type(error).__name__}`"
                ),
                color=discord.Color.red(),
                timestamp=datetime.now(timezone.utc)
            )
            embed.add_field(name="Детали ошибки", value=f"```py\n{error_details}```", inline=False)
            embed.set_footer(text=f"ID пользователя: {interaction.user.id}")
            
            await safe_send(log_channel, embed=embed)
        except Exception as log_err:
            print(f"❌ Ошибка отправки лога в канал: {log_err}")

    # Мягкое уведомление пользователя
    try:
        await safe_send(interaction, 
            "⚠️ Произошла неизвестная ошибка. Разработчик уже уведомлён.",
            ephemeral=True
        )
    except Exception:
        pass

# ========== ЗАПУСК КОГОВ БОТА ==========

class MyBot(commands.Bot):
    def __init__(self):
        # Включаем все необходимые интенты
        intents = discord.Intents.all()
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        # 1. Загружаем наш Ког защиты сервера
        # Бот автоматически найдет внутри него все команды с @app_commands.command
        try:
            await self.add_cog(ServerProtection(bot))
            print("✅ ServerProtection загружен")
        except Exception as e:
            print(f"❌ Ошибка загрузки ServerProtection: {e}")
        try:
            await self.add_cog(ModerationCommands(bot))
            print("✅ ModerationCommands загружен")
        except Exception as e:
            print(f"❌ Ошибка загрузки ModerationCommands: {e}")
        try:
            await self.add_cog(InfoCommands(bot))
            print("✅ InfoCommands загружен")
        except Exception as e:
            print(f"❌ Ошибка загрузки InfoCommands: {e}")
        # try:
        #     await self.add_cog(ProfanityFilter(bot))
        #     print("✅ ProfanityFilter загружен")
        # except Exception as e:
        #     print(f"❌ Ошибка загрузки ProfanityFilter: {e}")
        try:
            await self.add_cog(AntiSpam(bot))
            print("✅ AntiSpam загружен")
        except Exception as e:
            print(f"❌ Ошибка загрузки AntiSpam: {e}")
        try:
            await self.add_cog(RolePermissionDetector(bot))
            print("✅ RolePermissionDetector загружен")
        except Exception as e:
            print(f"❌ Ошибка загрузки RolePermissionDetector: {e}")
        try:
            await self.add_cog(AntiWebhook(bot))
            print("✅ AntiWebhook загружен")
        except Exception as e:
            print(f"❌ Ошибка загрузки AntiWebhook: {e}")
        try:
            await self.add_cog(TempVoice(bot))
            print("✅ TempVoice загружен")
        except Exception as e:
            print(f"❌ Ошибка загрузки TempVoice: {e}")
        try:
            await self.add_cog(VoiceSpamDetector(bot))
            print("✅ VoiceSpamDetector загружен")
        except Exception as e:
            print(f"❌ Ошибка загрузки VoiceSpamDetector: {e}")
        try:
            await self.add_cog(ThreadModeration(bot))
            print("✅ ThreadModeration загружен")
        except Exception as e:
            print(f"❌ Ошибка загрузки ThreadModeration: {e}")
        try:
            await self.add_cog(ReactionAntiSpam(bot))
            print("✅ ReactionAntiSpam загружен")
        except Exception as e:
            print(f"❌ Ошибка загрузки ReactionAntiSpam: {e}")
        try:
            await self.add_cog(ServerStatsCog(bot))
            print("✅ ServerStatsCog загружен")
        except Exception as e:
            print(f"❌ Ошибка загрузки ServerStatsCog: {e}")

        # 2. Мгновенная синхронизация для разработки
        # Слэш-команды, синхронизированные на конкретный сервер, появляются СРАЗУ (за 1 секунду)
        if BotConfig.GUILD_ID:
            guild = discord.Object(id=BotConfig.GUILD_ID)
            
            # Копируем наши глобальные команды из Когов в дерево этого сервера
            self.tree.copy_global_to(guild=guild)
            
            # Синхронизируем дерево конкретного сервера
            synced = await self.tree.sync(guild=guild)
            print(f"⚙️ [Локальная синхронизация] Успешно загружено {len(synced)} команд на сервер {guild.id}.")
        else:
            # Глобальная синхронизация (для продакшена, команды обновляются до 1 часа)
            synced = await self.tree.sync()
            print(f"⚙️ [Глобальная синхронизация] Успешно загружено {len(synced)} глобальных команд.")

commands_func = ModerationFunc(bot)
bot = MyBot()

# ========== ЗАПУСК БОТА ==========

@bot.event
async def on_ready():
    print("=========================================")
    print(f"Бот успешно запущен как: {bot.user.name} (ID: {bot.user.id})")
    
    # 1. Проверяем, какие коги (модули) реально загружены в бота
    loaded_cogs = list(bot.cogs.keys())
    print(f"Загруженные коги/модули ({len(loaded_cogs)} шт): {loaded_cogs}")
    if not loaded_cogs:
        print("⚠️ ВНИМАНИЕ: Ни один ког/модуль не загружен! Проверьте пути к папке cogs.")
    
    print("\nПроверка каналов из config.py:")
    for channel_name, channel_id in BotConfig.CHANNELS.items():
        channel = bot.get_channel(channel_id)
        if channel:
            print(f"✅ Канал [{channel_name}] (ID: {channel_id}) успешно найден на сервере: '{channel.guild.name}'")
        else:
            print(f"❌ Канал [{channel_name}] (ID: {channel_id}) НЕ найден! Бот не сможет отправить туда логи.")
            
    # 3. Проверяем статус интентов (Intents)
    print("\nСтатус Интентов:")
    print(f"• Message Content (Текст сообщений): {bot.intents.message_content}")
    print(f"• Members (Участники сервера): {bot.intents.members}")
    print("=========================================")

# Запуск бота
if __name__ == "__main__":
    TOKEN = os.getenv('BOT_TOKEN_RULER')
    manager = DB_Manager(BotConfig.DB_PATH)
    if TOKEN:
        bot.run(TOKEN)
    else:
        print("❌ Токен не найден! Создайте .env файл с BOT_TOKEN")
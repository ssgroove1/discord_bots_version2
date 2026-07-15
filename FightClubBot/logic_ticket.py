import discord, os, asyncio
from pathlib import Path
from config import BotConfig
from safe_commands import *

PANEL_CONFIGS = {}
BASE_DIR = Path(__file__).parent
# --- 1. Кнопка управления внутри созданного чата тикета ---
class CloseTicketView(discord.ui.View):

    def __init__(self, member):
        super().__init__(timeout=None)
        self.member = member

    @discord.ui.button(
        label="зᴀᴋᴩыᴛь ᴛиᴋᴇᴛ",
        style=discord.ButtonStyle.danger,
        custom_id="close_ticket_btn",
    )
    async def close_channel(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        # Безопасное получение ролей модерации
        second_order = getattr(BotConfig, "SUPPORT_ROLES", {}).get(
            "second_order", []
        )
        third_order = getattr(BotConfig, "SUPPORT_ROLES", {}).get("third_order", [])
        support_roles = second_order + third_order

        is_support = any(
            role.id in support_roles for role in interaction.user.roles
        )
        is_admin = interaction.user.guild_permissions.administrator

        if not is_admin and not is_support:
            await safe_send(
                interaction,
                "<:warningemoji:1515756604178305054> У вас нет прав для закрытия"
                " этого тикета.",
                ephemeral=True,
            )
            return

        await interaction.response.defer()
        try:
            dm_embed = discord.Embed(
                title="<:pencilemoji:1525177241749950464> ʙᴀɯ ᴛиᴋᴇᴛ быᴧ зᴀᴋᴩыᴛ",
                description=f"ʙᴀɯ ᴛиᴋᴇᴛ нᴀ ᴄᴇᴩʙᴇᴩᴇ **{interaction.guild.name}** быᴧ зᴀᴋᴩыᴛ.\nᴨожᴀᴧуйᴄᴛᴀ, оцᴇниᴛᴇ ᴩᴀбоᴛу нᴀɯᴇй ᴨоддᴇᴩжᴋи!",
                color=discord.Color.blue()
            )
            await self.member.send(embed=dm_embed, view=RatingView(member=self.member))
        except discord.Forbidden:
            # У пользователя закрыты ЛС
            print(f"Не удалось отправить отзыв в ЛС пользователю {self.member.name}")

        # Деактивируем кнопки для предотвращения спама
        self.clear_items()
        await safe_edit(interaction, view=self)

        await safe_send(
            interaction,
            "<:warningemoji:1515756604178305054> **ᴛиᴋᴇᴛ зᴀᴋᴩыᴛ"
            " ᴀдʍиниᴄᴛᴩᴀциᴇй.**\n<:forbiddenemoji:1515780232404144279> ϶ᴛоᴛ ᴋᴀнᴀᴧ"
            " будᴇᴛ ᴨоᴧноᴄᴛью удᴀᴧᴇн чᴇᴩᴇз **1 ʍинуᴛу**.",
        )

        channel = interaction.channel
        asyncio.create_task(self.delete_channel_after_delay(channel))

    async def delete_channel_after_delay(self, channel: discord.TextChannel):
        await asyncio.sleep(60)
        if channel:
            try:
                await channel.delete(
                    reason="Тикет закрыт и удален по истечении 1 минуты."
                )
                print(f"✅ Канал {channel.name} удален")
            except discord.NotFound:
                print("⚠️ Канал уже был удален")
            except discord.Forbidden:
                print("❌ Нет прав для удаления канала")
            except Exception as e:
                print(f"❌ Ошибка при удалении канала: {e}")

# --- 1. Выпадающее меню выбора категории ---
class TicketCategorySelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(
                label="жᴀᴧобᴀ нᴀ иᴦᴩоᴋᴀ", 
                description="Нарушение правил сервера или чата", 
                emoji="<:warnemoji:1515687856549658774>", 
                value="report"
            ),
            discord.SelectOption(
                label="ᴛᴇхничᴇᴄᴋᴀя ᴨоддᴇᴩжᴋᴀ", 
                description="Ошибки, баги или проблемы с ботами", 
                emoji="<:techicalemoji:1515678259767939262>", 
                value="tech"
            ),
            discord.SelectOption(
                label="ʙоᴨᴩоᴄы ᴋ ᴀдʍиниᴄᴛᴩᴀции", 
                description="Вопросы, уточнения к администрации", 
                emoji="<:smileemoji:1526114626557706252>", 
                value="question"
            ),
            discord.SelectOption(
                label="ᴨᴩᴇдᴧожиᴛь идᴇю", 
                description="Идеи, предложения к ботам/серверу", 
                emoji="<:pencilemoji:1525177241749950464>", 
                value="idea"
            ),
        ]
        super().__init__(
            placeholder="Выберите категорию обращения...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="ticket_category_select"
        )

    async def callback(self, interaction: discord.Interaction):
        selected_category = self.values[0]

        # Определяем вопросы в зависимости от выбранной категории
        if selected_category == "report":
            fields = ["Юзернейм нарушителя", "Опишите ситуацию", "Ссылка на доказательства (скрин/видео)"]
            title = "жᴀᴧобᴀ нᴀ ᴨоᴧьзоʙᴀᴛᴇᴧя"
        elif selected_category == "tech":
            fields = ["Ваш юзернейм", "Описание бага/проблемы", "Где и когда это произошло"]
            title = "ᴛᴇхничᴇᴄᴋᴀя ᴨᴩобᴧᴇʍᴀ"
        elif selected_category == "question":
            fields = ["Ваш юзернейм", "Какой вопрос вас тревожит", "Есть ли пути решения вопроса"]
            title = "ʙоᴨᴩоᴄ ᴋ ᴀдʍиниᴄᴛᴩᴀции"
        elif selected_category == "idea":
            fields = ["Ваш юзернейм", "Смысл идеи", "Как можно реализовать"]
            title = "ᴄᴛоящᴀя идᴇя"
        else:
            await safe_send(interaction, "Неизвестная категория.", ephemeral=True)
            return

        # Открываем модальное окно с соответствующими вопросами
        await interaction.response.send_modal(
            DynamicUserModal(title=title, fields_list=fields, category_type=selected_category)
        )

# --- 2. View для панели тикетов с меню ---
class TicketPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        # Добавляем выпадающее меню в View
        self.add_item(TicketCategorySelect())

class FeedbackModal(discord.ui.Modal, title="Отзыв о работе поддержки"):

    def __init__(self, member, rating: int):
        super().__init__()
        self.member = member
        self.rating = rating

        self.comment = discord.ui.TextInput(
            label="Ваш комментарий (опционально)",
            placeholder="Что вам понравилось или что стоит улучшить?",
            style=discord.TextStyle.paragraph,
            required=False,
            max_length=150,
        )
        self.add_item(self.comment)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        # Канал, куда отправляются отзывы
        FEEDBACK_LOG_CHANNEL_ID = BotConfig.CHANNELS.get("feedback")

        channel = None
        if FEEDBACK_LOG_CHANNEL_ID:
            channel = await safe_fetch_channel(
                interaction.client, FEEDBACK_LOG_CHANNEL_ID
            )

        stars = "<:smileemoji:1526114626557706252>" * self.rating
        embed = discord.Embed(
            title="<:verifiedemoji:1525207492928213204> оᴛзыʙ ᴨо ᴛиᴋᴇᴛу",
            color=discord.Color.brand_green() if self.rating >= 3 else discord.Color.red(),
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(
            name="`оᴛзыʙ:`",
            value=self.comment.value if self.comment.value else "*Без комментария*",
            inline=False,
        )
        embed.add_field(
            name="`оцᴇнᴋᴀ:`", value=f"{stars} ({self.rating}/5)", inline=False
        )
        embed.add_field(
            name="`зᴀᴋᴩыᴧ ᴛиᴋᴇᴛ:`",
            value=self.member.mention,
            inline=False,
        )
        embed.set_footer(
            text=interaction.user.display_name, 
            icon_url=interaction.user.display_avatar.url
        )

        if channel:
            await safe_send(channel, embed=embed)

        await safe_send(
            interaction,
            "<:congrantemoji:1517514349965475954> ᴄᴨᴀᴄибо зᴀ ʙᴀɯ оᴛзыʙ! он ᴨоʍожᴇᴛ"
            " нᴀʍ ᴄᴛᴀᴛь ᴧучɯᴇ.",
            ephemeral=True,
        )


class RatingSelect(discord.ui.Select):

    def __init__(self, member):
        self.member = member
        options = [
            discord.SelectOption(
                label="5 — Отлично!",
                emoji="<:successemoji:1515691944460685372>",
                value="5",
                description="Проблема решена быстро и вежливо",
            ),
            discord.SelectOption(
                label="4 — Хорошо",
                emoji="<:coolemoji:1517487042018410577>",
                value="4",
                description="Всё хорошо, но были нюансы",
            ),
            discord.SelectOption(
                label="3 — Нормально",
                emoji="<:smileemoji:1526114626557706252>",
                value="3",
                description="Обычное обслуживание",
            ),
            discord.SelectOption(
                label="2 — Плохо",
                emoji="<:forbbiden2emoji:1517479332866429008>",
                value="2",
                description="Помогли не до конца или долго отвечали",
            ),
            discord.SelectOption(
                label="1 — Ужасно",
                emoji="<:binemoji:1525176536607752202>",
                value="1",
                description="Администратор повел себя некорректно",
            ),
        ]
        super().__init__(
            placeholder="Оцените качество обслуживания...",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        rating = int(self.values[0])
        # 1. Отключаем выпадающий список
        self.disabled = True
        self.placeholder = "Вы уже оставили отзыв!"

        await interaction.response.send_modal(FeedbackModal(member=self.member, rating=rating))
        if interaction.message:
            try:
                await interaction.message.edit(view=self.view)
            except Exception:
                pass

class RatingView(discord.ui.View):

    def __init__(self, member):
        super().__init__(timeout=3600)
        self.member = member
        self.add_item(RatingSelect(self.member))

    async def on_timeout(self):
        # Метод срабатывает автоматически ровно через 1 час
        for item in self.children:
            item.disabled = True
        if isinstance(item, discord.ui.Select):
            item.placeholder = "Время для отзыва истекло."

        if self.message:
            try:
                await self.message.edit(view=self)
            except Exception:
                pass

# --- 2. Модальное окно анкеты для пользователя ---
class DynamicUserModal(discord.ui.Modal):

    def __init__(self, title: str, fields_list: list, category_type: str = "default"):
        super().__init__(title=title[:45])
        self.fields_list = fields_list
        self.category_type = category_type  # Сохраняем тип категории в объект
        self.inputs = []

        for label in fields_list[:4]:
            text_input = discord.ui.TextInput(
                label=label[:45],
                placeholder="Введите ответ...",
                required=True,
                max_length=250,
                style=discord.TextStyle.paragraph if len(label) > 20 else discord.TextStyle.short
            )
            self.add_item(text_input)
            self.inputs.append(text_input)
        self.priority_input = discord.ui.TextInput(
            label="Срочность (Низк. / Сред. / Высок. / Критич.)",
            placeholder="Укажите насколько срочна ваша проблема...",
            required=True,
            max_length=15
        )
        self.add_item(self.priority_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild
        member = interaction.user

        user_priority_text = self.priority_input.value.lower().strip()

        if (
            "крит" in user_priority_text
            or "фатал" in user_priority_text
            or "чрезв" in user_priority_text
            or "insa" in user_priority_text):
            priority_tag = "critical"
            priority_label = "чᴩᴇзʙычᴀйный ᴨᴩиоᴩиᴛᴇᴛ"
            emoji = "<:insaneemoji:1526218299313098752>"
        elif (
            "выс" in user_priority_text
            or "срочн" in user_priority_text
            or "чп" in user_priority_text
            or "high" in user_priority_text):
            priority_tag = "high"
            priority_label = "ʙыᴄоᴋий ᴨᴩиоᴩиᴛᴇᴛ"
            emoji = "<:redalertemoji:1526209446026678413>"
        elif "сред" in user_priority_text or "med" in user_priority_text:
            priority_tag = "medium"
            priority_label = "ᴄᴩᴇдний ᴨᴩиоᴩиᴛᴇᴛ"
            emoji = "<:warningemoji:1515756604178305054>"
        else:
            priority_tag = "low"
            priority_label = "низᴋий ᴨᴩиоᴩиᴛᴇᴛ"
            emoji = "<:smileemoji:1526114626557706252>"

        # Проверка: нет ли у пользователя уже открытого тикета
        channel_name = f"╠ticket-{member.name}".lower().replace(" ", "-")
        existing_channel = discord.utils.get(guild.channels, name=channel_name)
        if existing_channel:
            await safe_send(
                interaction,
                f"У вас уже есть открытый тикет: {existing_channel.mention}",
                ephemeral=True,
            )
            return

        # Настройка оверрайдов прав для приватного канала
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(
                read_messages=False
            ),  # Скрываем от всех
            member: discord.PermissionOverwrite(
                read_messages=True, send_messages=True, read_message_history=True
            ),  # Доступ автору
        }

        # Выдаем доступ ролям тех. поддержки
        raw_support = getattr(BotConfig, "SUPPORT_ROLES", {})
        support_roles = (
            raw_support.get("first_order", [])
            + raw_support.get("second_order", [])
            + raw_support.get("third_order", [])
        )

        for role_id in support_roles:
            role = guild.get_role(role_id)
            if role:
                overwrites[role] = discord.PermissionOverwrite(
                    read_messages=True, send_messages=True, read_message_history=True
                )

        # Получаем категорию для тикетов
        category_id = getattr(BotConfig, "CATEGORIES", {}).get("tickets")
        category = guild.get_channel(category_id) if category_id else None

        # Создаем текстовый канал
        try:
            ticket_channel = await guild.create_text_channel(
                name=channel_name,
                category=category,
                overwrites=overwrites,
                reason=f"Тикет для {member}",
            )
        except Exception as e:
            await safe_send(
                interaction,
                f"Ошибка при создании канала: {e}",
                ephemeral=True,
            )
            return

        # Эмбед с сохраненными стилями
        embed = discord.Embed(
            title=(
                f"{emoji} {self.title}"
            ),
            description=(
                "<:successemoji:1515691944460685372> добᴩо ᴨожᴀᴧоʙᴀᴛь ʙ"
                f" ᴨоддᴇᴩжᴋу, {member.mention}!\n<:techicalemoji:1515678259767939262>"
                " оᴨиɯиᴛᴇ ᴨоᴨодᴩобнᴇᴇ, ᴇᴄᴧи ϶ᴛо нᴇобходиʍо. ᴀдʍиниᴄᴛᴩᴀция"
                " ᴄᴋоᴩо оᴛʙᴇᴛиᴛ ʙᴀʍ."
            ),
            color=discord.Color.darker_grey(),
            timestamp=discord.utils.utcnow(),
        )

        # Заполняем поля анкеты
        for text_input in self.inputs:
            embed.add_field(name=str(text_input.label), value=text_input.value, inline=False)
        embed.add_field(name="Указанный приоритет", value=f"{emoji} {priority_label}", inline=False)
        embed.set_footer(
            text=interaction.user.display_name, 
            icon_url=interaction.user.display_avatar.url
        )
        content_ping = member.mention
        if priority_tag == "high" or priority_tag == "critical":
            admin_roles = BotConfig.SUPPORT_ROLES.get('first_order', [])+BotConfig.SUPPORT_ROLES.get('second_order', [])+BotConfig.SUPPORT_ROLES.get('third_order', [])
            pings = " ".join([f"<@&{r_id}>" for r_id in admin_roles])
            if pings:
                content_ping = f"\n<:warningemoji:1515756604178305054> **ᴄᴩочный ʙызоʙ ᴀдʍиниᴄᴛᴩᴀции:** {pings}"

        # Отправляем первичную анкету в созданный канал
        await safe_send(
            ticket_channel,
            content=f"{content_ping} | ᴀᴅᴍɪɴɪsᴛʀᴀᴛɪᴏɴ",
            embed=embed,
            view=CloseTicketView(member),
        )

        # Ответ пользователю
        await safe_send(
            interaction,
            f"Приватный чат успешно создан: {ticket_channel.mention}",
            ephemeral=True,
        )


# --- 3. Кнопка «Открыть тикет» на главной панели ---
class DynamicUserView(discord.ui.View):

    def __init__(self, custom_id: str):
        super().__init__(timeout=None)

        # Создаем кнопку динамически для правильной установки custom_id
        button = discord.ui.Button(
            label="оᴛᴋᴩыᴛь ᴛиᴋᴇᴛ",
            style=discord.ButtonStyle.green,
            custom_id=custom_id,
        )
        button.callback = self.open_ticket_btn
        self.add_item(button)

    async def open_ticket_btn(self, interaction: discord.Interaction):
        custom_id = interaction.data.get("custom_id")
        fields = PANEL_CONFIGS.get(custom_id)

        if not fields:
            await safe_send(
                interaction,
                "Ошибка: Настройки панели сброшены.",
                ephemeral=True,
            )
            return

        await interaction.response.send_modal(
            DynamicUserModal(title="Заполнение тикета", fields_list=fields)
        )


# --- 4. Конструктор панели для администратора ---
class AdminSetupModal(discord.ui.Modal, title="Конструктор анкеты тикетов"):

    panel_text = discord.ui.TextInput(
        label="Текст над меню в чате",
        style=discord.TextStyle.paragraph,
        max_length=500,
        placeholder="Опишите, для чего создана эта панель поддержки...",
    )

    def __init__(self, channel: discord.TextChannel):
        super().__init__()
        self.channel = channel

    async def on_submit(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="<:warnemoji:1515687856549658774> ᴄоздᴀᴛь обᴩᴀщᴇниᴇ",
            description=self.panel_text.value,
            color=discord.Color.darker_grey(),
        )

        # Отправляем сообщение с выпадающим меню TicketPanelView
        await safe_send(self.channel, embed=embed, view=TicketPanelView())
        await safe_send(
            interaction, "Панель с категориями успешно создана!", ephemeral=True)
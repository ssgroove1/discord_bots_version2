import os
from pathlib import Path
from discord import app_commands

BASE_DIR = Path(__file__).parent
class BotConfig:
    # =============== CHANNELS ===============
    CHANNELS = {
        'commands': 1468672520717865053,
        'mod_commands': 1526631623876022332,
        'radio': 1519803349711454298,
        'welcome': 1417900621155274762,
        'count': 1513576705896222861,
        'mod_logs': 1526548916084936831,
        'mod_logs_commands': 1526548916084936830,
        'warning_logs': 1526553007028830349,
        'tech_logs': 1526888079946944574,
        'emergency_logs': 1526607520519684096,
        'trigger_voice': 1513626188080353442,
        'rules': 1417897315452059689,
        'chat': 1468672223564005649,
        'help': 1513905501191147732,
        'feedback': 1526548916084936828,
    }

    STATS = {
        'total_id': 1526906991295991868,
        'humans_id': 1526907015061045288,
        'bots_id': 1526907031343075418,
    }

    # =============== CATEGORIES ===============
    CATEGORIES = {
        'tickets': 1515760709479174315,
        'temp_voices': 1513626023411978514,
    }

    # =============== ROLES ===============
    ROLES = {
        'muted': 1512893252141973558,
        'count_bad': 1513493354208301166,
        'first_warn': 1512794784216121344,
        'second_warn': 1512794946556530930,
        'third_warn': 1512794981138563072,
        'warnings_category': 1512794679219978270,
        'quarantine': 1526282672261959855,
    }

    # =============== ROLES ON JOIN ===============
    WELCOME_ROLES = {
        'join1': 1417897853149253713,
        'join2': 1513487355489554543,
        'join3': 1514181905422094336,
        'join4': 1525184122266456164,
        'join5': 1525184022899065023,
    }

    # =============== LEVEL_ROLES ===============
    LEVEL_ROLES = {
        1: 1517605063013568573,
        5: 1513266642988171304,
        10: 1512913425519345674,
    }

    # =============== SUPPORT_ROLES ===============
    SUPPORT_ROLES = {
        # Первый порядок
        'first_order': [
            1524682657739444254, # Кадет
            1513487279749074994, # Полиция
        ],
        # Второй порядок
        'second_order': [
            1524683578279985152, # Шерифф
            1513487556887449692, # Special Force
            1513487970127183912, # Supervisor
            1524689244818247791, # Overseer
        ],
        # Третий порядок
        'third_order': [
            1515424488014221524, # Tech Admin
            1513261409209811055, # The Watcher
            1513486055603703912, # Manager
            1513271328512147696, # Judge Overseer
            1417895449272258730, # Owner
        ],
    }

    RULE_CHOICES = [
        # Общие правила общения
        app_commands.Choice(name="П. 2.1 — Неуважительное отношение (Мут 60м / Варн)", value="П. 2.1 (Неуважение)"),
        app_commands.Choice(name="П. 2.2 — Оскорбления, травля, буллинг (Мут 120м / Варн)", value="П. 2.2 (Оскорбления)"),
        app_commands.Choice(name="П. 2.3 — Разжигание конфликтов, провокации (Мут 120м / Варн)", value="П. 2.3 (Конфликты)"),
        app_commands.Choice(name="П. 2.4 — Флуд, спам, оффтоп (Мут 60м / Варн)", value="П. 2.4 (Флуд/Спам/Оффтоп)"),
        app_commands.Choice(name="П. 2.5 — Чрезмерный КАПС в чате", value="П. 2.5 (КАПС)"),
        app_commands.Choice(name="П. 2.6 — Использование каналов не по назначению", value="П. 2.6 (Нецелевой канал)"),
        app_commands.Choice(name="П. 2.7 — Неадекватное поведение (Мут 60м / Варн)", value="П. 2.7 (Неадекватность)"),
        app_commands.Choice(name="П. 2.8 — Обсуждение шокирующего контента (Мут 120м)", value="П. 2.8 (Шок-контент в чате)"),
        
        # Контент
        app_commands.Choice(name="П. 3.1 — Запрещённый контент 18+ (Мут 120м / Варн)", value="П. 3.1 (Контент 18+)"),
        app_commands.Choice(name="П. 3.2 — Жестокие материалы / Насилие (Мут 120м + Варн)", value="П. 3.2 (Насилие/Жестокость)"),
        app_commands.Choice(name="П. 3.3 — Вредоносные ссылки или файлы (Мут 60м + Варн)", value="П. 3.3 (Вредоносные ссылки)"),
        app_commands.Choice(name="П. 3.4 — Слив личных данных / Переписок (Мут 60м / Варн)", value="П. 3.4 (Слив данных)"),
        
        # Политика, религия, национальности
        app_commands.Choice(name="П. 4.1 — Политические провокации / Агитация (Мут 120м / Варн)", value="П. 4.1 (Политика)"),
        app_commands.Choice(name="П. 4.2 — Дискриминация, нацизм, расизм (Мут 120м + Варн)", value="П. 4.2 (Дискриминация)"),
        app_commands.Choice(name="П. 4.3 — Оскорбления по нац. или рел. признаку (Мут 60м)", value="П. 4.3 (Нац/Рел оскорбления)"),
        app_commands.Choice(name="П. 4.5 — Разжигание ненависти и вражды (Мут 60м + Варн)", value="П. 4.5 (Разжигание вражды)"),
        app_commands.Choice(name="П. 4.6 — Призывы к насилию, экстремизму (Мут 120м / Варн)", value="П. 4.6 (Призывы к насилию)"),
        
        # Голосовые каналы
        app_commands.Choice(name="П. 5.1 — Помехи общению, крики, перебивание (Мут 30-60м)", value="П. 5.1 (Помехи в voice)"),
        app_commands.Choice(name="П. 5.2 — Громкие звуки, музыка без согласия (Мут 60м)", value="П. 5.2 (Шум в voice)"),
        app_commands.Choice(name="П. 5.3 — Нарушение личных границ в voice (Мут 120м / Варн)", value="П. 5.3 (Личные границы)"),
        app_commands.Choice(name="П. 5.4 — Обсуждение шокирующих сцен в voice (Мут 120м)", value="П. 5.4 (Шок-контент в voice)"),
        
        # Реклама и Администрация
        app_commands.Choice(name="П. 6.1 — Реклама проектов без разрешения", value="П. 6.1 (Реклама)"),
        app_commands.Choice(name="П. 6.2 — Массовая рассылка (Спам в ЛС / Резерв бана)", value="П. 6.2 (Массовая рассылка)"),
        app_commands.Choice(name="П. 7.2 — Попытка обмана администрации / саппорта", value="П. 7.2 (Обман администрации)"),
    ]

    # =============== PATH ===============
    FONT_PATH = str(BASE_DIR / "FightClubBot" / "UNCAGE-Regular.ttf")

    # =============== DB PATH ===============
    DB_PATH = str(BASE_DIR / "database" / "database.db")
    
    # =============== VARIABLES ===============
    GUILD_ID = 1417892629152010281
    DEVELOPER_ID = 777122004376879115
    COMMAND_PREFIX = '/'
    deleted_by_bot = set()
    trusted_bots = {
        1515369279724195891, # The Economic
        1513553810369417216, # The Fun Bot
        1512556017492295851, # The Ruler
        302050872383242240, # DISBOARD
        575776004233232386, # DSMonitoring
        315926021457051650, # Server Monitoring
    }

    # =============== PATTERNS ===============
    allowed_domains = ['youtube.com', 'youtu.be', 'twitch.tv', 'github.com', '.gif', 'tenor.com/view',
                        'giphy.com/gifs', 'klipy.com/gifs', 'gifs.', 'roblox.com/users/', 'steamcommunity.com/profiles/',
                        'cdn.discordapp.com/attachments/', 'media.discordapp.net/attachments/', 'tiktok.com', 'vt.tiktok.com', 'vm.tiktok.com',]

    # =============== ЗАПРЕЩЕННЫЕ КОМАНДЫ КОПИРОВАНИЯ ===============
    blocked = [
        r'discord\.gg/',
        r'discord\.com/invite/',
        r'discordapp\.com/invite/',
        r'discord\.me/',
        r'dis\.gd/',
        r'discord\.io/',
        r'discord\.li/',
        r'invite\.gg/',
        r'discordservers\.com/',
        
        # Команды экспорта (только в начале строки или с пробелом)
        r'(^|\s)!export',
        r'(^|\s)/export',
        r'(^|\s)!backup',
        r'(^|\s)/backup',
        r'(^|\s)!dump',
        r'(^|\s)/dump',
        r'(^|\s)!save',
        r'(^|\s)/save',
        r'(^|\s)!copy',
        r'(^|\s)/copy',
        r'(^|\s)!clone',
        r'(^|\s)/clone',
        r'(^|\s)!sync',
        r'(^|\s)/sync',
        r'(^|\s)!download',
        r'(^|\s)/download',
        
        # Токены и ключи (только как отдельные слова)
        r'\btoken\b',
        r'\bтокен\b',
        r'\bsecret\b',
        r'\bсекрет\b',
        r'\bkey\b',
        r'\bключ\b',
        r'\bapi_key\b',
        r'\bapikey\b',
        r'\bwebhook\b',
        r'\bbot_token\b',
        r'\bclient_secret\b',
        r'\bprivate_key\b',
        r'\bpublic_key\b',
        r'\baccess_token\b',
        r'\brefresh_token\b',
        r'\bauth_token\b',
        r'\bbearer_token\b',
        r'\bjwt_token\b',
        r'\boauth2\b',
        r'\boauth_token\b',
        
        # Кража данных (только в начале строки или с пробелом)
        r'(^|\s)!get_all',
        r'(^|\s)!getmembers',
        r'(^|\s)!getchannels',
        r'(^|\s)!getroles',
        r'(^|\s)!getperms',
        r'(^|\s)!getusers',
        r'(^|\s)!getbots',
        r'(^|\s)!getserver',
        r'(^|\s)!getguild',
        
        # SQL инъекции (только как отдельные слова, с учетом регистра)
        r'\bSELECT\b',
        r'\bINSERT\b',
        r'\bUPDATE\b',
        r'\bDELETE\b',
        r'\bDROP\b',
        r'\bALTER\b',
        r'\bTRUNCATE\b',
        r'\bUNION\b',
        r'\bWHERE\b',
        r'\bFROM\b',
        r'\bJOIN\b',
    ]
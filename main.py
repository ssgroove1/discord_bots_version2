import subprocess, os, sys
from pathlib import Path
from dotenv import load_dotenv

# 1. Определяем корневую папку проекта (там, где лежит main.py)
BASE_DIR = Path(__file__).parent.absolute()
print(f"📁 Корень проекта: {BASE_DIR}")

# 2. Загружаем переменные из shared.env в окружение
env_file = BASE_DIR / 'shared.env'
if env_file.exists():
    print(f"✅ Найден файл .env: {env_file}")
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                key, value = line.split('=', 1)
                os.environ[key] = value
else:
    print(f"❌ Файл .env НЕ НАЙДЕН: {env_file}")

# 3. Проверяем, что токены загружены
print("\n🔍 Проверка токенов:")
for name in ['BOT_TOKEN_RULER', 'BOT_TOKEN_FUNBOT', 'BOT_TOKEN_ECONOMIC']:
    token = os.getenv(name)
    print(f"  {'✅' if token else '❌'} {name}: {'найден' if token else 'НЕ НАЙДЕН!'}")

# 4. Список ботов (папки находятся в корне проекта)
bots = [
    {"path": BASE_DIR / "FightClubBot", "name": "FightClubBot"},
    {"path": BASE_DIR / "FunBot", "name": "FunBot"},
    {"path": BASE_DIR / "TheEconomic", "name": "TheEconomic"},
]

python_executable = sys.executable
print(f"\n🐍 Использую Python: {python_executable}")

processes = []
for bot in bots:
    bot_file = bot["path"] / "bot.py"
    if not bot_file.exists():
        print(f"❌ Файл не найден: {bot_file}")
        continue

    print(f"🚀 Запускаю: {bot['name']} из {bot['path']}")

    # Ключевой момент: передаем переменные окружения дочернему процессу
    env = os.environ.copy()
    process = subprocess.Popen(
        [python_executable, str(bot_file)],
        cwd=str(bot["path"]), # Рабочая папка процесса - папка бота
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1
    )
    processes.append(process)
    print(f"✅ Запущен (PID: {process.pid})")

print(f"\n🎯 Запущено ботов: {len(processes)}")
print("📝 Логи будут выводиться ниже...\n")

# 5. Простой цикл чтения логов
import time
try:
    while True:
        for i, p in enumerate(processes):
            try:
                stdout, stderr = p.communicate(timeout=0.1)
                if stdout:
                    print(f"[Bot{i+1}] {stdout.strip()}")
                if stderr:
                    print(f"[Bot{i+1} ERROR] {stderr.strip()}")
            except subprocess.TimeoutExpired:
                pass
            if p.poll() is not None:
                print(f"⚠️ Bot{i+1} завершился с кодом {p.returncode}")
        time.sleep(0.5)
except KeyboardInterrupt:
    print("\n🛑 Останавливаем ботов...")
    for p in processes:
        p.terminate()
        try:
            p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            p.kill()
    print("✅ Все боты остановлены")
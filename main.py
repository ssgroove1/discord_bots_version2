import subprocess
import os
import sys
import time
import threading
from pathlib import Path

# 1. Определяем корневую папку проекта
BASE_DIR = Path(__file__).parent.absolute()
print(f"📁 Корень проекта: {BASE_DIR}")

# 2. Загружаем переменные из shared.env
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

# 3. Проверяем токены
print("\n🔍 Проверка токенов:")
for name in ['BOT_TOKEN_RULER', 'BOT_TOKEN_FUNBOT', 'BOT_TOKEN_ECONOMIC']:
    token = os.getenv(name)
    print(f"  {'✅' if token else '❌'} {name}: {'найден' if token else 'НЕ НАЙДЕН!'}")

# 4. Список ботов
bots = [
    {"path": BASE_DIR / "FightClubBot", "name": "FightClubBot"},
    {"path": BASE_DIR / "FunBot", "name": "FunBot"},
    {"path": BASE_DIR / "TheEconomic", "name": "TheEconomic"},
]

python_executable = sys.executable
print(f"\n🐍 Использую Python: {python_executable}")

# Функция для чтения вывода процесса
def read_output(process, name):
    try:
        for line in iter(process.stdout.readline, ''):
            if line:
                print(f"[{name}] {line.strip()}")
    except Exception as e:
        print(f"[{name}] Ошибка чтения: {e}")

processes = []
threads = []

for bot in bots:
    bot_file = bot["path"] / "bot.py"
    if not bot_file.exists():
        print(f"❌ Файл не найден: {bot_file}")
        continue

    print(f"🚀 Запускаю: {bot['name']} из {bot['path']}")

    env = os.environ.copy()
    process = subprocess.Popen(
        [python_executable, str(bot_file)],
        cwd=str(bot["path"]),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,  # ← объединяем stderr в stdout
        text=True,
        bufsize=1
    )
    processes.append(process)
    
    # Запускаем поток для чтения вывода
    thread = threading.Thread(target=read_output, args=(process, bot['name']), daemon=True)
    thread.start()
    threads.append(thread)
    
    print(f"✅ {bot['name']} запущен (PID: {process.pid})")

print(f"\n🎯 Запущено ботов: {len(processes)}")
print("📝 Логи будут выводиться ниже...")
print("🛑 Нажмите Ctrl+C для остановки\n")

# Ждём завершения
try:
    while True:
        # Проверяем, не завершились ли процессы
        for i, p in enumerate(processes):
            if p.poll() is not None:
                print(f"⚠️ Bot{i+1} завершился с кодом {p.returncode}")
        time.sleep(1)
except KeyboardInterrupt:
    print("\n🛑 Останавливаем ботов...")
    for p in processes:
        p.terminate()
        try:
            p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            p.kill()
    print("✅ Все боты остановлены")
from pathlib import Path

# 1. Определяем, где сейчас запущен скрипт
current_dir = Path.cwd()
print(f"Текущая рабочая папка: {current_dir}")

# 2. Формируем путь к файлу
file_path = current_dir / "articles" / "ccc.py"
print(f"Ожидаемый путь к файлу: {file_path}")

# 3. Проверяем существование
if not file_path.exists():
    print("❌ Файл не найден!")
    
    # Покажем, что вообще есть в папке articles (если она есть)
    articles_dir = current_dir / "articles"
    if articles_dir.is_dir():
        print(f"Содержимое папки articles: {list(articles_dir.iterdir())}")
    else:
        print("Папки articles тоже нет.")
else:
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
            print("✅ Файл найден, его содержимое:")
            print(content)
    except Exception as e:
        print(f"❌ Произошла ошибка при чтении файла: {e}")

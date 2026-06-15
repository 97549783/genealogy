from pathlib import Path

base_dir = Path(__file__).resolve().parent
file_path = base_dir / "articles" / "ccc.py"

with open(file_path, "r", encoding="utf-8") as f:
    print(f.read())

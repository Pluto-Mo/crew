"""共享位置。环境变量可覆盖。

装到用户电脑上的独立版门口没有脚本目录，所以它在自己的"locations"段里直接定 HOME；
源码版从这里取。
"""
import os
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
PACKAGE = SCRIPTS.parent

SETTINGS = {}
try:
    import json
    override = os.environ.get("STARIXS_HOME")
    if override:
        HOME = Path(override).expanduser()
    elif os.name == "nt":
        HOME = Path(os.environ.get("LOCALAPPDATA") or str(Path.home())) / "starixs"
    else:
        HOME = Path.home() / ".local" / "share" / "starixs"
except Exception:  # 位置算不出来时也不能拦住消息
    HOME = Path.home() / ".local" / "share" / "starixs"

RULES_DIR = PACKAGE / "references" / "rules" if (PACKAGE / "references" / "rules").is_dir() else None
SKILL = PACKAGE / "SKILL.md"
CFG = HOME / "config.json"
ROLES = HOME / "model_roles.json"
USES = HOME / "uses.jsonl"

#!/usr/bin/env python3
"""装门口：把常驻规则钩子装到用户电脑上。

装的是两份东西：
1. 数据目录里一份**明文的独立版 gate.py**，旁边放 gate_rules.json（常驻规则和两条不可逆规则的原文，
   从 references/rules/ 原样抄进去，一个字不改）。钩子每条消息跑它，不经过任何加密运行时，不弹权限。
2. 宿主的钩子接线：
   - Claude Code：往 ~/.claude/settings.json 加两条钩子（每条消息、压缩之后），原文件先备份
   - Codex：在数据目录建一个本地插件市场，插件 starixs-gate 放市场根目录；用户得在 /hooks 里信任一次

默认 dry-run，只打印不写。--apply 才动。--uninstall 撤。

    python3 scripts/gate_install.py                 # 看会做什么
    python3 scripts/gate_install.py --apply         # 装
    python3 scripts/gate_install.py --apply --host codex
    python3 scripts/gate_install.py --uninstall
    python3 scripts/gate_install.py --check         # 只检查
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paths import HOME, RULES_DIR  # noqa: E402
import gate  # noqa: E402

MARK_BEGIN, MARK_END = "# ---- locations: begin", "# ---- locations: end"
STANDALONE = ('HOME = Path(__file__).resolve().parent  # 装在数据目录里：记录、开关、gate_rules.json 都在旁边\n'
              'RULES_DIR = None  # 没有规则目录：常驻规则从 gate_rules.json 读\n')
MARKER = "starixs-gate"
EMBEDDED_RULES = tuple(dict.fromkeys((gate.MOTHER, *gate.IRREVERSIBLE_RULES,
                                      *gate.HOST_RULES.get("codex", ()))))


def package_version() -> str:
    return gate.VERSION


def _stamp(text: str) -> str:
    """独立版里那行版本戳；没有返回空串（老版本装的）。"""
    match = re.search(r'^GATE_PACKAGE_VERSION = "([^"]*)"', text, re.M)
    return match.group(1) if match else ""


def _version_key(version: str) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", version or "")[:4])


def rule_body(name):
    """规则正文，原样。抄进 gate_rules.json 用。"""
    try:
        text = (RULES_DIR / f"{name}.md").read_text(encoding="utf-8")
        _, _, body = text.replace("\r\n", "\n").split("---\n", 2)
        return body.split("\n## ")[0].strip()
    except (OSError, ValueError, AttributeError, TypeError):
        return ""


def standalone_source() -> str:
    """把源码版 gate.py 的 locations 段换成"就在本目录"，并盖上版本戳，得到可独立运行的版本。
    版本戳让更新时能拒绝用旧包把新门换回去。"""
    source = (Path(__file__).resolve().parent / "gate.py").read_text(encoding="utf-8")
    start = source.index(MARK_BEGIN)
    end = source.index(MARK_END) + len(MARK_END)
    stamp = 'GATE_PACKAGE_VERSION = "%s"  # 装的是哪一版的门口：旧包不能把新门换回去\n' % package_version()
    return source[:start] + MARK_BEGIN + "\n" + STANDALONE + stamp + MARK_END + source[end:]


def state_files() -> dict:
    """装到数据目录、独立版门口要读的每一个文件。安装和更新都只从这里拿，
    所以两边写的永远是同一批；门口以后多读一个随包走的文件，加在这里，两边一起有。"""
    return {
        "gate.py": standalone_source(),
        "gate_rules.json": json.dumps({n: rule_body(n) for n in EMBEDDED_RULES},
                                      ensure_ascii=False, indent=1) + "\n",
    }


def refresh_installed(state=None) -> bool:
    """装过门口的电脑：包更新后把门口程序和它要读的文件一起换成这一版的，缺了的补上。

    宿主的钩子和配置不动（那些是用户电脑上别人的文件，不在更新时悄悄改；
    要重装由 --check 说）。没装过的不装。出错不影响取规则，下次再试。
    """
    state = Path(state) if state else HOME
    try:
        gate_path = state / "gate.py"
        if not gate_path.is_file():
            return False
        installed = _version_key(_stamp(gate_path.read_text(encoding="utf-8")))
        if installed > _version_key(package_version()):
            return False  # 别的（更新的）包装的门口，不能被这版换回去
    except (OSError, UnicodeError):
        return False
    changed = False
    for name, text in state_files().items():  # 一个一个来：哪个生成不了或写不进去，不挡别的
        try:
            path = state / name
            try:
                old = path.read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                old = None
            if old != text:
                path.write_text(text, encoding="utf-8")
                changed = True
        except (OSError, UnicodeError, ValueError):
            continue
    return changed


def python_for_hook() -> str:
    """钩子命令里用哪个 python。

    不能用当前进程的解释器：它常常是某个临时 venv（装完就删），钩子会跟着坏。
    优先系统的、稳定的解释器；都没有才退回 PATH 上的 python3。
    """
    if os.name == "nt":
        for candidate in ("py", "python"):
            found = shutil.which(candidate)
            if found:
                return found
        return sys.executable
    for fixed in ("/usr/bin/python3", "/usr/local/bin/python3", "/opt/homebrew/bin/python3"):
        if Path(fixed).is_file():
            return fixed
    for name in ("python3", "python"):
        found = shutil.which(name)
        if found and "venv" not in found and "virtualenv" not in found:
            return found
    return shutil.which("python3") or sys.executable


def claude_settings(home=None):
    home = Path.home() if home is None else Path(home)
    return home / ".claude" / "settings.json"


def claude_hook_block(gate_path: Path):
    command = f'"{python_for_hook()}" "{gate_path}" claude'
    return {
        "UserPromptSubmit": [{"hooks": [{"type": "command", "command": command, "timeout": 10}]}],
        "SessionStart": [{"matcher": "compact",
                          "hooks": [{"type": "command", "command": command, "timeout": 10}]}],
    }


def is_ours(hook) -> bool:
    command = str((hook or {}).get("command") or "")
    return "gate.py" in command and "starixs" in command


def plan(home=None, hosts=None):
    home = Path.home() if home is None else Path(home)
    hosts = hosts or [n for n in gate._HOST_ORDER]
    steps = []
    state = (home / ".local" / "share" / "starixs") if home == Path.home() else home / ".local/share/starixs"
    for name, content in state_files().items():
        steps.append(("write", str(state / name), f"{len(content)} bytes"))
    for tool in hosts:
        if tool == "claude":
            settings = claude_settings(home)
            if not (home / ".claude").is_dir():
                steps.append(("skip", str(settings), "Claude Code not present on this machine"))
                continue
            steps.append(("edit", str(settings), "add two hooks (backup first)"))
        elif tool == "codex":
            if not (home / ".codex").is_dir():
                steps.append(("skip", str(state / MARKER), "Codex not present on this machine"))
                continue
            market = state / "codex-market"
            steps.append(("write", str(market / MARKER / "hooks" / "hooks.json"), "plugin hooks"))
            steps.append(("write", str(market / MARKER / ".codex-plugin" / "plugin.json"), "plugin manifest"))
            steps.append(("write", str(market / ".agents" / "plugins" / "marketplace.json"), "marketplace"))
            steps.append(("run", "codex plugin marketplace add " + str(market), ""))
            steps.append(("run", "codex plugin add %s@%s" % (MARKER, MARKER), ""))
            steps.append(("note", "user action", "trust the plugin once in Codex /hooks"))
    return steps


def current_host():
    """正在跑我们的是哪家宿主。装门只接这一家——在 Codex 里装就不该动 Claude Code 的配置。"""
    return gate.host_by_env()


def apply(home=None, hosts=None, dry=False):
    home = Path.home() if home is None else Path(home)
    state = (home / ".local" / "share" / "starixs") if home == Path.home() else home / ".local/share/starixs"
    if hosts is None:
        here = current_host()
        if not here:
            print("Cannot tell which host is running this. Nothing was wired.")
            print("Pass --host codex or --host claude to say which one.")
            return []
        hosts = [here]
    written = []

    if not dry:
        state.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(state, 0o700)
        except OSError:
            pass
    for name, content in state_files().items():
        target = state / name
        if not dry:
            target.write_text(content, encoding="utf-8")
        written.append(str(target))
        print(("would write " if dry else "wrote ") + str(target))

    gate_path = state / "gate.py"

    for tool in hosts:
        if tool == "claude":
            settings = claude_settings(home)
            if not (home / ".claude").is_dir():
                print("skip Claude Code: not present")
                continue
            data = {}
            if settings.is_file():
                try:
                    data = json.loads(settings.read_text(encoding="utf-8"))
                except ValueError:
                    print("skip Claude Code: settings.json is not valid JSON; fix it first")
                    continue
            data = data if isinstance(data, dict) else {}
            hooks = data.get("hooks")
            hooks = hooks if isinstance(hooks, dict) else {}
            wanted = claude_hook_block(gate_path)
            for event, groups in wanted.items():
                existing = [g for g in (hooks.get(event) or [])
                            if isinstance(g, dict) and not any(is_ours(h) for h in (g.get("hooks") or []))]
                hooks[event] = existing + groups
            data["hooks"] = hooks
            if dry:
                print("would edit " + str(settings) + " (hooks: UserPromptSubmit, SessionStart)")
            else:
                backup = settings.with_name(settings.name + ".starixs-" + time.strftime("%Y%m%d-%H%M%S") + ".bak")
                if settings.is_file():
                    shutil.copy2(settings, backup)
                    print("backed up " + str(backup))
                settings.parent.mkdir(parents=True, exist_ok=True)
                settings.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
                print("wrote " + str(settings))
        elif tool == "codex":
            codex_home = Path(os.environ.get("CODEX_HOME") or (home / ".codex"))
            if not codex_home.is_dir():
                print("skip Codex: not present")
                continue
            files = install_codex(codex_home, state, gate_path, dry=dry)
            written.extend(files)

    return written


def install_codex(codex_home: Path, state: Path, gate_path: Path, dry: bool = False):
    """装 Codex 插件。Codex 不认散放的插件文件：它要一个**本地插件市场**——
    市场根目录下有 .agents/plugins/marketplace.json 列出插件，插件目录在市场根里面，
    然后由 `codex plugin marketplace add` + `codex plugin add` 登记进 config.toml。
    只写文件不登记，Codex 永远看不见，/hooks 里也不会出现。"""
    market = state / "codex-market"          # 市场根
    plugin = market / MARKER                  # 插件目录，必须在市场根里面
    hooks_file = plugin / "hooks" / "hooks.json"
    plugin_file = plugin / ".codex-plugin" / "plugin.json"
    market_file = market / ".agents" / "plugins" / "marketplace.json"
    command = '"%s" "%s" codex' % (python_for_hook(), gate_path)

    hooks_payload = {
        "description": "starixs gate: the standing request with each task message; two rules before a hard-to-undo action.",
        "hooks": {
            "UserPromptSubmit": [{"hooks": [{"type": "command", "command": command,
                                            "commandWindows": command, "timeout": 10}]}],
            "SessionStart": [{"matcher": "^compact$",
                              "hooks": [{"type": "command", "command": command,
                                         "commandWindows": command, "timeout": 10}]}],
        },
    }
    plugin_payload = {
        "name": MARKER,
        "version": package_version(),
        "description": "Runs the starixs gate on each user message and after compaction.",
        "hooks": "./hooks/hooks.json",
        "interface": {"displayName": "starixs gate",
                      "shortDescription": "The standing request with each task message",
                      "developerName": "starixs", "category": "Productivity"},
    }
    market_payload = {
        "name": MARKER,
        "interface": {"displayName": "starixs (local)"},
        "plugins": [{"name": MARKER,
                     "source": {"source": "local", "path": "./" + MARKER},
                     "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
                     "category": "Productivity"}],
    }

    if dry:
        for path in (hooks_file, plugin_file, market_file):
            print("would write " + str(path))
        print("  codex plugin marketplace add %s" % market)
        print("  codex plugin add %s@%s" % (MARKER, MARKER))
        return [str(hooks_file), str(plugin_file), str(market_file)]

    for path, payload in ((hooks_file, hooks_payload), (plugin_file, plugin_payload),
                          (market_file, market_payload)):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("wrote " + str(path))

    register_codex(codex_home, market)
    return [str(hooks_file), str(plugin_file), str(market_file)]


def register_codex(codex_home: Path, market: Path) -> bool:
    """让 Codex 真的登记这个市场和插件。没有这一步，插件文件在硬盘上也没用：
    Codex 只认 config.toml 里 [marketplaces.*] 和 [plugins.*] 的条目。"""
    codex = shutil.which("codex")
    if not codex:
        print("codex CLI not found: plugin files are written but not registered.")
        print("  when Codex is available, run:")
        print("    codex plugin marketplace add %s" % market)
        print("    codex plugin add %s@%s" % (MARKER, MARKER))
        return False
    env = dict(os.environ, CODEX_HOME=str(codex_home))
    ok = True
    for cmd in (["plugin", "marketplace", "add", str(market)],
                ["plugin", "add", "%s@%s" % (MARKER, MARKER)]):
        try:
            r = subprocess.run([codex, *cmd], capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=180, env=env)
        except (OSError, subprocess.SubprocessError) as error:
            print("FAILED: codex %s: %s" % (" ".join(cmd), error))
            ok = False
            continue
        if r.returncode != 0:
            detail = (r.stderr or r.stdout or "").strip()[:300]
            # 重复登记不算失败：已经加过的市场/插件会报错，但状态是对的
            if "already" in detail.lower():
                print("codex: %s already registered" % " ".join(cmd[1:]))
                continue
            print("FAILED: codex %s returned %d: %s" % (" ".join(cmd), r.returncode, detail))
            ok = False
        else:
            print("codex: " + " ".join(cmd))
    if ok:
        print("next: in Codex, open /hooks and trust the starixs gate hooks once")
    return ok


def own_skill_dir():
    """这个脚本所在的那个 skill 目录（scripts/ 的上一层）。不在 skill 里时返回 None。"""
    here = Path(__file__).resolve()
    if here.parent.name != "scripts":
        return None
    folder = here.parent.parent
    return folder if (folder / "SKILL.md").is_file() else None


def uninstall(home=None, purge=False, skill=False):
    """撤掉门：去掉宿主的钩子、删 gate.py 和规则、删 Codex 插件。

    默认保留数据目录——那里是记录和开关，删了不可恢复，而用户说的"卸载"
    通常只是不想再要这个钩子。--purge 才连数据目录一起删。
    """
    home = Path.home() if home is None else Path(home)
    state = (home / ".local" / "share" / "starixs") if home == Path.home() else home / ".local/share/starixs"
    removed = []
    settings = claude_settings(home)
    if settings.is_file():
        try:
            data = json.loads(settings.read_text(encoding="utf-8"))
        except ValueError:
            data = None
        if isinstance(data, dict) and isinstance(data.get("hooks"), dict):
            changed = False
            for event, groups in list(data["hooks"].items()):
                kept = [g for g in (groups or [])
                        if not (isinstance(g, dict) and any(is_ours(h) for h in (g.get("hooks") or [])))]
                if len(kept) != len(groups or []):
                    changed = True
                    if kept:
                        data["hooks"][event] = kept
                    else:
                        del data["hooks"][event]
            if changed:
                backup = settings.with_name(settings.name + ".starixs-uninstall-" + time.strftime("%Y%m%d-%H%M%S") + ".bak")
                shutil.copy2(settings, backup)
                settings.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
                removed.append(str(settings))
                print("removed our hooks from " + str(settings))
    for name in ("gate.py", "gate_rules.json"):
        target = state / name
        if target.is_file():
            target.unlink()
            removed.append(str(target))
            print("removed " + str(target))
    market = state / MARKER
    if market.is_dir():
        shutil.rmtree(market, ignore_errors=True)
        removed.append(str(market))
        print("removed " + str(market))
    if skill:
        folder = own_skill_dir()
        if folder is not None:
            shutil.rmtree(folder, ignore_errors=True)
            removed.append(str(folder))
            print("removed the skill folder " + str(folder))
        else:
            print("could not locate the skill folder from here; remove it by hand")
    if purge:
        if state.is_dir():
            shutil.rmtree(state, ignore_errors=True)
            removed.append(str(state))
            print("removed the whole state directory " + str(state))
        print("Gate and all local state removed.")
    else:
        print("state left in place: " + str(state))
        print("  (record and switch files; pass --purge to remove those too)")
    return removed


def ensure(home=None, hosts=None):
    """幂等：门已经在跑了就什么都不做；没装或装坏了就装上。

    退出码：0 = 门活着或刚装好；1 = 装了但还差用户点一下信任；2 = 环境挡住写不了。
    这样调用方不用自己解析状态——一条命令，看退出码。
    """
    home = Path.home() if home is None else Path(home)
    state = (home / ".local" / "share" / "starixs") if home == Path.home() else home / ".local/share/starixs"

    here = (hosts or [None])[0] if hosts else current_host()
    if not here:
        print("Cannot tell which host is running this, so nothing was wired.")
        print("Run it as: python3 gate_install.py --ensure --host codex   (or claude)")
        return 2
    if gate.HOSTS.get(here, {}).get("hook") not in ("settings", "plugin"):
        print("%s has no per-message hook in this build. The skill still works on demand."
              % gate.HOSTS.get(here, {}).get("label", here))
        return 0
    wired = [here]

    # 已经活着的什么都不做；装了一半（文件在、还差信任）也不重写，只提示
    states = {n: gate.hook_state(n, home) for n in wired}
    if all(states[n].get("active") or states[n].get("installed") for n in wired):
        for name in wired:
            label = gate.HOSTS[name]["label"]
            if states[name].get("active"):
                print("%s: hook active" % label)
            elif states[name].get("trusted") is False:
                print("%s: installed — needs one trust click in /hooks" % label)
            elif states[name].get("enabled") is False:
                print("%s: installed and trusted — needs enabling in plugins" % label)
            else:
                print("%s: installed" % label)
        return 0 if all(states[n].get("active") for n in wired) else 1

    try:
        apply(home, wired)
    except (OSError, PermissionError) as error:
        print("Could not write the gate: %s" % error)
        print("This needs permission to write under your home directory.")
        print("Run it yourself in a terminal: python3 %s --apply" % Path(__file__).resolve())
        return 2

    pending = [n for n in wired if not gate.hook_present(n, home)]
    for name in wired:
        state_info = gate.hook_state(name, home)
        label = gate.HOSTS[name]["label"]
        if state_info.get("active"):
            print("%s: hook active" % label)
        elif not state_info.get("installed"):
            print("%s: files written but the hook is not registered" % label)
        elif state_info.get("trusted") is False:
            print("%s: installed — needs one trust click in /hooks" % label)
        elif state_info.get("enabled") is False:
            print("%s: installed and trusted — needs enabling in plugins" % label)
        else:
            print("%s: installed" % label)
    return 0 if not pending else 1


def main(argv) -> int:
    parser = argparse.ArgumentParser(description="Install the starixs gate hook.")
    parser.add_argument("--apply", action="store_true", help="actually write (default is a dry run)")
    parser.add_argument("--uninstall", action="store_true", help="remove the hook, keep the record files")
    parser.add_argument("--purge", action="store_true", help="with --uninstall: remove the state directory too")
    parser.add_argument("--all", action="store_true",
                        help="with --uninstall: also remove this skill folder (one command, nothing left)")
    parser.add_argument("--check", action="store_true", help="report whether the hook is in place")
    parser.add_argument("--ensure", action="store_true",
                        help="idempotent: install the hook if it is not already active, else do nothing")
    parser.add_argument("--host", action="append", choices=list(gate._HOST_ORDER),
                        help="limit to one host; repeatable")
    parser.add_argument("--home", help="override home directory (for testing)")
    args = parser.parse_args(argv)
    home = Path(args.home) if args.home else None

    if args.check:
        print(gate.check(home))
        return 0
    if args.ensure:
        return ensure(home, args.host)
    if args.uninstall:
        uninstall(home, purge=args.purge or args.all, skill=args.all)
        return 0
    if not args.apply:
        print("Dry run. Nothing was changed. Add --apply to write.\n")
        for action, path, note in plan(home, args.host):
            print(f"{action:5s} {path}\n      {note}")
        return 0
    apply(home, args.host)
    print("\nVerify with: python3 %s --check" % (Path(__file__).resolve().parent / "gate.py"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

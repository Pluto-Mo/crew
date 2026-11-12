#!/usr/bin/env python3
"""门口：每条用户消息到 AI 之前跑一次的小程序，由 Claude Code / Codex 的钩子调用。

它只做字面上就能做对的三件事，听懂才能判的事（是不是纠正、是不是大任务）留给 AI：

1. 把常驻规则「重活四岗」原文整段放到 AI 眼前。对话第一条消息一定放；压缩之后一定放；
   15 个字以内、没有新内容的短回话（继续 / 还有吗 / 好 / B）不放，因为前面的消息里已经有了。
2. 消息里出现发布、上线、删、发邮件、付款这类收不回的动作时，把「收不回」「不越界」原文一起放上。
   只看用户自己说的话：贴进来的材料（<pasted_content>、代码块、引用行）和宿主加的通知不算，见 own_words。
3. 每条消息记一行（时间、工具、对话号、做了什么、放了哪些规则、消息长度、目录），不记内容。

用法：钩子的命令是「用 python 跑这个文件，参数 claude 或 codex」，标准输入是钩子给的 JSON。
没有标准输入约定的宿主用参数：``gate.py pi --session ID --prompt-file FILE [--transcript FILE]``
或 ``gate.py pi --event compact``。

``gate.py --check`` 自查装好没有；``gate.py --self-test`` 给安装器验钩子命令。

标准输出就是放给 AI 看的文字；什么都不放就不输出。**退出码永远是 0**：这个程序出任何错都不能影响用户发消息。
"""
import datetime
import json
import os
import re
import sys
from pathlib import Path

# ---- locations: begin（装到用户电脑上的那份由 gate_install.py 把这一段换成"就在本目录"）
sys.path.insert(0, str(Path(__file__).resolve().parent))
from paths import HOME, RULES_DIR  # noqa: E402
# ---- locations: end

LOG = HOME / "gate.jsonl"          # 每条消息一行
STATE = HOME / "gate_state.json"   # 每个对话最近一次经过门口的时间，用来认"第一条消息"
SWITCH = HOME / "switch.json"      # 和 starixs.py 同一个开关文件
MOTHER = "重活四岗"
IRREVERSIBLE_RULES = ("收不回", "不越界")
MARKER_PLUGIN = "starixs-gate"

# ---- 宿主总表：支持的每一家只在这里登记一次。是谁在调、会话编号从哪个变量取、装到哪，
#      都从这张表取；加一家只改这里。
HOSTS = {
    "codex": {"label": "Codex", "proc": ("codex",), "session": "CODEX_THREAD_ID",
              "env": ("CODEX_THREAD_ID", "CODEX_HOME"), "dir": ".codex", "dir_env": "CODEX_HOME",
              "hook": "plugin", "skills": ".agents/skills", "json_out": False},
    "claude": {"label": "Claude Code", "proc": ("claude",), "session": "CLAUDE_SESSION_ID",
               "env": ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT"), "dir": ".claude",
               "dir_env": "CLAUDE_CONFIG_DIR", "hook": "settings", "skills": ".claude/skills",
               "json_out": False},
    "opencode": {"label": "OpenCode", "proc": ("opencode",), "session": "OPENCODE_SESSION_ID",
                 "env": ("OPENCODE_SESSION_ID", "OPENCODE_TERMINAL"),
                 "dir": ".config/opencode", "dir_env": "OPENCODE_CONFIG_DIR",
                 "hook": "extension", "skills": ".agents/skills", "json_out": False},
    "kimi": {"label": "Kimi Code", "proc": ("kimi",), "session": "KIMI_SESSION_ID",
             "env": ("KIMI_SESSION_ID", "KIMI_CODE_HOME"), "dir": ".kimi-code",
             "dir_env": "KIMI_CODE_HOME", "hook": "toml", "skills": ".agents/skills",
             "json_out": False},
    "dsh": {"label": "DeepSeek Harness", "proc": ("deepseek",), "session": "DSH_SESSION_ID",
            "env": ("DSH_SESSION_ID", "DSH_HOME"), "dir": ".dsh", "dir_env": "DSH_HOME",
            "hook": "extension", "skills": ".agents/skills", "json_out": True},
    "pi": {"label": "pi", "proc": (), "session": "PI_SESSION_ID",
           "env": ("PI_SESSION_ID", "PI_CODING_AGENT_DIR"), "dir": ".pi/agent",
           "dir_env": "PI_CODING_AGENT_DIR", "hook": "extension", "skills": ".agents/skills",
           "json_out": False},
}
_HOST_ORDER = ("codex", "dsh", "pi", "opencode", "kimi", "claude")

# 某家宿主的已知短板，门口每条任务消息多带一条原文。这是补某个当前模型的补丁，
# 按 Sutton 的分法是随模型换代过期的那一类，所以带加入日期、依据和重测条件。
# 可在数据目录的 config.json 里用 "host_rules": {"codex": ["干到底"]} 改；空列表就不带。
HOST_PATCHES = {
    "codex": {
        "rules": ("干到底",),
        "since": "2026-11-12",
        "basis": "Codex 倾向在动工前先问、把活停在计划上；移植自同架构的既有做法",
        "retest": "Codex changes its underlying model, or 90 days after the patch went in",
        "retest_days": 90,
    },
}
HOST_RULES = {tool: patch["rules"] for tool, patch in HOST_PATCHES.items()}
HOST_HEAD = ("This host tends to stop before the work is finished and to wait to be pushed. "
             "The user's rule for that, in full:")
SHORT_CHARS = 15
STATE_TTL = 7 * 24 * 3600
STATE_KEEP = 200

# 收不回的动作：中英文都认；只看字面，宁可多放一次（多放只是多几百 token）。
# 「发布页」「上线交接」是文件名，不算。
IRREVERSIBLE = re.compile(
    r"发布(?![页会说])|上线(?!交接)|部署|推送|合并到|合到\s*main|删除|删掉|删了|清空|清掉|发邮件|发送|发给|群发|付款|支付|转账|购买|下单|退款|"
    r"\b(publish|deploy|release|push|merge|delete|drop|rm\s+-rf|send|email|pay|purchase|refund)\b", re.I)

# 找收不回的动作时，只看用户自己说的话：宿主发的后台任务通知、贴进来的材料里的字眼都不算，
# 块外面用户自己的话照样匹配。只影响放不放那两条；常驻规则照旧。
_HOST_BLOCK = re.compile(r"<(task-notification|system-reminder)\b[^>]*>.*?</\1\s*>", re.S | re.I)
_PASTED_BLOCKS = (
    re.compile(r"<(pasted[_-](?:content|text))\b[^>]*>.*?</\1\b[^>]*>", re.S | re.I),
    re.compile(r"^[ \t]*(`{3,}|~{3,})[^\n]*\n.*?^[ \t]*\1[ \t]*$", re.S | re.M),
    re.compile(r"^[ \t]*[>＞][^\n]*$", re.M),
)


def own_words(prompt):
    """消息里用户自己说的那部分：去掉宿主加的块和贴进来的材料。
    整条消息就是一块贴进来的东西（去掉以后什么都不剩）时，那一块就是用户要说的，原样留着。
    没成对的标签和代码块不动：拿不准就当作用户的话。"""
    text = _HOST_BLOCK.sub("\n", prompt or "")
    own = text
    for pattern in _PASTED_BLOCKS:
        own = pattern.sub("\n", own)
    return own if own.strip() else text


def rule_text(name):
    """规则文件正文（原样，不改一个字）；读不到返回空串。
    装到用户电脑上的那份没有规则目录（RULES_DIR 为 None），从旁边的 gate_rules.json 读。"""
    try:
        if RULES_DIR is None:
            return str(json.loads((HOME / "gate_rules.json").read_text(encoding="utf-8")).get(name) or "")
        text = (RULES_DIR / f"{name}.md").read_text(encoding="utf-8")
        _, _, body = text.replace("\r\n", "\n").split("---\n", 2)
        return body.split("\n## ")[0].strip()
    except (OSError, ValueError, AttributeError):
        return ""


HEAD = "The user's standing request for every task (the starixs skill keeps it in view):"
LEAD = ("Work through it in your own reasoning before you start, scaled to the task, and let it shape the work. "
        "It is for you, so leave it out of the reply at the start and the end alike; the user asked for the result "
        "without it. If the user asks how you approached it, say so. For a short follow-up such as 继续, just continue.")
IRREVERSIBLE_HEAD = ("This message mentions an action that is hard to undo (publishing, deleting, sending, paying or "
                     "the like). Two of the user's rules for that, in full:")


def mother_block():
    text = rule_text(MOTHER)
    return f"{HEAD}\n\n### {MOTHER}\n\n{text}\n\n{LEAD}" if text else ""


def host_rules(tool):
    """这家宿主每条任务消息多带哪几条规则：先看数据目录 config.json 的 host_rules，没有就用内置表。"""
    try:
        config = json.loads((HOME / "config.json").read_text(encoding="utf-8")).get("host_rules")
        if isinstance(config, dict) and tool in config:
            return tuple(str(x) for x in (config.get(tool) or []))
    except (OSError, ValueError, AttributeError):
        pass
    return HOST_RULES.get(tool, ())


def host_block(tool):
    parts = [f"### {name}\n\n{rule_text(name)}" for name in host_rules(tool) if rule_text(name)]
    return HOST_HEAD + "\n\n" + "\n\n".join(parts) if parts else ""


def irreversible_block():
    parts = [f"### {name}\n\n{rule_text(name)}" for name in IRREVERSIBLE_RULES if rule_text(name)]
    return IRREVERSIBLE_HEAD + "\n\n" + "\n\n".join(parts) if parts else ""


def is_off(sid):
    try:
        state = json.loads(SWITCH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return bool(state.get("all_off")) or bool(sid and sid in (state.get("off_sessions") or {}))


def inherit_switch(transcript_path, sid, now):
    """对话被压缩或续开后宿主会换一个会话编号，而「分工关」记在旧编号上。
    第一次见到一个编号时，扫一遍它的对话记录：最后一次 --off / --on 决定现在是开还是关。"""
    try:
        path = Path(transcript_path)
        if not path.is_file() or path.stat().st_size > 50 * 1024 * 1024:
            return
        last = None
        with path.open(encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if "--off" in line or "--on" in line:
                    last = line
        if last is None:
            return
        state = json.loads(SWITCH.read_text(encoding="utf-8"))
        state = state if isinstance(state, dict) else {}
    except (OSError, ValueError):
        return
    off = "--off" in last
    if off:
        state.setdefault("off_sessions", {})[sid] = now
    else:
        (state.get("off_sessions") or {}).pop(sid, None)
    try:
        SWITCH.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def load_state():
    try:
        state = json.loads(STATE.read_text(encoding="utf-8"))
        return state if isinstance(state, dict) else {}
    except (OSError, ValueError):
        return {}


def save_state(state):
    try:
        HOME.mkdir(parents=True, exist_ok=True)
        tmp = STATE.with_name(f"gate_state.{os.getpid()}.tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        tmp.replace(STATE)
    except OSError:
        pass


def prompt_text(prompt):
    """钩子给的消息内容 → 字符串。Claude / dsh 给字符串；Kimi Code 给内容块数组。"""
    if isinstance(prompt, str):
        return prompt
    if isinstance(prompt, list):
        return "\n".join(str(x.get("text", "")) for x in prompt
                         if isinstance(x, dict) and x.get("type") == "text")
    return None


def is_short(prompt):
    text = prompt.strip()
    return bool(text) and "\n" not in text and len(text) <= SHORT_CHARS


def decide(payload, tool, now, state):
    """返回 (kind, 要放的文字, 放了哪些规则, 对话号, 是不是这个对话的第一条)。
    kind：first / task / short / irreversible / compact / off / nocontent / host。
    纯函数（只读规则文件），测试直接调它。"""
    sid = str(payload.get("session_id") or payload.get("thread_id")
              or os.environ.get("CLAUDE_CODE_SESSION_ID" if tool == "claude" else "CODEX_THREAD_ID", "") or "")
    seen = bool(sid) and sid in state and now - float(state[sid].get("t", 0)) < STATE_TTL
    if sid and not seen and payload.get("transcript_path"):
        inherit_switch(payload["transcript_path"], sid, now)
    if is_off(sid):
        return "off", "", [], sid, False
    event = payload.get("hook_event_name") or ""
    extra_text, extra = host_block(tool), [n for n in host_rules(tool) if rule_text(n)]
    with_host = lambda text: "\n\n".join(x for x in (text, extra_text) if x)
    if event == "SessionStart" or (payload.get("source") in ("compact",) and "prompt" not in payload):
        return "compact", with_host(mother_block()), [MOTHER] + extra, sid, False
    prompt = prompt_text(payload.get("prompt"))
    if prompt is None:
        return "nocontent", with_host(mother_block()), [MOTHER] + extra, sid, False
    if not _HOST_BLOCK.sub("", prompt).strip():
        # 整条都是宿主自己发的（后台任务做完的通知等），不是用户的消息：什么都不放。
        return "host", "", [], sid, False
    first = not seen
    danger = bool(IRREVERSIBLE.search(own_words(prompt)))
    out, rules = [], []
    if first:
        out += [mother_block(), extra_text]
        rules += [MOTHER] + extra
    elif not is_short(prompt):
        out += [mother_block(), extra_text]
        rules += [MOTHER] + extra
    if danger:
        out.append(irreversible_block())
        rules += list(IRREVERSIBLE_RULES)
        kind = "irreversible"
    else:
        kind = "first" if first else ("short" if is_short(prompt) else "task")
    return kind, "\n\n".join(x for x in out if x), rules, sid, first


def log_line(tool, sid, kind, rules, prompt_len, first, pasted_skip=False):
    """pasted_skip：字眼只出现在贴进来的材料或宿主的通知里，所以没放那两条。"""
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        row = {"time": datetime.datetime.now().isoformat(timespec="seconds"), "tool": tool,
               "session": sid, "kind": kind, "first": first, "rules": rules, "chars": prompt_len,
               "cwd": os.getcwd()}
        if os.environ.get("STARIXS_TEST"):
            row["test"] = True
        if pasted_skip:
            row["pasted_skip"] = True
        with LOG.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError:
        pass


TOOLS = (*HOSTS, "other")
JSON_OUT = tuple(name for name, host in HOSTS.items() if host.get("json_out"))


def payload_from_args(args):
    """没有标准输入约定的宿主改用参数。没给任何一个返回 None。"""
    if not args:
        return None
    payload, i = {}, 0
    while i < len(args):
        arg, value = args[i], (args[i + 1] if i + 1 < len(args) else "")
        if arg == "--session":
            payload["session_id"] = value
        elif arg == "--prompt":
            payload["prompt"] = value
        elif arg == "--prompt-file":
            try:
                payload["prompt"] = Path(value).read_text(encoding="utf-8")
            except OSError:
                payload["prompt"] = ""
        elif arg == "--transcript":
            payload["transcript_path"] = value
        elif arg == "--event":
            if value == "compact":
                payload["hook_event_name"], payload["source"] = "SessionStart", "compact"
        else:
            i += 1
            continue
        i += 2
    return payload or None


def _stamp(text):
    """独立版里那行版本戳；没有返回空串。"""
    match = re.search(r'^GATE_PACKAGE_VERSION = "([^"]*)"', text, re.M)
    return match.group(1) if match else ""


def host_by_env(env=None):
    env = os.environ if env is None else env
    for name in _HOST_ORDER:
        for var in HOSTS[name]["env"]:
            if env.get(var):
                return name
    return ""


def host_file(name, home=None):
    home = Path.home() if home is None else Path(home)
    spec = HOSTS.get(name)
    return None if spec is None else home.joinpath(*spec["dir"].split("/"))


def host_present(name, home=None):
    directory = host_file(name, home)
    return bool(directory and directory.is_dir())


def codex_trusted(home=None):
    """Codex 的 config.toml 里给我们的插件记了几条信任（[hooks.state."starixs-gate@…"] 下有 trusted_hash）。
    读不到算 0。装了插件不等于它在跑：Codex 要求用户在 /hooks 里信任一次。"""
    home = Path.home() if home is None else Path(home)
    try:
        text = (home / ".codex" / "config.toml").read_text(encoding="utf-8")
    except OSError:
        return 0
    return sum(1 for match in re.finditer(
        r'(?ms)^\[hooks\.state\."starixs-gate@[^"\n]*"\]\n(.*?)(?=^\[|\Z)', text)
        if re.search(r"^\s*trusted_hash\s*=", match.group(1), re.M))


def codex_enabled(home=None, market=None):
    """Codex 的 config.toml 里 [plugins."starixs-gate@<市场>"] 是不是 enabled = true。
    市场名不传就接受任意市场（安装时用的是本地目录市场）。读不到算 False。"""
    home = Path.home() if home is None else Path(home)
    try:
        text = (home / ".codex" / "config.toml").read_text(encoding="utf-8")
    except OSError:
        return False
    name = re.escape("starixs-gate@" + (market or ""))
    pattern = re.escape('"starixs-gate@') + (re.escape(market) if market else r'[^"]*') + re.escape('"')
    if re.search(r'(?ms)^\[plugins\.' + pattern + r'\]\n(.*?)(?=^\[|\Z)', text):
        block = re.search(r'(?ms)^\[plugins\.' + pattern + r'\]\n(.*?)(?=^\[|\Z)', text).group(1)
        if re.search(r"^\s*enabled\s*=\s*true\b", block, re.M):
            return True
    if re.search(r'(?m)^\s*plugins\.' + pattern + r'\.enabled\s*=\s*true\b', text):
        return True
    return bool(re.search(r'(?m)^\s*' + pattern + r'\s*=\s*\{[^}\n]*\benabled\s*=\s*true\b', text))


def hook_present(tool, home=None):
    """钩子真的会在每条消息上跑吗。

    Claude：settings.json 里有我们的命令 → 会跑。
    Codex：光有插件文件不算——Codex 要求用户在 /hooks 里信任一次；
           还要确认插件在 config.toml 里是启用的。
    """
    home = Path.home() if home is None else Path(home)
    if tool == "claude":
        try:
            text = (home / ".claude" / "settings.json").read_text(encoding="utf-8")
        except OSError:
            return False
        return "gate.py" in text and "starixs" in text
    if tool == "codex":
        return bool(hook_state("codex", home).get("active"))
    return False


def hook_state(tool, home=None):
    """比 hook_present 更细：装了没、信任没、启用没。给 --check 说清楚下一步。"""
    home = Path.home() if home is None else Path(home)
    if tool == "claude":
        return {"installed": hook_present("claude", home)}
    if tool == "codex":
        # 三件事都要成立：市场登记了、插件装进 Codex 的缓存了、钩子被信任且启用。
        # 只看硬盘上有没有我们的文件没用——Codex 用的是它自己缓存里的副本。
        market = (home / ".local" / "share" / "starixs" / "codex-market" / MARKER_PLUGIN
                  / "hooks" / "hooks.json").is_file()
        codex_home = Path(os.environ.get("CODEX_HOME") or (home / ".codex"))
        cached = bool(list((codex_home / "plugins" / "cache").glob(
            "*/%s/*/hooks/hooks.json" % MARKER_PLUGIN))) if (codex_home / "plugins" / "cache").is_dir() else False
        trusted = codex_trusted(home)
        enabled = codex_enabled(home)
        # 市场名和插件名都叫 starixs-gate：codex 的写法是 plugin@marketplace
        return {"installed": market, "cached": cached, "trusted": trusted > 0,
                "enabled": enabled,
                "active": cached and trusted > 0 and enabled}
    return {"installed": False}


def self_test_line(tool):
    text = rule_text(MOTHER)
    return (f"starixs gate self-test: the hook command runs and the standing rule text is readable "
            f"({len(text)} chars, tool {tool})" if text else
            f"starixs gate self-test: the command runs but the standing rule text is NOT readable (tool {tool})")


def check(home=None):
    """--check：钩子真的会在每条消息上跑吗、规则读得到不、并打印会放给 AI 的那一段。
    每家宿主都给出下一步：装了什么、还差哪一步、谁来做。"""
    home = Path.home() if home is None else Path(home)
    lines = [f"starixs gate {VERSION}"]
    readable = sum(1 for name in (MOTHER, *IRREVERSIBLE_RULES) if rule_text(name))
    lines.append(f"  rule text readable: {readable}/3")
    active = []
    for name in _HOST_ORDER:
        if not host_present(name, home):
            continue
        label = HOSTS[name]["label"]
        if name == "codex":
            state = hook_state("codex", home)
            if state.get("active"):
                lines.append(f"  {label}: hook active")
                active.append(name)
            elif not state.get("installed"):
                lines.append(f"  {label}: present, plugin NOT installed")
                lines.append("      next: run scripts/gate_install.py --apply")
            elif not state.get("trusted"):
                lines.append(f"  {label}: plugin installed, waiting for you to trust it")
                lines.append("      next: in Codex, open /hooks and trust starixs-gate once")
            elif not state.get("enabled"):
                lines.append(f"  {label}: plugin installed and trusted, but not enabled")
                lines.append("      next: enable starixs-gate in Codex plugins")
            else:
                lines.append(f"  {label}: hook NOT active")
        elif HOSTS[name].get("hook") in ("settings", "plugin"):
            # 只有这两家有接线实现；其余家认得出但装不上钩子
            if hook_present(name, home):
                lines.append(f"  {label}: hook active")
                active.append(name)
            else:
                lines.append(f"  {label}: present, hook NOT installed")
                lines.append("      next: run scripts/gate_install.py --apply")
        else:
            lines.append(f"  {label}: present, no per-message hook in this build")
            lines.append("      the skill still works on demand: run plan at the start of a heavy task")
        for rule in host_rules(name):
            lines.append(f"      extra rule: {rule}")
    # 装的门和这个 skill 里的门是不是同一版：不是就说明该更新了
    try:
        installed = (HOME / "gate.py")
        if installed.is_file() and RULES_DIR is not None:
            got = _stamp(installed.read_text(encoding="utf-8"))
            want = VERSION
            if got and got != want:
                lines.append(f"  installed gate is {got}, this skill is {want}")
                lines.append("      next: run scripts/gate_install.py --apply to update it")
    except (OSError, UnicodeError):
        pass

    text = mother_block()
    lines.append("")
    if not active:
        lines.append("  NOT INSTALLED: nothing is placing rules with task messages yet.")
        lines.append("  fix: python3 <skill>/scripts/gate_install.py --ensure")
        return "\n".join(lines)
    lines.append("  what would be placed on the next task message:" if text else
                 "  NOTHING would be placed: the rule files are unreadable")
    if text:
        lines.append("  " + text.replace("\n", "\n  ")[:1200])
    return "\n".join(lines)


VERSION = "1.3.0"


def main(argv=None, stdin=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv and "--self-test" in argv[:2]:
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
        print(self_test_line(argv[0] if argv[0] in TOOLS else "claude"))
        return
    if argv and "--check" in argv[:2]:
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
        print(check())
        return
    tool = argv[0] if argv and argv[0] in TOOLS else "claude"
    payload = payload_from_args(argv[1:] if argv and argv[0] in TOOLS else argv)
    if payload is None:
        try:
            raw = (stdin if stdin is not None else sys.stdin).read()
            payload = json.loads(raw) if raw.strip() else {}
            if not isinstance(payload, dict):
                payload = {}
        except Exception:
            payload = {}
    now = datetime.datetime.now().timestamp()
    state = load_state()
    kind, text, rules, sid, first = decide(payload, tool, now, state)
    if sid and kind != "host":
        state = {k: v for k, v in state.items() if now - float(v.get("t", 0)) < STATE_TTL}
        state[sid] = {"t": now, "n": int(state.get(sid, {}).get("n", 0)) + 1}
        if len(state) > STATE_KEEP:
            for key in sorted(state, key=lambda k: state[k]["t"])[:len(state) - STATE_KEEP]:
                del state[key]
        save_state(state)
    prompt = prompt_text(payload.get("prompt"))
    skipped = (kind in ("first", "task", "short") and isinstance(prompt, str)
               and bool(IRREVERSIBLE.search(prompt)))
    log_line(tool, sid, kind, rules, len(prompt) if isinstance(prompt, str) else -1, first,
             pasted_skip=skipped)
    if text:
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
        if tool in JSON_OUT:
            print(json.dumps({"hookSpecificOutput": {
                "hookEventName": payload.get("hook_event_name") or "UserPromptSubmit",
                "additionalContext": text}}, ensure_ascii=False))
        else:
            print(text)


if __name__ == "__main__":
    try:
        main()
    except Exception:  # 门口出任何错都不能拦住用户的消息
        pass
    sys.exit(0)

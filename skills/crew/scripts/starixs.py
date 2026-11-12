#!/usr/bin/env python3
"""starixs — starixs 分工的明文分发版。

设计沿用已被验证的分工规则，只把密封分发换成明文：
- 只放规则：没有型号、档位、宿主能力和按数量分的情况，全部由 AI 当场识别。
- 三个块：match（第一次，要看宿主有什么）/ roles（用户确认的分工）/ quiet（本对话看过或用户不要）。
- 只给主代理；帮手（--from 派单）不再往下分。
- 认不出的宿主不能存分工，防止这家确认的分工用到那家。
- 记录里没有型号。

本文件只做三件事：把规则交给做重活的 AI，记下用户确认过的分工，数大脑实际被问了几次。
不联网、不写宿主配置。

直接运行就是「分工」：python3 starixs.py
config.json 写 "model_split": false 可以关掉（--off / --on）。
"""
import argparse
import hashlib
import json
import os
import platform
import sys
import time
from pathlib import Path

VERSION = "1.3.0"
UNKNOWN_HOST = "其他"
_SET = 'brain=NAME;executor=NAME;review=NAME;helpers=NAME,NAME'
_NONE = "none"


# ---------------------------------------------------------------- 位置

def home() -> Path:
    """starixs 自己的数据目录。STARIXS_HOME 可改。"""
    override = os.environ.get("STARIXS_HOME")
    if override:
        return Path(override).expanduser()
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home())
        return Path(base) / "starixs"
    return Path.home() / ".local" / "share" / "starixs"


HOME = home()
CFG = HOME / "config.json"
ROLES = HOME / "model_roles.json"
USES = HOME / "uses.jsonl"


def ensure():
    HOME.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(HOME, 0o700)
    except OSError:
        pass
    return HOME


def _read(path, fallback=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return fallback


def _write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def cfg() -> dict:
    value = _read(CFG, {})
    return value if isinstance(value, dict) else {}


# ---------------------------------------------------------------- 宿主

# 宿主总表。加一家只改这里。
# 只登记认人用的环境变量和配置目录；不登记任何型号或档位。
HOSTS = {
    "codex": ("CODEX_THREAD_ID", "CODEX_HOME"),
    "dsh": ("DSH_SESSION_ID", "DSH_HOME"),
    "pi": ("PI_SESSION_ID", "PI_CODING_AGENT_DIR"),
    "opencode": ("OPENCODE_SESSION_ID", "OPENCODE_CONFIG_DIR"),
    "kimi": ("KIMI_SESSION_ID", "KIMI_CODE_HOME"),
    "claude": ("CLAUDE_SESSION_ID", "CLAUDE_CONFIG_DIR"),
}
_HOST_ORDER = ("codex", "dsh", "pi", "opencode", "kimi", "claude")


def detect_host() -> str:
    """先看环境变量；都不行记「其他」。认不出的宿主不能存分工。"""
    forced = os.environ.get("STARIXS_HOST")
    if forced:
        return forced
    for name in _HOST_ORDER:
        session_var, dir_var = HOSTS[name]
        if os.environ.get(session_var) or os.environ.get(dir_var):
            return name
    if os.environ.get("CLAUDECODE") or os.environ.get("CLAUDE_CODE_ENTRYPOINT"):
        return "claude"
    if os.environ.get("OPENCODE_TERMINAL"):
        return "opencode"
    return UNKNOWN_HOST


def session_id() -> str:
    for name in ("CODEX_THREAD_ID", "CLAUDE_SESSION_ID", "OPENCODE_SESSION_ID",
                 "KIMI_SESSION_ID", "DSH_SESSION_ID", "PI_SESSION_ID", "STARIXS_SESSION"):
        value = os.environ.get(name)
        if value:
            return value
    seed = "|".join([os.getcwd(), time.strftime("%Y-%m-%d")])
    return "local-" + hashlib.sha256(seed.encode()).hexdigest()[:12]


def command(args: str = "") -> str:
    """给自己看的完整命令。"""
    base = "python3 %s" % (Path(__file__).resolve())
    return base + (" " + args if args else "")


# ---------------------------------------------------------------- 规则

_JOBS = """Heavy work has up to four jobs. Use only the ones this task needs.\
 Brain: settles the approach and the calls that are genuinely hard.\
 Hand: does the work.\
 Review: takes the finished result and judges it against the goal, in a context of its own, read-only, having taken no part in producing it.\
 Verify: runs something that is capable of failing, such as the test suite or the real path; a model stating an opinion is not verification."""

_BRAKE = """Scale all of this to the stakes, and verify wherever a check can actually be run; where none can, record that plainly rather than manufacturing one. Work spanning several steps gets a review of its own unless it qualifies as small, and the small test is strict. Judge smallness once the work is finished, from the change that actually landed and what actually happened, never from how the task looked at the outset. A change is small only when every one of these holds: the verification ran, it passed, it covers this change, and no test was altered to make it pass; the diff touches at most 2 files and changes at most 30 lines in total, counting additions and deletions; it stays clear of public interfaces, stored data or migrations, permissions, security, payment, release configuration and concurrency; nothing errored, nothing prevented the verification from running, and the change did not extend past the request; and it can be reversed, affects only the user, and no review was requested. Work that cannot be run is never small. Where the change qualifies, check the result against the goal yourself. A review ends after three rounds; if problems are still surfacing at that point, report what remains open rather than starting another. Never launch additional review or hardening rounds on your own initiative.
Bring in the brain only where the call is genuinely hard: when competing approaches would produce materially different outcomes, when the same error has come back, or immediately before a step that cannot be reversed. Work you can finish in a handful of steps needs neither brain nor helper — the one exception is long reading, described below. Leave out every step this task does not need.
Keep your own context lean. Each later step re-reads everything in it, which costs the user tokens and dilutes your attention. Read only the portion you need — a line range, a search result — rather than whole files, logs, data dumps, page dumps or screenshots. When you need the conclusion of something long rather than its full text, hand the reading to a helper on the cheapest model that can do it, and take back the conclusion together with the exact lines it rests on. Editing and judgement stay with you.
Set the effort per piece of work you hand off, not per task. Your own model and effort level are the user's choice to make. For a piece whose result can be checked, use the lowest level that can pass its verification; where nothing can be checked — writing, a judgement call, something hard to reverse — begin on the stronger side. Move up only on evidence: verification failed twice, or a review returned the same class of problem twice. Raise the effort level first, change the model second, add a helper last.
Choose the reviewer by what a miss would cost, never by the weakest option that will pass — an underpowered reviewer simply finds nothing, so the signal you were hoping for never arrives. Work that is not small but can be run and reversed, up to 200 lines: a fresh read-only reviewer on the same model as the one who did the work, at a middle effort level, not the top. Beyond 200 lines, spread across modules, or touching any of the areas listed above: the next model up, at a high effort level. Hard to reverse, something other people will act on, or nothing runnable: the strongest model available, at its top effort level. A reviewer weaker than the one who did the work does not review it — it may look things up on the reviewer's behalf. Never go past the row the work falls into. If the user has confirmed a reviewer, that one is used.
Pass the model and effort level along with the hand-off itself, in the parameters of the call that starts the helper or reviewer; where the host exposes no such parameters, everything runs at the user's settings. If a helper or reviewer may pull the user's rules, instruct it to append --from 派单 to that command so it is not mistaken for the main conversation."""

_REPORT = """On delivery, say nothing about how the work was divided unless the user asks — who ran what, how often the brain was consulted, how the review went. State briefly when nothing could be verified or when a review could not use the model it needed, name any problem the review found that remains open, and say whether a deeper review looks worthwhile."""

MATCH_BLOCK = """
### Division of labour

""" + _JOBS + """
{scene}
""" + _BRAKE + """
Work out the setup yourself from what this user really has. Find out, read-only, which models and effort levels this host offers and can actually use, from the host's own help, model list and config, or the parameters of its own tool for starting a subagent; read names only, never keys or tokens. Separate the jobs with whatever exists here: a different model, a different effort level, a fresh context, a separate session; for a reviewer, the model and level above decide. Do not invent what is not here. Do not guess what you cannot judge; stay on the current setup.
Go ahead with your pick without asking, and put the reasoning in the brief of whoever you hand work to, not in the chat. Speak up only if it would cost the user money or needs a setting only they can change. If the user asked for starixs 分工 by name, show your pick and why. If they want a fixed split, save it with: {set_cmd} If they say they do not want a split, save that with: {none_cmd} and stay on the current setup.
""" + _REPORT

ROLES_BLOCK = """
### Division of labour (the split the user confirmed)

""" + _JOBS + """
Brain: {brain}. Hand: you, on {executor}. Review: {review}. Helpers: {helpers}.
{scene}
""" + _BRAKE + """
When you consult the brain, do it in whatever way this host allows; give it the hand-off brief, the question, the evidence and the diff, and tell it that it is acting as the brain. Use helpers only for independent pieces or bulk work.
If what you are on or can call no longer matches this split, say so once and ask the user. Changing settings is theirs to approve. To change the split, run: {set_cmd}
""" + _REPORT

QUIET_BLOCK = """
### Division of labour

""" + _JOBS + """
{scene}
""" + _BRAKE + """
{why} If the user now asks for a fixed split, save it with: {set_cmd}
""" + _REPORT

_WHY_SEEN = ("You already looked at what this host offers earlier in this conversation; use what you found. "
             "If that is gone from view (compacted), look once more, read-only.")
_WHY_DECLINED = ("The user chose not to set up a split. Do the work yourself on the current setup, and keep any review on it too: "
                 "a fresh context, without changing model or level, whatever the reviewer rule above says.")


# ---------------------------------------------------------------- 分工

def _roles_path() -> Path:
    return ROLES


def _load_all() -> dict:
    data = _read(_roles_path(), {})
    return data if isinstance(data, dict) else {}


def load_roles(tool: str):
    if tool == UNKNOWN_HOST:
        return None
    roles = _load_all().get(tool)
    return roles if isinstance(roles, dict) and roles.get("brain") and roles.get("executor") else None


def declined(tool: str) -> bool:
    roles = None if tool == UNKNOWN_HOST else _load_all().get(tool)
    return isinstance(roles, dict) and bool(roles.get("declined"))


def save_roles(tool: str, text: str) -> dict:
    if text.strip().lower() == "none":
        if tool == UNKNOWN_HOST:
            raise ValueError("this host is not recognised, so the choice could be applied to another host")
        data = _load_all()
        data[tool] = {"declined": True}
        _write(_roles_path(), data)
        return data[tool]
    roles = {}
    for part in text.split(";"):
        key, _, value = part.partition("=")
        if key.strip() in ("brain", "executor", "review", "helpers") and value.strip():
            roles[key.strip()] = value.strip()
    if not (roles.get("brain") and roles.get("executor")):
        raise ValueError("needs at least brain=... and executor=...")
    if tool == UNKNOWN_HOST:
        raise ValueError("this host is not recognised, so a saved split could be applied to another host")
    data = _load_all()
    data[tool] = roles
    _write(_roles_path(), data)
    return roles


def _scene(tags) -> str:
    tags = tags or {}
    known = [f"{k} {tags[k]}" for k in ("type", "shape", "risk", "for") if tags.get(k) not in (None, "", "unclear")]
    return "This task: " + (", ".join(known) if known else "not described yet") + "."


def build(tags, tool, enabled=True, probed=False, asked=False):
    """返回 (种类, 分工说明)。种类：roles 用户确认的分工；match 第一次，要看宿主有什么；
    quiet 本对话看过或用户不要；"" 没给。一口气的活和关掉时没有。"""
    if not enabled or (tags or {}).get("steps") != "multi":
        return "", ""
    set_cmd, none_cmd = command('--set "%s"' % _SET), command("--set " + _NONE)
    roles = load_roles(tool)
    if roles:
        return "roles", ROLES_BLOCK.format(brain=roles["brain"], executor=roles["executor"], scene=_scene(tags),
                                           review=roles.get("review") or "a fresh read-only subagent or session, on the model and level set below",
                                           helpers=roles.get("helpers") or "none", set_cmd=set_cmd)
    if not asked and (declined(tool) or probed):
        why = _WHY_DECLINED if declined(tool) else _WHY_SEEN
        return "quiet", QUIET_BLOCK.format(scene=_scene(tags), why=why, set_cmd=set_cmd)
    return "match", MATCH_BLOCK.format(scene=_scene(tags), set_cmd=set_cmd, none_cmd=none_cmd)


def block(tags, tool, enabled=True, probed=False):
    return build(tags, tool, enabled, probed)[1]


def observe(tags, tool, kind=""):
    """给 uses.jsonl 的一条记录：没有型号。任何错误都不影响取规则。"""
    try:
        return {"host": str(tool), "shape": (tags or {}).get("shape") or "unclear",
                "roles_set": bool(load_roles(tool)), "division": kind,
                "brake": "strict" if kind else False}
    except Exception as error:  # 旁路记录
        return {"host": str(tool), "error": type(error).__name__, "division": kind,
                "brake": "strict" if kind else False}


def brain_usage(limit=30):
    """最近的 Claude Code 会话（只有这家的记录读得懂）：advisor 配了几份、真调用几次、
    派给用户定的大脑模型的子代理几次。读不到就是全 0。本地只读，不上传。"""
    root = Path.home() / ".claude" / "projects"
    brain = str((load_roles("claude") or {}).get("brain") or "").split("@")[0]
    out = {"sessions": 0, "advisor_set": 0, "advisor_calls": 0, "brain_subagents": 0}
    try:
        files = sorted(root.glob("*/*.jsonl"), key=lambda f: f.stat().st_mtime, reverse=True)[:limit]
    except OSError:
        return out
    for handle in files:
        seen = False
        try:
            with handle.open(encoding="utf-8", errors="replace") as fh:  # 会话可能上百 MB，逐行读
                for line in fh:
                    seen = seen or "advisor_20260301" in line
                    if 'tool_use"' not in line:
                        continue
                    try:
                        content = (json.loads(line).get("message") or {}).get("content")
                    except (ValueError, AttributeError):
                        continue
                    for item in content if isinstance(content, list) else []:
                        if not isinstance(item, dict):
                            continue
                        if item.get("type") == "server_tool_use" and item.get("name") == "advisor":
                            out["advisor_calls"] += 1
                        elif brain and item.get("type") == "tool_use" and item.get("name") in ("Agent", "Task") \
                                and brain in str((item.get("input") or {}).get("model") or ""):
                            out["brain_subagents"] += 1
        except OSError:
            continue
        out["sessions"] += 1
        out["advisor_set"] += seen
    return out


def switch(on: bool) -> None:
    """「分工开 / 关」：只改自己数据目录里 config.json 的 enabled，别的键不动。"""
    ensure()
    data = cfg()
    data["model_split"] = bool(on)
    _write(CFG, data)


# ---------------------------------------------------------------- 记录

def record(entry: dict) -> None:
    ensure()
    entry.setdefault("time", time.strftime("%Y-%m-%dT%H:%M:%S"))
    with USES.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


def uses(limit=None):
    if not USES.is_file():
        return []
    out = []
    try:
        for line in USES.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except ValueError:
                continue
            if isinstance(item, dict):
                out.append(item)
    except OSError:
        return []
    return out[-limit:] if limit else out


def probed_before(sid: str) -> bool:
    """这个对话里主代理是不是已经收到过分工建议（division == "match"）。"""
    if not sid:
        return False
    for item in reversed(uses(200)):
        if item.get("session") == sid and not item.get("child") and (item.get("combo") or {}).get("division") == "match":
            return True
    return False


# ---------------------------------------------------------------- CLI

def _tags(raw: str) -> dict:
    tags = {}
    for part in (raw or "").replace("，", ",").split(","):
        key, _, value = part.partition("=")
        if key.strip():
            tags[key.strip()] = value.strip() or "unclear"
    return tags


def refresh_gate() -> None:
    """包更新后，把已装的门换成这一版（没装过的不装；宿主配置一律不碰）。
    取规则优先：这一步出任何错都不影响分工说明。"""
    try:
        import gate_install
        gate_install.refresh_installed(HOME)
    except Exception:
        pass


def main(argv) -> int:
    parser = argparse.ArgumentParser(
        prog="starixs.py",
        description="分工：重活拆成脑、手、独立 review、验证。")
    parser.add_argument("--version", action="version", version="starixs " + VERSION)
    parser.add_argument("--set", dest="spec", help='记下用户确认的分工："%s"，或 none 表示不要建议' % _SET)
    parser.add_argument("--off", action="store_true", help="关掉分工（规则照常）")
    parser.add_argument("--on", action="store_true", help="打开分工")
    parser.add_argument("--tags", default="", help="这次活的情况：type=…,shape=…,risk=…,for=…,steps=multi")
    parser.add_argument("--from", dest="source", default="", help="子代理派活时传 派单：不再往下分")
    parser.add_argument("--host", help="覆盖宿主识别（调试用）")
    parser.add_argument("--session", help="覆盖会话编号（调试用）")
    parser.add_argument("--json", action="store_true", help="只输出记录，不输出分工说明")
    args = parser.parse_args(argv)

    refresh_gate()  # 先换门：新规则要能到已装的电脑上

    host = args.host or detect_host()
    sid = args.session or session_id()
    child = args.source.strip() == "派单"

    if args.off or args.on:
        try:
            switch(args.on)
        except OSError as error:
            print("Not changed: %s" % error)
            return 2
        print("Division of labour is " + ("on." if args.on else
                                          "off. Heavy work gets the rules without the division-of-labour note."))
        return 0

    if args.spec is not None:
        try:
            saved = save_roles(host, args.spec)
        except (ValueError, OSError) as error:
            print("Not saved: %s" % error)
            return 2
        record({"type": "set", "host": host, "value": saved})
        print("Saved: " + json.dumps(saved, ensure_ascii=False))
        return 0

    tags = _tags(args.tags)
    if not tags:
        tags = {"steps": "multi"}  # 直接运行就是「分工」：按重活给
    asked = not args.tags
    probed = probed_before(sid)
    kind, text = ("", "") if child else build(
        tags, host, enabled=cfg().get("model_split", True), probed=probed, asked=asked)

    entry = {"type": "use", "host": host, "session": sid, "child": child,
             "tags": tags, "combo": observe(tags, host, kind)}
    if args.json:
        print(json.dumps(entry, ensure_ascii=False))
        return 0
    if not text:
        return 0  # 没给说明就不记：一口气的活不占记录
    record(entry)
    print(text.rstrip("\n"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

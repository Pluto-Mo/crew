#!/usr/bin/env python3
"""自测：python3 tests/test_starixs.py。不联网，无外部依赖。"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BIN = ROOT / "scripts" / "starixs.py"
passed = failed = 0


def run(args, home, env_extra=None, cwd=None):
    env = dict(os.environ)
    env["STARIXS_HOME"] = str(home)
    for name in ("CODEX_THREAD_ID", "CODEX_HOME", "CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT",
                 "OPENCODE_SESSION_ID", "OPENCODE_TERMINAL", "KIMI_SESSION_ID", "KIMI_CODE_HOME",
                 "DSH_SESSION_ID", "DSH_HOME", "PI_SESSION_ID", "PI_CODING_AGENT_DIR", "STARIXS_HOST"):
        env.pop(name, None)
    if env_extra:
        env.update(env_extra)
    return subprocess.run([sys.executable, str(BIN), *args], capture_output=True,
                          text=True, env=env, cwd=cwd)


def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  ok   {name}")
    else:
        failed += 1
        print(f"  FAIL {name}")
        if detail:
            print("       " + str(detail)[:600])



def rule_files_text(root):
    directory = root / "references" / "rules"
    if not directory.is_dir():
        return []
    return [item.read_text(encoding="utf-8") for item in sorted(directory.glob("*.md"))]


def main():
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp) / "home"

        print("\n[1] 一口气的活不给分工")
        r = run(["--tags", "type=engineering,steps=one", "--host", "codex"], home)
        check("steps=one 什么都不出", r.stdout.strip() == "", r.stdout + r.stderr)

        print("\n[2] 重活第一次给 match，第二次同对话给 quiet")
        r = run(["--tags", "steps=multi", "--host", "codex", "--session", "s1"], home)
        check("出分工说明", "Division of labour" in r.stdout, r.stdout + r.stderr)
        check("第一次是 match（让探查宿主）", "Find out, read-only" in r.stdout, r.stdout)
        check("带着四角色", "Brain:" in r.stdout and "Verify:" in r.stdout)
        check("带着刹车（小任务严格判）", "small" in r.stdout and "at most 2 files" in r.stdout, r.stdout[:300])
        check("带着 reviewer 分级表",
              "Choose the reviewer by what a miss would cost" in r.stdout
              and "up to 200 lines" in r.stdout, r.stdout[:300])
        check("要求 --from 派单", "--from 派单" in r.stdout)

        r = run(["--tags", "steps=multi", "--host", "codex", "--session", "s1"], home)
        check("同对话第二次不再探查", "Find out, read-only" not in r.stdout, r.stdout)
        check("quiet 说已经看过", "already looked" in r.stdout, r.stdout)

        r = run(["--tags", "steps=multi", "--host", "codex", "--session", "s2"], home)
        check("新对话重新给 match", "Find out, read-only" in r.stdout, r.stdout)

        print("\n[3] 用户确认的分工")
        r = run(["--set", "brain=B;executor=E;review=R;helpers=H", "--host", "codex"], home)
        check("保存成功", "Saved" in r.stdout, r.stdout + r.stderr)
        saved = json.loads((home / "model_roles.json").read_text())
        check("存的是 codex 这一家", "codex" in saved and saved["codex"]["brain"] == "B", saved)

        r = run(["--tags", "steps=multi", "--host", "codex", "--session", "s3"], home)
        check("用上确认的分工", "the split the user confirmed" in r.stdout, r.stdout)
        check("四个值都出现", "Brain: B." in r.stdout and "on E." in r.stdout
              and "Review: R." in r.stdout and "Helpers: H." in r.stdout, r.stdout)
        check("roles 不再让探查", "Find out, read-only" not in r.stdout, r.stdout)

        print("\n[4] 宿主隔离")
        r = run(["--tags", "steps=multi", "--host", "claude", "--session", "s4"], home)
        check("另一家拿不到这家的分工", "Brain: B." not in r.stdout, r.stdout)
        r = run(["--set", "brain=B;executor=E"], home)
        check("认不出的宿主拒绝保存", r.returncode == 2 and "not recognised" in r.stdout,
              r.stdout + r.stderr)

        print("\n[5] 拒绝分工")
        r = run(["--set", "none", "--host", "codex"], home)
        check("记下 declined", "declined" in r.stdout, r.stdout)
        r = run(["--tags", "steps=multi", "--host", "codex", "--session", "s5"], home)
        check("拒绝后不探查", "Find out, read-only" not in r.stdout, r.stdout)
        check("拒绝后自己干", "chose not to set up a split" in r.stdout, r.stdout)

        print("\n[6] 帮手不再往下分")
        r = run(["--tags", "steps=multi", "--host", "codex", "--from", "派单"], home)
        check("--from 派单 不给分工", r.stdout.strip() == "", r.stdout)

        print("\n[7] 开关")
        r = run(["--off"], home)
        check("关掉", "off." in r.stdout, r.stdout)
        r = run(["--tags", "steps=multi", "--host", "codex", "--session", "s7"], home)
        check("关掉后不出说明", r.stdout.strip() == "", r.stdout)
        r = run(["--on"], home)
        check("打开", "on." in r.stdout, r.stdout)

        print("\n[8] 记录里没有型号")
        entries = [json.loads(line) for line in
                   (home / "uses.jsonl").read_text().splitlines() if line.strip()]
        combos = [e["combo"] for e in entries if "combo" in e]
        check("有 combo 记录", bool(combos), entries[:2])
        allowed = {"host", "shape", "roles_set", "division", "brake", "error"}
        keys = set()
        for item in combos:
            keys |= set(item)
        check("字段集合就是那六个", keys <= allowed, keys)

        print("\n[9] gate：每条消息的三个决定")
        gate = ROOT / "scripts" / "gate.py"
        ghome = Path(tmp) / "ghome"

        def gate_run(payload, home=ghome):
            env = dict(os.environ)
            env["STARIXS_HOME"] = str(home)
            env.pop("CODEX_THREAD_ID", None)
            env.pop("CLAUDE_CODE_SESSION_ID", None)
            return subprocess.run([sys.executable, str(gate), "claude"],
                                  input=json.dumps(payload), capture_output=True,
                                  text=True, env=env)

        r = gate_run({"session_id": "g1", "prompt": "把结算流程重做，涉及五个文件"})
        check("第一条任务消息放常驻规则", "重活四岗" in r.stdout, r.stdout[:200])
        check("第一条带四角色", "brain" in r.stdout.lower() and "verify" in r.stdout.lower())

        r = gate_run({"session_id": "g1", "prompt": "继续"})
        check("短回话不再重复放", r.stdout.strip() == "", r.stdout[:200])

        r = gate_run({"session_id": "g1", "prompt": "部署到生产环境"})
        check("不可逆动作加放两条", "收不回" in r.stdout and "不越界" in r.stdout, r.stdout[:200])

        r = gate_run({"session_id": "g2", "prompt": "<task-notification>done, pushed</task-notification>"})
        check("宿主自己的通知什么都不放", r.stdout.strip() == "", r.stdout[:200])

        r = gate_run({"session_id": "g3", "prompt": "看看这段 <pasted_content>deploy to prod</pasted_content> 有什么问题"})
        check("贴进来的材料不触发不可逆",
              "收不回" not in r.stdout and "重活四岗" in r.stdout, r.stdout[:200])
        r = gate_run({"session_id": "g3b", "prompt": "<pasted_content>deploy to prod</pasted_content>"})
        check("整条都是贴进来的，那块就是用户的话（设计如此）",
              "收不回" in r.stdout, r.stdout[:200])

        r = gate_run({"session_id": "g4", "hook_event_name": "SessionStart", "source": "compact"})
        check("压缩后重新放一次", "重活四岗" in r.stdout, r.stdout[:200])

        (ghome / "switch.json").write_text(json.dumps({"all_off": True}))
        r = gate_run({"session_id": "g5", "prompt": "重做一个模块"})
        check("关掉后什么都不放", r.stdout.strip() == "", r.stdout[:200])
        (ghome / "switch.json").write_text(json.dumps({"off_sessions": {"g6": 1}}))
        check("单对话关掉只管那一个",
              gate_run({"session_id": "g6", "prompt": "重做一个模块"}).stdout.strip() == ""
              and "重活四岗" in gate_run({"session_id": "g7", "prompt": "重做一个模块"}).stdout)
        (ghome / "switch.json").unlink()

        r = gate_run({"session_id": "g8", "prompt": "x" * 400})
        r2 = subprocess.run([sys.executable, str(gate), "claude"], input="not json",
                            capture_output=True, text=True,
                            env=dict(os.environ, STARIXS_HOME=str(ghome)))
        check("坏输入也退出 0", r2.returncode == 0, r2.returncode)
        r3 = subprocess.run([sys.executable, str(gate), "--self-test"], capture_output=True,
                            text=True, env=dict(os.environ, STARIXS_HOME=str(ghome)))
        check("自检报告规则读得到", "readable" in r3.stdout and "NOT" not in r3.stdout, r3.stdout)

        log = (ghome / "gate.jsonl").read_text().strip().splitlines()
        rows = [json.loads(line) for line in log]
        check("每条消息记一行", len(rows) >= 6, len(rows))
        check("记录里没有消息正文",
              all("把结算流程重做" not in json.dumps(row) for row in rows))
        check("记录字段里没有 content/prompt",
              not any("prompt" in row or "content" in row for row in rows), rows[0])

        print("\n[10] 包内没有型号名和档位名")
        import re
        text = "".join((ROOT / "scripts" / name).read_text()
                       for name in ("starixs.py", "gate.py", "paths.py", "gate_install.py"))
        for doc in (ROOT / "SKILL.full.md", ROOT / "skills" / "crew" / "SKILL.md"):
            if doc.is_file():
                text += doc.read_text()
        for rule in rule_files_text(ROOT):
            text += rule
        hosts = {"codex", "claude", "opencode", "kimi", "dsh", "pi", "其他",
                 "kimi-code", "deepseek", "deepseek harness", "claude code", "kimi code"}
        hits = re.findall(r"gpt-[0-9a-z.\-]*|claude-[a-z0-9.\-]+|opus|sonnet|haiku|fable|"
                          r"deepseek|qwen|glm-|grok-|gemini|kimi-[a-z0-9.\-]+", text, re.I)
        hits = [h for h in hits if h.lower() not in hosts]
        check("没有硬编码型号", not hits, hits)
        effort = re.findall(r'"(?:low|medium|high|xhigh|max|ultra)"', text)
        check("没有硬编码档位", not effort, effort)


        print("\n[12] 门会自动更新，且不会被旧包降级")
        ghome2 = Path(tmp) / "ghome2"
        # 造一个"已装门"的目录：先不带版本戳（模拟老版本装的）
        ghome2.mkdir(parents=True, exist_ok=True)
        gate_src = (ROOT / "scripts" / "gate.py").read_text()
        stamped = gate_src
        old = "\n".join(l for l in stamped.splitlines() if "GATE_PACKAGE_VERSION" not in l)
        (ghome2 / "gate.py").write_text(old + "\n")
        (ghome2 / "gate_rules.json").write_text("{}\n")

        env = dict(os.environ, STARIXS_HOME=str(ghome2))
        code = (
            "import sys; sys.path.insert(0, %r)\n"
            "import gate_install\n"
            "print(gate_install.refresh_installed(%r))\n"
            "print(gate_install._stamp(open(%r).read()))\n"
        ) % (str(ROOT / "scripts"), str(ghome2), str(ghome2 / "gate.py"))
        r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env)
        lines = r.stdout.strip().splitlines()
        check("无版本戳的旧门会被升级", lines and lines[0] == "True", r.stdout + r.stderr)
        check("升级后带上版本戳", len(lines) > 1 and lines[1] != "", r.stdout + r.stderr)
        check("规则文件也补上了", len(json.loads((ghome2 / "gate_rules.json").read_text())) >= 3,
              (ghome2 / "gate_rules.json").read_text()[:100])

        # 更新的门不能被旧包换回去
        (ghome2 / "gate.py").write_text(
            gate_src.replace('GATE_PACKAGE_VERSION = ""', 'GATE_PACKAGE_VERSION = "99.0.0"')
            if 'GATE_PACKAGE_VERSION = ""' in gate_src
            else gate_src.split("VERSION = ")[0]
            + 'GATE_PACKAGE_VERSION = "99.0.0"\nVERSION = "99.0.0"\n'
            + gate_src.split("VERSION = ", 1)[1].split("\n", 1)[1])
        r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env)
        check("更新版本的门不会被旧包换回去", r.stdout.strip().splitlines()[0] == "False",
              r.stdout + r.stderr)

        # 没装过的不装
        empty = Path(tmp) / "ghome3"
        empty.mkdir()
        code3 = ("import sys; sys.path.insert(0, %r)\nimport gate_install\n"
                 "print(gate_install.refresh_installed(%r))\n") % (str(ROOT / "scripts"), str(empty))
        r = subprocess.run([sys.executable, "-c", code3], capture_output=True, text=True, env=env)
        check("没装过门就不装", r.stdout.strip() == "False", r.stdout + r.stderr)
        check("确实没写文件", not (empty / "gate.py").exists())

        print("\n[11] 自审：无网络、无凭据、无 shell")
        bad = {
            "network": r"\b(socket|urllib|http\.client|requests|urlopen|smtplib|ftplib)\b",
            "eval/exec": r"(?<!re\.)\b(eval|exec|compile|__import__)\s*\(",
            "credentials": r"(auth\.json|\.ssh|keychain|Keychain|password|secret)",
            "shell=True": r"shell\s*=\s*True",
        }
        for label, pattern in bad.items():
            found = re.findall(pattern, text, re.I)
            check("没有 " + label, not found, found)
        check("subprocess 只用于读了也白读的地方", "subprocess." not in text, "found subprocess")
        print("  (参照实现里也没有 subprocess；本版保持一致)")

        print("\n[13] skill 目录与仓库根同步（分发时不能漂移）")
        import subprocess as _sp
        r = _sp.run([sys.executable, str(ROOT / "sync.py"), "--check"],
                    capture_output=True, text=True)
        check("skills/crew 与根目录一致", r.returncode == 0, r.stdout + r.stderr)

    print(f"\n{passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

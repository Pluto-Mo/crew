#!/usr/bin/env python3
"""Install starixs as a skill for the agent CLIs on this machine, with the gate hook.

Two things get installed:

1. The skill — SKILL.md, config.json, scripts/, references/rules/ into a skill directory.
2. The gate — a plain-text copy of gate.py plus gate_rules.json in the state directory,
   and the host wiring so it runs on every user message.

Default is a dry run: it prints exactly what it would write and changes nothing.
Nothing outside the listed paths is touched, and no file that is not ours is
overwritten without --force.

    python3 install.py                          # show the plan (skill + gate)
    python3 install.py --apply                  # skill only
    python3 install.py --apply --with-gate      # skill + gate hook
    python3 install.py --apply --with-gate --target codex
    python3 install.py --with-gate --check      # is the hook in place?
    python3 install.py --uninstall              # remove what this script wrote
"""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
MARKER = "starixs-skill.json"

TARGETS = {
    "agents": Path.home() / ".agents" / "skills" / "crew",
    "codex": Path.home() / ".agents" / "skills" / "crew",
    "claude": Path.home() / ".claude" / "skills" / "crew",
}

FILES = ["skills/crew/SKILL.md", "config.json", "scripts/starixs.py", "scripts/gate.py",
         "scripts/gate_install.py", "scripts/paths.py"]
RULE_DIR = "references/rules"


def rule_files():
    directory = HERE / RULE_DIR
    return sorted(p.name for p in directory.glob("*.md")) if directory.is_dir() else []


def plan(targets, with_gate):
    steps = []
    for name in targets:
        dest = TARGETS[name]
        if dest.exists() and not (dest / MARKER).is_file():
            steps.append(("SKIP", dest, "exists and was not installed by this script"))
            continue
        steps.append(("WRITE", dest, ", ".join(FILES) + ", " + RULE_DIR + "/*.md"))
    if with_gate:
        steps.append(("RUN", HERE / "scripts" / "gate_install.py",
                      "python3 gate_install.py --apply  (dry run shown below)"))
    return steps


def apply_skill(targets, force):
    written = []
    for name in targets:
        dest = TARGETS[name]
        if dest.exists() and not (dest / MARKER).is_file() and not force:
            print("skip " + str(dest) + " (not ours; use --force to overwrite)")
            continue
        dest.mkdir(parents=True, exist_ok=True)
        for rel in FILES:
            source = HERE / rel
            if not source.is_file():
                print("missing source: " + str(source))
                return 1
            # The skill text is authored at skills/<name>/SKILL.md but must land
            # at the root of the installed skill folder.
            out = dest / (rel.split("/")[-1] if rel.startswith("skills/") else rel)
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, out)
        rules = rule_files()
        (dest / RULE_DIR).mkdir(parents=True, exist_ok=True)
        for rule in rules:
            shutil.copy2(HERE / RULE_DIR / rule, dest / RULE_DIR / rule)
        (dest / MARKER).write_text(json.dumps({
            "installed_from": str(HERE),
            "target": name,
            "entry": "python3 " + str(dest / "scripts" / "starixs.py"),
            "gate": "python3 " + str(dest / "scripts" / "gate_install.py"),
        }, indent=1), encoding="utf-8")
        written.append(dest)
        print("wrote " + str(dest) + " (%d files + %d rules)" % (len(FILES), len(rules)))
    return 0


def gate_hosts(targets):
    """「agents」是 skill 目录的别名，不是宿主名；装门时用实际宿主名。"""
    mapping = {"agents": "codex", "codex": "codex", "claude": "claude"}
    return list(dict.fromkeys(mapping[name] for name in targets if name in mapping))


def run_gate_install(extra):
    script = HERE / "scripts" / "gate_install.py"
    if not script.is_file():
        print("missing " + str(script))
        return 1
    return subprocess.call([sys.executable, str(script), *extra])


def do_uninstall(purge=False):
    """删掉这份 installer 写进 skill 目录的东西。

    --purge 连门和本地状态一起撤，一条命令干净。不带时只删 skill 目录，
    并告诉用户还剩什么。
    """
    removed = []
    for name, dest in TARGETS.items():
        if not (dest / MARKER).is_file():
            continue
        shutil.rmtree(dest, ignore_errors=True)
        removed.append(str(dest))
        print("removed " + str(dest))
    # 用户用 npx skills add 装的目录没有我们的标记，但也是同一个 skill
    for name, dest in TARGETS.items():
        if dest.is_dir() and (dest / "SKILL.md").is_file() and (dest / "scripts" / "starixs.py").is_file():
            shutil.rmtree(dest, ignore_errors=True)
            removed.append(str(dest))
            print("removed " + str(dest) + " (installed by skills add)")
    if purge:
        return run_gate_install(["--uninstall", "--purge"])
    if removed:
        print("\nSkill removed. The gate hook may still be in place.")
        print("Remove it too: python3 scripts/gate_install.py --uninstall")
        print("Remove everything: python3 install.py --uninstall --purge")
    else:
        print("Nothing to remove from the skill folders.")
        print("Check the gate: python3 scripts/gate_install.py --check")
    return 0


def main(argv):
    parser = argparse.ArgumentParser(description="Install starixs as an agent skill.")
    parser.add_argument("--apply", action="store_true", help="actually write (default is a dry run)")
    parser.add_argument("--force", action="store_true", help="overwrite a directory we did not create")
    parser.add_argument("--uninstall", action="store_true", help="remove the skill folders")
    parser.add_argument("--purge", action="store_true", help="with --uninstall: also remove the gate and local state")
    parser.add_argument("--with-gate", action="store_true", help="also install the per-message gate hook")
    parser.add_argument("--check", action="store_true", help="report whether the gate hook is in place")
    parser.add_argument("--target", action="append", choices=sorted(TARGETS),
                        help="limit to one host; repeatable")
    args = parser.parse_args(argv)

    if args.check:
        return run_gate_install(["--check"])
    if args.uninstall:
        return do_uninstall(purge=args.purge)

    targets = args.target or ["agents"]
    if not args.apply:
        print("Dry run. Nothing was changed. Add --apply to write.\n", flush=True)
        for action, dest, note in plan(targets, args.with_gate):
            print("%-6s %s\n       %s" % (action, dest, note))
        print("\nReads: nothing outside this package. State and gate go to " +
              str(Path.home() / ".local" / "share" / "starixs"))
        if args.with_gate:
            print("\nGate plan (still a dry run):", flush=True)
            run_gate_install(["--host", *gate_hosts(targets)])
        return 0

    code = apply_skill(targets, args.force)
    if code:
        return code
    if args.with_gate:
        return run_gate_install(["--apply", "--host", *gate_hosts(targets)])
    print("\nSkill installed. To add the per-message gate hook: --with-gate")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

#!/usr/bin/env node
"use strict";

/**
 * starixs — npm entry point.
 *
 * A thin wrapper: all logic lives in the Python scripts, so the package stays
 * one implementation with one test suite. This file only finds a usable
 * interpreter, forwards argv, and turns the two common failure modes into a
 * readable message instead of a stack trace.
 */

const { spawnSync } = require("child_process");
const { existsSync } = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");
const INSTALL = path.join(ROOT, "install.py");
const GATE_INSTALL = path.join(ROOT, "scripts", "gate_install.py");
const GATE = path.join(ROOT, "scripts", "gate.py");
const SPLIT = path.join(ROOT, "scripts", "starixs.py");
const TESTS = path.join(ROOT, "tests", "test_starixs.py");

const PYTHON_CANDIDATES =
  process.platform === "win32" ? ["py", "python", "python3"] : ["python3", "python"];

function findPython() {
  for (const candidate of PYTHON_CANDIDATES) {
    const probe = spawnSync(candidate, ["-c", "import sys; print(sys.version_info[0])"], {
      encoding: "utf8",
    });
    if (probe.status === 0 && String(probe.stdout).trim() === "3") return candidate;
  }
  return null;
}

function run(python, script, args) {
  const child = spawnSync(python, [script, ...args], { stdio: "inherit" });
  return child.status === null ? 1 : child.status;
}

function usage() {
  console.log(`starixs — division of labour for heavy work

  npx @starixs/crew setup                         skill + hook, one command
  npx @starixs/crew install [--with-gate] [--target codex|claude|agents]
  npx @starixs/crew install --apply --with-gate   write it
  npx @starixs/crew check                         is the hook wired?
  npx @starixs/crew uninstall
  npx @starixs/crew test

  npx @starixs/crew plan --tags ...               the split for a task
  npx @starixs/crew --set "brain=X;executor=Y"    pin a split for this host
  npx @starixs/crew --set none                    decline for this host
  npx @starixs/crew --off | --on                  stop or resume the note

Nothing is written without --apply. Nothing is uploaded, ever.
State goes to ~/.local/share/starixs (STARIXS_HOME overrides).
`);
}

function main(argv) {
  const command = argv[0];
  const rest = argv.slice(1);

  if (!command || command === "--help" || command === "-h" || command === "help") {
    usage();
    return 0;
  }

  const python = findPython();
  if (!python) {
    console.error(
      "starixs needs Python 3.9 or newer, and could not find a `python3` on PATH.\n" +
        "Install Python (python.org or your package manager) and run this again."
    );
    return 1;
  }

  // `install` defaults to a dry run; --apply is required to write.
  if (command === "install") {
    if (!existsSync(INSTALL)) {
      console.error("Package looks incomplete: " + INSTALL + " is missing.");
      return 1;
    }
    return run(python, INSTALL, rest);
  }

  if (command === "setup") {
    // One command: skill folder + gate. Idempotent.
    const skill = run(python, INSTALL, ["--apply", "--with-gate", ...rest]);
    if (skill) return skill;
    return run(python, GATE_INSTALL, ["--check"]);
  }

  if (command === "check") {
    return run(python, GATE_INSTALL, ["--check"]);
  }

  if (command === "uninstall") {
    const skill = run(python, INSTALL, ["--uninstall"]);
    const gate = run(python, GATE_INSTALL, ["--uninstall"]);
    return skill || gate;
  }

  if (command === "gate") {
    return run(python, GATE, rest);
  }

  if (command === "plan") {
    // `plan --tags ...` is the same thing as passing --tags directly.
    return run(python, SPLIT, rest);
  }

  // Anything else that looks like a flag is the split command itself:
  // `npx @starixs/crew --tags ...`, `--set ...`, `--off`, `--on`.
  if (command.startsWith("-")) {
    return run(python, SPLIT, argv);
  }

  if (command === "test") {
    return run(python, TESTS, rest);
  }

  console.error("Unknown command: " + command + "\n");
  usage();
  return 1;
}

process.exit(main(process.argv.slice(2)));

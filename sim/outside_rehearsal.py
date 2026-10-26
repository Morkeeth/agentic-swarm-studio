"""Fresh, no-Docker rehearsal over three public command-line tools."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from sim.adapters import tokenfactory

SEEDS = (7, 13, 29)
SYSTEM = (
    "You are a release-test visitor using one command-line tool. "
    "Return exactly one JSON object with one key, args, whose value is an array of arguments. "
    "Do not include the executable, prose, markdown, shell operators, redirects, or absolute paths."
)
TASKS = (
    {
        "id": "git",
        "command": "git",
        "name": "Git",
        "source": "https://github.com/git/git",
        "task": "List only the file paths changed from tag fixture-base to tag fixture-head, one path per line.",
        "canonical": ["diff", "--name-only", "fixture-base", "fixture-head"],
        "expected": "db/migrations/002_add_owner.sql\nsrc/app.py\n",
    },
    {
        "id": "ripgrep",
        "command": "rg",
        "name": "ripgrep",
        "source": "https://github.com/BurntSushi/ripgrep",
        "task": "Find the exact fixed string ERROR_TOKEN in this directory, include line numbers, and respect .ignore.",
        "canonical": ["-n", "-F", "ERROR_TOKEN", "."],
        "expected": "./src/app.log:2:ERROR_TOKEN\n",
    },
    {
        "id": "jq",
        "command": "jq",
        "name": "jq",
        "source": "https://github.com/jqlang/jq",
        "task": "Read records.json, sort the records by name, and return each name and value as tab-separated text.",
        "canonical": ["-r", "sort_by(.name)[] | [.name,.value] | @tsv", "records.json"],
        "expected": "alpha\t1\nbeta\t2\n",
    },
)


def run(command, cwd):
    try:
        value = subprocess.run(command, cwd=cwd, text=True, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, timeout=15, check=False)
        return {"returncode": value.returncode, "output": value.stdout[:12000]}
    except subprocess.TimeoutExpired:
        return {"returncode": 124, "output": "Command timed out."}


def fixtures(root: Path):
    git_root = root / "git"; git_root.mkdir()
    run(["git", "init", "-q"], git_root)
    run(["git", "config", "user.email", "rehearsal@example.invalid"], git_root)
    run(["git", "config", "user.name", "Release Rehearsal"], git_root)
    (git_root / "src").mkdir(); (git_root / "src/app.py").write_text("print('one')\n")
    run(["git", "add", "."], git_root); run(["git", "commit", "-qm", "base"], git_root); run(["git", "tag", "fixture-base"], git_root)
    (git_root / "src/app.py").write_text("print('two')\n")
    (git_root / "db/migrations").mkdir(parents=True); (git_root / "db/migrations/002_add_owner.sql").write_text("alter table jobs add owner text;\n")
    run(["git", "add", "."], git_root); run(["git", "commit", "-qm", "head"], git_root); run(["git", "tag", "fixture-head"], git_root)

    rg_root = root / "ripgrep"; (rg_root / "src").mkdir(parents=True); (rg_root / "vendor").mkdir()
    (rg_root / ".ignore").write_text("vendor/\n")
    (rg_root / "src/app.log").write_text("ready\nERROR_TOKEN\n")
    (rg_root / "vendor/noise.log").write_text("ERROR_TOKEN\n")

    jq_root = root / "jq"; jq_root.mkdir()
    (jq_root / "records.json").write_text('[{"name":"beta","value":2},{"name":"alpha","value":1}]\n')
    return {"git": git_root, "ripgrep": rg_root, "jq": jq_root}


def parse_args(raw: str, tool_id: str):
    value = json.loads(raw)
    args = value.get("args") if isinstance(value, dict) and set(value) == {"args"} else None
    if not isinstance(args, list) or not args or len(args) > 20 or not all(isinstance(arg, str) and arg and "\0" not in arg for arg in args):
        raise ValueError("Model did not return a bounded argument array.")
    if any(arg in {"|", ">", ">>", "<", ";", "&&", "||"} for arg in args):
        raise ValueError("Shell syntax is not allowed.")
    if any(Path(arg).is_absolute() or arg == ".." or arg.startswith("../") or "/../" in arg for arg in args):
        raise ValueError("Arguments must stay inside the frozen fixture directory.")
    allowed = {
        "git": {"diff", "--name-only", "fixture-base", "fixture-head", "fixture-base..fixture-head"},
        "ripgrep": {"-n", "--line-number", "-F", "--fixed-strings", "ERROR_TOKEN", ".", "--ignore-file=.ignore"},
        "jq": {"-r", "--raw-output", "sort_by(.name)[] | [.name,.value] | @tsv", "records.json"},
    }
    if tool_id not in allowed or any(arg not in allowed[tool_id] for arg in args):
        raise ValueError("The proposed invocation exceeds this task's read-only argument allowlist.")
    return args


def version(executable):
    result = run([executable, "--version"], None)
    return result["output"].splitlines()[0][:200] if result["returncode"] == 0 else "version unavailable"


def check_passes(task, observed):
    if observed["returncode"] != 0:
        return False
    actual = observed["output"]
    if task["id"] == "ripgrep":
        actual = "\n".join(line.removeprefix("./") for line in actual.splitlines()) + ("\n" if actual else "")
        expected = task["expected"].removeprefix("./")
        return actual == expected
    return actual == task["expected"]


def execute(output: Path):
    missing = [task["command"] for task in TASKS if shutil.which(task["command"]) is None]
    if missing:
        raise SystemExit("Missing required public tools: " + ", ".join(missing))
    model = os.environ.get(tokenfactory.MODEL_ENV, "").strip()
    if not tokenfactory.model_requirement(model)["nvidia_nemotron_candidate"]:
        raise SystemExit("Set TOKEN_FACTORY_MODEL to the exact NVIDIA Nemotron model ID.")
    client = tokenfactory.client()
    rows = []
    with tempfile.TemporaryDirectory(prefix="outside-rehearsal-") as temp:
        roots = fixtures(Path(temp))
        for task in TASKS:
            control = run([task["command"], *task["canonical"]], roots[task["id"]])
            control["passed"] = check_passes(task, control)
            if not control["passed"]:
                raise RuntimeError(f"Controller control failed for {task['name']}; no agent result was published.")
            attempts = []
            for seed in SEEDS:
                prompt = (
                    f"Tool: {task['name']}\nTask: {task['task']}\n"
                    "All fixture paths are relative to the current directory. Choose the arguments now."
                )
                reply = client.chat([{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
                                    seed=seed, temperature=0, max_tokens=256,
                                    chat_template_kwargs={"enable_thinking": False})
                if reply.model != model:
                    raise RuntimeError("Provider response did not match the configured Nemotron model.")
                attempt = {"seed": seed, "model": reply.model, "usage": reply.usage,
                           "finish_reason": reply.finish_reason, "reply": reply.text[:2000]}
                try:
                    args = parse_args(reply.text, task["id"])
                    observed = run([task["command"], *args], roots[task["id"]])
                    attempt.update(args=args, **observed)
                    attempt["passed"] = check_passes(task, observed)
                    attempt["classification"] = "completed" if attempt["passed"] else "agent_or_interface_failure"
                except (ValueError, json.JSONDecodeError) as error:
                    attempt.update(passed=False, classification="agent_format_failure", error=str(error))
                attempts.append(attempt)
            passed = sum(row["passed"] for row in attempts)
            failures = [row for row in attempts if not row["passed"]]
            if not failures:
                finding = "No checked failure in this rehearsal."
            elif all(row["classification"] == "agent_format_failure" for row in failures):
                finding = f"{len(failures)} visitor response failure(s); the tool's canonical control passed."
            else:
                finding = f"{len(failures)} checked agent or interface failure(s); the tool's canonical control passed."
            rows.append({
                "id": task["id"], "name": task["name"], "source": task["source"],
                "version": version(task["command"]), "task": task["task"], "control": control,
                "attempts": attempts, "passed": passed, "attempted": len(attempts),
                "headline": f"{passed} of {len(attempts)} visitors completed the checked task.",
                "finding": finding,
            })
    payload = {
        "schema": "outside-rehearsal/1", "status": "complete",
        "finished_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "model": model, "provider": "Nebius Token Factory", "visitors_per_tool": len(SEEDS),
        "scope": "Fresh agent attempts on installed releases of three public tools. A failure is not called a tool defect when the canonical control passes.",
        "tools": rows,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.is_file():
        history = output.parent / "outside-runs"; history.mkdir(exist_ok=True)
        prior = json.loads(output.read_text())
        stamp = prior.get("finished_at", "unknown").replace(":", "-")
        os.replace(output, history / f"{stamp}.json")
    temporary = output.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, output)
    return payload


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(execute(args.output)))


if __name__ == "__main__":
    main()

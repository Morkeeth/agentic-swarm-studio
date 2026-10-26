"""Five-app review shop built on the read-only browser swarm.

Ultra plans the batch and triages candidate defects. Nano drives visitors.
Super VL checks completion claims against the final screen. A candidate is not
published as a defect until a human confirmation file marks it real.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import re
import time

from sim import app_swarm, hosted_cost, tool_trial
from sim.adapters import tokenfactory
from sim.adapters.openai_compat import ChatClient

CAP_USD = 5.0
APPS = (
    {"id": "store", "kind": "Store", "name": "Vercel Commerce demo", "url": "https://demo.vercel.store",
     "goal": "Find a black hoodie and open its product page"},
    {"id": "saas", "kind": "SaaS signup", "name": "Linear", "url": "https://linear.app",
     "goal": "Find where a new team starts using Linear"},
    {"id": "booking", "kind": "Booking", "name": "Cal.com", "url": "https://cal.com",
     "goal": "Find where a company can book a Cal.com demo"},
    {"id": "docs", "kind": "Documentation", "name": "Nebius docs", "url": "https://docs.nebius.com",
     "goal": "Find the Token Factory quickstart"},
    {"id": "vibe", "kind": "Vibe-coded app", "name": "Agentic Swarm Simulator", "url": "https://agentic-swarm-studio-568004190078.us-central1.run.app/studio",
     "goal": "Open a recorded swarm and find why one visitor got stuck"},
)


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def client(model, timeout=90):
    return ChatClient(base_url=tokenfactory.BASE_URL, model=model, label="RUNTIME",
                      api_key=tokenfactory.load_key(), timeout=timeout)


def _json_object(text):
    match = re.search(r"\{.*\}", text or "", re.S)
    if not match:
        raise ValueError("Model reply held no JSON object.")
    return json.loads(match.group(0))


def spent(prefix):
    try:
        rows = json.loads(hosted_cost.RECORD.read_text()).get("runs", {})
    except FileNotFoundError:
        return 0.0
    return sum(float(row.get("accounted_usd", 0)) for key, row in rows.items() if key.startswith(str(prefix)))


def ultra_call(store, label, system, payload):
    if spent(store) >= CAP_USD:
        raise ValueError("The review-shop USD 5 stop is reached.")
    budget = app_swarm.Budget(str(store), 1, run_cap_usd=CAP_USD - spent(store))
    reply, call = budget.call(client(hosted_cost.ULTRA_MODEL), [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ], label + "-" + now(), 0)
    return _json_object(reply.text), call


def plan(store, apps=APPS):
    system = """Plan a read-only first-use review across five web apps. Return one JSON object:
{"apps":[{"id":"...","risk":"at most 18 words","success":"observable screen evidence, at most 18 words"}]}
Keep every supplied id and goal. Do not add actions that type, sign in, buy, upload, submit, or save."""
    return ultra_call(store, "ultra-plan", system, {"apps": list(apps)})


def candidate_rows(results):
    rows = []
    for result in results:
        for index, finding in enumerate(result.get("findings") or []):
            evidence = finding.get("evidence") or []
            rows.append({
                "id": f"{result['id']}-F{index + 1}", "app": result["id"], "kind": finding.get("kind"),
                "title": finding.get("title"), "page": finding.get("page"),
                "what_happened": finding.get("what_happened"), "page_text": (finding.get("page_text") or "")[:1200],
                "screenshots": [e.get("screenshot") for e in evidence if e.get("screenshot")],
                "visitor_evidence": [{k: e.get(k) for k in ("name", "goal", "step", "said")} for e in evidence],
            })
    return rows


def triage(store, candidates):
    system = """You are the final defect judge for a read-only browser swarm. Return one JSON object:
{"decisions":[{"id":"...","class":"product_defect|missing_feature|usability_risk|agent_failure|simulator_limit|insufficient_evidence","why":"at most 24 words"}]}
Count a product defect only with direct page evidence of a broken response or contradiction. A visitor giving up is not a defect.
Count a missing feature only when the stated goal is normal for this app and the supplied page evidence shows the feature or route is absent.
Treat blocked writes, sign-in boundaries, model confusion, timeouts, and the read-only policy as non-product findings."""
    if not candidates:
        return ({"decisions": []}, {"call": "not-needed", "model": hosted_cost.ULTRA_MODEL, "accounted_usd": 0, "ms": 0})
    return ultra_call(store, "ultra-triage", system, {"candidates": candidates})


def human_map(path):
    if not path or not Path(path).is_file():
        return {}
    data = json.loads(Path(path).read_text())
    rows = data.get("findings", [])
    if not isinstance(rows, list):
        raise ValueError("Human confirmations must contain a findings list.")
    checked = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str) or type(row.get("confirmed")) is not bool:
            raise ValueError("Each human confirmation needs an id and an explicit true or false decision.")
        if not isinstance(row.get("reviewer"), str) or not row["reviewer"].strip():
            raise ValueError(f"{row.get('id', 'Finding')} needs the name of the person who checked it.")
        if not isinstance(row.get("method"), str) or not row["method"].strip():
            raise ValueError(f"{row['id']} needs the human check method.")
        if row["confirmed"] and (not isinstance(row.get("reproduced_against"), str) or not row["reproduced_against"].strip()):
            raise ValueError(f"{row['id']} cannot be confirmed without the intended app runtime used for reproduction.")
        checked[row["id"]] = row
    return checked


def full_report(batch, confirmations=None):
    confirmations = confirmations or {}
    decisions = {row["id"]: row for row in (batch.get("triage") or {}).get("decisions", [])}
    candidates = batch.get("candidates") or []
    for row in candidates:
        row["model_judgement"] = decisions.get(row["id"], {"class": "insufficient_evidence", "why": "No final judgement."})
        row["human_confirmation"] = confirmations.get(row["id"], {"confirmed": None, "note": "Not checked by a human."})
    confirmed = [row for row in candidates if row["human_confirmation"].get("confirmed") is True]
    reviewed = [row for row in candidates if row["human_confirmation"].get("confirmed") in (True, False)]
    precision = (len(confirmed) / len(reviewed)) if reviewed else None
    apps = []
    for result in batch.get("results", []):
        visitors = (result.get("tries") or [[]])[0]
        calls = (result.get("spend") or {}).get("calls", [])
        opened = any(check.get("label") == "The page loads" and check.get("status") == "passed"
                     for check in result.get("baseline", []))
        coverage = "visited" if opened and calls else "browser_failed_before_model" if not opened else "no_model_call"
        apps.append({
            "id": result["id"], "name": result.get("app_name"), "kind": result.get("app_kind"), "url": result.get("url"),
            "goal": (result.get("job") or {}).get("text"), "headline": result.get("headline"),
            "what_works": [check for check in result.get("baseline", []) if check.get("status") == "passed"],
            "where_people_leave": [{"visitor": v.get("name"), "outcome": v.get("outcome"), "last": (v.get("steps") or [{}])[-1].get("url")} for v in visitors if v.get("outcome") != "got_there"],
            "candidate_ids": [row["id"] for row in candidates if row["app"] == result["id"]],
            "coverage": coverage, "models": (result.get("spend") or {}).get("models", []), "calls": calls,
            "elapsed_ms": result.get("elapsed_ms"), "cost_usd": result.get("model_cost_usd", 0),
        })
    visited = sum(row["coverage"] == "visited" for row in apps)
    return {"generated_at": now(), "status": "complete" if visited == len(apps) else "incomplete",
            "coverage": {"apps_planned": len(apps), "apps_visited": visited,
                         "reason": None if visited == len(apps) else "Browser startup failed before Nano could visit."},
            "apps": apps, "findings": candidates,
            "precision": {"confirmed_real": len(confirmed), "human_reviewed": len(reviewed), "value": precision,
                          "label": "not measured" if precision is None else f"{len(confirmed)} of {len(reviewed)}"},
            "configured_models": batch.get("models"), "spend": batch.get("spend"),
            "limits": ["Software visitors are not people.", "The browser was read-only; sign-in, typing, saving, buying and submitting were not tested.",
                       "A candidate is not reported as real until a human checks its screenshot and page evidence."]}


def execute(store, apps=APPS, confirmations=None, visitors=2):
    store = Path(store); store.mkdir(parents=True, exist_ok=True)
    os.environ[hosted_cost.JUDGE_MODEL_ENV] = hosted_cost.JUDGE_MODEL
    planned, plan_call = plan(store / "cost", apps)
    results = []
    for app in apps:
        if spent(store) >= CAP_USD:
            raise ValueError("The review-shop USD 5 stop was reached before the next app.")
        folder = store / "runs" / app["id"]; folder.mkdir(parents=True, exist_ok=True)
        people = [{**p, "goal": app["goal"]} for p in app_swarm.personas_for(app["goal"])[:visitors]]
        tool_trial.dump(folder / "result.json", {"id": app["id"], "app_name": app["name"], "app_kind": app["kind"],
                                                 "url": app["url"], "job": {"text": app["goal"], "source": "you"},
                                                 "tries_planned": 1, "status": "queued"})
        result = app_swarm.run(folder, personas=people, run_cap_usd=min(0.75, CAP_USD - spent(store)))
        result.update({"app_name": app["name"], "app_kind": app["kind"]}); tool_trial.dump(folder / "result.json", result)
        results.append(result)
    candidates = candidate_rows(results)
    judged, triage_call = triage(store / "cost", candidates)
    batch = {"schema": "full-review-shop/1", "started_at": now(), "plan": planned, "results": results,
             "candidates": candidates, "triage": judged,
             "models": {"planning": hosted_cost.ULTRA_MODEL, "steps": hosted_cost.MODEL,
                        "screen_judge": hosted_cost.JUDGE_MODEL, "final_judge": hosted_cost.ULTRA_MODEL},
             "model_calls": {"plan": plan_call, "triage": triage_call},
             "spend": {"cap_usd": CAP_USD, "accounted_usd": spent(store), "price_source": hosted_cost.PRICE_SOURCE}}
    tool_trial.dump(store / "batch.json", batch)
    report = full_report(batch, human_map(confirmations)); tool_trial.dump(store / "report.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description="Run the five-app Nemotron review shop")
    parser.add_argument("--store", required=True); parser.add_argument("--confirmations"); parser.add_argument("--visitors", type=int, default=2)
    args = parser.parse_args()
    if not 1 <= args.visitors <= 3: raise SystemExit("Choose 1 to 3 visitors per app.")
    report = execute(args.store, confirmations=args.confirmations, visitors=args.visitors)
    print(json.dumps({"status": report["status"], "coverage": report["coverage"],
                      "precision": report["precision"], "spend": report["spend"]}, indent=2))


if __name__ == "__main__":
    main()

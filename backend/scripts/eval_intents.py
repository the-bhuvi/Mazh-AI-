import sys
import json
import time
import asyncio
import numpy as np
from pathlib import Path

# Ensure sys.path contains backend directory
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.llm.client import LLMClient

async def evaluate_intents(cases_file: str):
    cases_path = Path(cases_file)
    if not cases_path.exists():
        print(f"Error: intent cases file not found at {cases_path}")
        return

    with open(cases_path, "r", encoding="utf-8") as f:
        cases = json.load(f)

    llm = LLMClient()
    total_cases = len(cases)
    intent_matches = 0
    loc_matches = 0
    latencies = []

    print(f"\n--- Running Intent Evaluation Benchmark on {total_cases} test cases ---")

    for case in cases:
        case_id = case["id"]
        msg = case["message"]
        exp_intent = case["expected_intent"]
        exp_loc = case.get("expected_location")

        t0 = time.time()
        res = await llm.parse_intent(msg)
        elapsed_ms = (time.time() - t0) * 1000.0
        latencies.append(elapsed_ms)

        parsed_intent = res["intent"]
        parsed_loc = res.get("location")

        intent_correct = (parsed_intent == exp_intent)
        if intent_correct:
            intent_matches += 1

        loc_correct = False
        if exp_loc is None and parsed_loc is None:
            loc_correct = True
        elif exp_loc and parsed_loc and (exp_loc.lower() in str(parsed_loc).lower() or str(parsed_loc).lower() in exp_loc.lower()):
            loc_correct = True

        if loc_correct:
            loc_matches += 1

        status_mark = "PASS" if intent_correct else "FAIL"
        print(f"[{status_mark}] Case {case_id}: '{msg}' -> Intent: {parsed_intent} (exp: {exp_intent}) | Loc: {parsed_loc} | Latency: {round(elapsed_ms, 1)} ms")

    intent_acc = (intent_matches / total_cases) * 100.0
    loc_acc = (loc_matches / total_cases) * 100.0
    p50 = float(np.percentile(latencies, 50))
    p95 = float(np.percentile(latencies, 95))

    print("\n--- EVALUATION SUMMARY ---")
    print(f"Total Test Cases      : {total_cases}")
    print(f"Intent Accuracy       : {intent_acc:.1f}% ({intent_matches}/{total_cases})")
    print(f"Location Accuracy     : {loc_acc:.1f}% ({loc_matches}/{total_cases})")
    print(f"Latency P50           : {p50:.1f} ms")
    print(f"Latency P95           : {p95:.1f} ms")
    print("---------------------------\n")

if __name__ == "__main__":
    cases_arg = sys.argv[1] if len(sys.argv) > 1 else str(backend_dir / "tests" / "intent_cases.json")
    asyncio.run(evaluate_intents(cases_arg))

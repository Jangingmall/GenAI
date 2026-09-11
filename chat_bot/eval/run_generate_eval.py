"""generate.py의 build_reply(allowed_ids+공유 reply 구조)로 generate_cases.json 28건을
돌려 generate_grading.py로 채점한다.

eval/run_eval.py(검색 Recall@3·MRR)와는 다른 평가다 — 이쪽은 intent 분류·응답 생성의
정직성·인젝션 방어·환각 방지를 본다.

실행:
  python -m eval.run_generate_eval
"""

import json
import time
from functools import partial
from pathlib import Path

from app.pipeline.generate import build_reply
from app.pipeline.intent import classify_and_extract
from app.pipeline.llm import chat_json
from eval.generate_grading import grade_l1, grade_l2

_DIR = Path(__file__).resolve().parent
_MODEL = "gemma2:9b"


def _no_prices(ids):
    return {}


def _no_artisans(ids):
    return {}


def main() -> None:
    cases = json.loads((_DIR / "generate_cases.json").read_text(encoding="utf-8"))[
        "cases"
    ]
    contact2 = json.loads(
        (_DIR / "generate_fixtures" / "contact2.json").read_text(encoding="utf-8")
    )["cases"]
    chat = partial(chat_json, model=_MODEL)

    reports = []
    latencies = []
    call_failures = 0

    for case in cases:
        candidates = contact2.get(case["id"], [])
        t0 = time.perf_counter()
        error = None
        intent_result = None
        response = None
        try:
            intent_result = classify_and_extract(case["message"], chat=chat)
            response = build_reply(
                case["message"],
                candidates,
                intent_result["intent"],
                intent_result["filters"],
                chat=chat,
                fetch_prices=_no_prices,
                fetch_artisans=_no_artisans,
            )
        except Exception as exc:  # noqa: BLE001
            error = f"{type(exc).__name__}: {exc}"
            call_failures += 1
        latency = time.perf_counter() - t0
        latencies.append(latency)

        report = {
            "id": case["id"],
            "group": case["group"],
            "message": case["message"],
            "latency": round(latency, 2),
            "error": error,
        }
        if response is not None:
            l1 = grade_l1(case, response, intent_result["intent"])
            l2 = grade_l2(response["product_ids"], response["reply"], candidates)
            report.update(
                {
                    "intent": intent_result["intent"],
                    "reply": response["reply"],
                    "product_ids": response["product_ids"],
                    "l1": l1,
                    "l1_pass": all(l1.values()) if l1 else True,
                    "l2": l2,
                }
            )
        reports.append(report)
        status = "PASS" if report.get("l1_pass") else ("ERROR" if error else "FAIL")
        print(f"[{status}] {case['id']} ({case['group']}): {latency:.2f}초", flush=True)

    print()
    n = len(reports)
    l1_pass = sum(1 for r in reports if r.get("l1_pass"))
    print(f"L1 통과: {l1_pass}/{n}")
    lat_sorted = sorted(latencies)
    print(
        f"latency p50: {lat_sorted[len(lat_sorted)//2]:.2f}초  "
        f"평균: {sum(latencies)/len(latencies):.2f}초  최대: {max(latencies):.2f}초"
    )
    print(f"에러: {call_failures}건")
    fails = [r["id"] for r in reports if not r.get("l1_pass") and not r["error"]]
    print(f"실패 케이스: {fails}")

    out = _DIR / "reports" / "generate_report.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(reports, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()

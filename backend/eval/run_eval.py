"""run_eval.py — 跑 golden_qa.jsonl，对每个问题调 /v1/chat 并评分。

用法：
    python -m eval.run_eval --provider deepseek --model deepseek-chat
    python -m eval.run_eval --limit 5   # 仅测前 5 题（冒烟）
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

# 让 `python -m eval.run_eval` 也能找到 kb_qa_agent
_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

import httpx  # noqa: E402
from kb_qa_agent.domains import bootstrap  # noqa: E402
from kb_qa_agent.observability.cost import get_report, reset_report  # noqa: E402
from kb_qa_agent.observability.eval import EvalSample, score_answer  # noqa: E402

GOLDEN_PATH = Path(__file__).resolve().parent / "golden_qa.jsonl"
DEFAULT_API = os.environ.get("KB_QA_API_BASE", "http://localhost:8000")


def load_golden() -> list[EvalSample]:
    samples = []
    for line in GOLDEN_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        obj = json.loads(line)
        samples.append(EvalSample(
            question=obj["question"],
            expected_keywords=obj.get("expected_keywords", []),
            expected_domain=obj.get("domain", ""),
            expected_risk=obj.get("expected_risk", ""),
            forbidden_phrases=obj.get("forbidden_phrases"),
        ))
    return samples


async def call_chat(query: str, api: str) -> dict:
    """调一次 /v1/chat，等 final 事件返回。"""
    body = {
        "query": query,
        "enable_reflection": False,  # 评估时关掉反思，加快速度
        "enable_rag": True,
        "enable_skills": True,
    }
    final_data: dict = {}
    actual_domain = ""
    actual_risk = ""
    async with httpx.AsyncClient(timeout=120) as client:
        async with client.stream("POST", f"{api}/v1/chat", json=body) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if line.startswith("event:"):
                    evt_name = line.split(":", 1)[1].strip()
                elif line.startswith("data:"):
                    payload = line.split(":", 1)[1].strip()
                    try:
                        data = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                    if evt_name == "intake":
                        actual_domain = data.get("domain", "")
                    elif evt_name == "risk":
                        actual_risk = data.get("risk_level", "")
                    elif evt_name == "final":
                        final_data = data
                        break
    return {
        "answer": final_data.get("final_answer", ""),
        "domain": actual_domain,
        "risk": actual_risk,
    }


async def main_async(provider: str, model: str, limit: int | None, api: str):
    bootstrap()
    os.environ["KB_QA_ACTIVE_PROVIDER"] = provider
    samples = load_golden()
    if limit:
        samples = samples[:limit]

    reset_report()
    results = []
    start = time.time()

    print(f"Running {len(samples)} samples via {api} with provider={provider}/{model}")
    print("=" * 70)

    for i, sample in enumerate(samples, 1):
        t0 = time.time()
        try:
            resp = await call_chat(sample.question, api)
        except Exception as exc:
            print(f"[{i:2d}] ERROR  {sample.question[:40]}  {exc}")
            continue
        score = score_answer(sample, resp["answer"], actual_domain=resp["domain"], actual_risk=resp["risk"])
        dt = time.time() - t0
        results.append((sample, score, dt))
        status = "✅" if score.passed else "❌"
        print(
            f"[{i:2d}] {status}  recall={score.keyword_recall:.0%}  "
            f"domain={resp['domain']:8s}  risk={resp['risk']:6s}  "
            f"{dt:5.1f}s  {sample.question[:40]}"
        )

    elapsed = time.time() - start
    total = len(results)
    passed = sum(1 for _, s, _ in results if s.passed)
    avg_recall = sum(s.keyword_recall for _, s, _ in results) / max(1, total)
    avg_latency = sum(dt for _, _, dt in results) / max(1, total)

    print("=" * 70)
    print(f"Total: {total}, Passed: {passed} ({passed/max(1,total):.0%})")
    print(f"Avg keyword recall: {avg_recall:.2%}")
    print(f"Avg latency: {avg_latency:.2f}s")
    print(f"Total elapsed: {elapsed:.1f}s")

    cost = get_report()
    summary = cost.to_dict()
    print(f"Total cost: ${summary['total_usd']}  in={summary['total_input_tokens']} out={summary['total_output_tokens']}")

    # 写报告
    report = {
        "provider": provider,
        "model": model,
        "samples": total,
        "passed": passed,
        "avg_recall": avg_recall,
        "avg_latency": avg_latency,
        "elapsed": elapsed,
        "cost": summary,
        "details": [
            {
                "question": s.question.question,
                "expected_domain": s.sample.expected_domain,
                "actual_domain": s.actual_domain,
                "expected_risk": s.sample.expected_risk,
                "actual_risk": s.actual_risk,
                "keyword_recall": s.keyword_recall,
                "passed": s.passed,
                "latency": dt,
            }
            for s, _, dt in results
        ],
    }
    out = Path(__file__).resolve().parent / f"report_{provider}_{int(time.time())}.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Report saved to: {out}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--provider", default="deepseek")
    p.add_argument("--model", default="")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--api", default=DEFAULT_API)
    args = p.parse_args()
    asyncio.run(main_async(args.provider, args.model, args.limit, args.api))


if __name__ == "__main__":
    main()

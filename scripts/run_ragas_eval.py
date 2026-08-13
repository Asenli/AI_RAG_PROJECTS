#!/usr/bin/env python3
"""Run generated RAGAS cases against the local chat API and write an auditable report."""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = PROJECT_ROOT / "data" / "rag_evaluation" / "parenting_communication_ragas.jsonl"


def ask(base_url: str, question: str, index: int) -> dict:
    payload = json.dumps({
        "company_id": "1", "session_id": f"ragas_parenting_{index}",
        "question": question, "user_id": "ragas_runner", "user_role": "admin",
    }).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/chat/ask", data=payload,
        headers={"Content-Type": "application/json", "X-Company-Id": "1"}, method="POST",
    )
    with urllib.request.urlopen(request, timeout=180) as response:
        return json.loads(response.read().decode("utf-8"))


def retrieve(base_url: str, question: str) -> list[dict]:
    params = urllib.parse.urlencode({"q": question, "role": "admin", "top_k": 5, "company_id": "1"})
    with urllib.request.urlopen(f"{base_url.rstrip('/')}/knowledge/search-test?{params}", timeout=180) as response:
        report = json.loads(response.read().decode("utf-8"))
    return report.get("results") or report.get("stages", {}).get("rerank", [])


def source_values(sources: list[dict]) -> list[str]:
    return [str(item.get("source") or item.get("title") or "") for item in sources]


def source_hit(expected_sources: list[str], retrieved_sources: list[str]) -> bool:
    return bool(
        {Path(source).name for source in expected_sources if source}
        & {Path(source).name for source in retrieved_sources if source}
    )


def run_ragas(rows: list[dict]) -> dict | None:
    """Use RAGAS when installed; basic report remains available without it."""
    try:
        from datasets import Dataset
        from ragas import evaluate
        from ragas.metrics import answer_relevancy, context_precision, context_recall, faithfulness
    except ImportError:
        return None
    if os.getenv("DEEPSEEK_API_KEY") and not os.getenv("OPENAI_API_KEY"):
        os.environ["OPENAI_API_KEY"] = os.environ["DEEPSEEK_API_KEY"]
        base_url = os.getenv("LLM_BASE_URL", "https://api.deepseek.com")
        os.environ.setdefault("OPENAI_BASE_URL", base_url)
        os.environ.setdefault("OPENAI_API_BASE", base_url)
    dataset = Dataset.from_list([{key: row[key] for key in ("question", "answer", "contexts", "ground_truth")} for row in rows])
    result = evaluate(dataset, metrics=[context_precision, context_recall, faithfulness, answer_relevancy])
    return dict(result)


def main() -> None:
    parser = argparse.ArgumentParser(description="对本地售后智能助手运行 RAGAS 评测")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--base-url", default="http://localhost:5002")
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "data" / "rag_evaluation" / "reports")
    parser.add_argument("--limit", type=int, default=0, help="只运行前 N 条；0 表示全部")
    parser.add_argument("--skip-ragas", action="store_true")
    args = parser.parse_args()
    if not args.dataset.is_file():
        raise FileNotFoundError(f"测试数据不存在：{args.dataset}")

    cases = [json.loads(line) for line in args.dataset.read_text(encoding="utf-8").splitlines() if line.strip()]
    if args.limit:
        cases = cases[:args.limit]
    rows, failures = [], []
    for index, case in enumerate(cases, 1):
        try:
            response = ask(args.base_url, case["question"], index)
            retrieved = retrieve(args.base_url, case["question"])
            sources = source_values(retrieved)
            expected_sources = case.get("expected_doc_sources", [])
            rows.append({
                **case, "answer": response.get("answer", ""),
                "contexts": [str(item.get("content") or item.get("text") or "") for item in retrieved],
                "retrieved_sources": sources,
                "source_hit": source_hit(expected_sources, sources),
            })
            print(f"[{index}/{len(cases)}] {case['id']} 完成")
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as error:
            failures.append({"id": case["id"], "error": str(error)})
            print(f"[{index}/{len(cases)}] {case['id']} 失败：{error}", file=sys.stderr)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    (args.output_dir / f"parenting_ragas_results_{stamp}.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + ("\n" if rows else ""), encoding="utf-8"
    )
    summary = {"total": len(cases), "completed": len(rows), "failed": len(failures), "source_hit_rate": sum(row["source_hit"] for row in rows) / len(rows) if rows else 0, "failures": failures}
    if rows and not args.skip_ragas:
        try:
            summary["ragas"] = run_ragas(rows)
        except Exception as error:
            summary["ragas_error"] = str(error)
    report_path = args.output_dir / f"parenting_ragas_summary_{stamp}.json"
    report_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"报告：{report_path}")
    print(f"检索命中率：{summary['source_hit_rate']:.1%} ({summary['completed']}/{summary['total']})")


if __name__ == "__main__":
    main()

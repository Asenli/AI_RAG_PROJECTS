"""In-process evaluator for the admin RAGAS dashboard."""
from __future__ import annotations

import asyncio
import json
import logging
import math
import numbers
from datetime import datetime
import uuid
from pathlib import Path

from app.core.rag_engine import rag_engine
from app.config import settings

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATASET_PATH = PROJECT_ROOT / "data" / "rag_evaluation" / "parenting_communication_ragas.jsonl"
LOG_PATH = PROJECT_ROOT / "logs" / "ragas_eval.log"
logger = logging.getLogger("uvicorn.error")

# RAGAS needs several judge-model calls per test case. Keep the dashboard task
# alive long enough for a remote model provider to complete a small batch.
RAGAS_TOTAL_TIMEOUT_SECONDS = 3600
RAGAS_REQUEST_TIMEOUT_SECONDS = 120


class RagasEvaluationService:
    def __init__(self) -> None:
        self._status: dict = {"status": "idle", "report": None, "events": []}
        self._task: asyncio.Task | None = None

    def status(self) -> dict:
        return self._json_safe(self._status)

    def _emit(self, message: str) -> None:
        event = {"time": datetime.now().strftime("%H:%M:%S"), "message": message}
        self._status.setdefault("events", []).append(event)
        self._status["events"] = self._status["events"][-100:]
        print(f"[RAGAS] {message}", flush=True)
        logger.info("[RAGAS] %s", message)
        try:
            LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            with LOG_PATH.open("a", encoding="utf-8") as output:
                output.write(f"{event['time']} [RAGAS] {message}\n")
        except OSError:
            pass

    def start(self, company_id: str, limit: int = 0, include_ragas: bool = True) -> dict:
        if self._task and not self._task.done():
            return self._status
        if not DATASET_PATH.is_file():
            raise FileNotFoundError(f"测试数据不存在：{DATASET_PATH}")
        self._status = {
            "status": "running", "run_id": uuid.uuid4().hex[:12], "total": 0,
            "completed": 0, "failed": 0, "stage": "retrieval_and_answer", "include_ragas": include_ragas, "report": None, "events": [],
        }
        self._task = asyncio.create_task(self._run(str(company_id), limit, include_ragas))
        logger.info("RAGAS task started: run_id=%s, limit=%s, include_ragas=%s", self._status["run_id"], limit or "all", include_ragas)
        self._emit(f"任务启动 run_id={self._status['run_id']}，用例数={limit or '全部'}，RAGAS指标={include_ragas}")
        return self._status

    async def _run(self, company_id: str, limit: int, include_ragas: bool) -> None:
        try:
            cases = [json.loads(line) for line in DATASET_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
            if limit:
                cases = cases[:limit]
            self._status["total"] = len(cases)
            self._emit(f"已加载 {len(cases)} 条测试用例，开始检索和回答阶段")
            rows, failures = [], []
            for index, case in enumerate(cases, 1):
                try:
                    question = case["question"]
                    retrieval = await rag_engine.search_test(question, "admin", top_k=5, company_id=company_id)
                    retrieved = retrieval.get("results") or retrieval.get("stages", {}).get("rerank", [])
                    answer = await rag_engine.query(
                        question=question, user_role="admin", user_id="ragas_admin",
                        session_id=f"ragas_dashboard_{self._status['run_id']}_{index}", company_id=company_id,
                    )
                    sources = [str(item.get("source", "")) for item in retrieved]
                    expected = case.get("expected_doc_sources", [])
                    answer_text = answer.get("answer", "")
                    expected_phrases = case.get("expected_answer_contains", [])
                    source_hit = self._source_hit(expected, sources)
                    rows.append({
                        "question": question, "answer": answer_text,
                        "contexts": [str(item.get("text", "")) for item in retrieved],
                        "ground_truth": case["ground_truth"],
                        "source_hit": source_hit,
                        "answer_hit": any(phrase in answer_text for phrase in expected_phrases),
                    })
                    logger.info("RAGAS case %s/%s: id=%s source_hit=%s sources=%s", index, len(cases), case.get("id"), source_hit, sources)
                    self._emit(f"用例 {index}/{len(cases)} 完成 id={case.get('id')}，文档命中={source_hit}")
                except Exception as error:
                    failures.append({"id": case.get("id"), "error": str(error)[:300]})
                    logger.exception("RAGAS case failed: id=%s", case.get("id"))
                    self._emit(f"用例 {index}/{len(cases)} 失败 id={case.get('id')}：{str(error)[:160]}")
                self._status["completed"] = index
                self._status["failed"] = len(failures)

            report = {
                "total": len(cases), "completed": len(rows), "failed": len(failures),
                "source_hit_rate": self._rate(rows, "source_hit"),
                "answer_coverage_rate": self._rate(rows, "answer_hit"),
                "failures": failures, "ragas": None, "ragas_error": None,
            }
            if include_ragas and rows:
                self._status.update({"stage": "ragas_metrics", "message": "正在调用 RAGAS 裁判模型计算指标"})
                logger.info("RAGAS metrics started: run_id=%s cases=%s", self._status["run_id"], len(rows))
                timeout_minutes = RAGAS_TOTAL_TIMEOUT_SECONDS // 60
                self._emit(f"检索与回答完成，开始计算 RAGAS 指标（最长 {timeout_minutes} 分钟）")
                try:
                    report["ragas"] = await asyncio.wait_for(
                        asyncio.to_thread(self._ragas_metrics, rows),
                        timeout=RAGAS_TOTAL_TIMEOUT_SECONDS,
                    )
                    logger.info("RAGAS metrics completed: run_id=%s", self._status["run_id"])
                    self._emit("RAGAS 指标计算完成")
                except asyncio.TimeoutError:
                    report["ragas_error"] = (
                        f"RAGAS 指标计算超过 {RAGAS_TOTAL_TIMEOUT_SECONDS // 60} 分钟，任务已结束。"
                        "请检查模型服务或缩小运行数量。"
                    )
                    logger.error("RAGAS metrics timed out: run_id=%s", self._status["run_id"])
                    self._emit("RAGAS 指标计算超时，已结束任务")
                except Exception as error:
                    report["ragas_error"] = str(error)[:500]
                    logger.exception("RAGAS metric calculation failed")
                    self._emit(f"RAGAS 指标计算失败：{str(error)[:200]}")
            self._status.update({"status": "completed", "stage": "completed", "report": report})
            logger.info("RAGAS task completed: run_id=%s completed=%s failed=%s source_hit_rate=%.3f", self._status["run_id"], len(rows), len(failures), report["source_hit_rate"])
            self._emit(f"任务完成：完成={len(rows)}，失败={len(failures)}，文档命中率={report['source_hit_rate']:.1%}")
        except Exception as error:
            self._status.update({"status": "failed", "error": str(error)[:500]})
            logger.exception("RAGAS task failed: run_id=%s", self._status.get("run_id"))

    @staticmethod
    def _rate(rows: list[dict], key: str) -> float:
        return sum(bool(row[key]) for row in rows) / len(rows) if rows else 0.0

    @staticmethod
    def _source_hit(expected_sources: list[str], retrieved_sources: list[str]) -> bool:
        """Match by filename because upload category/module paths are configurable."""
        expected_names = {Path(source).name for source in expected_sources if source}
        retrieved_names = {Path(source).name for source in retrieved_sources if source}
        return bool(expected_names & retrieved_names)

    @classmethod
    def _json_safe(cls, value):
        if isinstance(value, dict):
            return {str(key): cls._json_safe(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [cls._json_safe(item) for item in value]
        if hasattr(value, "item"):
            return cls._json_safe(value.item())
        if isinstance(value, numbers.Real):
            number = float(value)
            return number if math.isfinite(number) else None
        return value

    @staticmethod
    def _ragas_metrics(rows: list[dict]) -> dict:
        try:
            from datasets import Dataset
            from ragas import evaluate
            from ragas.embeddings import LangchainEmbeddingsWrapper
            from ragas.llms import LangchainLLMWrapper
            from ragas.metrics import answer_relevancy, context_precision, context_recall, faithfulness
            from ragas.run_config import RunConfig
            from langchain_openai import ChatOpenAI, OpenAIEmbeddings
        except ImportError as error:
            raise RuntimeError("未安装 RAGAS，请执行 pip install -r requirements-eval.txt") from error
        if not settings.deepseek_api_key or not settings.siliconflow_api_key:
            raise RuntimeError("缺少 DEEPSEEK_API_KEY 或 SILICONFLOW_API_KEY，无法计算 RAGAS 指标")
        llm = LangchainLLMWrapper(ChatOpenAI(
            model=settings.llm_model,
            base_url=settings.llm_base_url,
            api_key=settings.deepseek_api_key,
            temperature=0,
            timeout=RAGAS_REQUEST_TIMEOUT_SECONDS,
            max_retries=0,
        ), bypass_n=True)
        embeddings = LangchainEmbeddingsWrapper(OpenAIEmbeddings(
            model=settings.embedding_model,
            base_url=settings.embedding_base_url,
            api_key=settings.siliconflow_api_key,
        ))
        dataset = Dataset.from_list([{key: row[key] for key in ("question", "answer", "contexts", "ground_truth")} for row in rows])
        result = evaluate(
            dataset,
            metrics=[context_precision, context_recall, faithfulness, answer_relevancy],
            llm=llm,
            embeddings=embeddings,
            run_config=RunConfig(
                timeout=RAGAS_REQUEST_TIMEOUT_SECONDS,
                max_retries=0,
                max_wait=10,
                max_workers=2,
            ),
        )
        return RagasEvaluationService._json_safe(result._repr_dict)


ragas_evaluation_service = RagasEvaluationService()

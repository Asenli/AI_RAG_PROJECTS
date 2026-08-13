# 亲子沟通话术 RAGAS 评测

`parenting_communication_ragas.jsonl` 由 `E:\BaiduNetdiskDownload\育儿\数据\沟通话术` 下的 Markdown 自动生成。每条用例包含 RAGAS 所需的 `question`、`ground_truth`、`reference_contexts`，以及项目检索回归所需的预期文档来源。

先启动后端，然后在项目根目录运行：

```powershell
.\scripts\run_parenting_ragas_eval.ps1
```

该命令会同步话术资料、入库、生成用例并运行端到端评测；首次会安装 `requirements-eval.txt` 中的 RAGAS 依赖。结果写入 `reports/`：

- `parenting_ragas_results_*.jsonl`：每条问题的模型回答、检索上下文和命中情况
- `parenting_ragas_summary_*.json`：完成数量、失败项、文档命中率及可用时的 RAGAS 指标

只验证导入与检索链路、不调用 RAGAS 裁判模型：

```powershell
.\scripts\run_parenting_ragas_eval.ps1 -SkipRagas
```

快速试跑前 3 条：

```powershell
.\scripts\run_parenting_ragas_eval.ps1 -Limit 3
```

#!/usr/bin/env python3
"""Build a deterministic RAGAS dataset from the parenting communication Markdown files."""
from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path

DEFAULT_SOURCE = Path(r"E:\BaiduNetdiskDownload\育儿\数据\沟通话术")
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "rag_evaluation" / "parenting_communication_ragas.jsonl"
DEFAULT_KB_DIR = PROJECT_ROOT / "knowledge_base" / "manual" / "亲子沟通话术"
SKIP_SECTIONS = {"元数据", "使用原则", "适用提醒"}


def sections(markdown: str) -> list[tuple[str, list[str]]]:
    matches = list(re.finditer(r"^##\s+(.+?)\s*$", markdown, re.MULTILINE))
    result = []
    for index, match in enumerate(matches):
        title = match.group(1).strip()
        if title in SKIP_SECTIONS or "不建议" in title:
            continue
        end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown)
        bullets = re.findall(r"^[-*]\s*[“\"]?(.+?)[”\"]?\s*$", markdown[match.end():end], re.MULTILINE)
        if bullets:
            result.append((title, bullets))
    return result


def make_question(title: str, section: str) -> str:
    return f"孩子遇到“{title}”的情况时，{section}可以怎么和他说？"


def build_records(source_dir: Path, kb_dir: Path, copy_sources: bool) -> list[dict]:
    if not source_dir.is_dir():
        raise FileNotFoundError(f"话术目录不存在：{source_dir}")
    if copy_sources:
        kb_dir.mkdir(parents=True, exist_ok=True)

    records = []
    for file_path in sorted(source_dir.glob("*.md")):
        content = file_path.read_text(encoding="utf-8")
        title_match = re.search(r"^#\s+(.+?)\s*$", content, re.MULTILINE)
        title = title_match.group(1).strip() if title_match else file_path.stem
        if copy_sources:
            shutil.copy2(file_path, kb_dir / file_path.name)
        source = f"manual/亲子沟通话术/{file_path.name}"
        for section_title, bullets in sections(content):
            ground_truth = "\n".join(f"- {item}" for item in bullets)
            records.append({
                "id": f"parenting-ragas-{len(records) + 1:03d}",
                "question": make_question(title, section_title),
                "query": f"{title} {section_title}",
                "ground_truth": ground_truth,
                "reference_contexts": [content],
                "expected_answer_contains": bullets[:2],
                "expected_doc_sources": [source],
                "category": "亲子沟通话术",
                "module": "亲子沟通话术",
                "sub_module": title,
                "knowledge_type": "manual",
                "user_role": "admin",
                "difficulty": "medium",
                "question_type": "沟通话术",
                "dataset_version": "parenting-communication-v1",
            })
    return records


def main() -> None:
    parser = argparse.ArgumentParser(description="生成亲子沟通话术 RAGAS 测试数据")
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--copy-to-kb", action="store_true", help="同步原始 Markdown 到项目知识库")
    parser.add_argument("--kb-dir", type=Path, default=DEFAULT_KB_DIR)
    args = parser.parse_args()

    records = build_records(args.source_dir, args.kb_dir, args.copy_to_kb)
    if not records:
        raise RuntimeError("没有从话术文件中提取到可评测章节")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as output:
        for record in records:
            output.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(f"已生成 {len(records)} 条用例：{args.output}")
    if args.copy_to_kb:
        print(f"已同步知识源：{args.kb_dir}")


if __name__ == "__main__":
    main()

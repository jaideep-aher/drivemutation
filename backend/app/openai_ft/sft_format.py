"""Convert Stage 2 dataset JSONL into OpenAI chat fine-tune JSONL."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def example_to_openai_messages_row(example: dict[str, Any]) -> dict[str, Any]:
    messages = example.get("messages")
    if not isinstance(messages, list) or len(messages) != 3:
        raise ValueError(f"example {example.get('id')} missing messages")
    cleaned = []
    for m in messages:
        role = m.get("role")
        content = m.get("content")
        if role not in {"system", "user", "assistant"} or not isinstance(content, str):
            raise ValueError(f"invalid message in {example.get('id')}")
        cleaned.append({"role": role, "content": content})
    return {"messages": cleaned}


def write_openai_finetune_jsonl(
    source_jsonl: Path,
    dest_jsonl: Path,
) -> dict[str, Any]:
    """Extract messages-only rows suitable for OpenAI fine-tuning upload."""
    n = 0
    dest_jsonl.parent.mkdir(parents=True, exist_ok=True)
    with source_jsonl.open(encoding="utf-8") as src, dest_jsonl.open(
        "w", encoding="utf-8"
    ) as dst:
        for line in src:
            line = line.strip()
            if not line:
                continue
            ex = json.loads(line)
            row = example_to_openai_messages_row(ex)
            dst.write(json.dumps(row, ensure_ascii=False) + "\n")
            n += 1
    return {"source": str(source_jsonl), "dest": str(dest_jsonl), "n": n}

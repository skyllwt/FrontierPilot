#!/usr/bin/env python3
"""
FrontierPilot JSON 写入辅助脚本

从 stdin 读取 JSON，校验后写入指定文件。避免 agent 使用 cat/heredoc 直接写文件导致的转义和解析问题。

Usage:
  python3 write_fp_json.py <output_path> < <json_from_stdin>
  或
  python3 write_fp_json.py <output_path> << 'ENDOFJSON'
  { "topic": "...", ... }
  ENDOFJSON

若 JSON 含 markdown 代码块包裹（```json ... ```），会自动 strip。
"""
from __future__ import print_function

import json
import sys
from pathlib import Path


def main():
    if len(sys.argv) != 2:
        print("Usage: python3 write_fp_json.py <output_path>", file=sys.stderr)
        print("Reads JSON from stdin, validates, writes to output_path.", file=sys.stderr)
        sys.exit(1)

    output_path = Path(sys.argv[1])
    raw = sys.stdin.read()

    # Strip markdown code block if present
    stripped = raw.strip()
    if stripped.startswith("```"):
        lines = stripped.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        stripped = "\n".join(lines)

    try:
        data = json.loads(stripped)
    except json.JSONDecodeError as e:
        print("JSON 解析失败: %s" % e, file=sys.stderr)
        # Show context around error
        pos = e.pos
        start = max(0, pos - 60)
        end = min(len(stripped), pos + 60)
        print("错误位置附近: ...%s..." % repr(stripped[start:end]), file=sys.stderr)
        sys.exit(1)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print("已写入: %s" % output_path)


if __name__ == "__main__":
    main()

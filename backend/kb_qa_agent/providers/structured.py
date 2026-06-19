"""结构化输出辅助：把 dict schema 注入 system prompt + 解析 JSON 响应。

多 Provider 场景下统一的 schema 注入流程：
  1. 把 schema 序列化进 system prompt
  2. 强制要求 json_object 输出（OpenAI 兼容协议支持）
  3. 用 json.loads 解析 + 用 schema 做轻校验（顶层 required + type）

复杂校验逻辑集中在这里，业务层不直接接触。
"""

from __future__ import annotations

import json
import re
from typing import Any

from .base import ChatMessage


def _schema_to_prompt(schema: dict[str, Any]) -> str:
    """把 schema dict 转成自然语言描述，注入 system prompt。"""
    pretty = json.dumps(schema, ensure_ascii=False, indent=2)
    return (
        "你必须只输出一个严格符合以下 JSON Schema 的 JSON 对象。\n"
        "规则：\n"
        "  1. 不得包含任何 JSON 以外的字符（包括 ```json 围栏、解释、注释）\n"
        "  2. 所有 schema 中声明的字段必须出现\n"
        "  3. 类型必须严格匹配（string / number / boolean / array / object）\n"
        f"Schema:\n{pretty}"
    )


def build_structured_messages(messages: list[ChatMessage], schema: dict[str, Any]) -> list[ChatMessage]:
    """在 messages 最前面插入 schema 提示。"""
    schema_msg = ChatMessage(role="system", content=_schema_to_prompt(schema))
    return [schema_msg, *messages]


def parse_json_response(content: str, schema: dict[str, Any]) -> dict[str, Any]:
    """解析 JSON + 校验顶层 key。"""
    text = _normalize_json_text(content)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Model output is not valid JSON: {exc}\nOutput was:\n{content}") from exc
    if not isinstance(parsed, dict):
        raise ValueError(f"Expected dict, got {type(parsed).__name__}: {parsed!r}")
    _validate_top_level(parsed, schema)
    return parsed


def strip_thinking_blocks(content: str) -> str:
    """移除模型显式输出的思考块，避免透出到用户响应。"""
    return re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL | re.IGNORECASE).strip()


def _normalize_json_text(content: str) -> str:
    """提取模型响应中的 JSON 对象文本。"""
    text = content.strip()
    if text.startswith("```"):
        return _strip_code_fence(text)

    without_thinking = strip_thinking_blocks(text)
    if without_thinking.startswith("```"):
        return _strip_code_fence(without_thinking)
    if without_thinking.startswith("{"):
        return without_thinking

    extracted = _extract_first_json_object(without_thinking)
    if extracted is not None:
        return extracted

    return text


def _extract_first_json_object(text: str) -> str | None:
    """在自由文本中抽取第一个顶层 JSON 对象 `{...}`（按括号匹配，跳过字符串中的括号）。"""
    in_string = False
    escape = False
    depth = 0
    start: int | None = None
    for i, ch in enumerate(text):
        if escape:
            escape = False
            continue
        if ch == "\\" and in_string:
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            if depth == 0:
                continue
            depth -= 1
            if depth == 0 and start is not None:
                return text[start:i + 1]
    return None


def _strip_code_fence(text: str) -> str:
    """剥离包裹完整 JSON 的 Markdown code fence。"""
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    stripped = stripped.strip("`")
    if stripped.startswith("json"):
        stripped = stripped[4:].lstrip()
    if stripped.endswith("```"):
        stripped = stripped[:-3].rstrip()
    return stripped


def _validate_top_level(payload: dict[str, Any], schema: dict[str, Any]) -> None:
    """校验顶层字段；嵌套校验交给业务层（Pydantic 等）。"""
    schema_props = schema.get("properties", {}) if isinstance(schema.get("properties"), dict) else {}
    required = schema.get("required", []) if isinstance(schema.get("required"), list) else []
    for key in required:
        if key not in payload:
            raise ValueError(f"Missing required field: {key!r}")
    # 类型粗校验
    type_map = {"string": str, "number": (int, float), "integer": int, "boolean": bool, "array": list, "object": dict}
    for key, prop_schema in schema_props.items():
        if key not in payload:
            continue
        # 支持两种写法：
        #   {"x": "integer"}          —— 简写
        #   {"x": {"type": "integer"}} —— 标准 JSON Schema
        if isinstance(prop_schema, str):
            expected_type = prop_schema
        elif isinstance(prop_schema, dict):
            expected_type = prop_schema.get("type", "")
        else:
            continue
        if not expected_type:
            continue
        py_type = type_map.get(expected_type)
        if not py_type:
            continue
        if isinstance(payload[key], py_type):
            # bool 是 int 子类，但 type=integer 时不应该接受 True/False
            if expected_type == "integer" and isinstance(payload[key], bool):
                raise ValueError(f"Field {key!r} expected integer, got bool")
            continue
        raise ValueError(f"Field {key!r} expected {expected_type}, got {type(payload[key]).__name__}")

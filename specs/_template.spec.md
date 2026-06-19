# <module>.spec

## 1. 用途（Purpose）

<一句话>

## 2. 公共 API（Public API）

```python
def function_name(arg: Type) -> ReturnType:
    """简短说明。"""
```

## 3. 输入契约（Input Contract）

| 参数 | 类型 | 约束 | 默认值 | 必需 |
|---|---|---|---|---|
| `arg1` | `str` | 非空 | — | ✅ |

## 4. 输出契约（Output Contract）

成功路径：返回 `<type>`，含字段 `...`。
失败路径：抛 `<ExceptionClass>`。

## 5. 不变量（Invariants）

- I1: ...
- I2: ...

## 6. 错误模式（Error Modes）

| 触发条件 | 异常 | 消息格式 |
|---|---|---|
| 输入为空 | `ValueError` | `"arg1 must be non-empty"` |

## 7. 边界情况（Edge Cases）

- 空输入：...
- 超大输入：...

## 8. 性能预期（Performance）

- 典型耗时：< 100ms
- 资源占用：内存 < 50MB

## 9. 不在本模块范围（Non-Goals）

- 不负责 ...
- 不处理 ...

## 10. 依赖（Dependencies）

- 内部：`kb_qa_agent.<module>`
- 外部：`<package>`
- 环境变量：`<VAR>`

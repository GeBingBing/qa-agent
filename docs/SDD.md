# Spec-Driven Development（SDD）

> 本项目采用 **规范驱动开发（Spec-Driven Development）**：在写代码之前先把"模块要做什么、不做什么、出错怎么办"写成可执行的规范，再用规范驱动测试和实现。

## 为什么用 SDD

LLM 应用最大的工程难点是**输入输出形态飘移**：模型偶尔返回奇怪的 JSON、Provider 限流、工具调用参数对不上 schema。如果只是"看着 prompt 调"，问题永远在不同环节复现。

SDD 把每个模块的契约固化下来：
- 输入是什么形状？
- 输出是什么形状？
- 哪些不变量必须满足？
- 出错的时候是什么错？

固化之后：
1. 测试可以直接对照 spec 写
2. 多 Provider 切换时，能精确定位是哪个 Provider 不满足 spec
3. 新人接手时，spec 是最权威的源（不是源代码）

## Spec 结构

每个模块在 `specs/<module>.spec.md` 下，结构固定：

```
# <module>.spec

## 1. 用途（Purpose）
一句话说清这个模块解决什么问题。

## 2. 公共 API（Public API）
列出所有暴露给外部调用的函数/类，含签名 + 一行说明。

## 3. 输入契约（Input Contract）
按字段列出每个入参的类型、约束、默认值、是否必需。

## 4. 输出契约（Output Contract）
按字段列出返回值/异常，含类型 + 语义。

## 5. 不变量（Invariants）
不论输入如何，必须始终成立的条件。例如：
- 返回值的某个字段不为空
- 调用前后 GLOBAL_REGISTRY 状态一致
- 资源（连接 / 文件句柄）一定关闭

## 6. 错误模式（Error Modes）
枚举所有定义良好的错误场景，每个含：
- 触发条件
- 抛出哪个异常
- 错误消息格式

## 7. 边界情况（Edge Cases）
不属于错误但需要明确行为的场景：
- 空输入
- 超大输入
- 并发调用
- Provider 不可用

## 8. 性能预期（Performance）
- 典型耗时
- 资源占用上限

## 9. 不在本模块范围（Non-Goals）
明确不做什么，避免范围蔓延。

## 10. 依赖（Dependencies）
- 其他模块
- 外部服务
- 环境变量
```

## 工作流

### 新增能力
```
1. 写 specs/<module>.spec.md
2. Review spec (自审 + 用户确认)
3. 根据 spec 写 backend/tests/test_<module>.py（红）
4. 写实现让测试过（绿）
5. 重构（保持绿）
6. 更新 docs/CODE_MAP.md 索引
```

### 修改 bug
```
1. 写一个最小复现 case 的失败测试
2. 检查是否需要更新 spec（行为变更 vs 实现 bug）
   - 行为变更：先改 spec，再改测试期望，最后改实现
   - 实现 bug：直接改实现让现有测试过
3. 提交：commit message 引用 spec 段落
```

### 评审 PR / Code Review
- 先看 spec 改动（如果有）
- 再看测试改动是否覆盖了 spec 改动
- 最后看实现是否最小化满足测试

## Spec 与代码的关系

```
specs/planner.spec.md           ← 单一事实源（Single Source of Truth）
       │
       ├── 决定 → backend/tests/test_planner.py（按 spec 用例写）
       │
       └── 决定 → backend/kb_qa_agent/core/planner.py（实现满足 spec）
```

当三者不一致时：
- spec ↔ test 不一致 → 改 test
- spec ↔ impl 不一致 → 改 impl
- test ↔ impl 不一致 → 改一边，但要回头看 spec

## 当前已有的 spec

| 模块 | 文件 | 状态 |
|---|---|---|
| Provider 适配层 | [`specs/providers.spec.md`](../specs/providers.spec.md) | ✅ |
| Tool Registry | [`specs/tool_registry.spec.md`](../specs/tool_registry.spec.md) | ✅ |
| Planner（DAG） | [`specs/planner.spec.md`](../specs/planner.spec.md) | ✅ |
| Sandbox | [`specs/sandbox.spec.md`](../specs/sandbox.spec.md) | ✅ |

待补：`router` / `rag` / `react_loop` / `skill_loader` / `flows/*`。

## SDD 不是什么

- **不是瀑布流**：spec 不需要先写完所有模块。每个模块独立演进
- **不是文档优先**：spec 是工作产物，不是给"领导看"的文档
- **不是不许重构**：spec 本身可以演进，但变更需要明示（git diff）
- **不是替代代码注释**：spec 讲 What，注释讲 Why

## 模板

新建 spec 时复制 [`specs/_template.spec.md`](../specs/_template.spec.md)。

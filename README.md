# 概念学习仓库（Concept Learning Workspace）

> 一个用于**「把任意新概念真正学透」**的个人学习工作流仓库：
> 自研概念学习 Skill → 对任意主题生成结构化学习资料 → 沉淀成可复用的知识资产。

---

## 仓库用途

本仓库解决一个问题：**如何从"听说过一个词"到"真正理解并能讲清楚一个概念"**。

为此搭建了一条完整流水线：

1. **自研 Skill**（`concept-learning-material`）——规定任何概念都要按固定方法生成学习资料：先消歧 → 强制联网检索核实 → 按「个人解释 / 核心机制 / 应用场景 / 边界辨析 / 来源链接」五段结构成稿 → 交付前自检。
2. **用该 Skill 产出学习资料**——已生成《Agent》《大模型的上下文》《Skill》三份 HTML，作为模板范例与知识沉淀。
3. **概念关系梳理**——用 `concept-relationship.md`（Mermaid 流程图 + 文字）说明 Agent、上下文、Skill 三个核心概念如何协作。

---

## 目录结构

```text
.
├── .workbuddy/
│   ├── skills/
│   │   └── concept-learning-skill/
│   │       └── SKILL.md            # 项目级 Skill 副本（本仓库随附）
│   └── memory/                     # 内部工作日志（非交付物）
├── learning-materials/             # 用 Skill 生成的学习资料（HTML，可直接打开）
│   ├── agent.html                  #   《Agent》——LLM 不够？Agent 是什么、如何运转
│   ├── llm-context.html            #   《大模型的上下文》——窗口、token、注意力边界
│   └── skill.html                  #   《Skill》——智能体技能（SKILL.md）如何工作
├── concept-relationship.md         # Agent × 上下文 × Skill 关系说明（Mermaid + 文字）
├── concept-learning-material.zip   # 用户级 Skill 的打包备份
└── README.md                       # 本文件
```

---

## Skill 存放路径

该 Skill 有两份副本，作用域不同：

| 位置 | 路径 | 作用域 | 说明 |
|---|---|---|---|
| 用户级（正式安装） | `C:\Users\Administrator\.workbuddy\skills\concept-learning-material\SKILL.md` | **所有项目可用** | YAML `name` 为 `concept-learning-material`，由官方脚手架校验通过 |
| 项目级（本仓库副本） | `./.workbuddy/skills/concept-learning-skill/SKILL.md` | 仅本仓库 | 内容与用户级一致；⚠️ 文件夹名（`concept-learning-skill`）与 YAML `name`（`concept-learning-material`）不一致，如需作为独立技能被工具自动识别，应改为同名 |

> 建议：日常使用以**用户级**安装为准；仓库内副本用于版本管理与共享，两者保持同步即可。

---

## 调用方法

**方式一：对话直接触发（推荐）**

在任意会话中说出类似指令即可，无需手动指定文件：

- "帮我学透 **Agent** 这个概念"
- "用概念学习资料生成一份关于 **XXX** 的学习讲义"
- "给 **多重共线性** 生成一份学习资料"

说明：新建的 Skill 一般在**下一个新会话**起被自动收录进工具列表；当前会话可直接使用**方式二**。

**方式二：手动加载执行**

让 Agent 直接读取 `SKILL.md` 并按其规范执行（适用于技能尚未被自动收录的会话）：

```
请先读取 .workbuddy/skills/concept-learning-skill/SKILL.md，然后按它的规范生成关于「XXX」的学习资料。
```

**方式三：离线阅读 / 人工参考**

不借助 Agent：直接按 SKILL.md 规定的五段结构，自行阅读 `learning-materials/` 下的 HTML 学习其写法，或手工套用结构创作新资料。

无论哪种方式，Skill 内部的执行流程都是：

```
消歧（明确学哪个含义）
  → 强制 WebSearch 检索核实（每个概念 ≥ 2 个独立权威来源）
  → 按五段结构成稿（个人解释 / 核心机制 / 应用场景 / 边界辨析 / 来源链接）
  → 交付前自检（准确性、通俗度、来源充分、无编造链接等 9 项）
```

---

## ✅ 人工核查说明（重要）

本仓库中的学习内容主要由 AI 辅助生成，因此**所有交付内容均已经作者人工逐条核查**，而非直接采信 AI 输出：

**核查时间：2026 年 9 月 8 日**

**核查范围与方法：**

1. **`learning-materials/` 三份 HTML**：
   - 文中引用的**来源链接逐条核实**——真实存在、可访问，并与文中标注的"类型 + 支撑点"相符；
   - 关键定义、机制描述与**源文核对一致**（如 ReAct 论文 arXiv:2210.03629、Anthropic《Building effective agents》、*Lost in the Middle* 论文 arXiv:2307.03172、Claude Agent Skills 官方文档等）；
   - 多义词均做了**消歧处理**（如 Skill 明确聚焦"智能体技能"语境）；
   - **全文无编造链接**；易变数字（如窗口大小、token 数）一律标注时点或注明"以官方文档为准"。
2. **`concept-relationship.md`**：三张 Mermaid 图与文字结论已核对，与三份 HTML 的表述一致，无相互矛盾。
3. **`SKILL.md`**：结构经官方 `package_skill.py` 校验通过（Skill is valid）。

**边界与局限（如实声明）：**

- 外链可能随时间失效；若链接打不开，请以链接指向的机构名 + 文章标题自行搜索最新出处；
- 标注"以官方文档为准"的内容（如各家模型的上下文长度、新功能）更新很快，使用前请核对官方最新文档；
- 如发现任何错误或过期信息，欢迎指出以便修订。

---

维护者：徐飞 · 创建于 2026-09-08

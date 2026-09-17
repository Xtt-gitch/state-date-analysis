---
name: push-to-github
description: 将本地工作区的变更安全推送到 GitHub 远程仓库。当用户说"推送到 GitHub""上传到远程仓库""提交并推送""把改动同步到仓库""push 一下""备份到 GitHub"时使用。适用于任何本地 git 仓库，自动读取当前仓库的 origin 远端与分支，推送前扫描敏感文件（.env、密钥、大文件）并逐项要求确认。
agent_created: true
---

# 推送本地内容到 GitHub

用一套"先扫描、再确认、最后推送"的流程，把本地改动安全送达远端仓库。核心目标是**绝不误推密钥、绝不误删远端历史**。

## 使用场景

- 用户完成了一批本地工作，想把成果同步到 GitHub
- 用户担心把 `.env`、密钥、大文件误传上去
- 用户需要把某个课程/项目仓库的最新状态备份到远端

## 关键前提

- **推送目标**：当前仓库的 `origin` 远端（由 `git remote get-url origin` 读取），不写死任何仓库地址
- **分支**：当前分支；若处于游离 HEAD，则切到 `main`
- **协议**：优先 SSH（`git@github.com:...`），HTTPS 通道在部分网络环境下 TLS 握手会失败
- **确认要求**：推送前**必须**向用户展示提交清单并获得明确同意，这是硬性要求

## 执行流程

### 第 1 步：环境自检

```bash
git -C "<repo>" rev-parse --is-inside-work-tree
git -C "<repo>" remote -v
git -C "<repo>" config --get user.name
```

若 `origin` 缺失，停下并告知用户：
```
git remote add origin git@github.com:<用户名>/<仓库名>.git
```
不要自行猜测用户名或仓库名。

### 第 2 步：扫描变更

```bash
python scripts/scan_changes.py "<repo>"
```

脚本输出 JSON，包含：

| 字段 | 含义 |
|------|------|
| `untracked` / `modified` / `deleted` / `renamed` | 各类变更文件路径 |
| `groups` | 按类型分组（代码/文档/数据/作业/图片/其他） |
| `blocked` | **必须排除**的文件（`.env`、`.pem`、`id_rsa`、`credentials.json` 等） |
| `warned` | 建议忽略但需用户判断（日志、`__pycache__`、`node_modules`、IDE 配置） |
| `large` | 超过 20MB 的文件；`hard: true` 表示超过 80MB |
| `secret_hits` | 文件**内容**中疑似密钥的匹配（`ghp_`、`sk-`、`AKIA`、私钥头） |
| `behind` / `ahead` | 相对远端领先/落后多少个提交 |

退出码 `1` 表示存在阻断级风险，此时**不得**继续推送。

### 第 3 步：拦截与告知

必须先处理这两类，再谈推送：

**阻断级（`blocked` 或 `secret_hits` 非空）**
- **不提交这些文件**，从文件清单中剔除
- 明确告知用户：文件名 + 原因（如"`.env` 是环境变量文件"）
- 若 `secret_hits` 命中，指出具体文件与行号，并提醒：**密钥一旦推送到 GitHub，即使后续删除，历史记录中仍可被检索到，必须立即到平台后台吊销并重新生成**

**警告级（`warned` / `large`）**
- 列出文件，说明原因，请用户决定是否纳入
- 对 `hard: true` 的文件，明确建议不要上传（GitHub 单文件上限 100MB）

若仓库没有 `.gitignore`，且 `warned` 非空，建议补一个 —— 列出应当忽略的模式，询问用户是否写入。

### 第 4 步：向用户确认（不可跳过）

用清晰的清单呈现，例如：

```
待推送仓库：state-date-analysis (git@github.com:Xtt-gitch/state-date-analysis.git)
分支：main  |  领先远端 3 个提交

将提交以下 5 个文件：
  文档  notes/ch03-summary.md
  代码  code/regression.R
  ...
已自动排除：
  .env（环境变量文件）
提交说明：添加第三章笔记与回归代码

确认推送？
```

使用 `AskUserQuestion` 工具，选项设计为"确认推送 / 调整文件范围 / 取消"。

### 第 5 步：执行推送

用户确认后，调用安全推送脚本：

```bash
python scripts/safe_push.py \
  --repo "<repo>" \
  --files "notes/ch03-summary.md" "code/regression.R" \
  --message "添加第三章笔记与回归代码"
```

要点：
- **`--files` 逐项列出**，脚本内部只用 `git add --` 指定路径，**绝不使用 `git add .`**
- 提交信息用中文，一句话概括本次改动（用户指定则用用户的）
- 首次推送新分支时加 `--set-upstream`
- 想先看命令不实际执行，加 `--dry-run`

脚本的几种返回情形：

| 情形 | `ok` | 说明 |
|------|------|------|
| 正常提交并推送 | `true` | 返回 `commit`（短 SHA）与 `commands` |
| `--dry-run` 预演 | `true` | 只返回 `commands`，不产生任何提交 |
| 暂存区为空但已有待推提交 | `true` | 带 `note`，跳过提交直接推送 `pushed_commits` |
| 暂存区为空且无待推提交 | `false` | 退出码 2，说明确实无改动可推 |
| 路径写错（工作区无且 git 不认识） | `false` | 退出码 2，返回 `missing` 列表 |

**注意**：脚本会真实执行提交与推送，且**不支持事务回滚**。因此务必先 `--dry-run` 确认命令，再正式执行。若中途失败，用 `git log` 确认提交是否已生成，不要盲目重跑（重跑可能产生重复提交）。

### 第 6 步：报告结果

推送成功后向用户复述关键信息（不要只说"已完成"）：

- 仓库与分支
- 提交短 SHA
- 本次提交的文件数量
- 与远端的同步状态
- 若有文件被排除，提醒用户这些文件仍在本地、未上传

## 错误处置

| 现象 | 原因 | 处理 |
|------|------|------|
| `Permission denied (publickey)` | SSH 密钥未配置 | 让用户执行 `ssh -T git@github.com` 验证；确认公钥已加入 GitHub |
| `rejected` / `non-fast-forward` | 远端有本地没有的提交 | 先 `git pull --rebase origin <branch>`，解决冲突后再推；**不要**擅自 `--force` |
| `schannel: failed to receive handshake` | HTTPS 通道受阻 | 改用 SSH：`git remote set-url origin git@github.com:<user>/<repo>.git` |
| 单文件超 100MB | 超出 GitHub 限制 | 排除该文件；若确需版本管理，建议 Git LFS |
| 命令长时间无响应 | 网络不通 | 检查代理设置；不要反复重试，先诊断 |

## 硬性约束

1. **禁止 `git add .` / `git add -A`** —— 只添加显式确认过的路径
2. **禁止 `git push --force`** —— 除非用户明确要求且理解后果；`main` 分支上尤其如此
3. **禁止提交 `blocked` 列表中的文件** —— 即使用户一时要求，也要先说明风险
4. **推送前必须获得用户确认** —— 这是外部动作，不可默默执行
5. **不修改远端配置** —— 不改 remote URL、不改分支保护、不删远端分支

## 配套文件

- `scripts/scan_changes.py` —— 变更扫描与风险识别，输出 JSON
- `scripts/safe_push.py` —— 分步执行添加/提交/推送，内置错误诊断
- `references/output_schema.md` —— 扫描脚本的完整输出字段说明

# scan_changes.py 输出字段说明

脚本接收一个可选参数 `repo_path`（默认当前目录），在 stdout 输出单个 JSON 对象。

## 顶层字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `ok` | bool | 脚本是否正常完成（`false` 仅出现在非 git 仓库的情况） |
| `repo` | string | 仓库绝对路径 |
| `error` | string | 出错时的原因说明 |
| `hint` | string | 出错时的建议操作 |

## 仓库状态

| 字段 | 类型 | 说明 |
|------|------|------|
| `branch` | string | 当前分支名 |
| `remote` | string | `origin` 的 URL；为空表示未配置远端 |
| `has_commits` | bool | 仓库是否已有提交（新建仓库为 `false`） |
| `ahead` | int | 本地领先远端多少个提交 |
| `behind` | int | 本地落后远端多少个提交（>0 表示推送前需先 pull） |

## 变更清单

| 字段 | 类型 | 说明 |
|------|------|------|
| `untracked` | string[] | 新增未跟踪的文件路径（相对仓库根） |
| `modified` | string[] | 已跟踪且内容有修改的文件 |
| `deleted` | string[] | 已删除的文件 |
| `renamed` | string[] | 重命名的文件 |
| `groups` | object | 按类型分组：键为 `代码`/`文档`/`数据`/`作业`/`图片`/`其他`，值为该组的文件路径数组 |

## 风险标记

| 字段 | 类型 | 说明 |
|------|------|------|
| `blocked` | object[] | **必须排除**。每项含 `path`（路径）与 `reason`（原因） |
| `warned` | object[] | 建议排除。每项含 `path` 与 `reason` |
| `large` | object[] | 超 20MB 的文件。每项含 `path`、`size_mb`、`hard`（`true` 表示超 80MB） |
| `secret_hits` | object[] | 文件内容疑似含密钥。每项含 `path`、`line`（行号）、`preview`（前 80 字符片段） |

## 统计

`stats.total` / `stats.untracked` / `stats.modified` / `stats.deleted` / `stats.blocked` / `stats.warned` / `stats.large`

## 退出码

| 码 | 含义 |
|----|------|
| 0 | 正常，无阻断级风险，可继续 |
| 1 | 存在 `blocked` 或 `secret_hits`，**不得继续推送** |
| 2 | 不是 git 仓库，或 git 未安装 |

## 阻断模式清单（`blocked` 判定依据）

`.env` 及其变体（除 `.env.example` / `.env.sample` / `.env.template`）、`*.pem`、`*.key`、`*.p12`、`*.pfx`、`id_rsa*`、`id_ed25519*`、`.ssh/` 目录内文件、`credentials.*`、`secrets.*`、`.npmrc`、`.pypirc`、`.netrc`、`*.keystore`、`*.jks`、`token.json`

## 警告模式清单（`warned` 判定依据）

`.DS_Store`、`Thumbs.db`、`desktop.ini`、`*.log`、`__pycache__/`、`*.pyc`、`node_modules/`、`.venv/`、`venv/`、`.idea/`、`.vscode/`、`*.tmp`/`*.bak`/`*.swp`、`*.zip`/`*.7z`/`*.rar`、`*.exe`/`*.dll`/`*.so`/`*.dylib`

## 内容嗅探正则（`secret_hits` 判定依据）

```
ghp_[A-Za-z0-9]{20,}           GitHub 经典 PAT
github_pat_[A-Za-z0-9_]{20,}   GitHub 细粒度 PAT
sk-[A-Za-z0-9]{20,}            OpenAI 风格 API Key
AKIA[0-9A-Z]{16}               AWS Access Key ID
-----BEGIN ... PRIVATE KEY-----  私钥文件头
xox[baprs]-[A-Za-z0-9-]{10,}   Slack Token
```

嗅探仅覆盖文本类扩展名（`.py` `.js` `.ts` `.json` `.yaml` `.yml` `.toml` `.md` `.txt` `.sh` `.env` `.cfg` `.ini` `.R`），且跳过大于 2MB 的文件。

## safe_push.py 输出字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `ok` | bool | 是否成功 |
| `dry_run` | bool | 是否为试运行 |
| `remote` | string | 推送目标 URL |
| `branch` | string | 推送分支 |
| `commit` | string | 提交短 SHA |
| `files` | string[] | 本次提交的文件 |
| `message` | string | 提交信息 |
| `commands` | string[] | 实际执行的命令（便于审计） |
| `error` | string | 失败原因 |
| `hint` | string | 失败时的建议 |

`safe_push.py` 退出码：0 成功 / 1 执行失败 / 2 参数或前置检查不通过。

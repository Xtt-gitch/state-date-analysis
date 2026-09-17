#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""扫描本地 git 仓库变更，输出分组清单与风险标记。

用法:
    python scan_changes.py [repo_path]

输出: JSON (stdout)，结构见 references/output_schema.md
退出码: 0 正常 / 1 有阻断级风险 / 2 环境异常
"""

import json
import os
import re
import subprocess
import sys

# 需要阻止提交的文件（密钥、凭据、本机配置）
BLOCK_PATTERNS = [
    (r"(^|/)\.env$", "环境变量文件"),
    (r"(^|/)\.env\.", "环境变量文件"),
    (r"(^|/)\.env\.example$", None),  # 豁免：示例文件允许提交
    (r"\.pem$", "私钥证书"),
    (r"\.key$", "私钥文件"),
    (r"\.p12$", "私钥容器"),
    (r"\.pfx$", "私钥容器"),
    (r"(^|/)id_rsa", "SSH 私钥"),
    (r"(^|/)id_ed25519", "SSH 私钥"),
    (r"(^|/)\.ssh/", "SSH 目录"),
    (r"(^|/)credentials(\.json|\.yaml|\.yml)?$", "凭据文件"),
    (r"(^|/)secrets?\.(json|yaml|yml|toml)$", "密钥文件"),
    (r"(^|/)\.npmrc$", "npm 认证配置"),
    (r"(^|/)\.pypirc$", "PyPI 认证配置"),
    (r"(^|/)\.netrc$", "网络凭据"),
    (r"\.keystore$", "Java 密钥库"),
    (r"\.jks$", "Java 密钥库"),
    (r"(^|/)token\.json$", "令牌文件"),
]

# 建议忽略但需用户判断的文件
WARN_PATTERNS = [
    (r"(^|/)\.DS_Store$", "macOS 系统文件"),
    (r"Thumbs\.db$", "Windows 缩略图缓存"),
    (r"(^|/)desktop\.ini$", "Windows 目录配置"),
    (r"\.(log)$", "日志文件"),
    (r"(^|/)__pycache__/", "Python 字节码缓存"),
    (r"\.pyc$", "Python 字节码"),
    (r"(^|/)node_modules/", "Node 依赖目录"),
    (r"(^|/)\.venv/", "Python 虚拟环境"),
    (r"(^|/)venv/", "Python 虚拟环境"),
    (r"(^|/)\.idea/", "IDE 配置"),
    (r"(^|/)\.vscode/", "IDE 配置"),
    (r"\.(tmp|temp|bak|swp)$", "临时文件"),
    (r"\.(zip|7z|rar)$", "压缩包"),
    (r"\.(exe|dll|so|dylib)$", "二进制可执行文件"),
]

BIG_FILE_MB = 20      # 单文件超过此大小视为大文件，需确认
BIG_FILE_HARD_MB = 80  # 超过此大小强烈建议不上传

# 密钥内容特征（用于已跟踪文件的内容嗅探）
SECRET_VALUE_RE = re.compile(
    r"(ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|"
    r"sk-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|"
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----|"
    r"xox[baprs]-[A-Za-z0-9-]{10,})"
)


def run(args, cwd):
    """执行命令并返回 (returncode, stdout, stderr)。"""
    try:
        p = subprocess.run(
            args, cwd=cwd, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=120,
        )
        return p.returncode, p.stdout.strip(), p.stderr.strip()
    except FileNotFoundError:
        return 127, "", "git 未安装或不在 PATH 中"
    except subprocess.TimeoutExpired:
        return 124, "", "命令执行超时"


def match_any(path, patterns):
    """返回第一个命中的 (原因) 或 None。"""
    norm = path.replace("\\", "/")
    for pat, reason in patterns:
        if reason is None:
            continue
        if re.search(pat, norm, re.IGNORECASE):
            return reason
    return None


def is_exempt(path):
    """检查是否为豁免文件（允许提交）。"""
    norm = path.replace("\\", "/")
    return bool(re.search(r"(^|/)\.env\.(example|sample|template)$", norm, re.I))


def classify(path):
    """给单个文件分类。"""
    norm = path.replace("\\", "/")
    if norm.startswith("data/") or "/data/" in norm:
        return "数据"
    if norm.startswith(("code/", "scripts/")) or "/code/" in norm:
        return "代码"
    if norm.startswith(("notes/", "notes")) or norm.endswith((".md", ".txt", ".rst")):
        return "文档"
    if norm.startswith("homework/") or "/homework/" in norm:
        return "作业"
    if norm.endswith((".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp")):
        return "图片"
    if norm.endswith((".csv", ".xlsx", ".xls", ".json", ".ipynb")):
        return "数据"
    if norm.endswith((".py", ".js", ".ts", ".sh", ".html", ".css", ".r", ".R")):
        return "代码"
    return "其他"


def main():
    repo = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
    repo = os.path.abspath(repo)

    if not os.path.isdir(os.path.join(repo, ".git")):
        print(json.dumps({
            "ok": False,
            "error": f"不是 git 仓库: {repo}",
            "hint": "先执行 git init 或切换到仓库目录",
        }, ensure_ascii=False, indent=2))
        sys.exit(2)

    result = {"ok": True, "repo": repo, "blocked": [], "warned": [],
              "large": [], "groups": {}, "untracked": [], "modified": [],
              "deleted": [], "renamed": [], "has_commits": False,
              "branch": "", "remote": "", "ahead": 0, "behind": 0,
              "secret_hits": [], "stats": {}}

    # 分支与远端
    _, branch, _ = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], repo)
    result["branch"] = branch
    _, remote, _ = run(["git", "remote", "get-url", "origin"], repo)
    result["remote"] = remote

    _, head, _ = run(["git", "rev-parse", "--verify", "HEAD"], repo)
    result["has_commits"] = bool(head)

    # 变更清单（含未跟踪）
    _, out, _ = run(["git", "status", "--porcelain", "-z", "--untracked-files=all"], repo)
    entries = [e for e in out.split("\0") if e]

    for entry in entries:
        code, path = entry[:2], entry[3:]
        norm = path.replace("\\", "/")
        if code.startswith("??"):
            result["untracked"].append(norm)
        elif "D" in code:
            result["deleted"].append(norm)
        elif "R" in code:
            result["renamed"].append(norm)
        else:
            result["modified"].append(norm)

        if code.startswith("??"):
            continue  # 未跟踪文件在下方单独做风险检查

    # 所有待提交文件 = 未跟踪 + 已修改 + 重命名
    candidates = result["untracked"] + result["modified"] + result["renamed"]

    for path in candidates:
        full = os.path.join(repo, path)
        groups = result["groups"].setdefault(classify(path), [])
        groups.append(path)

        if is_exempt(path):
            continue

        reason = match_any(path, BLOCK_PATTERNS)
        if reason:
            result["blocked"].append({"path": path, "reason": reason})
            continue

        wreason = match_any(path, WARN_PATTERNS)
        if wreason:
            result["warned"].append({"path": path, "reason": wreason})

        if os.path.isfile(full):
            mb = os.path.getsize(full) / (1024 * 1024)
            if mb >= BIG_FILE_MB:
                result["large"].append({
                    "path": path,
                    "size_mb": round(mb, 2),
                    "hard": mb >= BIG_FILE_HARD_MB,
                })

    # 内容嗅探：扫描待提交的文本文件是否含密钥
    text_ext = (".py", ".js", ".ts", ".json", ".yaml", ".yml", ".toml",
                ".md", ".txt", ".sh", ".env", ".cfg", ".ini", ".R", ".r")
    for path in candidates:
        if not path.lower().endswith(text_ext):
            continue
        full = os.path.join(repo, path)
        if not os.path.isfile(full):
            continue
        try:
            if os.path.getsize(full) > 2 * 1024 * 1024:
                continue
            with open(full, "r", encoding="utf-8", errors="ignore") as f:
                for lineno, line in enumerate(f, 1):
                    if SECRET_VALUE_RE.search(line):
                        result["secret_hits"].append(
                            {"path": path, "line": lineno,
                             "preview": line.strip()[:80]})
                        break
        except OSError:
            continue

    # 与远端的差距
    if result["has_commits"] and remote:
        run(["git", "fetch", "--quiet", "origin"], repo)
        _, ab, _ = run(
            ["git", "rev-list", "--left-right", "--count",
             f"origin/{branch}...HEAD"], repo)
        if ab and "\t" in ab:
            behind, ahead = ab.split("\t")[:2]
            result["behind"] = int(behind) if behind.isdigit() else 0
            result["ahead"] = int(ahead) if ahead.isdigit() else 0

    result["stats"] = {
        "total": len(candidates),
        "untracked": len(result["untracked"]),
        "modified": len(result["modified"]),
        "deleted": len(result["deleted"]),
        "blocked": len(result["blocked"]),
        "warned": len(result["warned"]),
        "large": len(result["large"]),
    }

    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(1 if (result["blocked"] or result["secret_hits"]) else 0)


if __name__ == "__main__":
    main()

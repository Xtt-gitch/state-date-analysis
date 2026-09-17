#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""安全推送：添加文件、生成提交、推送到远端。

设计原则：
- 只提交显式传入的文件列表，绝不使用 `git add .`
- 推送前打印将执行的命令，便于审计
- SSH 优先；HTTPS 失败时给出明确提示

用法:
    python safe_push.py --repo <path> --files a.txt b.txt --message "提交说明"
    python safe_push.py --repo <path> --files a.txt --message "msg" --dry-run
    python safe_push.py --repo <path> --files a.txt --message "msg" --set-upstream

退出码: 0 成功 / 1 失败 / 2 参数或前置检查失败
"""

import argparse
import json
import os
import subprocess
import sys


def run(args, cwd, allow_fail=False):
    p = subprocess.run(
        args, cwd=cwd, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=300,
    )
    if p.returncode != 0 and not allow_fail:
        raise RuntimeError(
            f"命令失败: {' '.join(args)}\n"
            f"退出码: {p.returncode}\n"
            f"stderr: {p.stderr.strip()}\n"
            f"stdout: {p.stdout.strip()}"
        )
    return p.returncode, p.stdout.strip(), p.stderr.strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--files", nargs="+", required=True)
    ap.add_argument("--message", required=True)
    ap.add_argument("--branch", default="")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--set-upstream", action="store_true")
    ap.add_argument("--allow-empty", action="store_true")
    args = ap.parse_args()

    repo = os.path.abspath(args.repo)
    log = []

    try:
        # 前置检查：远端可达性
        rc, remote, _ = run(["git", "remote", "get-url", "origin"], repo,
                            allow_fail=True)
        if rc != 0 or not remote:
            print(json.dumps({
                "ok": False,
                "error": "未配置 origin 远端",
                "hint": "执行 git remote add origin git@github.com:<用户名>/<仓库>.git",
            }, ensure_ascii=False, indent=2))
            sys.exit(2)

        rc, branch, _ = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], repo)
        branch = args.branch or branch
        if branch == "HEAD":
            branch = "main"
            run(["git", "checkout", "-B", "main"], repo)

        # 校验文件确实存在或被删除
        missing = [f for f in args.files
                   if not os.path.exists(os.path.join(repo, f))]
        if missing:
            print(json.dumps({
                "ok": False,
                "error": "以下路径在工作区中不存在（若为已删除文件，请先在远端确认）",
                "missing": missing,
            }, ensure_ascii=False, indent=2))
            sys.exit(2)

        # 1. 添加
        add_cmd = ["git", "add", "--"] + args.files
        log.append(add_cmd)
        if not args.dry_run:
            run(add_cmd, repo)

        # 2. 检查暂存区
        rc, staged, _ = run(["git", "diff", "--cached", "--name-only"], repo)
        if not staged and not args.allow_empty:
            print(json.dumps({
                "ok": False,
                "error": "暂存区为空，没有可提交的内容",
                "hint": "确认文件确实有变更，或改用 --allow-empty",
            }, ensure_ascii=False, indent=2))
            sys.exit(2)

        # 3. 提交
        commit_cmd = ["git", "commit", "-m", args.message]
        if args.allow_empty:
            commit_cmd.append("--allow-empty")
        log.append(commit_cmd)
        if not args.dry_run:
            run(commit_cmd, repo)
            _, sha, _ = run(["git", "rev-parse", "--short", "HEAD"], repo)
        else:
            sha = "(dry-run)"

        # 4. 推送（SSH 优先，失败自动降级为 HTTPS 提示）
        push_cmd = ["git", "push", "origin", branch]
        if args.set_upstream:
            push_cmd.insert(2, "-u")
        log.append(push_cmd)
        if not args.dry_run:
            rc, out, err = run(push_cmd, repo, allow_fail=True)
            if rc != 0:
                combined = (out + "\n" + err).strip()
                if "Permission denied" in combined or "publickey" in combined:
                    print(json.dumps({
                        "ok": False,
                        "error": "SSH 认证失败",
                        "raw": combined[:600],
                        "hint": "验证 SSH: ssh -T git@github.com；确认密钥已加入 GitHub 账号",
                    }, ensure_ascii=False, indent=2))
                    sys.exit(1)
                if "rejected" in combined or "non-fast-forward" in combined:
                    print(json.dumps({
                        "ok": False,
                        "error": "远端有本地没有的提交，推送被拒",
                        "raw": combined[:600],
                        "hint": "先执行 git pull --rebase origin " + branch + " 再推送",
                    }, ensure_ascii=False, indent=2))
                    sys.exit(1)
                if "schannel" in combined or "SSL" in combined:
                    print(json.dumps({
                        "ok": False,
                        "error": "HTTPS 通道 TLS 握手失败",
                        "raw": combined[:600],
                        "hint": "改用 SSH 远端: git remote set-url origin git@github.com:<user>/<repo>.git",
                    }, ensure_ascii=False, indent=2))
                    sys.exit(1)
                print(json.dumps({
                    "ok": False, "error": "推送失败",
                    "raw": combined[:800],
                }, ensure_ascii=False, indent=2))
                sys.exit(1)

        _, final_sha, _ = run(["git", "rev-parse", "--short", "HEAD"], repo,
                              allow_fail=True)

        print(json.dumps({
            "ok": True,
            "dry_run": args.dry_run,
            "repo": repo,
            "remote": remote,
            "branch": branch,
            "commit": final_sha or sha,
            "files": args.files,
            "message": args.message,
            "commands": [" ".join(c) for c in log],
        }, ensure_ascii=False, indent=2))

    except RuntimeError as e:
        print(json.dumps({
            "ok": False, "error": str(e)[:900], "repo": repo,
        }, ensure_ascii=False, indent=2))
        sys.exit(1)
    except subprocess.TimeoutExpired:
        print(json.dumps({
            "ok": False,
            "error": "命令超时（网络可能不通）",
            "hint": "检查网络或代理设置",
        }, ensure_ascii=False, indent=2))
        sys.exit(1)


if __name__ == "__main__":
    main()

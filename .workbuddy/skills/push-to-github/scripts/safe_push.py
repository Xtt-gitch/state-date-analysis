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
    """执行命令，返回 (returncode, stdout, stderr)。

    显式使用 PIPE 并关闭 stdin：避免 git 等待交互式输入而挂起，
    同时保证异常路径下 stdout/stderr 依然可读。
    """
    p = subprocess.run(
        args, cwd=cwd, stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace", timeout=300,
    )
    out = (p.stdout or "").strip()
    err = (p.stderr or "").strip()
    if p.returncode != 0 and not allow_fail:
        raise RuntimeError(
            f"命令失败: {' '.join(args)}\n"
            f"退出码: {p.returncode}\n"
            f"stderr: {err}\n"
            f"stdout: {out}"
        )
    return p.returncode, out, err


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
            # 文件不在工作区，可能是"已删除"（应正常记录删除）或"路径写错"。
            # 用 git ls-files 判断该路径是否曾被跟踪，据此区别处理。
            _, tracked, _ = run(["git", "ls-files", "--"] + missing,
                                repo, allow_fail=True)
            really_missing = [m for m in missing
                              if m not in tracked.replace("\\", "/").splitlines()]
            if really_missing:
                print(json.dumps({
                    "ok": False,
                    "error": "以下路径在工作区中不存在，且 git 也不认识（疑似路径写错）",
                    "missing": really_missing,
                    "hint": "用 git status 确认实际路径；若确为已删除文件，删除会被正常记录",
                }, ensure_ascii=False, indent=2))
                sys.exit(2)

        # 1. 添加
        add_cmd = ["git", "add", "--"] + args.files
        log.append(add_cmd)
        if not args.dry_run:
            run(add_cmd, repo)

        # 2. 检查暂存区（dry-run 不实际 add，故跳过检查直接预演）
        rc, staged, _ = run(["git", "diff", "--cached", "--name-only"], repo)
        if not staged and not args.allow_empty and not args.dry_run:
            # 区分"确实无改动"与"改动已被此前提交带走"：
            # 后者无需再提交，也不应报错，直接进入推送环节。
            rc2, unpushed, _ = run(
                ["git", "log", "origin/" + branch + "..HEAD", "--oneline"],
                repo, allow_fail=True)
            if rc2 == 0 and unpushed:
                push_cmd = ["git", "push", "origin", branch]
                log.append(push_cmd)
                rc3, out3, err3 = run(push_cmd, repo, allow_fail=True)
                if rc3 != 0:
                    print(json.dumps({
                        "ok": False, "error": "推送失败",
                        "raw": (out3 + "\n" + err3).strip()[:800],
                    }, ensure_ascii=False, indent=2))
                    sys.exit(1)
                _, fs, _ = run(["git", "rev-parse", "--short", "HEAD"], repo,
                               allow_fail=True)
                print(json.dumps({
                    "ok": True, "dry_run": False, "repo": repo,
                    "note": "暂存区为空，已有待推送提交，跳过提交直接推送",
                    "remote": remote, "branch": branch, "commit": fs,
                    "pushed_commits": unpushed.splitlines(),
                    "commands": [" ".join(c) for c in log],
                }, ensure_ascii=False, indent=2))
                sys.exit(0)

            print(json.dumps({
                "ok": False,
                "error": "暂存区为空，且没有待推送的提交",
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

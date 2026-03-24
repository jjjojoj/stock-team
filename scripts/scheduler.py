#!/usr/bin/env python3
"""
OpenClaw cron 兼容适配器

仓库内旧 scheduler 已退役。
当前唯一调度控制面是 OpenClaw cron，本脚本仅保留为兼容入口。

用法:
  python scheduler.py status          # 查看调度器状态
  python scheduler.py list [--json]   # 查看任务列表
  python scheduler.py run <job_id>    # 立即执行某个任务
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _run_openclaw(*args: str) -> subprocess.CompletedProcess[str]:
    """Run an OpenClaw cron command."""
    return subprocess.run(
        ["openclaw", "cron", *args],
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
    )


def _print_completed(result: subprocess.CompletedProcess[str]) -> int:
    """Print stdout/stderr and return the command code."""
    if result.stdout:
        print(result.stdout.strip())
    if result.stderr:
        print(result.stderr.strip(), file=sys.stderr)
    return result.returncode


def show_status() -> int:
    """Show OpenClaw cron scheduler status and a quick job summary."""
    status_result = _run_openclaw("status")
    code = _print_completed(status_result)

    jobs_result = _run_openclaw("list", "--json")
    if jobs_result.returncode != 0:
        return code or _print_completed(jobs_result)

    data = json.loads(jobs_result.stdout or "{}")
    jobs = data.get("jobs", [])
    enabled_jobs = sum(1 for job in jobs if job.get("enabled"))
    error_jobs = sum(
        1
        for job in jobs
        if (job.get("state") or {}).get("lastRunStatus") == "error"
    )

    print("\nOpenClaw Cron Summary")
    print(f"  总任务数: {len(jobs)}")
    print(f"  启用任务: {enabled_jobs}")
    print(f"  最近报错: {error_jobs}")
    return code


def list_jobs(as_json: bool = False) -> int:
    """List OpenClaw cron jobs."""
    result = _run_openclaw("list", "--json" if as_json else "")
    if result.args and result.args[-1] == "":
        result = _run_openclaw("list")
    return _print_completed(result)


def run_job(job_id: str) -> int:
    """Run one OpenClaw cron job immediately."""
    return _print_completed(_run_openclaw("run", job_id))


def print_deprecation(command: str) -> int:
    """Explain why local scheduler lifecycle commands are no longer supported."""
    print(
        f"本地 `{command}` 已退役。当前唯一调度控制面是 OpenClaw cron。\n"
        "请使用:\n"
        "  python scripts/scheduler.py status\n"
        "  python scripts/scheduler.py list\n"
        "  openclaw cron enable <job_id>\n"
        "  openclaw cron disable <job_id>"
    )
    return 1


def main() -> int:
    """CLI entrypoint."""
    if len(sys.argv) <= 1:
        return show_status()

    command = sys.argv[1]
    if command == "status":
        return show_status()
    if command == "list":
        return list_jobs("--json" in sys.argv[2:])
    if command == "run":
        if len(sys.argv) < 3:
            print("用法: python scheduler.py run <job_id>", file=sys.stderr)
            return 1
        return run_job(sys.argv[2])
    if command in {"start", "stop", "restart", "run_once"}:
        return print_deprecation(command)

    print("用法:")
    print("  python scheduler.py status")
    print("  python scheduler.py list [--json]")
    print("  python scheduler.py run <job_id>")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""
Enhanced Cron Handler for OpenClaw Cron Tasks
Integrates with existing dashboard_v3.py
"""

import json
import subprocess
import os
import re
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)


def extract_script_key(job):
    """Best-effort extraction of the underlying script name from a cron payload."""
    payload = job.get('payload', {}) or {}
    message = payload.get('message', '') or ''

    match = re.search(r"scripts/([A-Za-z0-9_]+)\.py", message)
    if match:
        return match.group(1)

    name = (job.get('name') or '').strip().lower()
    fallback_map = {
        '规则验证（每日）': 'rule_validator',
        '每日炒股书籍学习': 'daily_book_learning',
        '每日预测复盘': 'daily_review_closed_loop',
        '收盘复盘 + 选股标准进化': 'market_review_v2',
        '选股层 - 动态标准选股': 'selector',
        '交易层 - 自动买入': 'auto_trader_v3',
        '交易层 - 自动卖出': 'auto_trader_v3',
    }
    for display_name, script_key in fallback_map.items():
        if job.get('name') == display_name:
            return script_key

    return re.sub(r'[^a-z0-9]+', '_', name).strip('_')


def derive_display_status(job, state=None):
    """Map OpenClaw run/delivery state into a dashboard-friendly status."""
    state = state or job.get('state', {}) or {}
    raw_status = state.get('lastRunStatus') or state.get('lastStatus') or 'idle'
    last_error = (state.get('lastError') or '').strip()
    delivery_status = (state.get('lastDeliveryStatus') or '').strip()
    delivery_mode = ((job.get('delivery') or {}).get('mode') or '').strip()
    last_run_at = state.get('lastRunAtMs') or 0
    updated_at = job.get('updatedAtMs') or 0

    if state.get('runningAtMs'):
        return {
            'status': 'running',
            'status_label': 'running',
            'status_color': 'accent',
            'status_detail': '任务执行中',
            'raw_status': raw_status,
        }

    if delivery_mode == 'none' and raw_status == 'error' and updated_at > last_run_at:
        return {
            'status': 'ok',
            'status_label': 'history_cleared',
            'status_color': 'success',
            'status_detail': '旧错误来自切换前状态；当前已改为脚本 webhook，等待下次运行覆盖历史记录',
            'raw_status': raw_status,
        }

    if raw_status == 'error' and 'message failed' in last_error.lower():
        return {
            'status': 'warning',
            'status_label': 'notify_failed',
            'status_color': 'warning',
            'status_detail': '脚本可能已执行，通知发送失败',
            'raw_status': raw_status,
        }

    return {
        'status': raw_status,
        'status_label': raw_status,
        'status_color': get_status_color(raw_status),
        'status_detail': last_error or delivery_status,
        'raw_status': raw_status,
    }

def get_openclaw_cron_status():
    """
    Get real-time cron status from OpenClaw CLI
    Returns structured data for frontend display
    """
    try:
        # Execute openclaw cron list --json
        result = subprocess.run(
            ['openclaw', 'cron', 'list', '--json'],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode != 0:
            logger.error(f"OpenClaw cron list failed: {result.stderr}")
            return []
            
        cron_data = json.loads(result.stdout)
        jobs = cron_data.get('jobs', [])
        
        # Process each job into display format
        processed_jobs = []
        for job in jobs:
            # Get state object for timestamps and status
            state = job.get('state', {})
            
            # Convert timestamps to readable format
            last_run = state.get('lastRunAtMs')
            next_run = state.get('nextRunAtMs')
            
            last_run_str = format_timestamp(last_run) if last_run else "从未运行"
            next_run_str = format_timestamp(next_run) if next_run else "未计划"
            
            # Determine status color from state
            status_info = derive_display_status(job, state)
            
            # Extract schedule info
            schedule_info = job.get('schedule', {})
            schedule_expr = schedule_info.get('expr', 'unknown')
            
            processed_job = {
                'id': job.get('id'),
                'name': job.get('name', 'Unknown'),
                'schedule': schedule_expr,
                'enabled': job.get('enabled', True),
                'last_run': last_run_str,
                'next_run': next_run_str,
                'status': status_info['status'],
                'status_label': status_info['status_label'],
                'status_color': status_info['status_color'],
                'status_detail': status_info['status_detail'],
                'raw_status': status_info['raw_status'],
                'last_error': state.get('lastError'),
                'last_delivery_status': state.get('lastDeliveryStatus'),
                'script_key': extract_script_key(job),
                'agent_id': job.get('agentId', 'main'),
                'agentId': job.get('agentId', 'main'),  # Alias for HTML compatibility
                'last_run_raw': last_run or 0,  # Raw timestamp for sorting
                'next_run_raw': next_run or 0,  # Raw timestamp for sorting
                'model': '-',
                'target': job.get('sessionTarget', 'isolated')
            }
            processed_jobs.append(processed_job)
            
        return processed_jobs
        
    except Exception as e:
        logger.error(f"Failed to get OpenClaw cron status: {e}")
        return []

def format_timestamp(timestamp_ms):
    """Convert millisecond timestamp to readable string"""
    if not timestamp_ms:
        return "N/A"
    
    # Convert to datetime (assuming timestamp is in milliseconds)
    dt = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
    # Convert to local time (Asia/Shanghai)
    local_dt = dt.astimezone()
    return local_dt.strftime('%Y-%m-%d %H:%M')

def get_status_color(status):
    """Map status to color class"""
    status_colors = {
        'ok': 'success',
        'error': 'error',
        'warning': 'warning',
        'idle': 'warning',
        'running': 'accent'
    }
    return status_colors.get(status, 'text-secondary')

def handle_api_openclaw_cron():
    """API endpoint handler for OpenClaw cron data"""
    try:
        cron_data = get_openclaw_cron_status()
        return {
            "cron_tasks": cron_data,
            "total_count": len(cron_data),
            "success_count": sum(1 for task in cron_data if task['status'] == 'ok'),
            "error_count": sum(1 for task in cron_data if task['status'] == 'error'),
            "warning_count": sum(1 for task in cron_data if task['status'] == 'warning'),
            "last_updated": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
    except Exception as e:
        logger.error(f"API error: {e}")
        return {"error": str(e)}

if __name__ == "__main__":
    # Test function
    cron_status = get_openclaw_cron_status()
    print(json.dumps(cron_status, indent=2, ensure_ascii=False))

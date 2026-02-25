# -*- coding: utf-8 -*-
"""
每日汇总脚本：22:45最终汇报+清理文档，支持手动终止
cron: 45 22 * * *
new Env('OpenWrt监控-每日汇总');
"""
import requests
import time
import threading
import traceback
import gc
import signal
import sys
import os
import json
from config import *

# ====================== 全局变量 ======================
manual_stop_flag = False
current_operation_running = False

# ====================== 工具函数 ======================
def init_log():
    """初始化日志目录"""
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR, exist_ok=True)

def print_log(msg):
    """打印带时间戳的日志"""
    log_msg = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(log_msg)
    log_file = os.path.join(LOG_DIR, f"daily_{time.strftime('%Y%m%d')}.log")
    try:
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(log_msg + '\n')
    except:
        pass
    return log_msg

def safe_read_json(file_path):
    """容错读取JSON"""
    if not os.path.exists(file_path):
        return {"date": time.strftime('%Y-%m-%d'), "push_records": [], "manual_stop": False}
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            decoder = json.JSONDecoder()
            raw_data = f.read()
            data, _ = decoder.raw_decode(raw_data)
            return data
    except json.JSONDecodeError as e:
        print_log(f"JSON解析错误：{e}，使用空模板")
        return {"date": time.strftime('%Y-%m-%d'), "push_records": [], "manual_stop": False}
    except Exception as e:
        print_log(f"JSON读取失败：{e}，使用空模板")
        return {"date": time.strftime('%Y-%m-%d'), "push_records": [], "manual_stop": False}

def emergency_clean():
    """手动终止时紧急清理"""
    global current_operation_running
    current_operation_running = True
    print_log("执行紧急清理...")
    
    # 强制删除所有文档
    files_to_delete = [DETECT_REALTIME_FILE, PUSH_ARCHIVE_FILE, DAILY_FINAL_FILE]
    for f in files_to_delete:
        if os.path.exists(f):
            try:
                os.remove(f)
                print_log(f"✅ 删除文件：{f}")
            except Exception as e:
                print_log(f"⚠️  删除文件失败：{f} - {e}")
    
    current_operation_running = False
    print_log("紧急清理完成")

def signal_handler(signum, frame):
    """捕获手动终止信号"""
    global manual_stop_flag
    manual_stop_flag = True
    print_log("⚠️  检测到手动终止信号")
    emergency_clean()
    gc.collect()
    sys.exit(0)

# 注册终止信号
try:
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
except Exception as e:
    print_log(f"信号监听兼容提示：{e}")

# ====================== 汇总核心函数 ======================
def get_qywx_token():
    """获取企业微信Token"""
    try:
        url = f"https://qyapi.weixin.qq.com/cgi-bin/gettoken?corpid={CORP_ID}&corpsecret={CORP_SECRET}"
        resp = requests.get(url, timeout=10).json()
        if resp.get("errcode") == 0:
            return resp.get("access_token")
        else:
            print_log(f"❌ 获取Token失败：{resp}")
            return None
    except Exception as e:
        print_log(f"❌ 获取Token异常：{str(e)}")
        return None

def send_qywx_msg(content):
    """发送企业微信消息"""
    token = get_qywx_token()
    if not token:
        return False
    try:
        send_url = f"https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token={token}"
        data = {
            "touser": TO_USER,
            "msgtype": "text",
            "agentid": AGENT_ID,
            "text": {"content": content},
            "safe": 0
        }
        resp = requests.post(send_url, json=data, timeout=10).json()
        if resp.get("errcode") == 0:
            print_log("✅ 每日最终报告发送成功")
            return True
        else:
            print_log(f"❌ 发送最终报告失败：{resp}")
            return False
    except Exception as e:
        print_log(f"❌ 发送最终报告异常：{str(e)}")
        return False

def summarize_daily_data():
    """汇总当日所有推送数据"""
    archive_data = safe_read_json(PUSH_ARCHIVE_FILE)
    push_records = archive_data.get("push_records", [])
    if not push_records:
        return {
            "total_push": 0,
            "total_detect": 0,
            "total_abnormal": 0,
            "max_abnormal_target": "",
            "avg_availability_rate": 100.0,
            "manual_stop": archive_data.get("manual_stop", False),
            "date": archive_data.get("date", time.strftime('%Y-%m-%d'))
        }
    
    # 统计数据
    total_push = len(push_records)
    total_detect = sum([r["total_detect"] for r in push_records])
    total_abnormal = sum([r["abnormal"] for r in push_records])
    
    # 异常目标统计
    abnormal_target_count = {}
    for r in push_records:
        for target in r["abnormal_targets"]:
            abnormal_target_count[target] = abnormal_target_count.get(target, 0) + 1
    max_abnormal_target = max(abnormal_target_count.items(), key=lambda x: x[1], default=("", 0))
    
    # 平均可用率
    availability_rates = [r["availability_rate"] for r in push_records if r["total_detect"] > 0]
    avg_availability_rate = round(sum(availability_rates)/len(availability_rates), 1) if availability_rates else 100.0
    
    return {
        "total_push": total_push,
        "total_detect": total_detect,
        "total_abnormal": total_abnormal,
        "max_abnormal_target": max_abnormal_target[0],
        "max_abnormal_count": max_abnormal_target[1],
        "avg_availability_rate": avg_availability_rate,
        "manual_stop": archive_data.get("manual_stop", False),
        "date": archive_data.get("date", time.strftime('%Y-%m-%d'))
    }
def generate_daily_md(summary, content):
    """生成每日最终MD文档"""
    md_content = f"""# OpenWrt智能监控 · {summary['date']} 每日报告
## 汇总信息
- 推送次数：{summary['total_push']} 次
- 检测总次数：{summary['total_detect']} 次
- 异常总次数：{summary['total_abnormal']} 次
- 平均可用率：{summary['avg_availability_rate']}%
- 汇总时间：{time.strftime('%Y-%m-%d %H:%M:%S')}
- 手动终止：{summary['manual_stop']}

## 异常统计
- 异常最多目标：{summary['max_abnormal_target']}（{summary['max_abnormal_count']}次）

## 企业微信通知内容
{content}
"""
    try:
        with open(DAILY_FINAL_FILE, 'w', encoding='utf-8') as f:
            f.write(md_content)
        print_log("✅ 每日MD报告生成成功")
    except Exception as e:
        print_log(f"❌ MD报告生成失败：{e}")
📅 OpenWrt智能监控 · {date} 每日最终报告
━━━━━━━━━━━━━━━━━━━━━━━━
📊 当日概览：暂无推送数据
🕒 汇总时间：{now}
⚠️  状态：手动终止={summary['manual_stop']}
━━━━━━━━━━━━━━━━━━━━━━━━
🔹 运行时段：0-22点 | 汇总时间：22:45
🔹 数据清理：已执行 | 明日0点重新开始
""".strip()
    else:
        if summary["total_abnormal"] == 0:
            content = f"""
📅 OpenWrt智能监控 · {date} 每日最终报告
━━━━━━━━━━━━━━━━━━━━━━━━
📊 当日概览：
  • 推送次数：{summary['total_push']} 次
  • 检测总次数：{summary['total_detect']} 次
  • 异常总次数：{summary['total_abnormal']} 次
  • 平均可用率：{summary['avg_availability_rate']}%
🕒 汇总时间：{now}
⚠️  状态：手动终止={summary['manual_stop']}

✅ 当日所有检测目标均正常：
  • 域名：{', '.join(TEST_DOMAINS)}
  • 端口：{', '.join(TEST_IP_PORTS)}
━━━━━━━━━━━━━━━━━━━━━━━━
🔹 运行时段：0-22点 | 汇总时间：22:45
🔹 数据清理：已执行 | 明日0点重新开始
""".strip()
        else:
            content = f"""
📅 OpenWrt智能监控 · {date} 每日最终报告
━━━━━━━━━━━━━━━━━━━━━━━━
📊 当日概览：
  • 推送次数：{summary['total_push']} 次
  • 检测总次数：{summary['total_detect']} 次
  • 异常总次数：{summary['total_abnormal']} 次
  • 平均可用率：{summary['avg_availability_rate']}%
🕒 汇总时间：{now}
⚠️  状态：手动终止={summary['manual_stop']}

❌ 异常最多目标：
  • {summary['max_abnormal_target']}（异常{summary['max_abnormal_count']}次）
━━━━━━━━━━━━━━━━━━━━━━━━
🔹 运行时段：0-22点 | 汇总时间：22:45
🔹 数据清理：已执行 | 明日0点重新开始
""".strip()
    return content

def generate_daily_md(summary, content):
    """生成每日最终MD文档"""
    md_content = f"""# OpenWrt智能监控 · {summary['date']} 每日报告
## 汇总信息
- 推送次数：{summary['total_push']} 次
- 检测总次数：{summary['total_detect']} 次
- 异常总次数：{summary['total_abnormal']} 次
- 平均可用率：{summary['avg_availability_rate']}%
- 汇总时间：{time.strftime('%Y-%m-%d %H:%M:%S')}
- 手动终止：{summary['manual_stop']}

## 异常统计
- 异常最多目标：{summary['max_abnormal_target']}（{summary['max_abnormal_count']}次）

## 企业微信通知内容
# -*- coding: utf-8 -*-
"""
OpenWrt智能监控 - 推送脚本
功能：读取检测数据，异常时推送企业微信，正常时不推送
适配：与detect_script.py联动，统一数据路径
"""
import os
import json
import time
import requests
from datetime import datetime

# ===================== 全局配置 =====================
BASE_DIR = "/ql/data/scripts/Cigarr_openwrt-monitor-V1_master"
DETECT_REALTIME_FILE = os.path.join(BASE_DIR, "detect_realtime.json")
PUSH_ARCHIVE_FILE = os.path.join(BASE_DIR, "push_archive.json")
CORP_ID = ""
CORP_SECRET = ""
AGENT_ID = ""

# ===================== 工具函数 =====================
def print_log(msg):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {msg}")

def safe_read_json(file_path):
    if not os.path.exists(file_path):
        return {}
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print_log(f"读取JSON失败: {e}")
        return {}

def safe_write_json(file_path, data):
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print_log(f"写入JSON失败: {e}")
        return False

def send_wechat_msg(content):
    if not all([CORP_ID, CORP_SECRET, AGENT_ID]):
        print_log("企业微信配置未完善，跳过推送")
        return False
    try:
        token_url = f"https://qyapi.weixin.qq.com/cgi-bin/gettoken?corpid={CORP_ID}&corpsecret={CORP_SECRET}"
        token_res = requests.get(token_url, timeout=10)
        token_res.raise_for_status()
        access_token = token_res.json().get("access_token")
        if not access_token:
            print_log("获取企业微信token失败")
            return False
        push_url = f"https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token={access_token}"
        push_data = {
            "touser": "@all",
            "msgtype": "text",
            "agentid": AGENT_ID,
            "text": {"content": content},
            "safe": 0
        }
        push_res = requests.post(push_url, json=push_data, timeout=10)
        push_res.raise_for_status()
        if push_res.json().get("errcode") == 0:
            print_log("企业微信推送成功")
            return True
        else:
            print_log(f"推送失败：{push_res.json()}")
            return False
    except Exception as e:
        print_log(f"推送异常：{e}")
        return False

def summarize_detect_data():
    realtime_data = safe_read_json(DETECT_REALTIME_FILE)
    if not realtime_data or "detect_records" not in realtime_data:
        return {"total_detect": 0, "abnormal": 0, "abnormal_records": []}
    detect_records = realtime_data["detect_records"]
    total_detect = len(detect_records)
    abnormal_records = [r for r in detect_records if r["status"] == "abnormal"]
    abnormal_count = len(abnormal_records)
    return {
        "total_detect": total_detect,
        "abnormal": abnormal_count,
        "abnormal_records": abnormal_records
    }

def generate_push_content(summary):
    if summary["abnormal"] == 0:
        return None
    content = "OpenWrt监控异常告警\n"
    content += f"检测总次数：{summary['total_detect']}次\n"
    content += f"异常次数：{summary['abnormal']}次\n"
    for record in summary["abnormal_records"][-3:]:
        content += f"- {record['detect_time']}：{record['max_abnormal_target']} 异常{record['abnormal_count']}次\n"
    return content

def archive_push_result(summary):
    archive_data = safe_read_json(PUSH_ARCHIVE_FILE)
    if not archive_data:
        archive_data = {"date": datetime.now().strftime("%Y-%m-%d"), "push_records": []}
    push_record = {
        "push_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_detect": summary["total_detect"],
        "abnormal": summary["abnormal"]
    }
    archive_data["push_records"].append(push_record)
    safe_write_json(PUSH_ARCHIVE_FILE, archive_data)

def main():
    # ===== 新增：脚本名称日志标识 =====
    print_log("===== OpenWrt监控-异常推送脚本 启动 =====")
    summary = summarize_detect_data()
    print_log(f"检测汇总：总次数{summary['total_detect']}，异常{summary['abnormal']}")
    content = generate_push_content(summary)
    if content:
        send_wechat_msg(content)
        archive_push_result(summary)
    else:
        print_log("无异常，跳过推送")
    print_log("===== OpenWrt监控-异常推送脚本 执行完成 =====")

if __name__ == "__main__":
    main()
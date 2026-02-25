# -*- coding: utf-8 -*-
"""
OpenWrt智能监控 - 异常推送脚本
功能：读取检测数据，异常时推送科技感企业微信消息
"""
import os
import sys
import json
import time
import requests
from datetime import datetime

# ===================== 核心：导入统一配置 =====================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

# 导入config配置（容错）
try:
    import config
except ImportError:
    print(f"[ERROR] 未找到config.py配置文件！")
    sys.exit(1)

# ===================== 全局变量（从config读取） =====================
DETECT_REALTIME_FILE = config.DETECT_REALTIME_FILE
PUSH_ARCHIVE_FILE = config.PUSH_ARCHIVE_FILE
CORP_ID = config.CORP_ID
CORP_SECRET = config.CORP_SECRET
AGENT_ID = config.AGENT_ID
TO_USER = config.TO_USER
DEBOUNCE_TIMES = config.DEBOUNCE_TIMES

# ===================== 工具函数 =====================
def print_log(msg):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] 📤 {msg}")

def safe_read_json(file_path):
    if not os.path.exists(file_path):
        return {}
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print_log(f"❌ 读取JSON失败: {str(e)}")
        return {}

def safe_write_json(file_path, data):
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print_log(f"❌ 写入JSON失败: {str(e)}")
        return False

def get_wechat_token():
    """获取企业微信access_token"""
    try:
        token_url = f"https://qyapi.weixin.qq.com/cgi-bin/gettoken?corpid={CORP_ID}&corpsecret={CORP_SECRET}"
        res = requests.get(token_url, timeout=10)
        res.raise_for_status()
        token_data = res.json()
        if token_data.get("errcode") != 0:
            print_log(f"❌ 获取Token失败：{token_data}")
            return None
        return token_data["access_token"]
    except Exception as e:
        print_log(f"❌ 获取Token异常：{str(e)}")
        return None

def send_wechat_tech_msg(content):
    """发送科技感企业微信消息（优化排版）"""
    token = get_wechat_token()
    if not token:
        return False
    
    # 科技感消息模板（使用Emoji+分隔线+对齐）
    tech_content = f"""
┌─────────────────────────┐
🚨 【OpenWrt监控异常告警】 🚨
├─────────────────────────┤
📅 检测时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
{content}
├─────────────────────────┤
🔧 防抖阈值：{DEBOUNCE_TIMES}次 | 📡 监控节点：{len(config.TEST_DOMAINS)+len(config.TEST_IP_PORTS)}个
└─────────────────────────┘
"""
    
    try:
        push_url = f"https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token={token}"
        push_data = {
            "touser": TO_USER,
            "msgtype": "text",
            "agentid": AGENT_ID,
            "text": {"content": tech_content.strip()},
            "safe": 0,
            "enable_id_trans": 0,
            "enable_duplicate_check": 1,
            "duplicate_check_interval": 600  # 10分钟内避免重复推送
        }
        res = requests.post(push_url, json=push_data, timeout=10)
        res.raise_for_status()
        result = res.json()
        
        if result.get("errcode") == 0:
            print_log("✅ 科技感告警推送成功")
            return True
        else:
            print_log(f"❌ 告警推送失败：{result}")
            return False
    except Exception as e:
        print_log(f"❌ 告警推送异常：{str(e)}")
        return False

def summarize_detect_data():
    """汇总实时检测数据"""
    realtime_data = safe_read_json(DETECT_REALTIME_FILE)
    if not realtime_data or "detect_records" not in realtime_data:
        return {
            "total_detect": 0,
            "abnormal": 0,
            "abnormal_records": [],
            "abnormal_continuous_count": 0,
            "date": datetime.now().strftime("%Y-%m-%d")
        }
    
    # 取最新的检测记录
    detect_records = realtime_data["detect_records"]
    latest_record = detect_records[-1] if detect_records else {}
    
    return {
        "total_detect": len(detect_records),
        "abnormal": latest_record.get("abnormal_count", 0),
        "abnormal_records": [r for r in detect_records if r.get("status") == "abnormal"],
        "abnormal_continuous_count": realtime_data.get("abnormal_continuous_count", 0),
        "date": realtime_data.get("date", datetime.now().strftime("%Y-%m-%d")),
        "latest_record": latest_record
    }

def generate_tech_push_content(summary):
    """生成科技感推送内容"""
    if summary["abnormal_continuous_count"] < DEBOUNCE_TIMES:
        return None  # 未达到防抖次数，不推送
    
    latest = summary["latest_record"]
    if not latest or latest.get("status") != "abnormal":
        return None
    
    # 构建科技感内容
    content_lines = []
    content_lines.append(f"📊 累计检测：{summary['total_detect']}次")
    content_lines.append(f"⚠️  异常目标：{latest['abnormal_count']}个")
    content_lines.append(f"📈 可用率：{latest['availability_rate']}%")
    
    # 异常目标详情
    if latest.get("abnormal_targets"):
        content_lines.append(f"\n🔍 异常详情：")
        for idx, target in enumerate(latest["abnormal_targets"], 1):
            content_lines.append(f"  {idx}. {target}")
    
    return "\n".join(content_lines)

def archive_push_result(summary):
    """归档推送结果"""
    archive_data = safe_read_json(PUSH_ARCHIVE_FILE)
    if not archive_data:
        archive_data = {"date": summary["date"], "push_records": []}
    
    # 补充今日日期
    if archive_data["date"] != summary["date"]:
        archive_data["date"] = summary["date"]
        archive_data["push_records"] = []
    
    # 写入推送记录
    push_record = {
        "push_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_detect": summary["total_detect"],
        "abnormal": summary["abnormal"],
        "abnormal_continuous_count": summary["abnormal_continuous_count"]
    }
    archive_data["push_records"].append(push_record)
    safe_write_json(PUSH_ARCHIVE_FILE, archive_data)

# ===================== 主函数 =====================
def main():
    print_log("===== 🚀 OpenWrt监控-异常推送脚本 启动 =====")
    summary = summarize_detect_data()
    print_log(f"📊 检测汇总：总次数{summary['total_detect']}，当前异常{summary['abnormal']}个，连续异常{summary['abnormal_continuous_count']}次")
    
    # 生成科技感推送内容
    content = generate_tech_push_content(summary)
    if content:
        send_wechat_tech_msg(content)
        archive_push_result(summary)
    else:
        print_log("ℹ️  未达到防抖阈值/无异常，跳过推送")
    
    print_log("===== 🎉 OpenWrt监控-异常推送脚本 执行完成 =====")

if __name__ == "__main__":
    main()
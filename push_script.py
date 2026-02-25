# -*- coding: utf-8 -*-
"""
推送脚本：0-22点汇总检测结果，推送企业微信+归档，支持手动终止
cron: 0 */3 * * *  # 青龙定时：每3小时触发（可自定义）
new Env('OpenWrt监控-推送脚本');
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
    log_file = os.path.join(LOG_DIR, f"push_{time.strftime('%Y%m%d')}.log")
    try:
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(log_msg + '\n')
    except:
        pass
    return log_msg

def check_running_time():
    """检查是否在运行时段（0-22点）"""
    current_hour = time.localtime().tm_hour
    if current_hour >= RUN_HOUR_END or current_hour < RUN_HOUR_START:
        print_log(f"当前时间{current_hour}点，超出0-22点运行时段，脚本退出")
        sys.exit(0)

def safe_write_json(file_path, data):
    """原子化写入JSON"""
    temp_path = f"{file_path}.tmp"
    try:
        with open(temp_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        if os.path.exists(file_path):
            os.remove(file_path)
        os.rename(temp_path, file_path)
        return True
    except Exception as e:
        print_log(f"JSON写入失败：{e}")
        if os.path.exists(temp_path):
            os.remove(temp_path)
        return False

def safe_read_json(file_path):
    """容错读取JSON"""
    if not os.path.exists(file_path):
        return {"date": time.strftime('%Y-%m-%d'), "detect_records": [], "manual_stop": False}
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            decoder = json.JSONDecoder()
            raw_data = f.read()
            data, _ = decoder.raw_decode(raw_data)
            return data
    except json.JSONDecodeError as e:
        print_log(f"JSON解析错误：{e}，使用空模板")
        return {"date": time.strftime('%Y-%m-%d'), "detect_records": [], "manual_stop": False}
    except Exception as e:
        print_log(f"JSON读取失败：{e}，使用空模板")
        return {"date": time.strftime('%Y-%m-%d'), "detect_records": [], "manual_stop": False}

def emergency_archive():
    """手动终止时紧急归档"""
    global current_operation_running
    current_operation_running = True
    print_log("执行紧急归档...")
    
    # 读取归档数据
    archive_data = safe_read_json(PUSH_ARCHIVE_FILE)
    archive_data["date"] = time.strftime('%Y-%m-%d')
    archive_data["manual_stop"] = True
    archive_data["stop_time"] = time.strftime('%Y-%m-%d %H:%M:%S')
    
    # 保存归档
    if safe_write_json(PUSH_ARCHIVE_FILE, archive_data):
        print_log("紧急归档成功")
    current_operation_running = False

def signal_handler(signum, frame):
    """捕获手动终止信号"""
    global manual_stop_flag
    manual_stop_flag = True
    print_log("⚠️  检测到手动终止信号")
    emergency_archive()
    gc.collect()
    sys.exit(0)

# 注册终止信号
try:
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
except Exception as e:
    print_log(f"信号监听兼容提示：{e}")

# ====================== 推送核心函数 ======================
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
            print_log("✅ 企业微信通知发送成功")
            return True
        else:
            print_log(f"❌ 发送通知失败：{resp}")
            return False
    except Exception as e:
        print_log(f"❌ 发送通知异常：{str(e)}")
        return False

def summarize_detect_data():
    """汇总检测数据"""
    # 读取检测数据
    detect_data = safe_read_json(DETECT_REALTIME_FILE)
    records = detect_data.get("detect_records", [])
    if not records:
        return {
            "total_detect": 0,
            "success": 0,
            "abnormal": 0,
            "abnormal_targets": [],
            "availability_rate": 100.0,
            "manual_stop": detect_data.get("manual_stop", False)
        }
    
    # 统计数据
    total = len(records)
    abnormal = sum(1 for r in records if r["status"] == "abnormal")
    success = total - abnormal
    abnormal_targets = list(set([r["target"] for r in records if r["status"] == "abnormal"]))
    availability_rate = round((success/total)*100, 1) if total > 0 else 100.0
    
    return {
        "total_detect": total,
        "success": success,
        "abnormal": abnormal,
        "abnormal_targets": abnormal_targets,
        "availability_rate": availability_rate,
        "manual_stop": detect_data.get("manual_stop", False),
        "detect_date": detect_data.get("date", time.strftime('%Y-%m-%d'))
    }

def generate_push_content(summary):
    """生成推送内容"""
    now = time.strftime('%Y-%m-%d %H:%M:%S')
    if summary["total_detect"] == 0:
        content = f"""
🟢 OpenWrt智能监控 · 临时汇总报告
━━━━━━━━━━━━━━━━━━━━━━━━
📊 检测概览：暂无检测数据
🕒 推送时间：{now}
⚠️  状态：手动终止={summary['manual_stop']}
━━━━━━━━━━━━━━━━━━━━━━━━
🔹 检测节点：青龙面板(Docker) | 运行时段：0-22点
""".strip()
    else:
        if summary["abnormal"] == 0:
            content = f"""
🟢 OpenWrt智能监控 · 临时汇总报告
━━━━━━━━━━━━━━━━━━━━━━━━
📊 检测概览：总次数{summary['total_detect']}次 | 异常{summary['abnormal']}次 | 可用率{summary['availability_rate']}%
🕒 推送时间：{now}
⚠️  状态：手动终止={summary['manual_stop']}

📡 所有检测目标均正常：
  • 域名：{', '.join(TEST_DOMAINS)}
  • 端口：{', '.join(TEST_IP_PORTS)}
━━━━━━━━━━━━━━━━━━━━━━━━
🔹 检测节点：青龙面板(Docker) | 运行时段：0-22点
""".strip()
        else:
            content = f"""
🔴 OpenWrt智能监控 · 临时汇总报告
━━━━━━━━━━━━━━━━━━━━━━━━
📊 检测概览：总次数{summary['total_detect']}次 | 异常{summary['abnormal']}次 | 可用率{summary['availability_rate']}%
🕒 推送时间：{now}
⚠️  状态：手动终止={summary['manual_stop']}

❌ 异常目标：
  {chr(10).join([f'• {target}' for target in summary['abnormal_targets']])}
━━━━━━━━━━━━━━━━━━━━━━━━
🔹 检测节点：青龙面板(Docker) | 运行时段：0-22点
""".strip()
    return content

def archive_push_result(summary):
    """归档推送结果"""
    # 读取已有归档
    archive_data = safe_read_json(PUSH_ARCHIVE_FILE)
    archive_data["date"] = time.strftime('%Y-%m-%d')
    
    # 新增推送记录
    push_record = {
        "push_time": time.strftime('%Y-%m-%d %H:%M:%S'),
        "total_detect": summary["total_detect"],
        "success": summary["success"],
        "abnormal": summary["abnormal"],
        "abnormal_targets": summary["abnormal_targets"],
        "availability_rate": summary["availability_rate"],
        "manual_stop": summary["manual_stop"]
    }
    
    # 追加记录
    if "push_records" not in archive_data:
        archive_data["push_records"] = []
    archive_data["push_records"].append(push_record)
    archive_data["manual_stop"] = False  # 重置终止标记
    
    # 保存归档
    safe_write_json(PUSH_ARCHIVE_FILE, archive_data)
    print_log("✅ 推送结果归档成功")

# ====================== 主函数 ======================
def main():
    global manual_stop_flag
    try:
        init_log()
        check_running_time()  # 检查运行时段
        print_log("🚀 推送脚本启动")
        
        # 初始化归档文档
        if not os.path.exists(PUSH_ARCHIVE_FILE):
            init_data = {
                "date": time.strftime('%Y-%m-%d'),
                "push_records": [],
                "manual_stop": False
            }
            safe_write_json(PUSH_ARCHIVE_FILE, init_data)
        
        # 汇总检测数据
        summary = summarize_detect_data()
        print_log(f"📊 检测汇总：总次数{summary['total_detect']}，异常{summary['abnormal']}")
        
        # 生成并推送内容
        content = generate_push_content(summary)
        send_qywx_msg(content)
        
        # 归档推送结果
        if not manual_stop_flag:
            archive_push_result(summary)
        
        # 清空实时检测文档（可选）
        if not summary["manual_stop"] and not manual_stop_flag:
            init_data = {
                "date": time.strftime('%Y-%m-%d'),
                "detect_records": [],
                "manual_stop": False
            }
            safe_write_json(DETECT_REALTIME_FILE, init_data)
            print_log("✅ 实时检测文档已清空")
        
        print_log("🏁 推送脚本正常结束")
    except Exception as e:
        print_log(f"❌ 推送脚本异常：{str(e)}")
        traceback.print_exc()
        emergency_archive()
    finally:
        gc.collect()

if __name__ == "__main__":
    main()
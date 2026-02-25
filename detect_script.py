# -*- coding: utf-8 -*-
"""
OpenWrt智能监控 - 核心检测脚本
功能：手动/自动检测网络连通性，写入实时数据，支持防抖
"""
import os
import sys
import json
import time
import random
import traceback
import signal
import socket
from datetime import datetime, time as dt_time

# ===================== 核心：导入统一配置 =====================
# 获取脚本目录，加入Python搜索路径
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
# 配置读取
DETECT_REALTIME_FILE = config.DETECT_REALTIME_FILE
MANUAL_FLAG_FILE = config.MANUAL_FLAG_FILE
TEST_DOMAINS = config.TEST_DOMAINS
TEST_IP_PORTS = config.TEST_IP_PORTS
DETECT_TIMES_PER_RUN = config.DETECT_TIMES_PER_RUN
DETECT_TIME_RANGE = config.DETECT_TIME_RANGE
RUN_HOUR_START = config.RUN_HOUR_START
RUN_HOUR_END = config.RUN_HOUR_END
TIMEOUT = config.TIMEOUT
RETRY_TIMES = config.RETRY_TIMES
DEBOUNCE_TIMES = config.DEBOUNCE_TIMES

manual_stop_flag = False
abnormal_continuous_count = 0  # 连续异常计数（防抖）

# ===================== 工具函数 =====================
def print_log(msg):
    """带时间戳的日志输出"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] 📡 {msg}")

def safe_write_json(file_path, data):
    """安全写入JSON，自动创建目录"""
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print_log(f"❌ 写入JSON失败: {str(e)}")
        return False

def safe_read_json(file_path):
    """安全读取JSON，兼容文件不存在/格式错误"""
    if not os.path.exists(file_path):
        return {}
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print_log(f"❌ 读取JSON失败: {str(e)}")
        return {}

def is_in_auto_time_range():
    """判断是否在自动运行时段内"""
    now_hour = datetime.now().hour
    return RUN_HOUR_START <= now_hour <= RUN_HOUR_END

def judge_run_mode():
    """基于文件标记+时间段，判断运行模式"""
    is_manual_file = os.path.exists(MANUAL_FLAG_FILE)
    is_in_auto_time = is_in_auto_time_range()
    
    if is_manual_file:
        return "manual", True
    elif is_in_auto_time:
        return "auto", False
    else:
        return "manual", True

def check_domain(domain):
    """检测域名连通性"""
    try:
        socket.getaddrinfo(domain, None, socket.AF_INET, socket.SOCK_STREAM)
        return True, ""
    except Exception as e:
        return False, str(e)

def check_ip_port(ip_port):
    """检测IP+端口连通性"""
    ip, port = ip_port.split(":")
    port = int(port)
    for _ in range(RETRY_TIMES + 1):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(TIMEOUT)
                s.connect((ip, port))
            return True, ""
        except Exception as e:
            err_msg = str(e)
            time.sleep(1)
    return False, err_msg

def single_detect():
    """单次检测核心逻辑（包含防抖）"""
    global abnormal_continuous_count
    try:
        print_log("🔍 开始单次检测...")
        now = datetime.now()
        detect_result = {
            "detect_time": now.strftime("%Y-%m-%d %H:%M:%S"),
            "detect_timestamp": int(now.timestamp()),
            "status": "normal",
            "abnormal_targets": [],
            "abnormal_count": 0,
            "availability_rate": 100.0,
            "details": {}
        }

        # 检测所有域名
        domain_results = {}
        for domain in TEST_DOMAINS:
            success, err = check_domain(domain)
            domain_results[domain] = {"success": success, "error": err}
            if not success:
                detect_result["abnormal_targets"].append(f"域名-{domain}")
        
        # 检测所有IP+端口
        ip_port_results = {}
        for ip_port in TEST_IP_PORTS:
            success, err = check_ip_port(ip_port)
            ip_port_results[ip_port] = {"success": success, "error": err}
            if not success:
                detect_result["abnormal_targets"].append(f"服务-{ip_port}")
        
        # 统计异常
        detect_result["abnormal_count"] = len(detect_result["abnormal_targets"])
        total_checks = len(TEST_DOMAINS) + len(TEST_IP_PORTS)
        if total_checks > 0:
            success_count = sum([1 for v in domain_results.values() if v["success"]]) + \
                            sum([1 for v in ip_port_results.values() if v["success"]])
            detect_result["availability_rate"] = round((success_count / total_checks) * 100, 2)
        
        # 防抖逻辑
        if detect_result["abnormal_count"] > 0:
            abnormal_continuous_count += 1
            print_log(f"⚠️  连续异常次数：{abnormal_continuous_count}/{DEBOUNCE_TIMES}")
            if abnormal_continuous_count >= DEBOUNCE_TIMES:
                detect_result["status"] = "abnormal"  # 达到防抖次数，标记为异常
        else:
            abnormal_continuous_count = 0  # 恢复正常，重置计数
        
        # 补充详情
        detect_result["details"] = {
            "domains": domain_results,
            "ip_ports": ip_port_results
        }

        # 写入实时数据
        realtime_data = safe_read_json(DETECT_REALTIME_FILE)
        if not realtime_data:
            realtime_data = {
                "date": now.strftime("%Y-%m-%d"),
                "detect_records": [],
                "manual_stop": False,
                "abnormal_continuous_count": abnormal_continuous_count
            }
        realtime_data["detect_records"].append(detect_result)
        realtime_data["date"] = now.strftime("%Y-%m-%d")
        realtime_data["abnormal_continuous_count"] = abnormal_continuous_count
        safe_write_json(DETECT_REALTIME_FILE, realtime_data)
        
        print_log(f"✅ 单次检测完成：可用率{detect_result['availability_rate']}%，异常{detect_result['abnormal_count']}个目标")
        return detect_result
    except Exception as e:
        print_log(f"❌ 单次检测异常: {str(e)}")
        traceback.print_exc()
        return None

def auto_detect_cycle():
    """自动模式：随机间隔多次检测"""
    print_log(f"⚙️  自动模式启动：{DETECT_TIME_RANGE}秒内执行{DETECT_TIMES_PER_RUN}次检测")
    for i in range(DETECT_TIMES_PER_RUN):
        if manual_stop_flag:
            print_log("🛑 检测到手动终止信号，停止自动循环")
            break
        # 随机延迟
        delay = random.randint(0, DETECT_TIME_RANGE // DETECT_TIMES_PER_RUN)
        print_log(f"⏳ 第{i+1}次检测：等待{delay}秒后执行")
        # 延迟期间检测终止信号
        for _ in range(delay):
            if manual_stop_flag:
                print_log("🛑 等待中检测到终止信号，立即退出")
                return
            time.sleep(1)
        # 执行检测
        single_detect()
        # 最后一次不等待
        if i < DETECT_TIMES_PER_RUN - 1:
            time.sleep(10)  # 检测间隔

def signal_handler(signum, frame):
    """捕获终止信号"""
    global manual_stop_flag
    manual_stop_flag = True
    print_log("🛑 检测到手动终止信号")
    sys.exit(0)

# ===================== 主函数 =====================
def main():
    global manual_stop_flag
    manual_stop_flag = False
    
    # 注册终止信号
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # 日志标识
    print_log("===== 🚀 OpenWrt监控-核心检测脚本 启动 =====")
    
    # 判断运行模式
    run_mode, is_manual = judge_run_mode()
    print_log("===== 📌 运行模式识别 =====")
    print_log(f"文件标记：{'🟢 存在' if os.path.exists(MANUAL_FLAG_FILE) else '🔴 不存在'}")
    print_log(f"时间段：{'🟢 自动时段内' if is_in_auto_time_range() else '🔴 非自动时段'}")
    print_log(f"最终判定：{run_mode.upper()}（{'手动触发' if is_manual else '自动定时'}）")
    
    # 执行对应逻辑
    if is_manual:
        print_log("===== 🎯 手动模式执行 =====")
        single_detect()
        # 手动模式执行后，删除标记文件
        if os.path.exists(MANUAL_FLAG_FILE):
            os.remove(MANUAL_FLAG_FILE)
            print_log("🗑️  已删除手动标记文件")
        print_log("===== 🎉 OpenWrt监控-核心检测脚本 执行完成 =====")
    else:
        print_log("===== ⚡ 自动模式执行 =====")
        auto_detect_cycle()
        print_log("===== 🎉 OpenWrt监控-核心检测脚本 执行完成 =====")

if __name__ == "__main__":
    main()
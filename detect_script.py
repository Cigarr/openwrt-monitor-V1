# -*- coding: utf-8 -*-
"""
检测脚本：0-22点内随机检测N次，结果写入JSON，支持手动终止数据保存
cron: 0 */1 * * *
new Env('OpenWrt监控-检测脚本');
"""
import requests
import socket
import time
import threading
import traceback
import gc
import signal
import sys
import os
import random
import json
from concurrent.futures import ThreadPoolExecutor
from config import *

# ====================== 全局变量 ======================
manual_stop_flag = False
current_operation_running = False
detect_history = {
    "total_times": 0,
    "abnormal_times": 0,
    "domain_abnormal": [],
    "ip_port_abnormal": [],
    "last_abnormal_time": "",
    "consecutive_abnormal": 0
}
dns_cache = {}
TIMEOUT_DOMAIN = 1.5
TIMEOUT_IP_PORT = 1.0

# ====================== 工具函数 ======================
def init_log():
    """初始化日志目录"""
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR, exist_ok=True)

def print_log(msg):
    """打印带时间戳的日志"""
    log_msg = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(log_msg)
    log_file = os.path.join(LOG_DIR, f"detect_{time.strftime('%Y%m%d')}.log")
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
    """原子化写入JSON，避免手动终止损坏文件"""
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
        print_log(f"JSON解析错误（手动终止可能）：{e}，使用空模板")
        return {"date": time.strftime('%Y-%m-%d'), "detect_records": [], "manual_stop": False}
    except Exception as e:
        print_log(f"JSON读取失败：{e}，使用空模板")
        return {"date": time.strftime('%Y-%m-%d'), "detect_records": [], "manual_stop": False}

def emergency_save():
    """手动终止时紧急保存数据"""
    global current_operation_running
    current_operation_running = True
    print_log("执行紧急保存...")
    
    # 读取已有数据
    data = safe_read_json(DETECT_REALTIME_FILE)
    # 确保日期正确
    data["date"] = time.strftime('%Y-%m-%d')
    # 标记手动终止
    data["manual_stop"] = True
    data["stop_time"] = time.strftime('%Y-%m-%d %H:%M:%S')
    
    # 保存紧急数据
    if safe_write_json(DETECT_REALTIME_FILE, data):
        print_log("紧急保存成功")
    current_operation_running = False

def signal_handler(signum, frame):
    """捕获手动终止信号"""
    global manual_stop_flag
    manual_stop_flag = True
    print_log("⚠️  检测到手动终止信号")
    emergency_save()
    gc.collect()
    sys.exit(0)

# 注册终止信号
try:
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
except Exception as e:
    print_log(f"信号监听兼容提示：{e}")

# ====================== 检测核心函数 ======================
def get_dns_cache(domain):
    """DNS缓存"""
    now = time.time()
    if domain in dns_cache and now - dns_cache[domain]['time'] < DNS_CACHE_TTL:
        return dns_cache[domain]['ip']
    try:
        ip = socket.gethostbyname(domain)
        dns_cache[domain] = {'ip': ip, 'time': now}
        return ip
    except:
        return None

def check_single_domain(domain):
    """检测单个域名"""
    global current_operation_running
    current_operation_running = True
    result = {
        "detect_time": time.strftime('%Y-%m-%d %H:%M:%S'),
        "target_type": "domain",
        "target": domain,
        "status": "normal",
        "msg": "",
        "consecutive_abnormal": 0
    }
    try:
        ip = get_dns_cache(domain)
        if not ip:
            result["status"] = "abnormal"
            result["msg"] = f"{domain} 解析失败"
            current_operation_running = False
            return result
        
        s = socket.socket()
        s.settimeout(TIMEOUT_DOMAIN)
        conn_ok = s.connect_ex((ip, 80)) == 0
        s.close()
        if conn_ok:
            result["msg"] = f"{domain} 解析+连通正常（IP：{ip}）"
        else:
            result["status"] = "abnormal"
            result["msg"] = f"{domain} 解析成功，80端口不通"
    except Exception as e:
        result["status"] = "abnormal"
        result["msg"] = f"{domain} 异常：{str(e)}"
    current_operation_running = False
    return result

def check_single_ip_port(ip_port):
    """检测单个IP端口"""
    global current_operation_running
    current_operation_running = True
    result = {
        "detect_time": time.strftime('%Y-%m-%d %H:%M:%S'),
        "target_type": "ip_port",
        "target": ip_port,
        "status": "normal",
        "msg": "",
        "consecutive_abnormal": 0
    }
    try:
        ip, port = ip_port.split(":")
        port = int(port)
        s = socket.socket()
        s.settimeout(TIMEOUT_IP_PORT)
        s.connect((ip, port))
        s.close()
        result["msg"] = f"{ip_port} 连接成功（响应耗时{TIMEOUT_IP_PORT}s）"
    except Exception as e:
        result["status"] = "abnormal"
        result["msg"] = f"{ip_port} 失败：{str(e)}"
    current_operation_running = False
    return result

def get_random_intervals():
    """生成N次检测的随机间隔"""
    random_seconds = sorted([random.randint(0, DETECT_TIME_RANGE) for _ in range(DETECT_TIMES_PER_RUN)])
    intervals = [random_seconds[0]]
    for i in range(1, DETECT_TIMES_PER_RUN):
        intervals.append(random_seconds[i] - random_seconds[i-1])
    return intervals

def detect_once():
    """单次检测"""
    global detect_history
    detect_history["total_times"] += 1
    print_log(f"===== 第 {detect_history['total_times']} 次检测 =====")
    
    # 域名检测
    domain_results = []
    with ThreadPoolExecutor(MAX_WORKERS) as executor:
        domain_results = list(executor.map(check_single_domain, TEST_DOMAINS))
    
    # 端口检测
    ip_port_results = []
    with ThreadPoolExecutor(MAX_WORKERS) as executor:
        ip_port_results = list(executor.map(check_single_ip_port, TEST_IP_PORTS))
    
    # 汇总结果
    all_results = domain_results + ip_port_results
    abnormal_count = sum(1 for r in all_results if r["status"] == "abnormal")
    if abnormal_count > 0:
        detect_history["consecutive_abnormal"] += 1
        if detect_history["consecutive_abnormal"] >= DEBOUNCE_TIMES:
            detect_history["abnormal_times"] += 1
            detect_history["last_abnormal_time"] = time.strftime('%Y-%m-%d %H:%M:%S')
    else:
        detect_history["consecutive_abnormal"] = 0
    
    # 写入实时文档
    data = safe_read_json(DETECT_REALTIME_FILE)
    data["detect_records"].extend(all_results)
    data["manual_stop"] = False  # 重置终止标记
    safe_write_json(DETECT_REALTIME_FILE, data)
    
    # 打印日志
    for r in all_results:
        print_log(f"{r['target']} - {r['status']} - {r['msg']}")

# ====================== 主函数 ======================
def main():
    global manual_stop_flag
    manual_stop_flag = False  # 初始化手动终止标记
    
    # ===== 新增：识别运行模式 =====
    import os
    # 判定是否为青龙自动运行（通过青龙环境变量）
    is_ql_auto = True if "QL_BRANCH" in os.environ or "QL_DIR" in os.environ else False
    run_mode = "自动定时" if is_ql_auto else "手动触发"
    print_log(f"🔵 运行模式：{run_mode}")
    # =============================

    try:
        init_log()  # 初始化日志
        check_running_time()  # 时段检查（手动运行也可保留，或注释掉）
        
        # ===== 核心分支：按运行模式执行不同检测逻辑 =====
        if is_ql_auto:
            # 自动运行：保留原有随机检测逻辑
            detect_times = DETECT_TIMES_PER_RUN  # 配置的单次检测次数
            print_log(f"📌 自动模式：将在{DETECT_TIME_RANGE}秒内随机执行{detect_times}次检测")
            
            # 生成随机检测时间点（原有逻辑）
            import random
            detect_timestamps = sorted([random.randint(0, DETECT_TIME_RANGE) for _ in range(detect_times)])
            
            # 按随机间隔执行检测（原有逻辑）
            for idx, delay in enumerate(detect_timestamps):
                if manual_stop_flag:
                    print_log("⚠️ 检测被手动终止，保存已检测数据")
                    break
                print_log(f"⏳ 第{idx+1}次检测：等待{delay}秒后执行")
                time.sleep(delay)
                # 执行单次检测
                single_detect()
        else:
            # 手动运行：跳过随机，直接执行1次检测
            print_log(f"📌 手动模式：立即执行1次检测（跳过随机间隔）")
            single_detect()  # 直接调用核心检测函数
        # ==============================================

        print_log("✅ 检测流程执行完成")
    except Exception as e:
        print_log(f"❌ 检测流程异常：{e}")
        traceback.print_exc()
    finally:
        # 无论是否终止，确保数据写入（原有逻辑）
        save_detect_result()

if __name__ == "__main__":
    main()
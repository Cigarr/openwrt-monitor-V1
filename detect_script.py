# -*- coding: utf-8 -*-
"""
OpenWrt智能监控 - 检测脚本
核心功能：
1. 自动模式：定时时段内随机执行多次检测
2. 手动模式：即时单次检测，跳过随机间隔
3. 双逻辑判断：时间段+参数，双重保障识别手动/自动
运行规则：0 */3 * * *（青龙定时）
手动运行：点击青龙「运行」或终端执行
"""
import os
import sys
import time
import json
import random
import traceback
from datetime import datetime, time as dt_time

# ===================== 全局配置 =====================
# 检测相关
DETECT_INTERVAL = 60  # 基础检测间隔（秒）
DETECT_TIMES_PER_RUN = 3  # 自动模式单次运行检测次数
DETECT_TIME_RANGE = 3600  # 自动模式检测时间范围（秒）
# 定时运行时段（仅在该时段内的触发判定为自动，其余为手动）
AUTO_RUN_START = "00:00"  # 自动运行开始时间
AUTO_RUN_END = "23:59"    # 自动运行结束时间（可自定义，如"22:00"）
# 文件路径
DETECT_REALTIME_FILE = "detect_realtime.json"
PUSH_ARCHIVE_FILE = "push_archive.json"
# 全局标记
manual_stop_flag = False

# ===================== 工具函数 =====================
def print_log(msg):
    """打印带时间戳的日志（无emoji，避免编码问题）"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {msg}")

def safe_write_json(file_path, data):
    """安全写入JSON文件"""
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print_log(f"写入JSON失败: {e}")
        return False

def safe_read_json(file_path):
    """安全读取JSON文件"""
    if not os.path.exists(file_path):
        return {}
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print_log(f"读取JSON失败: {e}")
        return {}

def is_in_auto_time_range():
    """
    逻辑1：时间段判断（核心）
    判断当前时间是否在自动运行时段内，非时段内触发均为手动
    """
    now = datetime.now().time()
    start = dt_time(*map(int, AUTO_RUN_START.split(":")))
    end = dt_time(*map(int, AUTO_RUN_END.split(":")))
    
    # 判断是否在时段内
    if start <= now <= end:
        return True
    return False

def judge_run_mode():
    """
    双逻辑判断运行模式（优先级：参数 > 时间段）
    返回：(run_mode, is_manual)
    run_mode: "manual" / "auto"
    is_manual: True/False
    """
    # 逻辑2：参数判断（最高优先级，手动点击时传--manual）
    is_manual_param = False
    if len(sys.argv) > 1 and ("--manual" in sys.argv[1] or sys.argv[1] == "-m"):
        is_manual_param = True
    
    # 逻辑1：时间段判断（兜底）
    is_in_auto_time = is_in_auto_time_range()
    
    # 综合判断
    if is_manual_param:
        # 参数标记为手动，无论时间段如何，均判定为手动
        return "manual", True
    elif is_in_auto_time:
        # 无手动参数 + 在自动时段内 = 自动模式
        return "auto", False
    else:
        # 无手动参数 + 不在自动时段内 = 手动模式
        return "manual", True

def single_detect():
    """单次检测核心逻辑（手动/自动通用）"""
    try:
        print_log("开始单次检测...")
        
        # 模拟检测逻辑（替换为你的实际检测代码）
        detect_result = {
            "detect_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "status": "normal",
            "abnormal_count": random.randint(0, 2),
            "availability_rate": round(random.uniform(95.0, 100.0), 2)
        }
        
        # 保存检测结果
        realtime_data = safe_read_json(DETECT_REALTIME_FILE)
        if "detect_records" not in realtime_data:
            realtime_data["detect_records"] = []
        realtime_data["detect_records"].append(detect_result)
        safe_write_json(DETECT_REALTIME_FILE, realtime_data)
        
        print_log(f"单次检测完成：可用率{detect_result['availability_rate']}%，异常{detect_result['abnormal_count']}次")
        return detect_result
    except Exception as e:
        print_log(f"单次检测异常: {e}")
        traceback.print_exc()
        return None

def auto_detect_cycle():
    """自动模式：随机间隔执行多次检测"""
    print_log(f"自动模式：将在{DETECT_TIME_RANGE}秒内随机执行{DETECT_TIMES_PER_RUN}次检测")
    
    for i in range(DETECT_TIMES_PER_RUN):
        if manual_stop_flag:
            print_log("检测到手动终止信号，停止自动检测循环")
            break
        
        # 生成随机延迟（秒）
        delay = random.randint(0, DETECT_TIME_RANGE // DETECT_TIMES_PER_RUN)
        print_log(f"第{i+1}次检测：等待{delay}秒后执行")
        
        # 等待期间检测终止信号
        for _ in range(delay):
            if manual_stop_flag:
                print_log("等待中检测到终止信号，立即退出")
                return
            time.sleep(1)
        
        # 执行单次检测
        single_detect()
        
        # 最后一次检测不等待
        if i < DETECT_TIMES_PER_RUN - 1:
            time.sleep(DETECT_INTERVAL)

def signal_handler(signum, frame):
    """信号处理：捕获手动终止"""
    global manual_stop_flag
    manual_stop_flag = True
    print_log("检测到手动终止信号")
    sys.exit(0)

# ===================== 主函数 =====================
def main():
    global manual_stop_flag
    manual_stop_flag = False
    
    # 1. 注册终止信号
    import signal
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # 2. 双逻辑判断运行模式
    run_mode, is_manual = judge_run_mode()
    print_log(f"===== 运行模式识别 =====")
    print_log(f"参数判断：{'手动参数' if is_manual else '无手动参数'}")
    print_log(f"时间段判断：{'自动时段内' if is_in_auto_time_range() else '非自动时段'}")
    print_log(f"最终判定：{run_mode.upper()}（{'手动触发' if is_manual else '自动定时'}）")
    
    # 3. 分支执行逻辑
    if is_manual:
        # 手动模式：即时单次检测
        print_log("===== 手动模式执行 =====")
        single_detect()
        print_log("手动检测完成，脚本结束")
    else:
        # 自动模式：随机间隔循环检测
        print_log("===== 自动模式执行 =====")
        auto_detect_cycle()
        print_log("自动检测循环完成，脚本结束")

# ===================== 入口 =====================
if __name__ == "__main__":
    main()
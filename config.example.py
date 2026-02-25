# -*- coding: utf-8 -*-
"""配置文件模板（复制为config.py后修改）"""
import os

# ====================== 企业微信配置（必填）======================
CORP_ID = "你的企业ID"       
CORP_SECRET = "你的应用Secret"  
AGENT_ID = 1000002                  
TO_USER = "@all"                   

# ====================== 检测配置（可自定义）======================
TEST_DOMAINS = [                   
    "www.baidu.com",
    "你的域名.ddns.net"
]
TEST_IP_PORTS = [                   
    "192.168.0.1:80",
    "你的IP:端口"
]
DETECT_TIMES_PER_RUN = 3            # 单次检测次数
DETECT_TIME_RANGE = 3600            # 检测时间范围（秒）
DEBOUNCE_TIMES = 2                  # 异常防抖次数
DNS_CACHE_TTL = 300                 # DNS缓存时长
MAX_WORKERS = 3                     # 并行线程数

# ====================== 路径配置（无需修改）======================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DETECT_REALTIME_FILE = os.path.join(SCRIPT_DIR, "detect_realtime.json")
PUSH_ARCHIVE_FILE = os.path.join(SCRIPT_DIR, "push_archive.json")
DAILY_FINAL_FILE = os.path.join(SCRIPT_DIR, "daily_final.md")
LOG_DIR = os.path.join(SCRIPT_DIR, "logs")

# ====================== 时间配置（无需修改）======================
RUN_HOUR_START = 0                  
RUN_HOUR_END = 22                   
DAILY_SUMMARY_TIME = (22, 45)       
# -*- coding: utf-8 -*-
"""
OpenWrt智能监控 - 配置示例
使用说明：
1. 复制此文件为 config.py
2. 填写真实的企业微信配置
3. 不要将 config.py 上传到公共仓库
"""
import os

# ===================== 路径配置（自动适配，无需手动改） =====================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DETECT_REALTIME_FILE = os.path.join(SCRIPT_DIR, "detect_realtime.json")
PUSH_ARCHIVE_FILE = os.path.join(SCRIPT_DIR, "push_archive.json")
DAILY_FINAL_FILE = os.path.join(SCRIPT_DIR, "daily_final.md")
MANUAL_FLAG_FILE = os.path.join(os.path.dirname(SCRIPT_DIR), "manual_flag")

# ===================== 企业微信配置（请替换为真实值） =====================
CORP_ID = "wwdxxxxxxxxxxxxxx"
CORP_SECRET = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
AGENT_ID = "1000002"
TO_USER = "@all"

# ===================== 检测配置（核心监控规则） =====================
TEST_DOMAINS = ["你的域名"]
TEST_IP_PORTS = ["你的IP:端口"]
DETECT_TIMES_PER_RUN = 3
DETECT_TIME_RANGE = 3600
DEBOUNCE_TIMES = 2
RUN_HOUR_START = 0
RUN_HOUR_END = 22
DAILY_SUMMARY_TIME = "22:45"

# ===================== 网络检测配置（可选） =====================
TIMEOUT = 5
RETRY_TIMES = 1
# -*- coding: utf-8 -*-
"""
OpenWrt智能监控 - 每日汇总脚本
功能：生成科技感日报，推送企业微信，清理临时数据
"""
import os
import sys
import json
import time
import traceback
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
DAILY_FINAL_FILE = config.DAILY_FINAL_FILE
CORP_ID = config.CORP_ID
CORP_SECRET = config.CORP_SECRET
AGENT_ID = config.AGENT_ID
TO_USER = config.TO_USER

# ===================== 工具函数 =====================
def print_log(msg):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] 📋 {msg}")

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

def send_daily_tech_report(content):
    """发送科技感每日汇总报告"""
    token = get_wechat_token()
    if not token:
        return False
    
    # 科技感日报模板
    tech_report = f"""
┌─────────────────────────┐
📊 【OpenWrt监控每日报告】 📊
├─────────────────────────┤
📅 统计日期：{datetime.now().strftime('%Y-%m-%d')}
🕒 汇总时间：{datetime.now().strftime('%H:%M:%S')}
{content}
├─────────────────────────┤
🔧 监控节点：{len(config.TEST_DOMAINS)+len(config.TEST_IP_PORTS)}个 | 🎯 防抖阈值：{config.DEBOUNCE_TIMES}次
└─────────────────────────┘
"""
    
    try:
        push_url = f"https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token={token}"
        push_data = {
            "touser": TO_USER,
            "msgtype": "text",
            "agentid": AGENT_ID,
            "text": {"content": tech_report.strip()},
            "safe": 0
        }
        res = requests.post(push_url, json=push_data, timeout=10)
        res.raise_for_status()
        result = res.json()
        
        if result.get("errcode") == 0:
            print_log("✅ 科技感日报推送成功")
            return True
        else:
            print_log(f"❌ 日报推送失败：{result}")
            return False
    except Exception as e:
        print_log(f"❌ 日报推送异常：{str(e)}")
        return False

def parse_archive_data():
    """解析归档数据，生成汇总统计"""
    archive_data = safe_read_json(PUSH_ARCHIVE_FILE)
    realtime_data = safe_read_json(DETECT_REALTIME_FILE)
    today = datetime.now().strftime("%Y-%m-%d")
    
    # 初始化汇总数据
    summary = {
        "date": today,
        "total_detect": 0,
        "total_push": 0,
        "total_abnormal": 0,
        "max_abnormal_count": 0,
        "avg_availability_rate": 0.0,
        "abnormal_targets": set(),
        "manual_stop": realtime_data.get("manual_stop", False)
    }
    
    # 解析实时检测数据
    if realtime_data and realtime_data.get("date") == today and "detect_records" in realtime_data:
        detect_records = realtime_data["detect_records"]
        summary["total_detect"] = len(detect_records)
        
        # 计算平均可用率
        if detect_records:
            avg_availability = sum([r.get("availability_rate", 0) for r in detect_records]) / len(detect_records)
            summary["avg_availability_rate"] = round(avg_availability, 2)
        
        # 统计异常
        abnormal_records = [r for r in detect_records if r.get("status") == "abnormal"]
        summary["total_abnormal"] = len(abnormal_records)
        
        # 统计异常目标和最大异常次数
        for r in detect_records:
            if r.get("abnormal_targets"):
                summary["abnormal_targets"].update(r["abnormal_targets"])
            if r.get("abnormal_count") > summary["max_abnormal_count"]:
                summary["max_abnormal_count"] = r["abnormal_count"]
    
    # 解析推送归档
    if archive_data and archive_data.get("date") == today and "push_records" in archive_data:
        summary["total_push"] = len(archive_data["push_records"])
    
    # 转换集合为列表
    summary["abnormal_targets"] = list(summary["abnormal_targets"])
    return summary

def generate_daily_tech_content(summary):
    """生成科技感日报内容"""
    if summary["total_detect"] == 0:
        return "📡 今日无检测数据，系统运行正常！"
    
    content_lines = []
    # 核心统计
    content_lines.append(f"📈 总检测次数：{summary['total_detect']}次")
    content_lines.append(f"📊 平均可用率：{summary['avg_availability_rate']}%")
    content_lines.append(f"⚠️  异常告警次数：{summary['total_push']}次")
    content_lines.append(f"🔴 异常目标数：{len(summary['abnormal_targets'])}个")
    
    # 异常详情（如有）
    if summary["total_abnormal"] > 0:
        content_lines.append(f"\n🔍 异常详情：")
        content_lines.append(f"  • 累计异常次数：{summary['total_abnormal']}次")
        content_lines.append(f"  • 单次最大异常：{summary['max_abnormal_count']}个目标")
        if summary["abnormal_targets"]:
            content_lines.append(f"  • 异常目标列表：{', '.join(summary['abnormal_targets'])}")
    else:
        content_lines.append(f"\n✅ 今日无异常，网络运行稳定！")
    
    return "\n".join(content_lines)

def generate_md_report(summary):
    """生成Markdown格式日报（详细版）"""
    today = summary["date"]
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    md_content = f"""# 🚀 OpenWrt智能监控 · {today} 每日报告
**汇总时间**：{now}  
**运行状态**：{'🛑 手动终止' if summary['manual_stop'] else '🟢 正常运行'}

## 📊 核心统计
| 指标 | 数值 |
|------|------|
| 总检测次数 | {summary['total_detect']} 次 |
| 平均可用率 | {summary['avg_availability_rate']}% |
| 异常告警次数 | {summary['total_push']} 次 |
| 异常目标数 | {len(summary['abnormal_targets'])} 个 |
| 单次最大异常 | {summary['max_abnormal_count']} 个目标 |

## 🔍 异常详情
"""
    if summary["total_abnormal"] > 0:
        md_content += f"""
- 累计异常次数：{summary['total_abnormal']} 次
- 异常目标列表：{', '.join(summary['abnormal_targets']) if summary['abnormal_targets'] else '无'}
"""
    else:
        md_content += """
✅ 今日无异常，网络运行稳定！
"""
    
    md_content += f"""
## ⚙️ 系统配置
| 配置项 | 数值 |
|--------|------|
| 监控节点数 | {len(config.TEST_DOMAINS)+len(config.TEST_IP_PORTS)} 个 |
| 防抖阈值 | {config.DEBOUNCE_TIMES} 次 |
| 自动运行时段 | {config.RUN_HOUR_START}:00 - {config.RUN_HOUR_END}:00 |
| 检测超时时间 | {config.TIMEOUT} 秒 |

---
*报告由 OpenWrt智能监控套件 自动生成*
"""
    return md_content

def save_md_file(content):
    """保存Markdown日报"""
    try:
        with open(DAILY_FINAL_FILE, "w", encoding="utf-8") as f:
            f.write(content)
        print_log(f"📝 每日报告已保存：{DAILY_FINAL_FILE}")
        return True
    except Exception as e:
        print_log(f"❌ 保存MD失败：{str(e)}")
        return False

def clean_temp_files():
    """清理临时数据文件"""
    try:
        # 仅清理实时检测数据，保留推送归档（用于历史统计）
        if os.path.exists(DETECT_REALTIME_FILE):
            os.remove(DETECT_REALTIME_FILE)
            print_log(f"🗑️  已清理临时文件：{DETECT_REALTIME_FILE}")
        print_log("✅ 临时文件清理完成")
        return True
    except Exception as e:
        print_log(f"❌ 清理文件异常：{str(e)}")
        return False

# ===================== 主函数 =====================
def main():
    print_log("===== 🚀 OpenWrt监控-每日汇总脚本 启动 =====")
    summary = parse_archive_data()
    
    # 生成科技感推送内容
    push_content = generate_daily_tech_content(summary)
    # 推送日报
    send_daily_tech_report(push_content)
    
    # 生成并保存Markdown报告
    md_content = generate_md_report(summary)
    save_md_file(md_content)
    
    # 清理临时数据
    clean_temp_files()
    
    print_log("===== 🎉 OpenWrt监控-每日汇总脚本 执行完成 =====")

if __name__ == "__main__":
    main()
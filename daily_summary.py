# -*- coding: utf-8 -*-
"""
OpenWrt智能监控 - 每日汇总脚本
功能：22:45解析当日归档数据，推送最终日报，生成MD报告，清理临时文件
运行规则：45 22 * * *（青龙定时）
手动运行：直接执行，即时汇总；自动运行：青龙定时触发
"""
import os
import sys
import time
import json
import traceback
from datetime import datetime

# ===================== 全局配置（需和config.py保持一致） =====================
# 归档文件路径
PUSH_ARCHIVE_FILE = "push_archive.json"
# 每日最终报告MD文件
DAILY_FINAL_FILE = "daily_final.md"
# 企业微信配置（实际使用时从config.py导入，此处为示例）
try:
    from config import CORP_ID, CORP_SECRET, AGENT_ID
except ImportError:
    # 未配置config.py时的占位（青龙中需确保config.py存在）
    CORP_ID = ""
    CORP_SECRET = ""
    AGENT_ID = ""

# 全局终止标记
manual_stop_flag = False

# ===================== 工具函数 =====================
def print_log(msg):
    """打印带时间戳的日志"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {msg}")

def send_wechat_msg(content):
    """推送企业微信消息（适配青龙环境）"""
    if not all([CORP_ID, CORP_SECRET, AGENT_ID]):
        print_log("\U00026A0 企业微信配置未完善，跳过推送")
        return False
    
    try:
        import requests
        # 获取access_token
        token_url = f"https://qyapi.weixin.qq.com/cgi-bin/gettoken?corpid={CORP_ID}&corpsecret={CORP_SECRET}"
        token_res = requests.get(token_url, timeout=10)
        token_res.raise_for_status()
        access_token = token_res.json().get("access_token")
        
        if not access_token:
            print_log("\U000274C 获取企业微信token失败")
            return False
        
        # 推送消息
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
            print_log("\U0002705 企业微信日报推送成功")
            return True
        else:
            print_log(f"\U000274C 推送失败：{push_res.json()}")
            return False
    except Exception as e:
        print_log(f"\U000274C 推送异常：{e}")
        traceback.print_exc()
        return False

def clean_temp_files():
    """清理当日临时文件（保留配置文件）"""
    files_to_clean = [
        "detect_realtime.json",
        PUSH_ARCHIVE_FILE,
        # DAILY_FINAL_FILE 保留，作为日报存档
    ]
    try:
        for file in files_to_clean:
            if os.path.exists(file):
                os.remove(file)
                print_log(f"\U0001F5D1\U000FE0F 已清理临时文件：{file}")
        print_log("\U0002705 临时文件清理完成")
        return True
    except Exception as e:
        print_log(f"\U000274C 清理文件异常：{e}")
        return False

def generate_daily_report(summary):
    """生成每日汇总报告（企业微信+MD文档）"""
    date = datetime.now().strftime("%Y-%m-%d")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # 无数据场景
    if summary['total_push'] == 0:
        md_content = f"""\U0001F4C5 OpenWrt智能监控 · {date} 每日最终报告
\U0001F4CA 当日概览：暂无推送数据
\U00023F0 汇总时间：{now}
\U00026A0 状态：手动终止{summary['manual_stop']}

\U00023F0 运行时段：0-22点 | 汇总时间：22:45
\U0001F5D1\U000FE0F 数据清理：已执行 | 明日0点重新开始
""".strip()
        content = md_content
        return content, md_content
    
    # 有数据场景
    content = f"""\U0001F4C5 OpenWrt智能监控 · {date} 每日最终报告
\U0001F4CA 当日概览：
- 推送次数：{summary['total_push']} 次
- 检测总次数：{summary['total_detect']} 次
- 异常总次数：{summary['total_abnormal']} 次
- 平均可用率：{summary['avg_availability_rate']}%
"""
    
    # 补充异常详情
    if summary['total_abnormal'] > 0:
        content += f"""
\U00026A0 异常详情：
- 异常最多目标：{summary['max_abnormal_target']}（{summary['max_abnormal_count']}次）
"""
    
    content += f"""
\U00023F0 汇总时间：{now}
\U0001F5D1\U000FE0F 数据清理：已执行 | 明日0点重新初始化
"""
    md_content = content.strip()
    return content, md_content

def parse_archive_data():
    """解析归档数据，生成汇总统计"""
    summary = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "total_push": 0,
        "total_detect": 0,
        "total_abnormal": 0,
        "avg_availability_rate": 0.0,
        "max_abnormal_target": "",
        "max_abnormal_count": 0,
        "manual_stop": manual_stop_flag
    }
    
    # 归档文件不存在
    if not os.path.exists(PUSH_ARCHIVE_FILE):
        print_log("\U00026A0 归档文件不存在，按无数据处理")
        return summary
    
    try:
        with open(PUSH_ARCHIVE_FILE, "r", encoding="utf-8") as f:
            archive_data = json.load(f)
        
        # 无归档数据
        if not isinstance(archive_data, list) or len(archive_data) == 0:
            return summary
        
        # 统计核心数据
        abnormal_dict = {}
        total_availability = 0.0
        
        for item in archive_data:
            summary['total_push'] += 1
            summary['total_detect'] += item.get("detect_count", 0)
            summary['total_abnormal'] += item.get("abnormal_count", 0)
            
            # 异常目标统计
            abnormal_target = item.get("max_abnormal_target", "")
            if abnormal_target:
                abnormal_dict[abnormal_target] = abnormal_dict.get(abnormal_target, 0) + 1
            
            # 可用率统计
            availability = item.get("availability_rate", 0.0)
            total_availability += availability
        
        # 计算平均可用率
        if summary['total_push'] > 0:
            summary['avg_availability_rate'] = round(total_availability / summary['total_push'], 2)
        
        # 异常最多目标
        if abnormal_dict:
            max_target = max(abnormal_dict, key=abnormal_dict.get)
            summary['max_abnormal_target'] = max_target
            summary['max_abnormal_count'] = abnormal_dict[max_target]
        
        print_log("\U0002705 归档数据解析完成")
        return summary
    
    except Exception as e:
        print_log(f"\U000274C 解析归档数据异常：{e}")
        traceback.print_exc()
        return summary

def save_md_file(content):
    """保存每日最终MD报告"""
    try:
        with open(DAILY_FINAL_FILE, "w", encoding="utf-8") as f:
            f.write(content)
        print_log(f"\U0002705 每日报告已保存至：{DAILY_FINAL_FILE}")
        return True
    except Exception as e:
        print_log(f"\U000274C 保存MD文件异常：{e}")
        return False

# ===================== 主函数 =====================
def main():
    global manual_stop_flag
    manual_stop_flag = False
    
    # 1. 识别运行模式（青龙自动/手动）
    is_ql_auto = True if "QL_BRANCH" in os.environ or "QL_DIR" in os.environ else False
    run_mode = "\U0001F535 青龙自动定时运行" if is_ql_auto else "\U0001F535 手动触发运行"
    print_log(f"===== 启动每日汇总脚本 =====")
    print_log(f"运行模式：{run_mode}")
    
    try:
        # 2. 解析归档数据
        summary = parse_archive_data()
        
        # 3. 生成报告内容
        push_content, md_content = generate_daily_report(summary)
        
        # 4. 推送企业微信
        send_wechat_msg(push_content)
        
        # 5. 保存MD报告
        save_md_file(md_content)
        
        # 6. 清理临时文件（手动终止也执行清理）
        if not manual_stop_flag:
            clean_temp_files()
        else:
            print_log("\U00026A0 手动终止，跳过文件清理")
        
        print_log("===== 每日汇总脚本执行完成 =====")
    
    except KeyboardInterrupt:
        # 手动终止（Ctrl+C）
        manual_stop_flag = True
        print_log("\U00026A0 脚本被手动终止，保存已处理数据")
    except Exception as e:
        print_log(f"\U000274C 脚本执行异常：{e}")
        traceback.print_exc()

# ===================== 入口 =====================
if __name__ == "__main__":
    main()
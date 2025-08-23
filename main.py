#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from pathlib import Path
import json
import logging
from dp_bilibili_api import dp_bilibili
from dp_logging import setup_logger
import shutil
from worker_thread import WorkerThread
import time
import sqlite3


SCRIPT_DIR = Path(__file__).parent
CONFIG_FILE = SCRIPT_DIR / "config.json"
CONFIG_SAMPLE_FILE = SCRIPT_DIR / "config_sample.json"
logger = setup_logger(Path(__file__).stem, file_level=logging.DEBUG)

def parse_config_file():
    """解析配置文件，返回配置字典"""
    if not CONFIG_FILE.exists():
        logger.info(f"未找到配置文件 {CONFIG_FILE}，将从 {CONFIG_SAMPLE_FILE} 复制。")
        try:
            
            shutil.copy(CONFIG_SAMPLE_FILE, CONFIG_FILE)
        except Exception as e:
            logger.error(f"从 {CONFIG_SAMPLE_FILE} 复制配置文件失败: {e}")
            exit()

    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            _config = json.load(f)
    except (json.JSONDecodeError, Exception) as e:
        logger.error(f"读取配置文件 {CONFIG_FILE} 失败: {e}")
        logger.error(f"请检查文件格式是否正确，或删除 {CONFIG_FILE} 以从示例文件重新生成。")
        exit()

    return _config

CONFIG_FILE = SCRIPT_DIR / "config.json"
CONFIG_SAMPLE_FILE = SCRIPT_DIR / "config_sample.json"
config = parse_config_file()
DATA_DIR = SCRIPT_DIR / config.get("data_directory", "data")
DB_FILE = DATA_DIR / "bilibili_videos.db"

def get_target_groups():
    target_group_names = []
    # 读取并规范化目标分组配置
    target_groups_config = config.get("target_group_name")
    if not target_groups_config:
        logger.error(f"配置文件 {CONFIG_FILE} 中 'target_group_name' 未找到或为空。")

    if isinstance(target_groups_config, str):
        target_group_names = [target_groups_config]
    elif isinstance(target_groups_config, list):
        target_group_names = target_groups_config
    else:
        logger.error(f"配置文件 {CONFIG_FILE} 中 'target_group_name' 的值必须是字符串或字符串列表。")

    return target_group_names

def func_in_thread(dp_blbl, task):
    action, args = task
    if action == "get_videos_by_up":
        mid, pn, ps = args
        logger.info(f"获取UP主 {mid} 的视频列表")
        return dp_blbl.get_videos_in_up(mid, pn=pn, ps=ps)
    else:
        logger.error(f"未知的任务动作: {action}")
        return None

def setup_database():
    """初始化数据库和表"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    # 创建视频表，使用bvid作为主键防止重复
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS videos (
            bvid TEXT PRIMARY KEY,
            up_name TEXT NOT NULL,
            up_mid INTEGER NOT NULL,
            title TEXT NOT NULL,
            link TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def video_exist_in_database(conn: sqlite3.Connection, bvid: str):
    """安全的键存在检查"""
    cursor = conn.cursor()
    query = "SELECT 1 FROM videos WHERE bvid = ? LIMIT 1"
    cursor.execute(query, (bvid,))
    return cursor.fetchone() is not None
    
def save_video_to_database_if_not_exists(conn: sqlite3.Connection, video_info: dict):
    """如果视频不存在，则保存到数据库并返回True，否则返回False。"""
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO videos (bvid, up_name, up_mid, title, link)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            video_info['bvid'],
            video_info['up_name'],
            video_info['up_mid'],
            video_info['title'],
            video_info['link']
        ))
        conn.commit()
        return True  # 插入成功
    except sqlite3.IntegrityError:
        # bvid (主键) 已存在，忽略错误
        return False # 未插入
    except Exception as e:
        logger.error(f"保存视频到数据库时发生错误: {e}")
        return False # 保存失败
            
def main():
    debug = config.get("debug", False)
    
    # 获取目标分组
    target_groups = get_target_groups()
    logger.debug(f"目标分组: {target_groups}")
    
    # 初始化 dp_bilibili 实例
    cookies = {}
    cookies_file = Path("cookies.json")
    if cookies_file.exists():
        with open("cookies.json", "r") as f:
            cookies = json.load(f)
    dp_blbl = dp_bilibili(cookies=cookies, logger=logger)
    if dp_blbl.login():
        with open("cookies.json", "w") as f:
            json.dump(dp_blbl.session.cookies.get_dict(), f)
            
    # 获取关注分组
    following_groups = dp_blbl.get_following_groups()
    logger.debug(f"关注分组: {following_groups}")
    
    # 初始化数据库
    setup_database()
    conn = sqlite3.connect(DB_FILE)

    # 遍历目标分组
    all_new_videos = []
    for group in target_groups:
        for follow_group_id in following_groups:
            follow_group_name = following_groups[follow_group_id]['name']
            follow_group_ups_count = following_groups[follow_group_id]['count']
            if group == follow_group_name:
                logger.info(f"正在处理分组: {follow_group_name} (ID: {follow_group_id}, 个数: {follow_group_ups_count})")
                ups = dp_blbl.get_ups_in_group(follow_group_id)
                logger.debug(f"分组 {follow_group_name} 中的UP主: {ups}")
                c = 0
                up_count = 1
                for up_mid in ups:
                    up_name = ups[up_mid]['name']
                    logger.info(f"[{up_count}/{follow_group_ups_count}]UP主: {up_name}")
                    videos = dp_blbl.get_videos_in_up(up_mid)
                    logger.debug(f"UP主 {up_name} 的视频列表: {videos}")
                    for bvid in videos:
                        title = videos[bvid]['title']
                        video_info = {
                            "up_name": up_name,
                            "up_mid": up_mid,
                            "bvid": bvid,
                            "title": title,
                            "link": f"https://www.bilibili.com/video/{bvid}"
                        }
                        if not video_exist_in_database(conn, bvid):
                            video_info.update(dp_blbl.get_video_info(bvid))
                            if save_video_to_database_if_not_exists(conn, video_info):
                                logger.info(f"      [新视频] {video_info['title']}")
                                all_new_videos.append(video_info)
                            time.sleep(1)
                    c += 1
                    up_count += 1
                    if debug and c >= 1:
                        break
    
    logger.info("-------------------------------------\n")
    if all_new_videos:
        # 按长度排序
        all_new_videos.sort(key=lambda v: v['duration'])
        
        new_videos_count = len(all_new_videos)
        current_time = time.strftime("%Y%m%d-%H%M%S")
        output_filename = DATA_DIR / "list" / f"new_videos_{current_time}.txt"
        output_filename.parent.mkdir(parents=True, exist_ok=True)

        # 写入文件
        with open(output_filename, 'w', encoding='utf-8') as f:
            for video in all_new_videos:
                line = f"- {video['title']} | 作者: {video['up_name']} | 链接: {video['link']} | 时长: {video['duration']} | 发布时间: {video['pubdate']} | bvid: {video['bvid']} | cid: {video['cid']}\n"
                f.write(line)
        
        logger.info(f"检查完成，共发现 {new_videos_count} 个新视频。")
        logger.info(f"新视频列表已保存到 {output_filename}")
        logger.info(f"所有视频历史记录已更新到 {DB_FILE}")
    else:
        logger.info("所有指定分组检查完成，没有发现新视频。")
    
if __name__ == "__main__":
    main()
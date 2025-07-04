import requests
import time
import hashlib
import urllib.parse
import json
import os
from functools import reduce
import sqlite3
import qrcode

MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
    33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40,
    61, 26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11,
    36, 20, 34, 44, 52
]

def get_mixin_key(orig: str):
    """根据B站的规则对imgKey和subKey进行打乱，生成mixinKey"""
    return reduce(lambda s, i: s + orig[i], MIXIN_KEY_ENC_TAB, '')[:32]


COOKIE_FILE = "bili_cookies.json"

def login_by_qrcode():
    """通过二维码扫描进行登录并返回一个包含cookies的session对象"""
    # 1. 获取二维码URL和key
    login_url_api = "https://passport.bilibili.com/x/passport-login/web/qrcode/generate"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    }
    try:
        # 增加 User-Agent 头，模拟浏览器访问，解决412错误
        response = requests.get(login_url_api, headers=headers)
        response.raise_for_status()
        data = response.json()['data']
        qrcode_key = data['qrcode_key']
        qr_url = data['url']
    except Exception as e:
        print(f"获取登录二维码失败: {e}")
        return None

    # 2. 在终端显示二维码
    qr = qrcode.QRCode()
    qr.add_data(qr_url)
    qr.make(fit=True)
    qr.print_ascii(invert=True)
    print("请使用Bilibili手机客户端扫描上方二维码")

    # 3. 轮询登录状态
    poll_api = "https://passport.bilibili.com/x/passport-login/web/qrcode/poll"
    session = requests.Session()
    session.headers.update(headers) # 为轮询的 session 也设置 User-Agent
    
    try:
        while True:
            time.sleep(3)
            params = {'qrcode_key': qrcode_key}
            poll_response = session.get(poll_api, params=params) # 此处将自动使用 session 的 headers
            poll_response.raise_for_status()
            poll_data = poll_response.json()['data']
            
            code = poll_data['code']
            if code == 0:
                print("登录成功！")
                with open(COOKIE_FILE, 'w') as f:
                    json.dump(session.cookies.get_dict(), f)
                print(f"登录信息已保存到 {COOKIE_FILE}")
                return session
            elif code == 86038:
                print("二维码已失效，请重新运行程序。")
                return None
            elif code == 86090:
                print("二维码已扫描，请在手机上确认登录...")
    except Exception as e:
        print(f"轮询登录状态时发生错误: {e}")
        return None

def get_wbi_keys(session: requests.Session):
    """获取WBI签名所需的img_key和sub_key"""
    url = "https://api.bilibili.com/x/web-interface/nav"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.5",
    }
    try:
        response = session.get(url, headers=headers, timeout=5)
        response.raise_for_status()
        data = response.json()
        img_url = data["data"]["wbi_img"]["img_url"]
        sub_url = data["data"]["wbi_img"]["sub_url"]
        img_key = img_url.split("/")[-1].split(".")[0]
        sub_key = sub_url.split("/")[-1].split(".")[0]
        return img_key, sub_key
    except Exception as e:
        print(f"获取WBI密钥失败: {e}")
        return None, None

def get_authenticated_session():
    """获取一个经过认证的session，优先从本地文件加载，否则扫码登录"""
    session = requests.Session()
    # 为整个会话设置一个统一的 User-Agent
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    }
    session.headers.update(headers)

    if os.path.exists(COOKIE_FILE):
        try:
            with open(COOKIE_FILE, 'r') as f:
                cookies = json.load(f)
            session.cookies.update(cookies)
            
            nav_api = "https://api.bilibili.com/x/web-interface/nav"
            response = session.get(nav_api) # 此处将自动使用 session 的 headers
            if response.json().get('data', {}).get('isLogin'):
                print("已使用本地保存的登录信息。")
                return session
            else:
                print("本地登录信息已失效，请重新扫码登录。")
        except Exception as e:
            print(f"加载本地登录信息失败: {e}，请重新扫码登录。")
    return login_by_qrcode()

def sign_params(params: dict, img_key: str, sub_key: str):
    """为请求参数进行WBI签名"""
    mixin_key = get_mixin_key(img_key + sub_key)
    curr_time = int(time.time())
    params['wts'] = curr_time
    
    # 参数按key排序
    params = dict(sorted(params.items()))
    
    # 过滤value中的特殊字符并URL编码
    params_filtered = {
        k: ''.join(filter(lambda ch: ch not in "!'()*", str(v)))
        for k, v in params.items()
    }
    query = urllib.parse.urlencode(params_filtered)
    
    # 计算签名
    w_rid = hashlib.md5((query + mixin_key).encode()).hexdigest()
    params['w_rid'] = w_rid
    return params

def get_my_info(session: requests.Session):
    """获取当前登录用户的UID和昵称"""
    url = "https://api.bilibili.com/x/web-interface/nav"
    try:
        response = session.get(url)
        response.raise_for_status()
        data = response.json()
        if data['code'] == 0:
            user_data = data['data']
            return user_data['mid'], user_data['uname']
        else:
            print(f"获取用户信息失败: {data['message']}")
            return None, None
    except Exception as e:
        print(f"获取用户信息时发生错误: {e}")
        return None, None

def get_following_groups(session: requests.Session):
    """获取关注分组列表，返回一个字典 {group_name: tag_id}"""
    url = "https://api.bilibili.com/x/relation/tags"
    try:
        response = session.get(url)
        response.raise_for_status()
        data = response.json()
        if data['code'] == 0:
            # 包含默认的“全部关注”和“悄悄关注”等
            groups = {group['name']: group['tagid'] for group in data['data']}
            return groups
        else:
            print(f"获取关注分组失败: {data['message']}")
            return {}
    except Exception as e:
        print(f"获取关注分组时发生错误: {e}")
        return {}

def get_followings_in_group(session: requests.Session, mid: int, tag_id: int):
    """根据分组ID获取关注的UP主列表"""
    # 此API (x/relation/tag) 不需要WBI签名
    # 旧的API (x/relation/followings) 会返回全部关注，tagid参数无效
    api_url = "https://api.bilibili.com/x/relation/tag"
    params = {
        "mid": mid,
        "tagid": tag_id,
        "pn": 1,
        "ps": 100,  # 最多获取10个UP主
    }
    headers = {
        "Referer": f"https://space.bilibili.com/{mid}/fans/follow",
    }
    
    try:
        # session中已包含User-Agent
        response = session.get(api_url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        if data.get('code') == 0:
            # 此API返回的数据在 'data' 键下，是一个列表
            return data.get("data", [])
        print(f"获取分组关注列表失败: {data.get('message')}")
        return []
    except Exception as e:
        print(f"请求关注列表时发生错误: {e}")
        return []

def get_up_videos(mid, session: requests.Session):
    """获取UP主第一页视频信息"""
    # 获取签名密钥
    img_key, sub_key = get_wbi_keys(session)
    if not img_key or not sub_key:
        return []
    
    # 构造基本参数
    params = {
        "mid": mid,
        "ps": 30,       # 每页视频数
        "pn": 1,        # 页码
        "order": "pubdate",
        "platform": "web",
        "web_location": "1550101"
    }
    
    # 生成签名
    signed_params = sign_params(params, img_key, sub_key)
    
    # 请求头
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Referer": f"https://space.bilibili.com/{mid}/"
    }
    
    try:
        # 发送API请求
        response = session.get(
            "https://api.bilibili.com/x/space/wbi/arc/search",
            params=signed_params,
            headers=headers,
            timeout=10
        )
        data = response.json()
        
        # 检查响应状态
        if data["code"] != 0:
            print(f"API请求失败: {data['message']}")
            return []
        
        # 提取视频数据
        videos = []
        for video in data["data"]["list"]["vlist"]:
            title = video["title"]
            bvid = video["bvid"]
            link = f"https://www.bilibili.com/video/{bvid}"
            videos.append({"title": title, "link": link, "bvid": bvid})
        
        return videos
    
    except Exception as e:
        print(f"请求发生错误: {e}")
        return []

DB_FILE = "bilibili_videos.db"

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

def save_video_if_not_exists(conn: sqlite3.Connection, video_info: dict):
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

if __name__ == "__main__":
    print("正在初始化，准备登录...")
    session = get_authenticated_session()

    if not session:
        print("登录失败，程序退出。")
        exit()

    setup_database()

    my_mid, my_name = get_my_info(session)
    if not my_mid:
        print("无法获取您的用户ID，程序退出。")
        exit()
    print(f"登录成功，欢迎您：{my_name} (UID: {my_mid})")

    print("\n正在获取您的关注分组...")
    groups = get_following_groups(session)
    time.sleep(5)

    if "投资" in groups:
        investment_tag_id = groups["投资"]
        print(f"找到 '投资' 分组，正在获取该分组下的UP主列表...")
        
        investment_ups = get_followings_in_group(session, my_mid, investment_tag_id)
        new_videos_count = 0
        new_videos_list = []
        
        if investment_ups:
            conn = sqlite3.connect(DB_FILE)
            try:
                print("\n--- '投资' 分组下的UP主视频检查 ---")
                total_ups = len(investment_ups)
                for i, up in enumerate(investment_ups, 1):
                    print(f"  - [{i}/{total_ups}] 正在检查UP主: {up['uname']:<20} MID: {up['mid']}")
                    mid = str(up['mid'])
                    
                    videos = get_up_videos(mid, session)
                    if videos:
                        print(f"    获取到 {len(videos)} 个最新视频，正在比对数据库...")
                        for video in videos:
                            video_info = {
                                "up_name": up['uname'],
                                "up_mid": up['mid'],
                                "bvid": video['bvid'],
                                "title": video['title'],
                                "link": video['link']
                            }
                            if save_video_if_not_exists(conn, video_info):
                                print(f"      [新视频] {video['title']}")
                                print(f"        链接: {video['link']}")
                                new_videos_count += 1
                                new_videos_list.append(video_info)
                    else:
                        print("    未能获取到视频列表。")
                    print("") # 空行分隔不同的UP主
                    time.sleep(5)
            finally:
                conn.close()

            # 将新视频列表写入文本文件，每行一个
            current_time = time.strftime("%Y%m%d-%H%M%S")
            output_filename = f"investment_videos_{current_time}.txt"

            with open(output_filename, 'w', encoding='utf-8') as f:
                for video in new_videos_list:
                    line = f"- {video['title']} | 作者: {video['up_name']} | 链接: {video['link']}\n"
                    f.write(line)

            print("-------------------------------------\n")
            if new_videos_count > 0:
                print(f"检查完成，共发现 {new_videos_count} 个新视频。")
                print(f"新视频列表已保存到 {output_filename}，每行一个视频。")
                print(f"所有视频历史记录已更新到 {DB_FILE}")
            else:
                print("检查完成，没有发现新视频。")
                print(f"已生成空的 {output_filename} 文件。")
        else:
            print("'投资' 分组下没有关注的UP主或获取失败。\n")
    else:
        print("未找到名为 '投资' 的关注分组。\n")

        
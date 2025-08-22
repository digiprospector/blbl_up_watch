#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests
import logging
import qrcode
import time
import json
from functools import reduce
import urllib.parse
import hashlib
from pathlib import Path
from pprint import pprint

class dp_bilibili:
    def __init__(self, ua="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3", cookies=None, logger=None, retry_max=10, retry_interval=5):
        self.ua = ua
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': self.ua})
        if cookies:
            self.session.cookies.update(cookies)
        if logger:
            self.logger = self.logger
        else:
            self.logger = logging.getLogger(__name__)
            self.logger.setLevel(logging.INFO)
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
        self.img_key = None
        self.sub_key = None
        self.groups = {}
        self.retry_max = retry_max
        self.retry_interval = retry_interval
        self.get_wbi_keys()
        self.mid = 0
        self.name = ""


    def login_by_qrcode(self) -> bool:
        """通过二维码扫描进行登录并返回一个包含cookies的session对象"""
        # 1. 获取二维码URL和key
        login_url_api = "https://passport.bilibili.com/x/passport-login/web/qrcode/generate"

        try:
            response = self.session.get(login_url_api)
            response.raise_for_status()
            data = response.json()['data']
            qrcode_key = data['qrcode_key']
            qr_url = data['url']
        except Exception as e:
            self.logger.info(f"获取登录二维码失败: {e}")
            return False

        # 2. 在终端显示二维码
        qr = qrcode.QRCode()
        qr.add_data(qr_url)
        qr.make(fit=True)
        qr.print_ascii(invert=True)
        self.logger.info("请使用Bilibili手机客户端扫描上方二维码")

        # 3. 轮询登录状态
        poll_api = "https://passport.bilibili.com/x/passport-login/web/qrcode/poll"
        
        try:
            while True:
                time.sleep(3)  # 等待一段时间后再轮询
                params = {'qrcode_key': qrcode_key}
                poll_response = self.session.get(poll_api, params=params) # 此处将自动使用 session 的 headers
                poll_response.raise_for_status()
                poll_data = poll_response.json()['data']
                
                code = poll_data['code']
                if code == 0:
                    self.logger.info("登录成功！")
                    return True
                elif code == 86038:
                    self.logger.info("二维码已失效，请重新运行程序。")
                    return False
                elif code == 86090:
                    self.logger.info("二维码已扫描，请在手机上确认登录...")
        except Exception as e:
            self.logger.info(f"轮询登录状态时发生错误: {e}")
            return False
        
    def login(self) -> bool:
        if not self.test_login():
            self.logger.info("请重新扫码登录")
            self.login_by_qrcode()
            if not self.test_login():
                self.logger.error("登录失败，请检查二维码或网络连接")
                return False
            else:
                self.logger.info("登录成功")
                return True
        else:
            self.logger.info("已经登录，无需扫码登录")
            return True

    def test_login(self):
        nav_api = "https://api.bilibili.com/x/web-interface/nav"
        try:
            response = self.session.get(nav_api)
            response.raise_for_status()
            data = response.json().get('data', {})
            if data.get('isLogin'):
                self.mid = data.get('mid', 0)
                self.name = data.get('uname', "")
                self.logger.info(f"已经登录 {self.name} mid:{self.mid}")
                return True
            else:
                return False
        except Exception as e:
            self.logger.info(f"测试是否登录时发生错误: {e}")
            self.groups = {}
            return False
        
    def get_following_groups(self):
        url = "https://api.bilibili.com/x/relation/tags"
        try:
            response = self.session.get(url)
            response.raise_for_status()
            data = response.json()
            if data['code'] == 0:
                # 包含默认的“全部关注”和“悄悄关注”等
                self.groups = {group['tagid']: {'name':group['name'], 'count':group['count']} for group in data['data']}
            else:
                self.logger.info(f"获取关注分组失败: {data['message']}")
                self.groups = {}
        except Exception as e:
            self.logger.info(f"获取关注分组时发生错误: {e}")
            self.groups = {}
            
        return self.groups

    def get_wbi_keys(self):
        """获取WBI签名所需的img_key和sub_key，失败时会自动重试。"""
        url = "https://api.bilibili.com/x/web-interface/nav"

        for attempt in range(self.retry_max):
            try:
                response = self.session.get(url, timeout=10)
                response.raise_for_status()
                data = response.json()
                img_url = data["data"]["wbi_img"]["img_url"]
                sub_url = data["data"]["wbi_img"]["sub_url"]
                self.img_key = img_url.split("/")[-1].split(".")[0]
                self.sub_key = sub_url.split("/")[-1].split(".")[0]
                return self.img_key, self.sub_key
            except Exception as e:
                self.logger.info(f"获取WBI密钥失败 (尝试 {attempt + 1}/{self.retry_max}): {e}")
                if attempt < self.retry_max - 1:
                    self.logger.info(f"将在 {self.retry_interval} 秒后重试...")
                    time.sleep(self.retry_interval)
                else:
                    self.logger.info("已达到最大重试次数，获取WBI密钥失败。")
        return None, None

    def get_mixin_key(self, orig: str):
        """根据B站的规则对imgKey和subKey进行打乱，生成mixinKey"""
        MIXIN_KEY_ENC_TAB = [
            46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
            33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40,
            61, 26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11,
            36, 20, 34, 44, 52
        ]
        return reduce(lambda s, i: s + orig[i], MIXIN_KEY_ENC_TAB, '')[:32]

    def sign_params(self, params: dict):
        if not self.img_key or not self.sub_key:
            return {}
        
        """为请求参数进行WBI签名"""
        mixin_key = self.get_mixin_key(self.img_key + self.sub_key)
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

    def get_up_videos(self, mid, ps=30, pn=1):
        """获取UP主第一页视频信息"""

        
        # 构造基本参数
        params = {
            "mid": mid,
            "ps": ps,       # 每页视频数
            "pn": pn,        # 页码
            "order": "pubdate",
            "platform": "web",
            "web_location": "1550101"
        }
        
        # 生成签名
        signed_params = self.sign_params(params)
        
        # 请求头
        headers = {
            "Referer": f"https://space.bilibili.com/{mid}/"
        }
        self.session.headers.update(headers)
        
        try:
            # 发送API请求
            response = self.session.get(
                "https://api.bilibili.com/x/space/wbi/arc/search",
                params=signed_params,
                headers=headers,
                timeout=10
            )
            data = response.json()
            
            # 检查响应状态
            if data["code"] != 0:
                self.logger.info(f"API请求失败: {data['message']}")
                return []
            
            # 提取视频数据
            videos = {}
            for video in data["data"]["list"]["vlist"]:
                title = video["title"]
                bvid = video["bvid"]
                videos[bvid] = {'title':title}
            
            return videos
        
        except Exception as e:
            self.logger.info(f"请求发生错误: {e}")
            return {}

    def get_ups_in_group(self, tag_id: int, pn: int = 1, ps: int = 300):
        """根据分组ID获取关注的UP主列表，失败时会自动重试。"""
        api_url = "https://api.bilibili.com/x/relation/tag"
        params = {
            "mid": self.mid,
            "tagid": tag_id,
            "pn": 1,
            "ps": 300,  # 每页数量，对于此API，通常一次返回分组内所有UP主
        }
        headers = {
            "Referer": f"https://space.bilibili.com/{self.mid}/fans/follow",
        }
        self.session.headers.update(headers)

        for attempt in range(self.retry_max):
            try:
                # session中已包含User-Agent
                response = self.session.get(api_url, params=params, timeout=10)
                response.raise_for_status()
                data = response.json()
                if data.get('code') == 0:
                    # 成功获取，返回数据
                    ups = {data["mid"]: {'name':data["uname"]} for data in data.get("data", {})}
                    return ups
                else:
                    # API返回错误码，打印信息并重试
                    self.logger.info(f"获取分组关注列表失败 (尝试 {attempt + 1}/{self.retry_max}): {data.get('message')}")
            except Exception as e:
                # 请求或解析过程发生异常，打印信息并重试
                self.logger.info(f"请求关注列表时发生错误 (尝试 {attempt + 1}/{self.retry_max}): {e}")
                
            if attempt < self.retry_max - 1:
                self.logger.info(f"将在 {self.retry_interval} 秒后重试...")
                time.sleep(self.retry_interval)
            else:
                self.logger.info("已达到最大重试次数，获取关注列表失败。")
                
        return {} # 所有重试都失败后
    
    def get_video_info(self, bvid):
        """获取视频信息"""

        api_url = "https://api.bilibili.com/x/web-interface/view"
        params = {
            "bvid": bvid
        }
        
        headers = {
            "Referer": f"https://www.bilibili.com/video",
        }

        for attempt in range(self.retry_max):
            try:
                # session中已包含User-Agent
                response = self.session.get(api_url, params=params, headers=headers, timeout=10)
                response.raise_for_status()
                data = response.json()
                if data.get('code') == 0:
                    # 成功获取，返回数据
                    data_json = data.get("data", {})
                    video_info = {data_json["bvid"]:{'pubdate':data_json["pubdate"],'title':data_json['title'],'duration':data_json['duration'], 'cid':data_json['cid']}}
                    return video_info
                else:
                    # API返回错误码，打印信息并重试
                    self.logger.info(f"获取视频信息失败 (尝试 {attempt + 1}/{self.retry_max}): {data.get('message')}")
            except Exception as e:
                # 请求或解析过程发生异常，打印信息并重试
                self.logger.info(f"请求视频信息时发生错误 (尝试 {attempt + 1}/{self.retry_max}): {e}")
                
            if attempt < self.retry_max - 1:
                self.logger.info(f"将在 {self.retry_interval} 秒后重试...")
                time.sleep(self.retry_interval)
            else:
                self.logger.info("已达到最大重试次数，获取视频信息失败。")
                
        return {} # 所有重试都失败后
    
    def get_audio_download_url(self, bvid, cid):
        """获取视频下载链接"""

        api_url = "https://api.bilibili.com/x/player/wbi/playurl"
        params = {
            'fnval': 16,  # 16表示dash格式的视频
            "bvid": bvid,
            "cid": cid
        }
        
        for attempt in range(self.retry_max):
            try:
                # session中已包含User-Agent
                response = self.session.get(api_url, params=params, timeout=10)
                response.raise_for_status()
                data = response.json()
                if data.get('code') == 0:
                    # 成功获取，返回数据
                    data_json = data.get("data", {})
                    audio_json_list = data_json.get("dash", {}).get("audio", [])
                    # 优先选择id为30280, 30232, 30216的音频
                    target_ids = [30280, 30232, 30216]
                    selected_audio = ""
                    for target_id in target_ids:
                        for audio in audio_json_list:
                            if audio.get("id") == target_id:
                                selected_audio = audio.get('baseUrl', "")
                                break
                    return selected_audio
                else:
                    # API返回错误码，打印信息并重试
                    self.logger.info(f"获取视频下载链接失败 (尝试 {attempt + 1}/{self.retry_max}): {data.get('message')}")
            except Exception as e:
                # 请求或解析过程发生异常，打印信息并重试
                self.logger.info(f"请求视频下载链接时发生错误 (尝试 {attempt + 1}/{self.retry_max}): {e}")
                
            if attempt < self.retry_max - 1:
                self.logger.info(f"将在 {self.retry_interval} 秒后重试...")
                time.sleep(self.retry_interval)
            else:
                self.logger.info("已达到最大重试次数，获取视频下载链接失败。")
                
        return {} # 所有重试都失败后

def download_file_with_resume(session, url, file_path:Path):
    headers = {}
    # 检查是否已存在部分下载的文件
    if file_path.exists():
        file_size = file_path.stat().st_size
        headers['Range'] = f'bytes={file_size}-'
    
    try:
        response = session.get(url, headers=headers, stream=True, timeout=30)
        
        # 检查服务器是否支持断点续传
        if response.status_code == 206:  # 部分内容
            mode = 'ab'  # 追加模式
        elif response.status_code == 200:  # 全部内容
            mode = 'wb'  # 写入模式
        else:
            print(f"服务器返回异常状态码: {response.status_code}")
            return False
        
        with open(file_path, mode) as file:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    file.write(chunk)
        
        print("下载完成!")
        return True
        
    except Exception as e:
        print(f"下载过程中出现错误: {e}")
        return False

if __name__ == "__main__":
    cookies = {}
    cookies_file = Path("cookies.json")
    if cookies_file.exists():
        with open("cookies.json", "r") as f:
            cookies = json.load(f)
    dp_blbl = dp_bilibili(cookies=cookies)
    if dp_blbl.login():
        with open("cookies.json", "w") as f:
            json.dump(dp_blbl.session.cookies.get_dict(), f)
    gp = dp_blbl.get_following_groups()
    dp_blbl.logger.debug(f"关注分组: {gp}")
    group_id, (group_name, ups_count) = next(iter(gp.items()))  # 获取第一个分组名称
    dp_blbl.logger.info(f"第一个分组: {group_name}, ID: {group_id}, UP主数量: {ups_count}")
    ups =dp_blbl.get_ups_in_group(group_id)
    dp_blbl.logger.info(f"分组 {group_name} 中的UP主: {ups}")
    up_id, up_name = next(iter(ups.items()))  # 获取第一个UP主
    dp_blbl.logger.info(f"第一个UP主: {up_name}, ID: {up_id}")
    videos = dp_blbl.get_up_videos(up_id)
    dp_blbl.logger.info(f"UP主 {up_name} 的视频列表: {videos}")
    bvid, title = next(iter(videos.items()))  # 获取第一个视频
    dp_blbl.logger.info(f"第一个视频: {title}, BV号: {bvid}")
    video_info = dp_blbl.get_video_info(bvid)
    dp_blbl.logger.info(f"视频 {title} 的详细信息: {video_info}")
    with open("video_info.json", "w") as f:
        json.dump(video_info, f, ensure_ascii=False, indent=4)
    dl_url = dp_blbl.get_audio_download_url(bvid, video_info[bvid]['cid'])
    dp_blbl.logger.info(f"视频 {title} 的下载链接: {dl_url}")
    with open("download_url.json", "w") as f:
        json.dump(dl_url, f, ensure_ascii=False, indent=4)
    download_file_with_resume(dp_blbl.session, dl_url, Path(f"audio.m4s"))
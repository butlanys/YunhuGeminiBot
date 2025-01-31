import uvicorn
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse,HTMLResponse
import json
import threading
import requests
import sqlite3
import google.generativeai as genai
import os
import time
from google.generativeai.types import HarmCategory, HarmBlockThreshold
from datetime import date, datetime
import re
import mysql.connector
from yunhu import *
from config import *
from getYoutube import *
from getSite import *
from log import *

class sql: #所有数据库操作
    @staticmethod
    def create_tables():
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS user_data (user_id TEXT PRIMARY KEY, message_id TEXT, count INTEGER)")
        # 删除 system_prompts 表的创建
        # cursor.execute(
        #     "CREATE TABLE IF NOT EXISTS system_prompts (sender_id TEXT PRIMARY KEY, prompt TEXT)")
        # 创建 user_usage_logs 表
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS user_usage_logs (user_id TEXT, usage_date DATE, token_count INTEGER, call_count INTEGER, PRIMARY KEY (user_id, usage_date))")
        # 创建 group_usage_logs 表
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS group_usage_logs (group_id TEXT, usage_date DATE, token_count INTEGER, call_count INTEGER, PRIMARY KEY (group_id, usage_date))")
        # 创建 user_agreements 表
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS user_agreements (user_id TEXT PRIMARY KEY, agreed BOOLEAN)")
        # 创建 group_settings 表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS group_settings (
                group_id TEXT PRIMARY KEY,
                keywords TEXT,
                system_prompt TEXT,
                user_blacklist TEXT
            )
        """)
        # 新增：创建 user_settings 表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_settings (
                user_id TEXT PRIMARY KEY,
                enable_web_search BOOLEAN DEFAULT FALSE,
                api_key TEXT,
                system_prompt TEXT,
                model TEXT DEFAULT 'gemini-1.5-flash-latest'
            )
        """)
        conn.commit()
        conn.close()

        # 创建 MySQL 对话日志表
        sql.create_mysql_chat_log_table()
    @staticmethod
    def get_mysql_connection():
        """获取 MySQL 数据库连接。"""
        return mysql.connector.connect(
            host=MYSQL_HOST,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            database=MYSQL_DATABASE
        )
    @staticmethod
    def create_mysql_chat_log_table():
        """创建 MySQL 对话日志表。"""
        conn = sql.get_mysql_connection()
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chat_logs (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id TEXT,
                chat_type TEXT,
                input_text TEXT,
                output_text TEXT,
                timestamp DATETIME
            )
        """)
        conn.commit()
        conn.close()

    @staticmethod
    def log_chat_to_mysql(user_id, chat_type, input_text, output_text):
        """记录对话日志到 MySQL 数据库。"""
        conn = sql.get_mysql_connection()
        cursor = conn.cursor()
        timestamp = datetime.now()
        cursor.execute("""
            INSERT INTO chat_logs (user_id, chat_type, input_text, output_text, timestamp)
            VALUES (%s, %s, %s, %s, %s)
        """, (user_id, chat_type, input_text, output_text, timestamp))
        conn.commit()
        conn.close()

def push_message(recvType,
                recvId,
                contentType,
                user_text,
                prompt,
                system_prompt=None,
                file_urls=None,
                site_text=None,
                enable_web_search=False,
                user_model="gemini-1.5-flash-latest"):
    msgId = yhchat_push(recvId, recvType, contentType, "Loading…………")

    if enable_web_search:
        yhchat_remsg(recvId, recvType, contentType, "正在搜索🔍", msgId)
        search_text = "来自网络搜索内容（此内容自动附加，非用户提供）：\n"
        search_urls = get_search_urls(user_text)
        """for search_url in search_urls:
            search_text += f"{search_url}：{get_clean_text(search_url)}\n"""
        result_dict = {}
        lock = threading.Lock()
        def process_url(search_url):
            text = get_clean_text(search_url)
            with lock:
                if text is None:
                    return False  # 返回 False 表示处理失败
                result_dict[search_url] = f"{search_url}：{text}"
                return True
            
        threads = []
        failed_urls = []  # 用于存储处理失败的 URL
        for search_url in search_urls:
            thread = threading.Thread(target=process_url, args=(search_url,))
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        # 收集失败的 URL
        for search_url in search_urls:
            if search_url not in result_dict:
                failed_urls.append(search_url)

        # 从 search_urls 中移除失败的 URL
        for url in failed_urls:
            search_urls.remove(url)

        for search_url in search_urls:  # 现在 search_urls 中只包含成功的 URL
            search_text += f"{result_dict[search_url]}\n"

        search_text += "来自网络的搜索内容<结束>"
        prompt = f"{search_text}\n{site_text}\n{prompt}"

    text_ok = ""
    # 获取下一个 API Key
    api_key = next(api_key_cycle)

    # 创建 GenerativeModel 实例时设置 system_instruction 和 safety_settings
    safety_settings = {
        HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE
    }

    # 使用获取的 API Key 初始化模型
    genai.configure(api_key=api_key)

    # Gemini自带的网络搜索(已废弃)
    # if user_model in ("gemini-1.5-flash-latest", "gemini-1.5-pro-latest"):
    #     tools = [
    #         genai.protos.Tool(
    #         google_search_retrieval = genai.protos.GoogleSearchRetrieval(
    #             dynamic_retrieval_config = genai.protos.DynamicRetrievalConfig(
    #             mode = genai.protos.DynamicRetrievalConfig.Mode.MODE_DYNAMIC,
    #             dynamic_threshold = 0.3,
    #             ),
    #         ),
    #         ),
    #     ]
    #     model_config = {
    #         "model_name": user_model,
    #         "safety_settings": safety_settings,
    #         #"tools": tools,
    #     }
    #     if system_prompt:
    #         model_config["system_instruction"] = system_prompt
    #     model = genai.GenerativeModel(**model_config)
        
        
    # else:
    if system_prompt:
        model = genai.GenerativeModel(user_model, system_instruction=system_prompt, safety_settings=safety_settings)
    else:
        model = genai.GenerativeModel(user_model, safety_settings=safety_settings)
    
    total_tokens = 0  # 初始化总 token 数
    
    #图片
    if file_urls:
        yhchat_remsg(recvId, recvType, contentType, "上传文件📄ing", msgId)
        uploaded_files = []
        try:
            for file_url in file_urls:
                file_name = file_url['url'].split("/")[-1].split("?")[0]
                file_path = os.path.join("tmp", file_name)
                os.makedirs("tmp", exist_ok=True)
                headers = {"Referer": "http://myapp.jwznb.com"} #防403
                with open(file_path, "wb") as f:
                    response = requests.get(file_url['url'], headers=headers)
                    response.raise_for_status()  # 检查状态码
                    f.write(response.content)  # 直接写入所有内容
                #uploaded_file = genai.upload_file(file_path)
                uploaded_file = genai.upload_file(file_path)
                # 循环检查文件状态，直到状态为 ACTIVE
                while True:
                    file_metadata = genai.get_file(uploaded_file.name)
                    if file_metadata.state == 2:
                        break
                    time.sleep(1)  # 等待 1 秒后重试
                uploaded_files.append(uploaded_file)
                #print(file_url, file_path, file_name, uploaded_files) # 简化输出
            yhchat_remsg(recvId, recvType, contentType, "上传文件📄完成，正在思考问题ing", msgId)
            # 正确调用 generate_content，只调用一次
            response = model.generate_content([prompt] + uploaded_files, stream=True) 

            for chunk in response:
                text_ok += chunk.text
                yhchat_remsg(recvId, recvType, contentType, text_ok, msgId)
                total_tokens += model.count_tokens([chunk.text]).total_tokens

        finally:
            for uploaded_file in uploaded_files:
                genai.delete_file(uploaded_file.name)
            for file_url in file_urls:
                file_name = file_url['url'].split("/")[-1].split("?")[0]
                file_path = os.path.join("tmp", file_name)
                if os.path.exists(file_path):
                    os.remove(file_path)
        #return #  将 return 移到 finally 块之后
        # 新增：记录日志到 MySQL
        if recvType == "user":
            sql.log_chat_to_mysql(recvId, "user", prompt, text_ok)
        else:
            sql.log_chat_to_mysql(recvId, "group", prompt, text_ok)
        return
    yhchat_remsg(recvId, recvType, contentType, "正在思考问题ing", msgId)
    # chat = model.start_chat(history=history)
    response = model.generate_content(prompt, stream=True)  # 启用流式输出
    for chunk in response:
        text_ok += chunk.text
        yhchat_remsg(recvId, recvType, contentType, text_ok, msgId)
        total_tokens += model.count_tokens([chunk.text]).total_tokens  # 累加每个 chunk 的 token 数
    if recvType == "user":
        record_usage(recvId, total_tokens, 1, "user")  # 记录用户总 token 数和调用次数
    else:
        record_usage(recvId, total_tokens, 1, "group")  # 记录群组总 token 数和调用次数
    # 新增：记录日志到 MySQL
    if recvType == "user":
        sql.log_chat_to_mysql(recvId, "user", prompt, text_ok)
    else:
        sql.log_chat_to_mysql(recvId, "group", prompt, text_ok)

#==========================================URL====================================================

def extract_url(string):
    url_regex = re.compile(
        r'(?:(?:https?|ftp):\/\/)?'  # http:// or https:// or ftp://
        r'(?:\S+(?::\S*)?@)?'  # user and password
        r'(?:'
        r'(?!(?:10|127)(?:\.\d{1,3}){3})'
        r'(?!(?:169\.254|192\.168)(?:\.\d{1,3}){2})'
        r'(?!172\.(?:1[6-9]|2\d|3[0-1])(?:\.\d{1,3}){2})'
        r'(?:[1-9]\d?|1\d\d|2[01]\d|22[0-3])'
        r'(?:\.(?:1?\d{1,2}|2[0-4]\d|25[0-5])){2}'
        r'(?:\.(?:[1-9]\d?|1\d\d|2[0-4]\d|25[0-4]))'
        r'|'
        r'(?:www.)?'  # www.
        r'(?:[a-z\u00a1-\uffff0-9]-?)*[a-z\u00a1-\uffff0-9]+'
        r'(?:\.(?:[a-z\u00a1-\uffff]{2,}))+'
        r'(?:\.(?:[a-z\u00a1-\uffff]{2,})+)*'
        r')'
        r'(?::\d{2,5})?'  # port
        r'(?:[/?#]\S*)?',  # resource path
        re.IGNORECASE
    )
    match = re.search(url_regex, string)
    return match.group(0) if match else None

def is_youtube_url(url):
    # Regular expression to match YouTube URL
    if url == None:
        return False
    youtube_regex = (
        r'(https?://)?(www\.)?'
        '(youtube|youtu|youtube-nocookie)\.(com|be)/'
        '(watch\?v=|embed/|v/|.+\?v=)?([^&=%\?]{11})'
    )

    youtube_regex_match = re.match(youtube_regex, url)
    return youtube_regex_match is not None

def process_messages(parsed_data):
    messages = []
    file_urls = []
    site_text = ""
    file_num = 0
    for message in parsed_data['data']['list']:
        if 'text' in message['content']:
            content_text = message['content']['text']
            if not content_text.startswith("/") and not content_text.startswith("系统消息"):
                if message['senderType'] == 'user':
                    messages.append(f"user: {content_text}")
                    extracted_url = extract_url(content_text)
                    if extracted_url:
                        url1 = is_youtube_url(extracted_url)
                        if url1 == True:
                            url2 = get_video_id(extracted_url)
                            text = get_youtube_subtitles_auto_lang(url2)
                            site_text += f"{extracted_url}：{text}"
                        else:
                            text = get_clean_text(extracted_url)
                            site_text += f"{extracted_url}：{text}"
                elif message['senderType'] == 'bot':
                    messages.append(f"model: {content_text}")
        elif 'fileUrl' in message['content']:
            file_num += 1
            messages.append(f"user: <这是第{file_num}个文件>")
            file_name = message['content']['fileUrl']
            file_url = f"{yhchat_url_chat}/file/{file_name}"
            # 将文件 URL 和描述信息存储在字典中
            file_urls.append({"file_type": "file","url": file_url})
        elif 'videoUrl' in message['content']:
            file_num += 1
            messages.append(f"user: <这是第{file_num}个视频>")
            video_name = message['content']['videoUrl']
            video_url = f"{yhchat_url_chat}/video/{video_name}"
            # 将视频 URL 和描述信息存储在字典中
            file_urls.append({"file_type": "video","url": video_url})
        elif 'audioUrl' in message['content']:
            file_num += 1
            messages.append(f"user: <这是第{file_num}条语音>")
            audio_name = message['content']['audioUrl']
            audio_url = f"{yhchat_url_chat}/audio/{audio_name}"
            # 将语音 URL 和描述信息存储在字典中
            file_urls.append({"file_type": "audio","url": audio_url})
        elif 'imageName' in message['content']:
            file_num += 1
            messages.append(f"user: <这是第{file_num}张图片>")
            image_name = message['content']['imageName']
            image_url = f"{yhchat_url_chat}/img/{image_name}"
            # 将图片 URL 和描述信息存储在字典中
            file_urls.append({"file_type": "img","url": image_url})
    messages.reverse()
    return "\n".join(messages), file_urls, site_text

def messages_list(chat_id, message_id):
    if not message_id:
        return [], []

    # 设置访问 API 所需的参数和头部
    after = 60

    # 发送 GET 请求获取消息列表
    response = requests.get(
        f'{yhchat_url_chat_go}/open-apis/v1/bot/messages',
        params={'token': TOKEN, 'chat-id': chat_id, 'chat-type': 'user', 'message-id': message_id,
                'after': after},
    )

    # 调用消息处理函数进行处理
    messages, image_urls, site_text = process_messages(response.json())

    # 返回按照原始顺序排列的消息内容字符串
    return messages, image_urls, site_text

def messages_sql(senderId, message_id_tmp, text_messages_list_tmp):
    # 连接到 SQLite 数据库（如果不存在，则会自动创建）
    conn = sqlite3.connect('data.db')
    cursor = conn.cursor()

    # 1. 检测 text_messages_list_tmp 值是否等于 "/RESET"
    if text_messages_list_tmp == "/RESET" or text_messages_list_tmp == "/清除上下文":
        # **关键改动：只发送一条消息 "会话已重置"，并删除整个元组**
        yhchat_push(senderId, "user", "text", "会话已重置")
        # print("上下文已清除")

        # 直接删除 senderId 对应的记录
        cursor.execute(f"DELETE FROM user_data WHERE user_id = '{senderId}'")
        conn.commit()
        return "clean_text"

    # 2. 检测表是否存在，如果不存在则创建
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS user_data (user_id TEXT PRIMARY KEY, message_id TEXT, count INTEGER)")

    # 3. 查找 senderId 对应的记录
    cursor.execute(f"SELECT * FROM user_data WHERE user_id = '{senderId}'")
    user_data = cursor.fetchone()

    if user_data is None:
        # 如果记录不存在，则插入新记录
        cursor.execute(
            f"INSERT INTO user_data (user_id, message_id, count) VALUES (?, ?, ?)",
            (senderId, message_id_tmp, 1))
        conn.commit()
        return message_id_tmp
    else:
        # 如果记录存在，则更新 message_id 和 count
        message_id, count = user_data[1], user_data[2]
        if count > 30:
            # 如果 count 超过限制，则删除记录并提示用户
            cursor.execute(f"DELETE FROM user_data WHERE user_id = '{senderId}'")
            conn.commit()
            yhchat_push(senderId, "user", "text", "上下文达到限制，已自动清除")
            return "clean_text"
        else:
            # 只有 message_id 为空时才更新 message_id，表示新的会话开始
            if not message_id:
                cursor.execute(
                    f"UPDATE user_data SET message_id = '{message_id_tmp}', count = {count + 1} WHERE user_id = '{senderId}'")
                conn.commit()
            return message_id

def get_user_settings_from_db(user_id):
    """从数据库获取用户设置"""
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("SELECT enable_web_search, api_key, system_prompt, model FROM user_settings WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    conn.close()
    if result:
        return {
            "enable_web_search": bool(result[0]),
            "api_key": result[1],
            "system_prompt": result[2],
            "model": result[3]
        }
    else:
        return {
            "enable_web_search": False,
            "api_key": None,
            "system_prompt": None,
            "model": "gemini-1.5-pro-latest"
        }

def update_user_settings(user_id, enable_web_search, api_key, system_prompt, model):
    """更新用户设置到数据库"""
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO user_settings (user_id, enable_web_search, api_key, system_prompt, model)
        VALUES (?, ?, ?, ?, ?)
    """, (user_id, enable_web_search, api_key, system_prompt, model))
    conn.commit()
    conn.close()

def record_usage(user_id, token_count, call_count, usage_type):
    """
    记录用户或群组的用量信息。

    Args:
        user_id (str): 用户 ID 或群组 ID。
        token_count (int): 使用的 token 数量。
        call_count (int): 调用次数。
        usage_type (str): 用量类型，"user" 或 "group"。
    """
    today = date.today()
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    if usage_type == "user":
        table_name = "user_usage_logs"
        id_column = "user_id"
    elif usage_type == "group":
        table_name = "group_usage_logs"
        id_column = "group_id"  # 关键改动：将 user_id 替换为 group_id
    else:
        raise ValueError("Invalid usage_type.")

    # 尝试更新用量数据，如果记录不存在则插入新记录
    cursor.execute(
        f"UPDATE {table_name} SET token_count = token_count + ?, call_count = call_count + ? WHERE {id_column} = ? AND usage_date = ?",
        (token_count, call_count, user_id, today)
    )
    if cursor.rowcount == 0:
        # 如果没有更新任何记录，说明记录不存在，则插入新记录
        cursor.execute(
            f"INSERT INTO {table_name} ({id_column}, usage_date, token_count, call_count) VALUES (?, ?, ?, ?)",
            (user_id, today, token_count, call_count)
        )

    conn.commit()
    conn.close()

def get_usage(user_id, usage_type="user"):
    """
    获取用户或群组的用量信息。

    Args:
        user_id (str): 用户 ID 或群组 ID。
        usage_type (str): 用量类型，"user" 或 "group"。

    Returns:
        tuple: (token_count, call_count) 或 (0, 0) 如果没有记录。
    """
    today = date.today()
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    if usage_type == "user":
        table_name = "user_usage_logs"
        id_column = "user_id"
    elif usage_type == "group":
        table_name = "group_usage_logs"
        id_column = "group_id"  # 使用 group_id 查询 group_usage_logs 表
    else:
        raise ValueError("Invalid usage_type.")

    cursor.execute(
        f"SELECT token_count, call_count FROM {table_name} WHERE {id_column} = ? AND usage_date = ?",  # 使用 id_column
        (user_id, today)
    )
    result = cursor.fetchone()
    conn.close()
    return result if result else (0, 0)  # 返回 token_count 和 call_count

def format_token_count(token_count):
    if token_count >= 1000000:
        return f"{token_count / 1000000:.1f}M"
    elif token_count >= 1000:
        return f"{token_count / 1000:.1f}K"
    else:
        return str(token_count)

def get_all_usage_table(parsed_json):
    today = date.today()

    # 查询用户用量
    user_table = get_usage_table("user_usage_logs", parsed_json, today)

    # 查询群聊用量
    group_table = get_usage_table("group_usage_logs", parsed_json, today, is_group=True)

    return f"用户用量：\n{user_table}\n\n群聊用量：\n{group_table}"

def get_usage_table(table_name, parsed_json, today, is_group=False):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    # 查询用量数据
    cursor.execute(
        f"SELECT * FROM {table_name} WHERE usage_date = ? ORDER BY token_count DESC",
        (today,)
    )
    results = cursor.fetchall()

    conn.close()

    if is_group:
        table = "| 群聊名称 | 群聊ID | Token 使用量 | 调用次数 |\n|---|---|---|---|"
    else:
        table = "| 用户昵称 | 用户ID | Token 使用量 | 调用次数 |\n|---|---|---|---|"

    for row in results:
        if is_group:
            # 获取群聊名称
            group_name = get_group_name(row[0])
            table += f"\n| {group_name} | {row[0]} | {format_token_count(row[2])} | {row[3]} |"
        else:
            # 获取用户昵称
            user_nickname = get_user_nickname_from_db(row[0])  # 从数据库获取用户昵称
            table += f"\n| {user_nickname} | {row[0]} | {format_token_count(row[2])} | {row[3]} |"

    return table

def get_user_nickname_from_db(user_id):
    """
    从数据库中获取指定 user_id 的 nickname。
    """
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("SELECT nickname FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else "未知昵称"

def get_user_nickname(parsed_json, user_id):
    # 遍历 parsed_json 中的所有 sender 对象，查找匹配的 user_id
    sender = parsed_json['event'].get('sender') # 从 event.sender 中获取 sender 信息
    if sender and sender.get('senderId') == user_id:
        return sender.get('senderNickname', '未知昵称')
    return '未知昵称'

def update_user_nickname(user_id, nickname):
    """
    更新用户的昵称。
    """
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    # 检查 users 表是否存在，如果不存在则创建
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            nickname TEXT
        )
    """)

    # 更新或插入用户昵称
    cursor.execute("""
        INSERT OR REPLACE INTO users (user_id, nickname)
        VALUES (?, ?)
    """, (user_id, nickname))

    conn.commit()
    conn.close()

def check_agreement(user_id):
    """
    检查用户是否已同意许可协议。
    """
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("SELECT agreed FROM user_agreements WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else False

def set_agreement(user_id, agreed):
    """
    设置用户是否同意许可协议。
    """
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO user_agreements (user_id, agreed) VALUES (?, ?)", (user_id, agreed))
    conn.commit()
    conn.close()

def send_agreement_message(user_id):
    """
    发送许可协议消息。
    """
    buttons = [
        [
            {
                "text": "同意",
                "actionType": 3,
                "value": "true"
            },
            {
                "text": "拒绝",
                "actionType": 3,
                "value": "false"
            }
        ]
    ]
    msg_id = yhchat_push(user_id,"user", "markdown", botAgreement,buttons)
    # 记录 msgId
    agreement_msg_ids[user_id] = msg_id

def get_group_settings(group_id):
    """
    获取群聊设置。
    """
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM group_settings WHERE group_id = ?", (group_id,))
    result = cursor.fetchone()
    conn.close()
    if result:
        return {
            "keywords": result[1].split("\n") if result[1] else group_at,
            "system_prompt": result[2],
            "user_blacklist": result[3].split(",") if result[3] else []
        }
    else:
        # 如果没有设置，则使用默认值
        return {
            "keywords": group_at,
            "system_prompt": None,
            "user_blacklist": []
        }
    
def update_group_settings(group_id, keywords, system_prompt, user_blacklist):
    """
    更新群聊设置。
    """
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO group_settings (group_id, keywords, system_prompt, user_blacklist)
        VALUES (?, ?, ?, ?)
    """, (group_id, "\n".join(keywords), system_prompt, "\n".join(user_blacklist)))  # 使用 "\n" 连接用户黑名单
    conn.commit()
    conn.close()

def handle_message(parsed_json):
    # print(parsed_json)
    event_type = parsed_json['header']['eventType']

    if event_type == "bot.followed":
        # 用户添加机器人
        user_id = parsed_json['event']['userId']
        chat_type = parsed_json['event']['chatType']
        # 只有私聊才发送许可协议消息
        if chat_type == "bot":
            send_agreement_message(user_id)

    elif event_type == "button.report.inline":
        # 处理按钮点击事件
        user_id = parsed_json['event']['userId']
        value = parsed_json['event']['value']
        msg_id = parsed_json['event']['msgId']
        if user_id in agreement_msg_ids and msg_id == agreement_msg_ids[user_id]:
            # 用户点击了许可协议消息的按钮
            if value == "true":
                # 同意协议
                set_agreement(user_id, True)
                yhchat_remsg(user_id, "user", "text", "系统消息：\n您已同意此许可协议，可以正常使用此bot", msg_id)
            else:
                # 拒绝协议
                set_agreement(user_id, False)
                yhchat_remsg(user_id, "user", "text",
                             "系统消息：\n您已拒绝此许可协议，将禁止使用此bot，如需重新同意，请发送任意消息", msg_id)
            # 删除 msgId 记录
            del agreement_msg_ids[user_id]

    elif event_type == "bot.setting":
        # 处理群聊设置事件
        group_id = parsed_json['event']['groupId']
        setting_json = json.loads(parsed_json['event']['settingJson'])
        keywords = setting_json['bempft']['value'].split("\n") if setting_json['bempft']['value'] else group_at
        system_prompt = setting_json['zbspby']['value']
        user_blacklist = setting_json['lewvhx']['value'].split("\n") if setting_json['lewvhx'][
            'value'] else []
        update_group_settings(group_id, keywords, system_prompt, user_blacklist)
        #print(f"群聊 {group_id} 设置已更新：\n关键词：{keywords}\n系统提示词：{system_prompt}\n用户黑名单：{user_blacklist}")

    elif event_type == "message.receive.normal" or event_type == "message.receive.instruction":
        # 处理普通消息和指令消息
        senderType_tmp = parsed_json['event']['chat']['chatType']
        if senderType_tmp == "bot":
            # 私聊
            senderId = parsed_json['event']['sender']['senderId']
            user_nickname = get_user_nickname(parsed_json, senderId)
            update_user_nickname(senderId, user_nickname)  # 添加更新用户昵称的函数
        else:
            # 群聊
            senderId = parsed_json['event']['chat']['chatId']  # 群组 ID 不需要添加前缀

        instruction_id = parsed_json['event']['message'].get('instructionId')
        content_type = parsed_json['event']['message']['contentType']

        # 只有私聊才检查许可协议
        if senderType_tmp == "bot" and not check_agreement(senderId):
            # 用户未同意许可协议
            send_agreement_message(senderId)
            return

        if senderType_tmp == "bot" and senderId in user_ban:
            yhchat_push(senderId, "user", "text", "已被列入黑名单，请联系管理员！")
            return

        if senderType_tmp == "group" and senderId in group_ban:  # 检查群组 ID 是否在黑名单中
            yhchat_push(senderId, "group", "text", "该群组已被列入黑名单，请联系管理员！")
            return

        if instruction_id == INSTRUCTION_ID_RESET_SESSION:
            # 重置会话指令
            messages_sql(senderId, None, "/RESET")

        elif instruction_id == INSTRUCTION_ID_SETTINGS and senderType_tmp == "bot":
            # 设置指令 (仅私聊可用)
            form_json = parsed_json['event']['message']['content']['formJson']
            enable_web_search = form_json['jywrir']['value']
            api_key = form_json['odmbsu']['value']
            system_prompt = form_json['tgwbcc']['value']
            model = form_json['ymjjxg']['selectValue']

            update_user_settings(senderId, enable_web_search, api_key, system_prompt, model)
            yhchat_push(senderId, "user", "text", f"系统消息：\n个人设置已更新：\n模型联网：{enable_web_search}\n自定义Gemini密钥：{api_key}\n系统提示词：{system_prompt}\nGemini模型：{model}")

        elif instruction_id == INSTRUCTION_ID_USAGE_QUERY:
            # 查询用量指令
            # 使用 ADMIN_ID 判断用户是否是管理员
            if senderId == ADMIN_ID:
                # 管理员查看所有用户的用量
                usage_table = get_all_usage_table(parsed_json)
                yhchat_push(senderId, "user" if senderType_tmp == "bot" else "group", "markdown",
                           "系统消息：\n" + usage_table)
            else:
                # 普通用户查看自己的用量
                if senderType_tmp == "bot":
                    # 私聊
                    token_count, call_count = get_usage(senderId, usage_type="user")
                else:
                    # 群聊
                    token_count, call_count = get_usage(senderId, usage_type="group")

                # 格式化 token 数量
                formatted_token_count = format_token_count(token_count)
                if senderType_tmp == 'bot':
                    # 私聊
                    yhchat_push(senderId, "user", "text",
                               f"系统消息：\n您今日的用量为：{formatted_token_count} tokens，调用次数为：{call_count}")
                else:
                    # 群聊
                    yhchat_push(senderId, "group", "text",
                               f"系统消息：\n此群今日的用量为：{formatted_token_count} tokens，调用次数为：{call_count}")

        elif senderType_tmp == "bot":
            # 处理用户消息
            message_id_tmp = parsed_json['event']['message']['msgId']
            text_messages_list_tmp = parsed_json['event']['message']['content'].get('text', '')
            message_id = messages_sql(senderId, message_id_tmp, text_messages_list_tmp)

            # 获取用户设置
            user_settings = get_user_settings_from_db(senderId)
            system_prompt = user_settings["system_prompt"]
            enable_web_search = user_settings["enable_web_search"]
            user_model = user_settings["model"]

            # 只有在非重置会话指令的情况下才调用 messages_list 获取历史消息
            if text_messages_list_tmp != "/RESET" and text_messages_list_tmp != "/清除上下文":
                history, file_urls, site_text = messages_list(senderId, message_id)
            else:
                history, file_urls, site_text = None, None, None  # 重置会话指令后，无需历史消息

            # 文本消息
            if content_type in {"text","markdown","audio"}:
                threading.Thread(target=push_message,args=("user",
                                                           senderId,
                                                           "markdown",
                                                           text_messages_list_tmp,
                                                           history,
                                                           system_prompt,
                                                           file_urls,
                                                           site_text,
                                                           enable_web_search,
                                                           user_model)).start()

        elif senderType_tmp == "group":
            # 处理群组消息
            text = parsed_json['event']['message']['content']['text']

            # 获取群聊设置
            group_settings = get_group_settings(senderId)

            # 检查用户是否在黑名单中
            if parsed_json['event']['sender']['senderId'] in group_settings['user_blacklist']:
                print(f"用户 {parsed_json['event']['sender']['senderId']} 在群聊 {senderId} 的黑名单中，已忽略消息。")
                return

            # 检查消息是否包含关键词
            for keyword in group_settings['keywords']:
                if re.search(keyword,text,re.IGNORECASE):
                    break
            else:
                return

            history = [{"role": "user", "parts": text}]
            system_prompt = group_settings['system_prompt']
            threading.Thread(target=push_message,args=("group", senderId, "markdown", history, system_prompt)).start()
            
app = FastAPI()
# Flask接收消息的路由，使用POST方法接收消息
@app.post('/yhchat')
async def receive_message(request: Request):
    try:
        genai.configure(api_key=next(api_key_cycle)) 
        json_data = await request.json()
        handle_message(json_data)
        # 返回处理成功的响应
        return JSONResponse(content={"StatusCode": "200"}, status_code=200)
    except Exception as e:
        tb_str = traceback.format_exc()
        error_logger.error(f"Error: {e}\n{tb_str}")
        raise HTTPException(status_code=200)

# 主函数，运行Flask应用
if __name__ == '__main__':
    # 初始化 Google Generative AI
    # genai.configure(api_key=next(api_key_cycle))  # 初始化时使用第一个 API Key
    # 创建数据库表
    sql.create_tables()
    uvicorn.run(app, host='0.0.0.0', port=56667)
from itertools import cycle

usage_data = {} # 每个用户每天的 token 使用量
agreement_msg_ids = {} #临时存储用户是否同意协议的消息ID

yhchat_url_chat_go = ""
yhchat_url_chat = ""

ADMIN_ID = "5587539"  # 管理员 ID

# 机器人token
TOKEN = "xxx"

# 黑名单(示例："0000000","0000001")
group_ban = []  # 群组
user_ban = []  # 用户

# 群组被at关键词
group_at = ["@Gemini"]

API_KEYS = [
    "xxx",
    "xxx",
]
api_key_cycle = cycle(API_KEYS)

INSTRUCTION_ID_RESET_SESSION = 979
INSTRUCTION_ID_USAGE_QUERY = 981
INSTRUCTION_ID_SETTINGS = 1142

#MySQL
MYSQL_HOST = "localhost"
MYSQL_USER = ""
MYSQL_PASSWORD = ""
MYSQL_DATABASE = ""

DATABASE = 'data.db'

def get_bot_agreement(filepath="botAgreement.md"):
  try:
    with open(filepath, 'r', encoding='utf-8') as f:
      botAgreement = f.read()
    return botAgreement
  except FileNotFoundError:
    return "未找到用户协议文件，请联系管理员。"

botAgreement = get_bot_agreement()
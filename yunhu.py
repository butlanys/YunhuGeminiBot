import requests,json
from config import TOKEN, yhchat_url_chat_go
def yhchat_push(recvId, recvType, contentType, text, buttons=None):
    url = f"{yhchat_url_chat_go}/open-apis/v1/bot/send?token={TOKEN}"
    
    # 构建 content 字典
    content = {
        "text": text
    }
    
    # 如果有按钮，则添加到 content 字典中
    if buttons:
        content["buttons"] = buttons

    # 构建完整的 payload
    payload = json.dumps({
        "recvId": recvId,
        "recvType": recvType,
        "contentType": contentType,
        "content": content
    })

    headers = {
        'Content-Type': 'application/json'
    }
    # 发送POST请求推送消息
    response = requests.request("POST", url, headers=headers, data=payload)

    json_msgId = json.loads(response.text)
    msgId = json_msgId['data']['messageInfo']['msgId']

    return msgId

# 消息编辑api，用于流式输出
def yhchat_remsg(recvId, recvType, contentType, text, msgId, buttons=None):
    url = f'{yhchat_url_chat_go}/open-apis/v1/bot/edit'
    headers = {
        'Content-Type': 'application/json'
    }
    data = {
        "msgId": msgId,
        "recvId": recvId,
        "recvType": recvType,
        "contentType": contentType,
        "content": {
            "text": text,
        }
    }
    if buttons:
        data['content']['buttons'] = buttons
    params = {
        'token': TOKEN
    }

    response = requests.post(url, headers=headers, json=data, params=params)
    return response.text
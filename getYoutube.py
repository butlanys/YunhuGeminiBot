# from youtube_transcript_api import YouTubeTranscriptApi
# from youtube_transcript_api._errors import TranscriptsDisabled
import urllib.parse as urlparse
import yt_dlp, json, requests

# def get_transcript_from_url(url):
#     try:
#         # parse the URL
#         parsed_url = urlparse.urlparse(url)
        
#         # extract the video ID from the 'v' query parameter
#         video_id = urlparse.parse_qs(parsed_url.query)['v'][0]
        
#         # get the transcript
#         transcript_list = YouTubeTranscriptApi.get_transcript(video_id)
        
#         # concatenate the transcript
#         transcript = ' '.join([i['text'] for i in transcript_list])
        
#         return transcript
#     except (KeyError, TranscriptsDisabled):
#         return "Error retrieving transcript from YouTube URL"

def get_video_id(url):
    # parse the URL
    parsed_url = urlparse.urlparse(url)
    
    if "youtube.com" in parsed_url.netloc:
        # extract the video ID from the 'v' query parameter
        video_id = urlparse.parse_qs(parsed_url.query).get('v')
        
        if video_id:
            return video_id[0]
        
    elif "youtu.be" in parsed_url.netloc:
        # extract the video ID from the path
        return parsed_url.path[1:] if parsed_url.path else None
    
    return "Unable to extract YouTube video and get text"

def get_youtube_subtitles_auto_lang(video_id):
    """
    使用 yt-dlp 获取 YouTube 视频的字幕，自动检测语言，优先简体中文，其次英文。

    Args:
        video_id (str): YouTube 视频 ID.

    Returns:
        tuple: (字幕文本, 字幕语言代码)，如果没有找到字幕则返回 (None, None).
    """

    ydl_opts = {
        'skip_download': True,
        'writesubtitles': True,
        'writeautomaticsub': True,  # 下载自动生成的字幕
        'subtitleslangs': ['all'],  # 下载所有语言的字幕
        'subtitlesformat': 'json3',
        'verbose': True,
        'no_warnings': True,
        'outtmpl': '-',
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)

            # 优先选择用户上传的字幕
            subtitles = info_dict.get('subtitles')
            
            # 如果没有用户上传的字幕，则选择自动生成的字幕
            if not subtitles:
                subtitles = info_dict.get('automatic_captions')

            if not subtitles:
                print(f"No subtitles found for video ID: {video_id}")
                return None, None

            # 优先选择简体中文
            if any(lang.startswith('zh-Hans') for lang in subtitles):
                language = next(lang for lang in subtitles if lang.startswith('zh-Hans'))
            elif 'zh-CN' in subtitles:
                language = 'zh-CN'
            elif 'zh-TW' in subtitles:
                language = 'zh-TW'
            elif 'zh' in subtitles:
                language = 'zh'
            elif 'en' in subtitles:
                language = 'en'
            else:
                # 选择第一个字幕
                language = list(subtitles.keys())[0]
                print(f"No preferred language found, using: {language}")
            
            print(f"Using language: {language}")

            subtitle_url = subtitles[language][0]['url']
            subtitle_info = ydl.extract_info(subtitle_url, download=False)

            subtitle_data = subtitle_info['subtitles'][language][0]

            if subtitle_data['ext'] == 'json3':
                subtitle_json_str = ydl.urlopen(subtitle_url).read().decode('utf-8')
                subtitle_json = json.loads(subtitle_json_str)

                if 'events' not in subtitle_json:
                    print(f"No 'events' found in json3 for video ID: {video_id} in language: {language}")
                    return None, None

                paragraphs = []
                current_paragraph = ""
                for event in subtitle_json['events']:
                    if 'segs' in event:
                        for seg in event['segs']:
                            if 'utf8' in seg:
                                current_paragraph += seg['utf8'].strip() + " "

                paragraphs.append(current_paragraph.strip())
                
                return "\n\n".join(paragraphs), language
            else:
                print(f"Unsupported subtitle format: {subtitle_data['ext']}")
                return None, None

    except yt_dlp.DownloadError as e:
        print(f"Error downloading subtitles: {e}")
        return None, None
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return None, None

def get_group_name(group_id):
    """
    通过 API 获取指定 group_id 的 groupName。
    """
    url = 'https://chat-web-go.jwzhd.com/v1/group/group-info'
    data = {"groupId": group_id}
    response = requests.post(url, json=data)
    if response.status_code == 200:
        try:
            result = response.json()
            if result['code'] == 1:
                return result['data']['group']['name']
        except Exception as e:
            print(f"解析群聊信息失败：{e}")
    return '未知群名'  # 如果获取失败，则返回 "未知群名"
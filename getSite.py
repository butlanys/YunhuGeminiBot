import requests
from log import *
from playwright.sync_api import sync_playwright, Error as PlaywrightError

def get_search_urls(text):
    # 使用 google 搜索引擎获取url
    search_url = f"https://search.butlanys.de/search?engine=Google&format=json&q={text}"
    response = requests.get(search_url)
    if response.status_code == 200:
        search_results = response.json()
        urls = [result['url'] for result in search_results['results'][:5]]
        return urls
    else:
        return None

def get_clean_text(url):
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                proxy={
                    "server": "http://127.0.0.1:34314"
                    #"server": "http://alicehk:eAKr7dUT4C@127.0.0.1:34314"
                    #"server": "socks5://alice:alicefofo123..@@hkhome.kvm.one:40000"
                }
            )
            page = browser.new_page(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36 Edg/132.0.0.0'
            )
            page.goto(url)

            # 改进的文本提取方法
            page_text = page.evaluate('''() => {
                const excludeTags = ['script', 'style', 'head', 'meta', 'link', 'svg', 'img'];

                // 递归提取文本，避免重复
                function extractText(element) {
                    // 检查element是否存在且是元素节点
                    if (!element || element.nodeType !== Node.ELEMENT_NODE) {
                        return '';
                    }

                    // 跳过不需要的标签
                    const tagName = element.tagName ? element.tagName.toLowerCase() : '';
                    if (excludeTags.includes(tagName)) {
                        return '';
                    }

                    // 收集子节点文本
                    let text = '';
                    for (let child of element.childNodes) {
                        if (child.nodeType === Node.TEXT_NODE) {
                            text += child.textContent.trim() + ' ';
                        } else if (child.nodeType === Node.ELEMENT_NODE) {
                            text += extractText(child) + ' ';
                        }
                    }

                    return text.trim();
                }

                // 从body提取文本
                return extractText(document.body)
                    .replace(/\s+/g, ' ')  // 替换多个空白字符为单个空格
                    .trim();
            }''')

            browser.close()
            return page_text
    except PlaywrightError as e:
        error_logger.error(f"访问URL {url} 时出错: {e}")
        # 在这里可以根据需要进行错误处理，例如返回空字符串或者记录错误日志
        # return f"访问URL {url} 时出错: {e}"
    except Exception as e:
        error_logger.error(f"处理URL {url} 时发生其他错误: {e}")
        # return f"处理URL {url} 时发生其他错误: {e}"
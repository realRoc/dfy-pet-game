"""调 DeepSeek 对话接口。桌宠的聊天框和 IM 机器人（im/）共用这一份。

只发一次请求、把出错变成一句能直接冒泡的短话；历史、人设、截断都由调用方自己管。
不 import Qt，后台线程里随便调。"""
import requests

DS_BASE_URL = "https://api.deepseek.com/v1"
DS_MODEL = "deepseek-chat"


class LLMError(Exception):
    """str(e) 是给人看的短句（「请求超时，检查网络」），不含 Key。"""


def chat(key, messages, max_tokens=100, temperature=0.9, json_mode=False, timeout=10):
    """messages 是 OpenAI 格式的列表，返回回复文字（去掉首尾空白）。失败抛 LLMError。"""
    if not key:
        raise LLMError("还没设置 DeepSeek Key")
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    payload = {"model": DS_MODEL, "messages": messages, "max_tokens": max_tokens, "temperature": temperature}
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    try:
        resp = requests.post(f"{DS_BASE_URL}/chat/completions", json=payload, headers=headers, timeout=timeout)
    except requests.exceptions.Timeout:
        raise LLMError("请求超时，检查网络") from None
    except requests.exceptions.ConnectionError:
        raise LLMError("连接失败，检查网络") from None
    except Exception as e:
        raise LLMError(f"请求失败: {str(e)[:12]}") from None
    if resp.status_code != 200:
        try:
            msg = resp.json().get("error", {}).get("message", "")
        except ValueError:
            msg = ""
        print(f"[DeepSeek] 状态码: {resp.status_code}, 返回: {resp.text[:300]}")
        raise LLMError(f"API错误: {(msg or str(resp.status_code))[:12]}")
    try:
        return (resp.json()["choices"][0]["message"]["content"] or "").strip()
    except (ValueError, KeyError, IndexError, TypeError):
        raise LLMError("API 返回看不懂") from None

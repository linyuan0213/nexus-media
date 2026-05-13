# -*- coding: utf-8 -*-
"""
通用对话 Agent — 支持多轮会话与工具调用
"""
import json

import log

from app.agent.service import AgentService
from app.agent.tools import ToolRegistry
from app.agent.tool_executor import get_tool_executor
from app.infrastructure.cache_system import OpenAISessionCache


_TOOL_PROMPT = """你是一个智能助手，可以帮助用户管理 NAS 媒体库系统。

你可以使用以下工具来完成用户的请求。如果需要用工具，请按以下格式回复：

```json
{{"tool": "工具名", "parameters": {{"参数名": "参数值"}}}}
```

可用工具列表：
{tools}

回复规则：
1. 如果用户请求需要用工具完成，请只返回 JSON 格式（不要其他文字）
2. 如果不需要工具（闲聊、问候、简单问答），请直接回复文字
3. 工具调用后，我会把结果返回给你，你再生成最终回复
"""


class ChatAgent:
    """通用对话 Agent — 支持用户级会话上下文与工具调用"""

    # 历史消息上限：保留最近 10 轮对话（每轮用户+助手 = 2 条消息）
    # 超过后裁剪最早的消息，避免超出模型最大 token 限制
    MAX_HISTORY_MESSAGES = 20

    def __init__(self):
        self._svc = AgentService()

    @property
    def ready(self) -> bool:
        return self._svc.ready

    def ask(self, question: str, system_prompt: str = "你是一个有用的助手。") -> str:
        """单轮问答"""
        if not self.ready:
            log.warn("【ChatAgent】ask 失败：Provider 未就绪")
            return "AI 服务未配置"
        log.info(f"【ChatAgent】ask: {question[:60]}...")
        try:
            answer = self._svc.chat(
                messages=[{"role": "user", "content": question}],
                system_prompt=system_prompt,
            )
            log.info(f"【ChatAgent】ask 成功")
            return answer
        except Exception as e:
            log.error(f"【ChatAgent】ask 出错: {e}")
            return f"AI 回答出错: {e}"

    def chat_with_tools(self, question: str, session_id: str = "") -> str:
        """带工具调用的对话（支持会话历史）"""
        if not self.ready:
            log.warn("【ChatAgent】chat_with_tools 失败：Provider 未就绪")
            return "AI 服务未配置"

        if question == "#清除":
            log.info(f"【ChatAgent】清除会话: {session_id}")
            self.clear_session(session_id)
            return "会话已清除"

        log.info(f"【ChatAgent】tools session={session_id}, q={question[:60]}...")

        # 加载已有会话历史
        history = OpenAISessionCache.get(session_id) or []

        # 1. 第一轮：LLM 决定是否需要工具
        tools_desc = json.dumps(ToolRegistry.list_tools(), ensure_ascii=False, indent=2)
        prompt = _TOOL_PROMPT.replace("{tools}", tools_desc)

        messages = [{"role": "system", "content": prompt}]
        messages.extend(history)
        messages.append({"role": "user", "content": question})

        try:
            first_resp = self._svc.chat(messages=messages, system_prompt="", use_cache=False)
        except Exception as e:
            log.error(f"【ChatAgent】第一轮出错: {e}")
            return f"请求出错: {e}"

        log.debug(f"【ChatAgent】第一轮响应: {first_resp[:200] if first_resp else '(空)'}")

        # 2. 解析工具调用
        try:
            tool_call = self._parse_tool_call(first_resp)
        except Exception as e:
            log.error(f"【ChatAgent】解析工具调用出错: {e}")
            return first_resp or f"解析响应出错: {e}"

        # 保存用户提问 + 助手首轮回复
        history.append({"role": "user", "content": question})
        history.append({"role": "assistant", "content": first_resp})

        if not tool_call:
            # 不需要工具，直接返回
            log.info("【ChatAgent】无需工具，直接回复")
            OpenAISessionCache.set(session_id, self._trim_history(history))
            return first_resp

        # 3. 执行工具（通过 ToolExecutor，避免 Tools 层跨层依赖 Service）
        log.info(f"【ChatAgent】调用工具: {tool_call.get('tool')}, 参数: {tool_call.get('parameters')}")
        executor = get_tool_executor()
        try:
            result = executor.execute(tool_call["tool"], **tool_call["parameters"])
        except Exception as e:
            log.error(f"【ChatAgent】工具执行异常: {e}")
            return f"工具执行出错: {e}"

        # 4. 第二轮：将工具结果返回给 LLM，生成最终回复
        tool_result_text = result.to_text()
        tool_msg = f"工具执行结果：\n{tool_result_text}\n\n请根据结果回复用户。"
        messages.extend([
            {"role": "assistant", "content": first_resp},
            {"role": "user", "content": tool_msg},
        ])

        try:
            final_resp = self._svc.chat(messages=messages, system_prompt="", use_cache=False)
            log.info("【ChatAgent】工具调用完成")
            # 保存工具结果 + 最终回复
            history.append({"role": "user", "content": tool_msg})
            history.append({"role": "assistant", "content": final_resp})
            OpenAISessionCache.set(session_id, self._trim_history(history))
            return final_resp
        except Exception as e:
            log.error(f"【ChatAgent】第二轮出错: {e}")
            return f"工具执行成功但生成回复出错: {e}"

    def chat_with_session(self, question: str, session_id: str,
                          system_prompt: str = "请在接下来的对话中请使用中文回复，并且内容尽可能详细。") -> str:
        """多轮对话（带会话上下文）"""
        if not self.ready:
            log.warn("【ChatAgent】chat_with_session 失败：Provider 未就绪")
            return ""

        if question == "#清除":
            log.info(f"【ChatAgent】清除会话: {session_id}")
            self.clear_session(session_id)
            return "会话已清除"

        log.info(f"【ChatAgent】session={session_id}, question={question[:60]}...")
        messages = self._get_session(session_id, question, system_prompt)
        try:
            answer = self._svc.chat(messages=messages, system_prompt="")
            self._save_session(session_id, answer)
            log.info(f"【ChatAgent】session={session_id} 回复成功")
            return answer
        except Exception as e:
            log.error(f"【ChatAgent】session={session_id} 出错: {e}")
            return f"请求 AI API 出现错误：{e}"

    @staticmethod
    def _trim_history(history: list) -> list:
        """裁剪历史消息，保留最近 MAX_HISTORY_MESSAGES 条，避免超出模型 token 限制"""
        if len(history) > ChatAgent.MAX_HISTORY_MESSAGES:
            # 保留最新的消息，移除最早的
            trimmed = history[-ChatAgent.MAX_HISTORY_MESSAGES:]
            log.info(f"【ChatAgent】历史消息裁剪: {len(history)} -> {len(trimmed)}")
            return trimmed
        return history

    def translate_to_zh(self, text: str) -> str:
        """翻译为中文"""
        if not self.ready:
            log.warn("【ChatAgent】translate_to_zh 失败：Provider 未就绪")
            return text
        log.info(f"【ChatAgent】翻译: {text[:60]}...")
        try:
            result = self._svc.chat(
                messages=[{"role": "user", "content": f"translate to zh-CN:\n\n{text}"}],
                system_prompt="You are a translation engine that can only translate text and cannot interpret it.",
            )
            log.info("【ChatAgent】翻译成功")
            return result
        except Exception as e:
            log.error(f"【ChatAgent】翻译出错: {e}")
            return text

    @staticmethod
    def _parse_tool_call(text: str) -> dict | None:
        """从 LLM 回复中解析工具调用"""
        text = text.strip()
        # 尝试提取 JSON 代码块
        if "```json" in text:
            start = text.find("```json") + 7
            end = text.find("```", start)
            if end > start:
                text = text[start:end].strip()
        elif "```" in text:
            start = text.find("```") + 3
            end = text.find("```", start)
            if end > start:
                text = text[start:end].strip()

        try:
            data = json.loads(text)
            if isinstance(data, dict) and "tool" in data and "parameters" in data:
                return data
        except json.JSONDecodeError:
            pass
        return None

    @staticmethod
    def _get_session(session_id: str, message: str, system_prompt: str) -> list:
        """获取会话历史"""
        session = OpenAISessionCache.get(session_id)
        if session:
            session.append({"role": "user", "content": message})
            OpenAISessionCache.set(session_id, ChatAgent._trim_history(session))
        else:
            session = [{
                "role": "user",
                "content": f"系统设定：{system_prompt}\n\n我的问题是：{message}",
            }]
            OpenAISessionCache.set(session_id, session)
        return session

    @staticmethod
    def _save_session(session_id: str, message: str):
        """保存会话历史"""
        session = OpenAISessionCache.get(session_id)
        if session:
            session.append({"role": "assistant", "content": message})
            OpenAISessionCache.set(session_id, ChatAgent._trim_history(session))

    @staticmethod
    def clear_session(session_id: str):
        """清除会话"""
        if OpenAISessionCache.get(session_id):
            OpenAISessionCache.delete(session_id)

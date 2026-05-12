# -*- coding: utf-8 -*-
"""通用对话 Agent — 支持多轮会话"""
import log

from app.agent.service import AgentService
from app.infrastructure.cache_system import OpenAISessionCache


class ChatAgent:
    """通用对话 Agent — 支持用户级会话上下文"""

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
    def _get_session(session_id: str, message: str, system_prompt: str) -> list:
        """获取会话历史"""
        session = OpenAISessionCache.get(session_id)
        if session:
            session.append({"role": "user", "content": message})
        else:
            session = [{
                "role": "user",
                "content": f"系统设定：{system_prompt}\n\n我的问题是：{message}",
            }]
            OpenAISessionCache.set(session_id, session)
        return session

    @staticmethod
    def _save_session(session_id: str, message: str):
        """保存助手回复到会话"""
        session = OpenAISessionCache.get(session_id)
        if session:
            session.append({"role": "assistant", "content": message})
            OpenAISessionCache.set(session_id, session)

    @staticmethod
    def clear_session(session_id: str):
        """清除会话"""
        if OpenAISessionCache.get(session_id):
            OpenAISessionCache.delete(session_id)

"""问题回答 Agent — 用于选择题等场景"""

import log


class QuestionAnswerAgent:
    """问题回答 Agent — 选择题、判断题等"""

    def __init__(self, svc):

        self._svc = svc

    @property
    def ready(self) -> bool:
        return self._svc.ready

    def answer(self, question: str) -> str:
        """回答问题，返回最简洁的答案"""
        if not self.ready:
            log.warn("[QuestionAnswerAgent]answer 失败：Provider 未就绪")
            return ""
        log.info(f"[QuestionAnswerAgent]答题: {question[:60]}...")
        try:
            answer = self._svc.chat(
                messages=[{"role": "user", "content": question}],
                system_prompt=(
                    "下面我们来玩一个游戏，你是老师，我是学生，你需要回答我的问题。"
                    "我会给你一个题目和几个选项，你的回复必须是给定选项中正确答案对应的序号，请直接回复数字。"
                ),
            )
            log.info(f"[QuestionAnswerAgent]答案: {answer}")
            return answer
        except Exception as e:
            log.error(f"[QuestionAnswerAgent]答题出错: {e}")
            return ""

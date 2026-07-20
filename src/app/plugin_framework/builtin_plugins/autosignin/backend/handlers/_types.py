import json
import os
import random
import re
from typing import Any, cast

from lxml import etree

from app.agent.agents.question_answer import QuestionAnswerAgent
from app.infrastructure.http.auth import CookieAuth
from app.plugin_framework.builtin_plugins.autosignin.backend.handlers.base import (
    SigninResult,
    SiteSigninContext,
    SiteSigninHandler,
)
from app.utils.json_utils import JsonUtils
from app.utils.path_utils import get_temp_path


class BakatestQaHandler(SiteSigninHandler):
    _sign_regex = ["今天已经签过到了"]
    _success_regex = ["\\d+点魔力值"]
    _name: str = ""

    def __init__(self, plugin_ctx, rate_limiter=None, agent_service=None):
        super().__init__(plugin_ctx, rate_limiter)
        self._agent_service = agent_service

    @property
    def _answer_file(self) -> str:
        answer_path = os.path.join(get_temp_path(), "signin")
        return os.path.join(answer_path, f"{self._name}.json")

    def signin(self, ctx: SiteSigninContext) -> SigninResult:
        site = ctx.site
        signurl = ctx.site_url
        cookie = ctx.cookie
        ua = ctx.ua

        if not os.path.exists(os.path.dirname(self._answer_file)):
            os.makedirs(os.path.dirname(self._answer_file), exist_ok=True)

        client = self._http_client(ctx)
        try:
            index_res = client.get(
                url=signurl,
                headers={"User-Agent": ua} if ua else None,
                cookies=CookieAuth._parse_cookies(cookie),
            )
        except Exception:
            return SigninResult.fail(site, SigninResult.SITE_UNREACHABLE)

        if cookie_result := self._check_cookie(index_res.text, site):
            return cookie_result

        if self.sign_in_result(html_res=index_res.text, regexs=self._sign_regex):
            return SigninResult.already(site)

        html = etree.HTML(index_res.text)
        if not html:
            return SigninResult.fail(site, "签到失败")

        qid_nodes = cast(list[Any], html.xpath("//input[@name='questionid']/@value"))
        opt_nodes = cast(list[Any], html.xpath("//input[@name='choice[]']/@value"))
        opt_texts = cast(list[Any], html.xpath("//input[@name='choice[]']/following-sibling::text()"))
        question_nodes = cast(list[Any], html.xpath("//td[@class='text' and contains(text(),'请问：')]/text()"))
        if not qid_nodes or not opt_nodes or not question_nodes:
            return SigninResult.fail(site, "未获取到签问题目，可能已签到或页面变更")
        questionid = str(qid_nodes[0])
        option_ids = [str(v) for v in opt_nodes]
        option_values = [str(v) for v in opt_texts]
        question_str = str(question_nodes[0])
        answers = list(zip(option_ids, option_values, strict=False))

        match = re.search(r"请问：(.+)", str(question_str))
        if not match:
            return SigninResult.fail(site, "未获取到签到问题")
        question_str = match.group(1)
        self._plugin_ctx.debug(f"获取到签到问题 {question_str}")

        choice = self._lookup_local_answer(question_str, answers)
        if choice:
            return self._do_signin(questionid, choice, ctx)

        choice = [option_ids[random.randint(0, len(option_ids) - 1)]]
        ai_question = self._build_ai_question(question_str, answers)
        self._plugin_ctx.debug(f"组装AI问题 {ai_question}")

        answer = QuestionAnswerAgent(svc=self._agent_service).answer(ai_question)
        self._plugin_ctx.debug(f"AI返回结果 {answer}")

        if answer:
            answer_nums = list(map(int, re.findall(r"\d+", answer)))
            if answer_nums:
                new_choice = []
                for a in answer_nums:
                    if str(a) in [str(o) for o in option_ids]:
                        new_choice.append(int(a))
                        self._plugin_ctx.info(f"AI返回答案id {a} 在签到选项 {option_ids} 中")
                if new_choice:
                    choice = new_choice
                else:
                    self._plugin_ctx.warn(f"无法从AI回复 {answer} 中获取答案, 将采用随机签到")
        else:
            self._plugin_ctx.warn("AI未启用, 开始随机签到")

        return self._do_signin(questionid, choice, ctx, question=question_str)

    def _lookup_local_answer(self, question_str: str, answers: list) -> list:
        try:
            with open(self._answer_file) as f:
                existing_answers = JsonUtils.loads(f.read())
            question_answer = existing_answers.get(question_str)
            if not question_answer:
                return []
            if not isinstance(question_answer, list):
                question_answer = [question_answer]
            choice = []
            for q in question_answer:
                for num, _ in answers:
                    if str(q) == str(num):
                        choice.append(int(q))
            return choice
        except (FileNotFoundError, OSError, json.JSONDecodeError, KeyError):
            return []

    @staticmethod
    def _build_ai_question(question_str: str, answers: list) -> str:
        ai_options = "{\n" + ",\n".join([f"{num}:{value}" for num, value in answers]) + "\n}"
        return f"题目：{question_str}\n选项：{ai_options}"

    def _do_signin(self, questionid, choice, ctx: SiteSigninContext, question=None):
        site = ctx.site
        cookie = ctx.cookie
        ua = ctx.ua
        signurl = ctx.site_url

        data = {
            "questionid": questionid,
            "choice[]": choice[0] if len(choice) == 1 else choice,
            "usercomment": "太难了！",
            "wantskip": "不会",
        }

        client = self._http_client(ctx)
        try:
            sign_res = client.post(
                url=signurl,
                data=data,
                headers={"User-Agent": ua} if ua else None,
                cookies=CookieAuth._parse_cookies(cookie),
            )
        except Exception:
            return SigninResult.fail(site, SigninResult.REQUEST_FAILED)

        if self.sign_in_result(html_res=sign_res.text, regexs=self._success_regex):
            if question and choice:
                self._write_local_answer(question, choice)
            return SigninResult.success(site)

        if self.sign_in_result(html_res=sign_res.text, regexs=self._sign_regex):
            return SigninResult.already(site)

        return SigninResult.fail(site, "请到页面查看")

    def _write_local_answer(self, question: str, answer: list):
        existing_answers: dict = {}
        try:
            with open(self._answer_file) as f:
                existing_answers = JsonUtils.loads(f.read())
        except (FileNotFoundError, OSError):
            pass
        try:
            existing_answers[question] = answer
            with open(self._answer_file, "w") as f:
                f.write(JsonUtils.dumps(existing_answers, indent=4))
        except (FileNotFoundError, OSError):
            pass

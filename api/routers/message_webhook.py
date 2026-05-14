"""
消息客户端 Webhook Router
处理 Telegram / WeChat / SynologyChat / Slack 等消息平台的回调
"""

import asyncio

from fastapi import APIRouter, HTTPException, Request, status

import log
from app.message import Message
from app.services.apikey_service import APIKeyService
from app.services.search_message_service import MessageSearchService
from app.services.system_service import MessageCommandHandler
from app.utils.types import SearchType

router = APIRouter()


_MESSAGE_INITIALIZED = False


def _ensure_message_initialized():
    """确保消息客户端已初始化（懒加载触发）"""
    global _MESSAGE_INITIALIZED
    if not _MESSAGE_INITIALIZED:
        _ = Message().active_clients
        _MESSAGE_INITIALIZED = True


def _verify_apikey(request: Request):
    """验证 API Key（使用数据库管理的 API Key）"""
    api_key = request.query_params.get("apikey") or request.query_params.get("api_key")
    if not api_key:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Missing API Key")

    service = APIKeyService()
    key = service.validate_key(api_key)
    if not key:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid API Key")


def _get_user_id_from_update(update: dict, channel: SearchType) -> str:
    """从各平台消息中提取用户ID"""
    if channel == SearchType.TG:
        msg = update.get("message") or update.get("edited_message", {})
        user = msg.get("from", {})
        return str(user.get("id", ""))
    if channel == SearchType.WX:
        return update.get("FromUserName", "")
    if channel == SearchType.SYNOLOGY:
        return update.get("user_id", "")
    if channel == SearchType.SLACK:
        return update.get("user", "")
    return ""


def _get_text_from_update(update: dict, channel: SearchType) -> str:
    """从各平台消息中提取文本"""
    if channel == SearchType.TG:
        msg = update.get("message") or update.get("edited_message", {})
        text = msg.get("text", "")
        # 处理命令（如 /start）
        if text.startswith("/"):
            entities = msg.get("entities", [])
            for ent in entities:
                if ent.get("type") == "bot_command":
                    offset = ent.get("offset", 0)
                    length = ent.get("length", 0)
                    text = text[offset : offset + length]
                    break
        return text
    if channel == SearchType.WX:
        return update.get("Content", "")
    if channel == SearchType.SYNOLOGY:
        return update.get("text", "")
    if channel == SearchType.SLACK:
        # Slack 消息可能 text 为空，用 blocks 或 command
        text = update.get("text", "")
        if not text:
            text = update.get("command", "")
        return text
    return ""


def _handle_webhook(update: dict, channel: SearchType):
    """统一处理各平台 webhook"""
    _ensure_message_initialized()

    user_id = _get_user_id_from_update(update, channel)
    text = _get_text_from_update(update, channel)
    if not text:
        return {"ok": True}

    log.info(f"【Webhook】{channel.value} 收到消息: user={user_id}, text={text[:60]}...")

    search_handler = MessageSearchService()
    handler = MessageCommandHandler(search_handler=search_handler)
    handler.handle_message_job(msg=text, in_from=channel, user_id=user_id)
    return {"ok": True}


@router.post("/telegram")
async def telegram_webhook(request: Request):
    """Telegram Bot Webhook"""
    _verify_apikey(request)
    data = await request.json()
    return await asyncio.to_thread(_handle_webhook, data, SearchType.TG)


@router.post("/wechat")
async def wechat_webhook(request: Request):
    """WeChat 企业微信/公众号 Webhook"""
    _verify_apikey(request)
    data = await request.json()
    return await asyncio.to_thread(_handle_webhook, data, SearchType.WX)


@router.post("/synologychat")
async def synologychat_webhook(request: Request):
    """Synology Chat Webhook"""
    _verify_apikey(request)
    data = await request.json()
    return await asyncio.to_thread(_handle_webhook, data, SearchType.SYNOLOGY)


@router.post("/slack")
async def slack_webhook(request: Request):
    """Slack Event/Webhook"""
    _verify_apikey(request)
    data = await request.json()
    # Slack 有 URL 验证 challenge
    if data.get("type") == "url_verification":
        return {"challenge": data.get("challenge")}
    return await asyncio.to_thread(_handle_webhook, data, SearchType.SLACK)

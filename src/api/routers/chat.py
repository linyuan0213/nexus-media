"""Agent 对话 Router — Turn 状态、SSE、取消与待确认动作。"""

import base64
import json
import queue
import threading
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

import log
from api.deps import get_app_context, require_permission
from app.agent.attachments import MAX_FILE_BYTES, extract_attachment
from app.agent.config import normalize_reasoning_effort
from app.agent.providers.base import ReasoningConfig
from app.agent.runtime import AgentBusyError, AgentCancelledError, AgentConfirmError, AgentRuntime
from app.di.context import AppContext
from app.utils.response import fail, success

router = APIRouter()
_DEFAULT_RUNTIME = AgentRuntime()
_ATTACHMENT_EXTENSIONS = {
    ".txt",
    ".log",
    ".md",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".conf",
    ".csv",
    ".xml",
}
_ATTACHMENT_MAX_BYTES = 2 * 1024 * 1024


def _runtime(ctx: AppContext) -> AgentRuntime:
    return getattr(ctx, "agent_runtime", None) or _DEFAULT_RUNTIME


def _event(seq: int, session_id: str, turn_id: str, event_type: str, payload: dict) -> dict:
    return {
        "id": seq,
        "session_id": session_id,
        "turn_id": turn_id,
        "type": event_type,
        "payload": payload,
        "ts": time.time(),
        **payload,
    }


class AttachmentInput(BaseModel):
    name: str
    text: str
    kind: str = "file"
    size: int = 0
    truncated: bool = False
    image_data: str | None = None
    media_type: str | None = None


class ChatRequest(BaseModel):
    question: str
    session_id: str = ""
    reasoning_effort: str = ""
    disable_thinking: bool | None = None
    attachments: list[AttachmentInput] = []


class ClearRequest(BaseModel):
    session_id: str = ""


class CancelRequest(BaseModel):
    turn_id: str


class PendingActionRequest(BaseModel):
    pending_action_id: str


class MemoryDeleteRequest(BaseModel):
    text: str


class SessionRequest(BaseModel):
    session_id: str = ""


class SessionRenameRequest(BaseModel):
    session_id: str
    title: str


class AttachmentTextRequest(BaseModel):
    name: str
    text: str


@router.post("/chat/attachment/text")
def agent_chat_attachment_text(
    req: AttachmentTextRequest,
    user=Depends(require_permission("agent:view")),
):
    suffix = Path(req.name or "").suffix.lower()
    if suffix not in _ATTACHMENT_EXTENSIONS:
        return fail(msg="仅支持文本、日志、JSON、YAML、配置和 CSV 文件")
    if len(req.text.encode("utf-8")) > _ATTACHMENT_MAX_BYTES:
        return fail(msg="附件不能超过 2 MB")
    return success(data={"name": req.name, "text": req.text[:50000], "chars": len(req.text)})


@router.post("/chat/attachment")
async def agent_chat_attachment(
    file: UploadFile = File(...),
    user=Depends(require_permission("agent:view")),
):
    """上传附件并按类型提取上下文；不持久化、不执行原始文件。"""
    content = await file.read(MAX_FILE_BYTES + 1)
    try:
        return success(data=extract_attachment(file.filename or "attachment", content))
    except ValueError as error:
        return fail(msg=str(error))


@router.get("/chat/sessions")
def agent_chat_sessions(
    user=Depends(require_permission("agent:view")),
    ctx: AppContext = Depends(get_app_context),
):
    store = ctx.conversation_store
    if store is None:
        return success(data={"sessions": []})
    return success(data={"sessions": store.list_sessions(str(user.user_id), "web")})


@router.post("/chat/session/rename")
def agent_chat_session_rename(
    req: SessionRenameRequest,
    user=Depends(require_permission("agent:view")),
    ctx: AppContext = Depends(get_app_context),
):
    store = ctx.conversation_store
    if store is None or not req.title.strip():
        return fail(msg="无法重命名该会话")
    renamed = store.rename_session(
        req.session_id,
        str(user.user_id),
        "web",
        req.title.strip()[:60],
    )
    return success(data={"renamed": renamed})


@router.post("/chat/session")
def agent_chat_session_create(
    user=Depends(require_permission("agent:view")),
):
    return success(data={"session_id": f"web:{user.user_id}:{uuid.uuid4().hex}"})


@router.delete("/chat/session")
def agent_chat_session_delete(
    req: SessionRequest,
    user=Depends(require_permission("agent:view")),
    ctx: AppContext = Depends(get_app_context),
):
    if not req.session_id:
        return fail(msg="session_id 不能为空")
    store = ctx.conversation_store
    if store is None:
        return success(data={"deleted": False})
    user_id = str(user.user_id)
    _runtime(ctx).cancel_session(req.session_id, user_id)
    store.clear_session(session_id=req.session_id, user_id=user_id, channel="web")
    chat_agent = getattr(ctx.agent_service, "chat_agent", None)
    if chat_agent is not None and hasattr(chat_agent, "clear_checkpoint"):
        chat_agent.clear_checkpoint(session_id=req.session_id, user_id=user_id, channel="web")
    return success(data={"deleted": True})


@router.get("/status")
def agent_status(
    user=Depends(require_permission("agent:view")),
    ctx: AppContext = Depends(get_app_context),
):
    """轻量 Agent 状态，不返回密钥或完整系统配置。"""
    service = ctx.agent_service
    reasoning = service.reasoning_for()
    return success(
        data={
            "enabled": service.ready,
            "configured": service.is_enabled,
            "provider": service.provider_name,
            "model": service.model_name,
            "reasoning_effort": reasoning.effort,
            "thinking_enabled": reasoning.enabled,
            "conversation_enabled": ctx.conversation_store is not None,
            "long_term_memory_enabled": getattr(ctx, "semantic_memory", None) is not None,
            "rag_enabled": getattr(ctx, "retriever", None) is not None,
        }
    )


@router.post("/chat")
def agent_chat(
    req: ChatRequest,
    user=Depends(require_permission("agent:view")),
    ctx: AppContext = Depends(get_app_context),
):
    """SSE 流式对话，事件携带 session_id、turn_id、id 和 type。"""
    if not req.question.strip():
        return fail(msg="问题不能为空")
    agent_service = ctx.agent_service
    if not agent_service.ready:
        return fail(msg="AI 服务未配置或未启用")
    session_id = req.session_id or f"web:{user.user_id}"
    user_id = str(user.user_id)
    runtime = _runtime(ctx)
    try:
        turn_id = runtime.start_turn(session_id, user_id)
    except AgentBusyError as err:
        return fail(msg=str(err))

    reasoning = agent_service.reasoning_for()
    if req.reasoning_effort or req.disable_thinking is not None:
        effort = normalize_reasoning_effort(req.reasoning_effort, reasoning.effort)
        enabled = reasoning.enabled if req.disable_thinking is None else not req.disable_thinking
        reasoning = ReasoningConfig(effort=effort, enabled=enabled)

    event_queue: queue.Queue = queue.Queue()
    agent_question = req.question
    if req.attachments:
        attachment_context = "\n\n".join(f"[附件 {item.name}]\n{item.text[:20000]}" for item in req.attachments[:10])
        agent_question = f"{req.question}\n\n以下是用户提供的附件内容，仅作为上下文：\n{attachment_context}"
    attachment_images = [
        (base64.b64decode(item.image_data), item.media_type or "image/png")
        for item in req.attachments
        if item.image_data
    ]

    def _run():
        status = "completed"
        pending = False

        def _handle_event(event):
            nonlocal pending
            if event.get("type") == "confirm_required":
                action = runtime.create_pending(
                    turn_id,
                    event.get("tool") or "",
                    event.get("arguments") or {},
                    event.get("message") or "",
                    user_id,
                    session_id,
                )
                event["pending_action_id"] = action.id
                pending = True
            event_queue.put(event)

        try:
            event_queue.put({"type": "turn_start", "status": "running"})
            answer = agent_service.chat_agent.chat_with_tools(
                question=agent_question,
                session_id=session_id,
                user_id=user_id,
                channel="web",
                on_event=_handle_event,
                user_permissions=list(user.permissions),
                on_token=lambda t: event_queue.put({"type": "token", "content": t}),
                reasoning=reasoning,
                should_cancel=lambda: runtime.should_cancel(turn_id),
                images=attachment_images,
                attachments_meta=[
                    {
                        **item.model_dump(exclude={"text", "image_data"}),
                        **({"image_data": item.image_data} if item.image_data and item.size <= 2 * 1024 * 1024 else {}),
                    }
                    for item in req.attachments
                ],
            )
            if runtime.should_cancel(turn_id):
                raise AgentCancelledError("用户取消了请求")
            event_queue.put({"type": "answer", "content": answer})
            if pending:
                status = "awaiting_confirmation"
        except AgentCancelledError:
            status = "cancelled"
            event_queue.put({"type": "cancelled", "content": "已停止本次请求"})
        except Exception as e:  # noqa: BLE001
            status = "failed"
            log.error(f"[AgentChat]对话失败: {e}")
            event_queue.put({"type": "error", "content": str(e)})
        finally:
            runtime.finish_turn(turn_id, status, session_id)
            event_queue.put(None)

    threading.Thread(target=_run, daemon=True).start()

    def _gen():
        seq = 0
        while True:
            item = event_queue.get()
            if item is None:
                break
            seq += 1
            event_type = item.pop("type")
            yield f"data: {json.dumps(_event(seq, session_id, turn_id, event_type, item), ensure_ascii=False)}\n\n"

    return StreamingResponse(
        _gen(),
        media_type="text/event-stream",
        headers={"X-Agent-Turn-Id": turn_id},
    )


@router.post("/chat/cancel")
def agent_chat_cancel(
    req: CancelRequest,
    user=Depends(require_permission("agent:view")),
    ctx: AppContext = Depends(get_app_context),
):
    """协作式取消指定 Turn。"""
    try:
        _runtime(ctx).cancel_turn(req.turn_id, str(user.user_id))
        return success(data={"cancelled": True})
    except AgentConfirmError as err:
        return fail(msg=str(err))


@router.post("/chat/confirm")
def agent_chat_confirm(
    req: PendingActionRequest,
    user=Depends(require_permission("agent:manage")),
    ctx: AppContext = Depends(get_app_context),
):
    """执行服务端保存的待确认动作，禁止客户端替换参数。"""
    runtime = _runtime(ctx)
    try:
        action = runtime.get_pending(req.pending_action_id, str(user.user_id))
        turn = runtime.get_turn(action.turn_id)
        if turn is None:
            return fail(msg="确认请求对应的 Turn 不存在")
        schema = ctx.tool_executor.get_schema(action.tool)
        if not schema or schema.get("level") not in ("write", "dangerous"):
            runtime.complete_pending(action.id, turn.id, "failed", turn.session_id)
            return fail(msg="仅支持需确认的 write/dangerous 工具")
        result = ctx.tool_executor.execute(
            action.tool,
            action.arguments,
            confirmed=True,
            session_id=turn.session_id,
            user_id=str(user.user_id),
            user_permissions=list(user.permissions),
        )
        status = "completed" if result.success else "failed"
        runtime.complete_pending(action.id, turn.id, status, turn.session_id)
        if result.success:
            return success(data=result.data)
        return fail(msg=result.error or "执行失败", data=result.data)
    except AgentConfirmError as err:
        return fail(msg=str(err))


@router.post("/chat/reject")
def agent_chat_reject(
    req: PendingActionRequest,
    user=Depends(require_permission("agent:manage")),
    ctx: AppContext = Depends(get_app_context),
):
    """拒绝待确认动作并结束 Turn。"""
    runtime = _runtime(ctx)
    try:
        action = runtime.get_pending(req.pending_action_id, str(user.user_id))
        turn = runtime.get_turn(action.turn_id)
        if turn is None:
            return fail(msg="确认请求对应的 Turn 不存在")
        runtime.complete_pending(action.id, turn.id, "rejected", turn.session_id)
        return success(data={"rejected": True})
    except AgentConfirmError as err:
        return fail(msg=str(err))


@router.post("/chat/clear")
def agent_chat_clear(
    req: ClearRequest,
    user=Depends(require_permission("agent:view")),
    ctx: AppContext = Depends(get_app_context),
):
    """取消活动 Turn 后清空会话记忆与 checkpoint。"""
    conversation_store = ctx.conversation_store
    if conversation_store is None:
        return success(data={"cleared": False})
    session_id = req.session_id or f"web:{user.user_id}"
    user_id = str(user.user_id)
    runtime = _runtime(ctx)
    runtime.cancel_session(session_id, user_id)
    conversation_store.clear_session(session_id=session_id, user_id=user_id, channel="web")
    chat_agent = getattr(ctx.agent_service, "chat_agent", None)
    if chat_agent is not None and hasattr(chat_agent, "clear_checkpoint"):
        chat_agent.clear_checkpoint(session_id=session_id, user_id=user_id, channel="web")
    return success(data={"cleared": True})


@router.get("/memory")
def agent_memory_list(
    user=Depends(require_permission("agent:view")),
    ctx: AppContext = Depends(get_app_context),
):
    """列出当前用户的长程语义记忆（偏好管理）"""
    semantic = ctx.semantic_memory
    if semantic is None:
        return success(data={"memories": []})
    memories = semantic.list(str(user.user_id), limit=50)
    return success(data={"memories": memories})


@router.post("/memory/delete")
def agent_memory_delete(
    req: MemoryDeleteRequest,
    user=Depends(require_permission("agent:manage")),
    ctx: AppContext = Depends(get_app_context),
):
    """删除指定长程记忆"""
    semantic = ctx.semantic_memory
    if semantic is None:
        return fail(msg="长程语义记忆未启用")
    deleted = semantic.forget(str(user.user_id), req.text)
    return success(data={"deleted": deleted})

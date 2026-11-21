import datetime

from astrbot.api import star
from astrbot.api.event import AstrMessageEvent, MessageEventResult
from astrbot.core.platform.astr_message_event import MessageSession
from astrbot.core.platform.message_type import MessageType
from astrbot.core.utils.active_event_registry import active_event_registry

from ._compat import (
    THIRD_PARTY_AGENT_RUNNER_KEY,
    THIRD_PARTY_AGENT_RUNNER_STR,
    clear_third_party_agent_runner_state,
    get_agent_runtime,
    get_using_provider_compat,
    is_event_admin,
    is_unique_session_enabled,
    mark_clean_group_context,
    resolve_selected_persona_compat,
    update_conversation_title_compat,
    uses_session_override_persona,
)


def _format_persona_name(
    persona_id: str | None,
    force_applied_persona_id: str | None = None,
) -> str:
    if persona_id == "[%None]" or not persona_id:
        persona_name = "无"
    else:
        persona_name = persona_id

    if force_applied_persona_id:
        persona_name = f"{persona_name} (自定义规则)"
    return persona_name


class ConversationCommands:
    def __init__(self, context: star.Context) -> None:
        self.context = context

    async def _get_current_persona_id(self, session_id):
        curr = await self.context.conversation_manager.get_curr_conversation_id(
            session_id,
        )
        if not curr:
            return None
        conv = await self.context.conversation_manager.get_conversation(
            session_id,
            curr,
        )
        if not conv:
            return None
        return conv.persona_id

    async def _resolve_session_persona_name(
        self,
        umo: str,
        platform_name: str,
        provider_settings: dict,
    ) -> str | None:
        if not uses_session_override_persona(self.context):
            return None
        (
            session_persona_id,
            _,
            _,
            _,
            _,
        ) = await resolve_selected_persona_compat(
            self.context,
            umo=umo,
            conversation_persona_id=None,
            platform_name=platform_name,
            provider_settings=provider_settings,
        )
        return _format_persona_name(session_persona_id)

    async def his(self, message: AstrMessageEvent, page: int = 1) -> None:
        """查看对话记录"""
        if not await get_using_provider_compat(self.context, message.unified_msg_origin):
            message.set_result(
                MessageEventResult().message("未找到任何 LLM 提供商。请先配置。"),
            )
            return

        size_per_page = 6
        page = max(1, page)

        conv_mgr = self.context.conversation_manager
        umo = message.unified_msg_origin
        session_curr_cid = await conv_mgr.get_curr_conversation_id(umo)

        if not session_curr_cid:
            session_curr_cid = await conv_mgr.new_conversation(
                umo,
                message.get_platform_id(),
            )

        contexts, total_pages = await conv_mgr.get_human_readable_context(
            umo,
            session_curr_cid,
            page,
            size_per_page,
        )

        parts = []
        for context in contexts:
            if len(context) > 150:
                context = context[:150] + "..."
            parts.append(f"{context}\n")

        history = "".join(parts)
        ret = (
            f"当前对话历史记录："
            f"{history or '无历史记录'}\n\n"
            f"第 {page} 页 | 共 {total_pages} 页\n"
            f"*输入 /history 2 跳转到第 2 页"
        )

        message.set_result(MessageEventResult().message(ret).use_t2i(False))

    async def convs(self, message: AstrMessageEvent, page: int = 1) -> None:
        """查看对话列表"""
        umo = message.unified_msg_origin
        cfg = self.context.get_config(umo=umo)
        agent_runner_type = get_agent_runtime(cfg)
        if agent_runner_type in THIRD_PARTY_AGENT_RUNNER_KEY:
            message.set_result(
                MessageEventResult().message(
                    f"{THIRD_PARTY_AGENT_RUNNER_STR} 对话列表功能暂不支持。",
                ),
            )
            return

        size_per_page = 6
        conversations_all = await self.context.conversation_manager.get_conversations(
            umo,
        )
        total_pages = (len(conversations_all) + size_per_page - 1) // size_per_page
        page = max(1, min(page, total_pages)) if total_pages > 0 else 1
        start_idx = (page - 1) * size_per_page
        end_idx = start_idx + size_per_page
        conversations_paged = conversations_all[start_idx:end_idx]

        parts = ["对话列表：\n---\n"]
        global_index = start_idx + 1

        _titles = {}
        for conv in conversations_all:
            title = conv.title if conv.title else "新对话"
            _titles[conv.cid] = title

        provider_settings = cfg.get("provider_settings", {})
        platform_name = message.get_platform_name()
        session_persona_name = await self._resolve_session_persona_name(
            umo=umo,
            platform_name=platform_name,
            provider_settings=provider_settings,
        )

        if not conversations_paged:
            parts.append("暂无对话。\n")
        else:
            for conv in conversations_paged:
                if session_persona_name is not None:
                    persona_name = session_persona_name
                else:
                    (
                        persona_id,
                        _,
                        force_applied_persona_id,
                        _,
                        _,
                    ) = await resolve_selected_persona_compat(
                        self.context,
                        umo=umo,
                        conversation_persona_id=conv.persona_id,
                        platform_name=platform_name,
                        provider_settings=provider_settings,
                    )
                    persona_name = _format_persona_name(
                        persona_id,
                        force_applied_persona_id,
                    )

                title = _titles.get(conv.cid, "新对话")
                parts.append(
                    f"{global_index}. {title}({conv.cid[:4]})\n"
                    f"  人格情景: {persona_name}\n"
                    f"  上次更新: {datetime.datetime.fromtimestamp(conv.updated_at).strftime('%m-%d %H:%M')}\n"
                )
                global_index += 1

        parts.append("---\n")
        ret = "".join(parts)
        curr_cid = await self.context.conversation_manager.get_curr_conversation_id(umo)
        if curr_cid:
            title = _titles.get(curr_cid, "新对话")
            ret += f"\n当前对话: {title}({curr_cid[:4]})"
        else:
            ret += "\n当前对话: 无"

        if session_persona_name is not None:
            ret += f"\n当前会话人格情景: {session_persona_name}"

        if is_unique_session_enabled(self.context, message):
            ret += "\n会话隔离粒度: 个人"
        else:
            ret += "\n会话隔离粒度: 群聊"

        ret += f"\n第 {page} 页 | 共 {total_pages} 页"
        ret += "\n*输入 /ls 2 跳转到第 2 页"

        message.set_result(MessageEventResult().message(ret).use_t2i(False))

    async def groupnew_conv(self, message: AstrMessageEvent, sid: str = "") -> None:
        """创建新群聊对话"""
        sid = sid.strip()
        if not sid:
            message.set_result(
                MessageEventResult().message("请输入群聊 ID。/groupnew 群聊ID。"),
            )
            return

        session = str(
            MessageSession(
                platform_name=message.platform_meta.id,
                message_type=MessageType("GroupMessage"),
                session_id=sid,
            ),
        )

        session_cfg = self.context.get_config(umo=session)
        agent_runner_type = get_agent_runtime(session_cfg)
        active_event_registry.stop_all(session, exclude=message)
        if agent_runner_type in THIRD_PARTY_AGENT_RUNNER_KEY:
            await clear_third_party_agent_runner_state(
                self.context,
                session,
                agent_runner_type,
            )

        cpersona = await self._get_current_persona_id(session)
        cid = await self.context.conversation_manager.new_conversation(
            session,
            message.get_platform_id(),
            persona_id=cpersona,
        )
        if session == message.unified_msg_origin:
            mark_clean_group_context(message)
        message.set_result(
            MessageEventResult().message(
                f"群聊 {session} 已切换到新对话: 新对话({cid[:4]})。",
            ),
        )

    async def switch_conv(
        self,
        message: AstrMessageEvent,
        index: int | None = None,
    ) -> None:
        """通过 /ls 前面的序号切换对话"""
        if index is None:
            message.set_result(
                MessageEventResult().message(
                    "请输入对话序号。/switch 对话序号。/ls 查看对话 /new 新建对话",
                ),
            )
            return

        if isinstance(index, bool) or not isinstance(index, int):
            message.set_result(
                MessageEventResult().message("类型错误，请输入数字对话序号。"),
            )
            return

        conversations = await self.context.conversation_manager.get_conversations(
            message.unified_msg_origin,
        )
        if index > len(conversations) or index < 1:
            message.set_result(
                MessageEventResult().message("对话序号错误，请使用 /ls 查看"),
            )
        else:
            conversation = conversations[index - 1]
            title = conversation.title if conversation.title else "新对话"
            active_event_registry.stop_all(message.unified_msg_origin, exclude=message)
            await self.context.conversation_manager.switch_conversation(
                message.unified_msg_origin,
                conversation.cid,
            )
            message.set_result(
                MessageEventResult().message(
                    f"切换到对话: {title}({conversation.cid[:4]})。",
                ),
            )

    async def rename_conv(self, message: AstrMessageEvent, new_name: str = "") -> None:
        """重命名对话"""
        new_name = new_name.strip()
        if not new_name:
            message.set_result(MessageEventResult().message("请输入新的对话名称。"))
            return
        updated = await update_conversation_title_compat(
            self.context,
            message.unified_msg_origin,
            new_name,
        )
        if not updated:
            message.set_result(
                MessageEventResult().message(
                    "当前未处于对话状态，请 /switch 序号 切换或 /new 创建。",
                ),
            )
            return
        message.set_result(MessageEventResult().message("重命名对话成功。"))

    async def del_conv(self, message: AstrMessageEvent) -> None:
        """删除当前对话"""
        umo = message.unified_msg_origin
        is_isolated = is_unique_session_enabled(self.context, message)
        if message.get_group_id() and not is_isolated and not is_event_admin(message):
            # 群聊，没开独立会话（或平台不支持隔离），且发送人不是管理员
            message.set_result(
                MessageEventResult().message(
                    f"会话处于群聊，并且未开启独立会话，并且您 (ID {message.get_sender_id()}) 不是管理员，因此没有权限删除当前对话。",
                ),
            )
            return

        cfg = self.context.get_config(umo=umo)
        agent_runner_type = get_agent_runtime(cfg)
        if agent_runner_type in THIRD_PARTY_AGENT_RUNNER_KEY:
            active_event_registry.stop_all(umo, exclude=message)
            await clear_third_party_agent_runner_state(
                self.context,
                umo,
                agent_runner_type,
            )
            mark_clean_group_context(message)
            message.set_result(MessageEventResult().message("重置对话成功。"))
            return

        session_curr_cid = (
            await self.context.conversation_manager.get_curr_conversation_id(umo)
        )

        if not session_curr_cid:
            message.set_result(
                MessageEventResult().message(
                    "当前未处于对话状态，请 /switch 序号 切换或 /new 创建。",
                ),
            )
            return

        active_event_registry.stop_all(umo, exclude=message)

        await self.context.conversation_manager.delete_conversation(
            umo,
            session_curr_cid,
        )

        ret = "删除当前对话成功。不再处于对话状态，使用 /switch 序号 切换到其他对话或 /new 创建。"
        mark_clean_group_context(message)
        message.set_result(MessageEventResult().message(ret))

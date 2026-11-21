from typing import TYPE_CHECKING

from astrbot.api import star
from astrbot.api.event import AstrMessageEvent, MessageEventResult

from ._compat import (
    get_profile_default_persona_name,
    get_session_overrides,
    has_session_overrides,
    lookup_persona_v3,
    resolve_selected_persona_compat,
    update_conversation_persona_compat,
)

if TYPE_CHECKING:
    from astrbot.core.db.po import Persona


class PersonaCommands:
    def __init__(self, context: star.Context) -> None:
        self.context = context

    def _build_tree_output(
        self,
        folder_tree: list[dict],
        all_personas: list["Persona"],
        depth: int = 0,
    ) -> list[str]:
        """递归构建树状输出，使用短线条表示层级"""
        lines: list[str] = []
        # 使用短线条作为缩进前缀，每层只用 "│" 加一个空格
        prefix = "│ " * depth

        for folder in folder_tree:
            # 输出文件夹
            lines.append(f"{prefix}├ 📁 {folder['name']}/")

            # 获取该文件夹下的人格
            folder_personas = [
                p for p in all_personas if p.folder_id == folder["folder_id"]
            ]
            child_prefix = "│ " * (depth + 1)

            # 输出该文件夹下的人格
            for persona in folder_personas:
                lines.append(f"{child_prefix}├ 👤 {persona.persona_id}")

            # 递归处理子文件夹
            children = folder.get("children", [])
            if children:
                lines.extend(
                    self._build_tree_output(
                        children,
                        all_personas,
                        depth + 1,
                    )
                )

        return lines

    @staticmethod
    def _extract_raw_args(message: AstrMessageEvent, args: str | None) -> str:
        if args is not None:
            return args.strip()
        parts = message.message_str.strip().split(maxsplit=1)
        return parts[1].strip() if len(parts) > 1 else ""

    async def persona(
        self,
        message: AstrMessageEvent,
        args: str | None = None,
    ) -> None:
        raw_args = self._extract_raw_args(message, args)
        umo = message.unified_msg_origin

        curr_persona_name = "无"
        cid = await self.context.conversation_manager.get_curr_conversation_id(umo)
        default_persona_name = await get_profile_default_persona_name(
            self.context,
            umo=umo,
        )
        force_applied_persona_id = None
        provider_settings = self.context.get_config(umo=umo).get(
            "provider_settings",
            {},
        )
        platform_name = message.get_platform_name()
        session_override_supported = has_session_overrides()

        curr_cid_title = "无"
        conv_persona_id: str | None = None
        if cid:
            conv = await self.context.conversation_manager.get_conversation(
                unified_msg_origin=umo,
                conversation_id=cid,
                create_if_not_exists=True,
            )
            if conv is None:
                if not session_override_supported:
                    message.set_result(
                        MessageEventResult().message(
                            "当前对话不存在，请先使用 /new 新建一个对话。",
                        ),
                    )
                    return
                cid = None
            else:
                conv_persona_id = conv.persona_id
                curr_cid_title = conv.title if conv.title else "新对话"
                curr_cid_title += f"({cid[:4]})"

        if cid or session_override_supported:
            (
                persona_id,
                _,
                force_applied_persona_id,
                _,
                is_session_override_model,
            ) = await resolve_selected_persona_compat(
                self.context,
                umo=umo,
                conversation_persona_id=conv_persona_id,
                platform_name=platform_name,
                provider_settings=provider_settings,
            )

            if persona_id == "[%None]":
                curr_persona_name = "无"
            elif persona_id:
                curr_persona_name = persona_id

            if force_applied_persona_id:
                curr_persona_name = f"{curr_persona_name} (自定义规则)"
            elif is_session_override_model:
                overrides = await get_session_overrides(umo)
                if (
                    "agent.config.persona.persona_id" in overrides
                    or "agent.config.persona_id" in overrides
                ):
                    curr_persona_name = f"{curr_persona_name} (会话覆盖)"
        else:
            is_session_override_model = False

        if not raw_args:
            inherit_line = (
                "\n- 恢复继承默认人格: `/persona --inherit`"
                if session_override_supported
                else ""
            )
            current_label = (
                f"当前会话的人格情景: {curr_persona_name}"
                if is_session_override_model
                else f"当前对话 {curr_cid_title} 的人格情景: {curr_persona_name}"
            )
            message.set_result(
                MessageEventResult()
                .message(
                    f"""[Persona]

- 人格情景列表: `/persona list`
- 设置人格情景: `/persona 人格`
- 人格情景详细信息: `/persona view 人格`
- 取消人格: `/persona unset`{inherit_line}

默认人格情景: {default_persona_name}
{current_label}

配置人格情景请前往管理面板-扩展功能-人格
""",
                )
                .use_t2i(False),
            )
            return

        subcmd, _, rest = raw_args.partition(" ")
        rest = rest.strip()

        if raw_args == "list":
            folder_tree = await self.context.persona_manager.get_folder_tree()
            all_personas = self.context.persona_manager.personas

            lines = ["📂 人格列表：\n"]

            tree_lines = self._build_tree_output(folder_tree, all_personas)
            lines.extend(tree_lines)

            root_personas = [p for p in all_personas if p.folder_id is None]
            if root_personas:
                if tree_lines:
                    lines.append("")
                for persona in root_personas:
                    lines.append(f"👤 {persona.persona_id}")

            total_count = len(all_personas)
            lines.append(f"\n共 {total_count} 个人格")
            lines.append("\n*使用 `/persona <人格名>` 设置人格")
            lines.append("*使用 `/persona view <人格名>` 查看详细信息")

            msg = "\n".join(lines)
            message.set_result(MessageEventResult().message(msg).use_t2i(False))
        elif subcmd == "view":
            if not rest:
                message.set_result(MessageEventResult().message("请输入人格情景名"))
                return
            persona = lookup_persona_v3(self.context, rest)
            if persona:
                msg = f"人格{rest}的详细信息：\n{persona['prompt']}\n"
            else:
                msg = f"人格{rest}不存在"
            message.set_result(MessageEventResult().message(msg))
        elif raw_args == "unset":
            if not cid and not session_override_supported:
                message.set_result(
                    MessageEventResult().message("当前没有对话，无法取消人格。"),
                )
                return
            await update_conversation_persona_compat(
                self.context,
                umo,
                "[%None]",
                conversation_id=cid,
            )
            message.set_result(MessageEventResult().message("取消人格成功。"))
        elif raw_args == "--inherit":
            if not session_override_supported:
                message.set_result(
                    MessageEventResult().message("当前 AstrBot 版本不支持会话级人格继承。"),
                )
                return
            await update_conversation_persona_compat(
                self.context,
                umo,
                None,
                conversation_id=cid,
            )
            message.set_result(
                MessageEventResult().message("已恢复继承配置文件的默认人格。"),
            )
        else:
            ps = raw_args
            if not cid and not session_override_supported:
                message.set_result(
                    MessageEventResult().message(
                        "当前没有对话，请先开始对话或使用 /new 创建一个对话。",
                    ),
                )
                return
            if lookup_persona_v3(self.context, ps):
                await update_conversation_persona_compat(
                    self.context,
                    umo,
                    ps,
                    conversation_id=cid,
                )
                force_warn_msg = ""
                if force_applied_persona_id:
                    force_warn_msg = (
                        "提醒：由于自定义规则，您现在切换的人格将不会生效。"
                    )

                message.set_result(
                    MessageEventResult().message(
                        f"设置成功。如果您正在切换到不同的人格，请注意使用 /reset 来清空上下文，防止原人格对话影响现人格。{force_warn_msg}",
                    ),
                )
            else:
                message.set_result(
                    MessageEventResult().message(
                        "不存在该人格情景。使用 /persona list 查看所有。",
                    ),
                )

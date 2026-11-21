from astrbot.api import star
from astrbot.api.event import AstrMessageEvent, MessageEventResult

from ._compat import (
    get_writable_profile_config,
    save_config_compat,
    update_session_overrides,
)


class LLMCommands:
    def __init__(self, context: star.Context) -> None:
        self.context = context

    async def llm(self, event: AstrMessageEvent, mode: str = "") -> None:
        """开启/关闭 LLM"""
        umo = event.unified_msg_origin
        if mode.strip() == "--inherit":
            if await update_session_overrides(umo, {"provider_settings.enable": None}):
                event.set_result(
                    MessageEventResult().message("已恢复继承配置文件的 LLM 开关设置。"),
                )
            else:
                event.set_result(
                    MessageEventResult().message("当前 AstrBot 版本不支持会话级配置继承。"),
                )
            return

        cfg = self.context.get_config(umo=umo)
        enable = bool(cfg.get("provider_settings", {}).get("enable", True))
        new_enable = not enable
        status = "开启" if new_enable else "关闭"

        if await update_session_overrides(umo, {"provider_settings.enable": new_enable}):
            event.set_result(
                MessageEventResult().message(f"已为当前会话{status} LLM 聊天功能。"),
            )
            return

        profile_cfg = get_writable_profile_config(self.context, umo)
        profile_cfg.setdefault("provider_settings", {})["enable"] = new_enable
        await save_config_compat(profile_cfg)
        event.set_result(MessageEventResult().message(f"{status} LLM 聊天功能。"))

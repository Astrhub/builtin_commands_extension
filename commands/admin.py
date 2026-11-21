from astrbot.api import star
from astrbot.api.event import AstrMessageEvent, MessageEventResult

from ._compat import get_writable_profile_config, save_config_compat


class AdminCommands:
    def __init__(self, context: star.Context) -> None:
        self.context = context

    async def op(self, event: AstrMessageEvent, admin_id: str = "") -> None:
        """授权管理员。op <admin_id>"""
        umo = event.unified_msg_origin
        admin_id = str(admin_id).strip()
        if not admin_id:
            event.set_result(
                MessageEventResult().message(
                    "使用方法: /op <id> 授权管理员；/deop <id> 取消管理员。可通过 /sid 获取 ID。",
                ),
            )
            return
        cfg = get_writable_profile_config(self.context, umo)
        admins = cfg.get("admins_id")
        if not isinstance(admins, list):
            admins = []
            cfg["admins_id"] = admins
        if admin_id in admins:
            event.set_result(MessageEventResult().message("此用户 ID 已在管理员名单内。"))
            return
        admins.append(admin_id)
        await save_config_compat(cfg)
        event.set_result(MessageEventResult().message("授权成功。"))

    async def deop(self, event: AstrMessageEvent, admin_id: str = "") -> None:
        """取消授权管理员。deop <admin_id>"""
        umo = event.unified_msg_origin
        admin_id = str(admin_id).strip()
        if not admin_id:
            event.set_result(
                MessageEventResult().message(
                    "使用方法: /deop <id> 取消管理员。可通过 /sid 获取 ID。",
                ),
            )
            return
        cfg = get_writable_profile_config(self.context, umo)
        admins = cfg.get("admins_id")
        if not isinstance(admins, list):
            admins = []
        try:
            admins.remove(admin_id)
            await save_config_compat(cfg)
            event.set_result(MessageEventResult().message("取消授权成功。"))
        except ValueError:
            event.set_result(
                MessageEventResult().message("此用户 ID 不在管理员名单内。"),
            )

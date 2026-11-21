from astrbot.api import star
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.core.star.filter.command import GreedyStr

from .commands import (
    AdminCommands,
    ConversationCommands,
    LLMCommands,
    PersonaCommands,
    PluginCommands,
    ProviderCommands,
)


def _shared_group_admin_if_supported():
    shared_group_admin = getattr(filter.PermissionType, "SHARED_GROUP_ADMIN", None)
    if shared_group_admin is not None:
        return filter.permission_type(shared_group_admin)

    def _identity(func):
        return func

    return _identity


class Main(star.Star):
    def __init__(self, context: star.Context) -> None:
        super().__init__(context)
        self.context = context

        self.admin_c = AdminCommands(self.context)
        self.conversation_c = ConversationCommands(self.context)
        self.llm_c = LLMCommands(self.context)
        self.persona_c = PersonaCommands(self.context)
        self.plugin_c = PluginCommands(self.context)
        self.provider_c = ProviderCommands(self.context)

    async def terminate(self) -> None:
        self.provider_c.cleanup()

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("llm")
    async def llm(self, event: AstrMessageEvent, mode: str = "") -> None:
        """开启/关闭 LLM"""
        await self.llm_c.llm(event, mode)

    @filter.command_group("plugin")
    def plugin(self) -> None:
        """插件管理"""

    @plugin.command("ls")
    async def plugin_ls(self, event: AstrMessageEvent) -> None:
        """获取已经安装的插件列表。"""
        await self.plugin_c.plugin_ls(event)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @plugin.command("off")
    async def plugin_off(self, event: AstrMessageEvent, plugin_name: str = "") -> None:
        """禁用插件"""
        await self.plugin_c.plugin_off(event, plugin_name)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @plugin.command("on")
    async def plugin_on(self, event: AstrMessageEvent, plugin_name: str = "") -> None:
        """启用插件"""
        await self.plugin_c.plugin_on(event, plugin_name)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @plugin.command("get")
    async def plugin_get(self, event: AstrMessageEvent, plugin_repo: str = "") -> None:
        """安装插件"""
        await self.plugin_c.plugin_get(event, plugin_repo)

    @plugin.command("help")
    async def plugin_help(self, event: AstrMessageEvent, plugin_name: str = "") -> None:
        """获取插件帮助"""
        await self.plugin_c.plugin_help(event, plugin_name)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("op")
    async def op(self, event: AstrMessageEvent, admin_id: str = "") -> None:
        """授权管理员。op <admin_id>"""
        await self.admin_c.op(event, admin_id)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("deop")
    async def deop(self, event: AstrMessageEvent, admin_id: str = "") -> None:
        """取消授权管理员。deop <admin_id>"""
        await self.admin_c.deop(event, admin_id)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("model")
    async def model_ls(
        self,
        message: AstrMessageEvent,
        idx_or_name: int | str | None = None,
    ) -> None:
        """查看或者切换模型"""
        await self.provider_c.model_ls(message, idx_or_name)

    @filter.command("history")
    async def his(self, message: AstrMessageEvent, page: int = 1) -> None:
        """查看对话记录"""
        await self.conversation_c.his(message, page)

    @filter.command("ls")
    async def convs(self, message: AstrMessageEvent, page: int = 1) -> None:
        """查看对话列表"""
        await self.conversation_c.convs(message, page)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("groupnew")
    async def groupnew_conv(self, message: AstrMessageEvent, sid: str = "") -> None:
        """创建新群聊对话"""
        await self.conversation_c.groupnew_conv(message, sid)

    @filter.command("switch")
    async def switch_conv(
        self, message: AstrMessageEvent, index: int | None = None
    ) -> None:
        """通过 /ls 前面的序号切换对话"""
        await self.conversation_c.switch_conv(message, index)

    @filter.command("rename")
    async def rename_conv(self, message: AstrMessageEvent, new_name: GreedyStr) -> None:
        """重命名对话"""
        await self.conversation_c.rename_conv(message, new_name)

    @filter.command("del")
    @_shared_group_admin_if_supported()
    async def del_conv(self, message: AstrMessageEvent) -> None:
        """删除当前对话"""
        await self.conversation_c.del_conv(message)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("persona")
    async def persona(self, message: AstrMessageEvent, args: GreedyStr) -> None:
        """查看或者切换 Persona"""
        await self.persona_c.persona(message, args)

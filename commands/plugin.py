from astrbot.api import star
from astrbot.api.event import AstrMessageEvent, MessageEventResult
from astrbot.core import DEMO_MODE, logger
from astrbot.core.star.filter.command import CommandFilter
from astrbot.core.star.filter.command_group import CommandGroupFilter
from astrbot.core.star.star_handler import StarHandlerMetadata, star_handlers_registry
from astrbot.core.star.star_manager import PluginManager
from astrbot.core.utils.error_redaction import safe_error

try:
    from astrbot.core.star import command_management as _command_management
except ImportError:
    _command_management = None


class PluginCommands:
    def __init__(self, context: star.Context) -> None:
        self.context = context

    async def plugin_ls(self, event: AstrMessageEvent) -> None:
        """获取已经安装的插件列表。"""
        parts = ["已加载的插件：\n"]
        for plugin in self.context.get_all_stars():
            line = f"- `{plugin.name}` By {plugin.author}: {plugin.desc}"
            if not plugin.activated:
                line += " (未启用)"
            parts.append(line + "\n")

        if len(parts) == 1:
            plugin_list_info = "没有加载任何插件。"
        else:
            plugin_list_info = "".join(parts)

        plugin_list_info += "\n使用 /plugin help <插件名> 查看插件帮助和加载的指令。\n使用 /plugin on/off <插件名> 启用或者禁用插件。"
        event.set_result(
            MessageEventResult().message(f"{plugin_list_info}").use_t2i(False),
        )

    async def plugin_off(self, event: AstrMessageEvent, plugin_name: str = "") -> None:
        """禁用插件"""
        if DEMO_MODE:
            event.set_result(MessageEventResult().message("演示模式下无法禁用插件。"))
            return
        plugin_name = plugin_name.strip()
        if not plugin_name:
            event.set_result(
                MessageEventResult().message("/plugin off <插件名> 禁用插件。"),
            )
            return
        star_mgr = self.context._star_manager
        if not star_mgr:
            event.set_result(MessageEventResult().message("插件管理器不可用。"))
            return
        plugin = self.context.get_registered_star(plugin_name)
        if plugin is None:
            event.set_result(MessageEventResult().message(f"未找到插件 {plugin_name}。"))
            return
        if getattr(plugin, "reserved", False):
            event.set_result(
                MessageEventResult().message(
                    f"插件 {plugin_name} 是 AstrBot 内置保留插件，无法通过此指令禁用。",
                ),
            )
            return
        try:
            await star_mgr.turn_off_plugin(plugin_name)
            event.set_result(MessageEventResult().message(f"插件 {plugin_name} 已禁用。"))
        except Exception as e:
            logger.error(f"禁用插件 {plugin_name} 失败: {e}")
            event.set_result(
                MessageEventResult().message(safe_error(f"禁用插件 {plugin_name} 失败: ", e)),
            )

    async def plugin_on(self, event: AstrMessageEvent, plugin_name: str = "") -> None:
        """启用插件"""
        if DEMO_MODE:
            event.set_result(MessageEventResult().message("演示模式下无法启用插件。"))
            return
        plugin_name = plugin_name.strip()
        if not plugin_name:
            event.set_result(
                MessageEventResult().message("/plugin on <插件名> 启用插件。"),
            )
            return
        star_mgr = self.context._star_manager
        if not star_mgr:
            event.set_result(MessageEventResult().message("插件管理器不可用。"))
            return
        plugin = self.context.get_registered_star(plugin_name)
        if plugin is None:
            event.set_result(MessageEventResult().message(f"未找到插件 {plugin_name}。"))
            return
        try:
            await star_mgr.turn_on_plugin(plugin_name)
            event.set_result(MessageEventResult().message(f"插件 {plugin_name} 已启用。"))
        except Exception as e:
            logger.error(f"启用插件 {plugin_name} 失败: {e}")
            event.set_result(
                MessageEventResult().message(safe_error(f"启用插件 {plugin_name} 失败: ", e)),
            )

    async def plugin_get(self, event: AstrMessageEvent, plugin_repo: str = "") -> None:
        """安装插件"""
        if DEMO_MODE:
            event.set_result(MessageEventResult().message("演示模式下无法安装插件。"))
            return
        plugin_repo = plugin_repo.strip()
        if not plugin_repo:
            event.set_result(
                MessageEventResult().message("/plugin get <插件仓库地址> 安装插件"),
            )
            return
        logger.info(f"准备从 {plugin_repo} 安装插件。")
        if self.context._star_manager:
            star_mgr: PluginManager = self.context._star_manager
            try:
                await star_mgr.install_plugin(plugin_repo)
                event.set_result(MessageEventResult().message("安装插件成功。"))
            except Exception as e:
                logger.error(f"安装插件失败: {e}")
                event.set_result(
                    MessageEventResult().message(safe_error("安装插件失败: ", e)),
                )
        else:
            event.set_result(MessageEventResult().message("插件管理器不可用。"))

    @staticmethod
    async def _build_command_lines_from_management(module_path: str) -> list[str] | None:
        if _command_management is None or not hasattr(_command_management, "list_commands"):
            return None
        try:
            commands = await _command_management.list_commands()
        except Exception:
            return None

        lines: list[str] = []

        def walk(items: list[dict], indent: int = 0) -> None:
            for item in items:
                if item.get("module_path") != module_path:
                    continue
                if indent == 0 and (
                    item.get("type") == "sub_command" or item.get("parent_signature")
                ):
                    continue
                effective = (
                    item.get("effective_command")
                    or item.get("original_command")
                    or item.get("handler_name")
                )
                if not effective:
                    continue
                prefix = "  " * indent
                line = f"{prefix}- {effective}"
                if item.get("enabled") is False:
                    line += " (已禁用)"
                if item.get("description"):
                    line += f": {item['description']}"
                lines.append(line + "\n")
                sub_commands = item.get("sub_commands") or []
                if sub_commands:
                    walk(sub_commands, indent + 1)

        walk(commands)
        return lines

    @staticmethod
    def _build_command_lines_from_registry(module_path: str) -> list[str]:
        lines: list[str] = []
        for handler in star_handlers_registry:
            assert isinstance(handler, StarHandlerMetadata)
            if handler.handler_module_path != module_path:
                continue
            for filter_ in handler.event_filters:
                if isinstance(filter_, CommandFilter):
                    complete_names = (
                        filter_.get_complete_command_names()
                        if hasattr(filter_, "get_complete_command_names")
                        else []
                    )
                    cmd_name = complete_names[0] if complete_names else filter_.command_name
                    line = f"- {cmd_name}"
                    if handler.desc:
                        line += f": {handler.desc}"
                    lines.append(line + "\n")
                    break
                if isinstance(filter_, CommandGroupFilter):
                    line = f"- {filter_.group_name}"
                    if handler.desc:
                        line += f": {handler.desc}"
                    lines.append(line + "\n")
                    break
        return lines

    async def plugin_help(self, event: AstrMessageEvent, plugin_name: str = "") -> None:
        """获取插件帮助"""
        plugin_name = plugin_name.strip()
        if not plugin_name:
            event.set_result(
                MessageEventResult().message("/plugin help <插件名> 查看插件信息。"),
            )
            return
        plugin = self.context.get_registered_star(plugin_name)
        if plugin is None:
            event.set_result(MessageEventResult().message("未找到此插件。"))
            return
        help_msg = f"\n\n✨ 作者: {plugin.author}\n✨ 版本: {plugin.version}"

        command_lines = await self._build_command_lines_from_management(
            plugin.module_path,
        )
        if command_lines is None:
            command_lines = self._build_command_lines_from_registry(plugin.module_path)

        if command_lines:
            help_msg += "\n\n🔧 指令列表：\n" + "".join(command_lines)
            help_msg += "\nTip: 指令的触发需要添加唤醒前缀，默认为 /。\n"
        else:
            help_msg += "\n\n"

        ret = f"🧩 插件 {plugin_name} 帮助信息：\n" + help_msg
        ret += "更多帮助信息请查看插件仓库 README。"
        event.set_result(MessageEventResult().message(ret).use_t2i(False))

from __future__ import annotations

import inspect
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from astrbot.api import sp, star
from astrbot.core import logger
from astrbot.core.agent.runners.deerflow.constants import (
    DEERFLOW_PROVIDER_TYPE,
    DEERFLOW_THREAD_ID_KEY,
)

if TYPE_CHECKING:
    from astrbot.api.event import AstrMessageEvent

try:
    from astrbot.core.session_overrides import (
        get_overrides as _core_get_overrides,
        update_overrides as _core_update_overrides,
    )
except ImportError:
    _core_get_overrides = None
    _core_update_overrides = None

try:
    from astrbot.core.agent.runners.deerflow.deerflow_api_client import (
        DeerFlowAPIClient as _DeerFlowAPIClient,
    )
except ImportError:
    _DeerFlowAPIClient = None


THIRD_PARTY_AGENT_RUNNER_KEY: dict[str, str] = {
    "dify": "dify_conversation_id",
    "coze": "coze_conversation_id",
    "dashscope": "dashscope_conversation_id",
    DEERFLOW_PROVIDER_TYPE: DEERFLOW_THREAD_ID_KEY,
}
THIRD_PARTY_AGENT_RUNNER_STR = ", ".join(THIRD_PARTY_AGENT_RUNNER_KEY.keys())


def has_session_overrides() -> bool:
    """Return whether AstrBot exposes the v4.30+ session_overrides API."""
    return callable(_core_update_overrides)


async def get_session_overrides(umo: str) -> dict[str, Any]:
    """Read explicit session overrides if supported, else return an empty dict."""
    if not callable(_core_get_overrides) or not umo:
        return {}
    result = await _core_get_overrides(umo)
    return dict(result) if isinstance(result, Mapping) else {}


async def update_session_overrides(umo: str, changes: dict[str, Any]) -> bool:
    """Apply session overrides on v4.30+, returning False on older versions."""
    if not callable(_core_update_overrides) or not umo:
        return False
    await _core_update_overrides(umo, changes)
    return True


def get_writable_profile_config(context: star.Context, umo: str | None) -> Any:
    """Return the writable base profile config for a UMO.

    On AstrBot v4.30+, ``context.get_config(umo=umo)`` inside a pipeline returns
    a read-only ``AstrBotConfigSnapshot`` whose ``save_config()`` raises
    ``ValueError``. Resolving the profile directly through ``astrbot_config_mgr``
    yields the underlying writable ``AstrBotConfig`` on both legacy and v4.30+.
    """
    acm = getattr(context, "astrbot_config_mgr", None)
    if acm is not None:
        confs = getattr(acm, "confs", None)
        if isinstance(confs, dict):
            if umo:
                get_conf_info = getattr(acm, "get_conf_info", None)
                if callable(get_conf_info):
                    conf_info = get_conf_info(umo)
                    conf_id = (
                        conf_info.get("id") if isinstance(conf_info, Mapping) else None
                    )
                    if conf_id and conf_id in confs:
                        return confs[conf_id]
            if "default" in confs:
                return confs["default"]
    return context.get_config(umo=umo)


async def save_config_compat(cfg: Any) -> None:
    """Persist an AstrBotConfig using async save when available."""
    save_async = getattr(cfg, "save_config_async", None)
    if callable(save_async):
        await save_async()
        return
    cfg.save_config()


def get_agent_runtime_and_config(cfg: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
    """Resolve active agent runtime name and runner config across AstrBot versions.

    Resolution order:
    1. v4.30+: ``cfg["agent"]["runtime"]`` / ``cfg["agent"]["config"]``
    2. v4.28–v4.29: ``cfg["agent_runner"]["runner_type"]`` / ``cfg["agent_runner"]["config"]``
    3. v4.23–v4.27: ``cfg["provider_settings"]["agent_runner_type"]``
    """
    agent = cfg.get("agent")
    if isinstance(agent, Mapping) and agent.get("runtime") is not None:
        raw_config = agent.get("config")
        return (
            str(agent["runtime"]),
            dict(raw_config) if isinstance(raw_config, Mapping) else {},
        )

    agent_runner = cfg.get("agent_runner")
    if (
        isinstance(agent_runner, Mapping)
        and agent_runner.get("runner_type") is not None
    ):
        raw_config = agent_runner.get("config")
        return (
            str(agent_runner["runner_type"]),
            dict(raw_config) if isinstance(raw_config, Mapping) else {},
        )

    provider_settings = cfg.get("provider_settings")
    if isinstance(provider_settings, Mapping):
        legacy_type = provider_settings.get("agent_runner_type")
        if legacy_type is not None:
            return str(legacy_type), {}

    return "astrbot", {}


def get_agent_runtime(cfg: Mapping[str, Any]) -> str:
    """Resolve active agent runtime name across AstrBot versions."""
    runtime, _ = get_agent_runtime_and_config(cfg)
    return runtime


async def get_using_provider_compat(context: star.Context, umo: str | None) -> Any:
    """Get the active chat provider without triggering deprecation warnings."""
    get_async = getattr(context, "get_using_provider_async", None)
    if callable(get_async):
        return await get_async(umo)
    return context.get_using_provider(umo)


def _extract_profile_persona_id(cfg: Mapping[str, Any]) -> str | None:
    agent = cfg.get("agent")
    if isinstance(agent, Mapping) and agent.get("runtime") is not None:
        runner_config = agent.get("config")
        if isinstance(runner_config, Mapping):
            if agent.get("runtime") == "astrbot":
                persona_cfg = runner_config.get("persona")
                if isinstance(persona_cfg, Mapping) and "persona_id" in persona_cfg:
                    return persona_cfg.get("persona_id")
            elif "persona_id" in runner_config:
                return runner_config.get("persona_id")
        return "default"

    agent_runner = cfg.get("agent_runner")
    if isinstance(agent_runner, Mapping):
        runner_config = agent_runner.get("config")
        if isinstance(runner_config, Mapping):
            persona_cfg = runner_config.get("persona")
            if isinstance(persona_cfg, Mapping) and "persona_id" in persona_cfg:
                return persona_cfg.get("persona_id")
            if "persona_id" in runner_config:
                return runner_config.get("persona_id")

    return None


async def get_profile_default_persona_name(context: star.Context, umo: str) -> str:
    """Return the base profile's default persona name.

    On AstrBot v4.30+, ``persona_manager.get_default_persona_v3(umo=umo)`` reads
    the effective session config (including session overrides). Reading the base
    profile directly preserves the distinction between profile default and
    session override.
    """
    if has_session_overrides():
        profile_cfg = get_writable_profile_config(context, umo)
        if isinstance(profile_cfg, Mapping):
            profile_persona_id = _extract_profile_persona_id(profile_cfg)
            if profile_persona_id == "[%None]":
                return "无"
            if profile_persona_id:
                persona = lookup_persona_v3(context, profile_persona_id)
                if persona and persona.get("name"):
                    return str(persona["name"])
                return str(profile_persona_id)

    default_persona = await context.persona_manager.get_default_persona_v3(umo=umo)
    name = default_persona.get("name") if isinstance(default_persona, Mapping) else None
    if not name or name == "[%None]":
        return "无"
    return str(name)


def lookup_persona_v3(context: star.Context, persona_name: str) -> dict[str, Any] | None:
    """Find a v3 persona dict by name, preferring PersonaManager over legacy aliases."""
    persona_mgr = getattr(context, "persona_manager", None)
    if persona_mgr is not None:
        personas_v3 = getattr(persona_mgr, "personas_v3", None)
        if personas_v3 is not None:
            for item in personas_v3:
                if item.get("name") == persona_name:
                    return item

        get_by_id = getattr(persona_mgr, "get_persona_v3_by_id", None)
        if callable(get_by_id):
            found = get_by_id(persona_name)
            if found is not None:
                return found

    provider_mgr = getattr(context, "provider_manager", None)
    if provider_mgr is not None:
        for item in getattr(provider_mgr, "personas", []) or []:
            if item.get("name") == persona_name:
                return item

    return None


def uses_session_override_persona(context: star.Context) -> bool:
    """Return True when PersonaManager.resolve_selected_persona uses the v4.30+ signature."""
    resolver = context.persona_manager.resolve_selected_persona
    return "conversation_persona_id" not in inspect.signature(resolver).parameters


async def resolve_selected_persona_compat(
    context: star.Context,
    *,
    umo: str,
    conversation_persona_id: str | None,
    platform_name: str,
    provider_settings: dict[str, Any] | None = None,
) -> tuple[str | None, Any | None, str | None, bool, bool]:
    """Call ``PersonaManager.resolve_selected_persona`` across v4.23–v4.30+.

    Returns:
        ``(persona_id, persona_obj, force_applied_persona_id,
        use_webchat_special_default, is_session_override_model)``
    """
    resolver = context.persona_manager.resolve_selected_persona
    params = inspect.signature(resolver).parameters

    if "conversation_persona_id" in params:
        kwargs: dict[str, Any] = {
            "umo": umo,
            "conversation_persona_id": conversation_persona_id,
            "platform_name": platform_name,
        }
        if "provider_settings" in params:
            kwargs["provider_settings"] = provider_settings
        result = await resolver(**kwargs)
        if len(result) == 4:
            persona_id, persona, force_applied, use_webchat = result
            return persona_id, persona, force_applied, use_webchat, False
        persona_id, persona, use_webchat = result[:3]
        return persona_id, persona, None, use_webchat, False

    result = await resolver(umo=umo, platform_name=platform_name)
    if len(result) >= 4:
        persona_id, persona, force_applied, use_webchat = result[:4]
        return persona_id, persona, force_applied, use_webchat, True
    persona_id, persona, use_webchat = result[:3]
    return persona_id, persona, None, use_webchat, True


async def update_conversation_title_compat(
    context: star.Context,
    umo: str,
    title: str,
    conversation_id: str | None = None,
) -> bool:
    """Update the current conversation's title across v4.23–v4.30+.

    Returns False when no active conversation exists.
    """
    conv_mgr = context.conversation_manager
    cid = conversation_id or await conv_mgr.get_curr_conversation_id(umo)
    if not cid:
        return False

    update_conv = getattr(conv_mgr, "update_conversation", None)
    if callable(update_conv):
        await update_conv(
            unified_msg_origin=umo,
            conversation_id=cid,
            title=title,
        )
        return True

    await conv_mgr.update_conversation_title(umo, title, cid)
    return True


async def update_conversation_persona_compat(
    context: star.Context,
    umo: str,
    persona_id: str | None,
    conversation_id: str | None = None,
) -> bool:
    """Update persona selection across v4.23–v4.30+.

    Passing ``persona_id=None`` clears the session persona override to restore
    profile inheritance (only supported on v4.30+).
    """
    if persona_id is None:
        return await update_session_overrides(
            umo,
            {
                "agent.config.persona.persona_id": None,
                "agent.config.persona_id": None,
            },
        )

    conv_mgr = context.conversation_manager
    update_conv = getattr(conv_mgr, "update_conversation", None)
    if callable(update_conv):
        await update_conv(
            unified_msg_origin=umo,
            conversation_id=conversation_id,
            persona_id=persona_id,
        )
        return True

    await conv_mgr.update_conversation_persona_id(umo, persona_id)
    return True


def is_unique_session_enabled(
    context: star.Context,
    event: AstrMessageEvent | None = None,
) -> bool:
    """Check whether session isolation is active for the given event/default config."""
    if event is not None and event.get_group_id():
        isolated = event.get_extra("_session_isolated", None)
        if isolated is not None:
            return bool(isolated)

    default_cfg = context.get_config()
    if isinstance(default_cfg, Mapping):
        platform_settings = default_cfg.get("platform_settings")
        if isinstance(platform_settings, Mapping) and "unique_session" in platform_settings:
            return bool(platform_settings["unique_session"])

    if event is not None:
        umo_cfg = context.get_config(umo=event.unified_msg_origin)
        if isinstance(umo_cfg, Mapping):
            return bool(umo_cfg.get("platform_settings", {}).get("unique_session", False))

    return False


def is_event_admin(event: AstrMessageEvent) -> bool:
    """Check whether the event sender is an AstrBot admin."""
    is_admin = getattr(event, "is_admin", None)
    if callable(is_admin):
        return bool(is_admin())
    return getattr(event, "role", None) == "admin"


def mark_clean_group_context(event: AstrMessageEvent) -> None:
    """Mark the event to clean group chat temporary context on both old and new cores."""
    event.set_extra("_clean_group_context_session", True)
    event.set_extra("_clean_ltm_session", True)


def _resolve_deerflow_runner_config(
    context: star.Context,
    cfg: Mapping[str, Any],
) -> dict[str, Any]:
    runtime, runner_config = get_agent_runtime_and_config(cfg)
    if runtime != DEERFLOW_PROVIDER_TYPE:
        return {}
    if runner_config:
        return runner_config

    # Legacy v4.23.1–v4.27 stored DeerFlow settings in a provider referenced by provider_settings.
    provider_settings = cfg.get("provider_settings")
    if not isinstance(provider_settings, Mapping):
        return {}
    provider_id = provider_settings.get("deerflow_agent_runner_provider_id", "")
    if not provider_id:
        return {}
    provider_mgr = getattr(context, "provider_manager", None)
    get_cfg = getattr(provider_mgr, "get_provider_config_by_id", None)
    if not callable(get_cfg):
        return {}
    merged = get_cfg(provider_id, merged=True)
    return dict(merged) if isinstance(merged, Mapping) else {}


async def _cleanup_deerflow_thread_if_present(
    context: star.Context,
    umo: str,
) -> None:
    if _DeerFlowAPIClient is None or not hasattr(_DeerFlowAPIClient, "delete_thread"):
        return

    try:
        thread_id = await sp.get_async(
            scope="umo",
            scope_id=umo,
            key=DEERFLOW_THREAD_ID_KEY,
            default="",
        )
        if not thread_id:
            return

        cfg = context.get_config(umo=umo)
        runner_config = _resolve_deerflow_runner_config(context, cfg)
        if not runner_config:
            return

        client = _DeerFlowAPIClient(
            api_base=runner_config.get(
                "deerflow_api_base",
                "http://127.0.0.1:2026",
            ),
            api_key=runner_config.get("deerflow_api_key", ""),
            auth_header=runner_config.get("deerflow_auth_header", ""),
            proxy=runner_config.get("proxy", ""),
        )
        try:
            await client.delete_thread(thread_id)
        finally:
            try:
                await client.close()
            except Exception as e:
                logger.warning(
                    "Failed to close DeerFlow API client after thread cleanup: %s",
                    e,
                )
    except Exception as e:
        logger.warning(
            "Failed to clean up DeerFlow thread for session %s: %s",
            umo,
            e,
        )


async def clear_third_party_agent_runner_state(
    context: star.Context,
    umo: str,
    agent_runner_type: str,
) -> None:
    """Clear local and remote conversation state for third-party agent runners."""
    session_key = THIRD_PARTY_AGENT_RUNNER_KEY.get(agent_runner_type)
    if not session_key:
        return

    if agent_runner_type == DEERFLOW_PROVIDER_TYPE:
        await _cleanup_deerflow_thread_if_present(context, umo)

    await sp.remove_async(
        scope="umo",
        scope_id=umo,
        key=session_key,
    )

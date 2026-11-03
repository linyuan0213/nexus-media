from dataclasses import dataclass, field
from typing import Any

# ==================== 旧版插件 DTO ====================


@dataclass
class PluginAppsDTO:
    plugins: Any = None
    statistic: Any = None


@dataclass
class PluginPageDTO:
    title: str | None = None
    content: str | None = None
    func: Any = None


@dataclass
class PluginInstallResultDTO:
    success: bool = False
    msg: str = ""


# ==================== 插件框架 v2 DTO ====================


@dataclass
class PluginToolConfig:
    """插件声明式 Agent 工具定义（由后端在启用时暴露给 Agent）"""

    name: str = ""
    description: str = ""
    parameters: dict = field(default_factory=dict)
    level: str = "read"  # read | write | dangerous
    permission: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> "PluginToolConfig":
        return cls(
            name=data.get("name", ""),
            description=data.get("description", ""),
            parameters=data.get("parameters") or {},
            level=data.get("level", "read"),
            permission=data.get("permission", ""),
        )

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
            "level": self.level,
            "permission": self.permission,
        }


@dataclass
class PluginMetadataConfig:
    """插件声明的元数据扩展（provider / discovery / profile）."""

    visibility: str = "public"
    required_permission: str = ""
    providers: list[dict] = field(default_factory=list)
    discovery_providers: list[dict] = field(default_factory=list)
    indexer_providers: list[dict] = field(default_factory=list)
    content_profiles: list[dict] = field(default_factory=list)
    match_profiles: list[dict] = field(default_factory=list)
    parser_profiles: list[dict] = field(default_factory=list)
    naming_profiles: list[dict] = field(default_factory=list)
    nfo_profiles: list[dict] = field(default_factory=list)
    message_templates: dict = field(default_factory=dict)
    message_labels: dict = field(default_factory=dict)
    image_referers: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict | None) -> "PluginMetadataConfig":
        data = data or {}

        def normalize(items) -> list[dict]:
            result = []
            for item in items or []:
                if isinstance(item, str):
                    result.append({"key": item})
                elif isinstance(item, dict):
                    result.append(item)
            return result

        message_templates = data.get("message_templates")
        message_labels = data.get("message_labels")
        image_referers = data.get("image_referers")
        return cls(
            visibility=data.get("visibility", "public"),
            required_permission=data.get("required_permission", ""),
            providers=normalize(data.get("providers")),
            discovery_providers=normalize(data.get("discovery_providers")),
            indexer_providers=normalize(data.get("indexer_providers")),
            content_profiles=normalize(data.get("content_profiles")),
            match_profiles=normalize(data.get("match_profiles")),
            parser_profiles=normalize(data.get("parser_profiles")),
            naming_profiles=normalize(data.get("naming_profiles")),
            nfo_profiles=normalize(data.get("nfo_profiles")),
            message_templates=dict(message_templates) if isinstance(message_templates, dict) else {},
            message_labels=dict(message_labels) if isinstance(message_labels, dict) else {},
            image_referers=dict(image_referers) if isinstance(image_referers, dict) else {},
        )

    def keys(self, kind: str) -> set[str]:
        items = getattr(self, kind, []) or []
        return {str(item.get("key")) for item in items if item.get("key")}

    def to_dict(self) -> dict:
        return {
            "visibility": self.visibility,
            "required_permission": self.required_permission,
            "providers": self.providers,
            "discovery_providers": self.discovery_providers,
            "indexer_providers": self.indexer_providers,
            "content_profiles": self.content_profiles,
            "match_profiles": self.match_profiles,
            "parser_profiles": self.parser_profiles,
            "naming_profiles": self.naming_profiles,
            "nfo_profiles": self.nfo_profiles,
            "message_templates": self.message_templates,
            "message_labels": self.message_labels,
            "image_referers": self.image_referers,
        }


@dataclass
class PluginBackendConfig:
    entry: str = ""
    api_prefix: str = ""
    permissions: list[str] = field(default_factory=list)
    hooks: list[str] = field(default_factory=list)
    supports_run: bool = False
    dependencies: list[str] = field(default_factory=list)
    tools: list[PluginToolConfig] = field(default_factory=list)
    metadata: PluginMetadataConfig = field(default_factory=PluginMetadataConfig)


@dataclass
class PluginRouteConfig:
    path: str = ""
    component: str = ""
    title: str = ""
    icon: str = ""
    menu: bool = True
    parent: str = ""
    permission: str = ""
    order: int | None = None


@dataclass
class PluginFieldConfig:
    key: str = ""
    type: str = ""
    label: str = ""
    default: Any = None
    placeholder: str = ""
    options: Any = None
    source: str = ""
    source_filter: str = ""
    multiple: bool = False
    required: bool = False
    help: str = ""


@dataclass
class PluginSettingsConfig:
    component: str = ""
    fields: list[PluginFieldConfig] = field(default_factory=list)


@dataclass
class PluginSlotConfig:
    target: str = ""
    position: str = ""
    component: str = ""


@dataclass
class PluginFrontendConfig:
    routes: list[PluginRouteConfig] = field(default_factory=list)
    settings: PluginSettingsConfig | None = None
    slots: list[PluginSlotConfig] = field(default_factory=list)
    content_profiles: list[dict] = field(default_factory=list)


@dataclass
class PluginManifest:
    manifest_version: str = "1.0"
    id: str = ""
    name: str = ""
    version: str = "1.0.0"
    author: str = ""
    author_url: str = ""
    description: str = ""
    category: str = "tool"
    tags: list[str] = field(default_factory=list)
    icon: str = ""
    color: str = ""
    min_app_version: str = ""
    backend: PluginBackendConfig = field(default_factory=PluginBackendConfig)
    frontend: PluginFrontendConfig = field(default_factory=PluginFrontendConfig)

    @classmethod
    def from_dict(cls, data: dict) -> "PluginManifest":
        backend_data = data.get("backend", {})
        frontend_data = data.get("frontend", {})

        routes = [PluginRouteConfig(**r) for r in frontend_data.get("routes", [])]
        fields = [PluginFieldConfig(**f) for f in frontend_data.get("settings", {}).get("fields", [])]
        slots = [PluginSlotConfig(**s) for s in frontend_data.get("slots", [])]
        content_profiles = [
            item for item in frontend_data.get("content_profiles", []) if isinstance(item, dict) and item.get("key")
        ]

        return cls(
            manifest_version=data.get("manifest_version", "1.0"),
            id=data.get("id", ""),
            name=data.get("name", ""),
            version=data.get("version", "1.0.0"),
            author=data.get("author", ""),
            author_url=data.get("author_url", ""),
            description=data.get("description", ""),
            category=data.get("category", "tool"),
            tags=data.get("tags", []),
            icon=data.get("icon", ""),
            color=data.get("color", ""),
            min_app_version=data.get("min_app_version", ""),
            backend=PluginBackendConfig(
                entry=backend_data.get("entry", ""),
                api_prefix=backend_data.get("api_prefix", ""),
                permissions=backend_data.get("permissions", []),
                hooks=backend_data.get("hooks", []),
                supports_run=backend_data.get("supports_run", False),
                dependencies=backend_data.get("dependencies", []),
                tools=[PluginToolConfig.from_dict(t) for t in backend_data.get("tools", [])],
                metadata=PluginMetadataConfig.from_dict(backend_data.get("metadata")),
            ),
            frontend=PluginFrontendConfig(
                routes=routes,
                settings=PluginSettingsConfig(
                    component=frontend_data.get("settings", {}).get("component", ""),
                    fields=fields,
                )
                if frontend_data.get("settings")
                else None,
                slots=slots,
                content_profiles=content_profiles,
            ),
        )

    def to_dict(self) -> dict:
        return {
            "manifest_version": self.manifest_version,
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "author": self.author,
            "author_url": self.author_url,
            "description": self.description,
            "category": self.category,
            "tags": self.tags,
            "icon": self.icon,
            "color": self.color,
            "min_app_version": self.min_app_version,
            "backend": {
                "entry": self.backend.entry,
                "api_prefix": self.backend.api_prefix,
                "permissions": self.backend.permissions,
                "hooks": self.backend.hooks,
                "supports_run": self.backend.supports_run,
                "dependencies": self.backend.dependencies,
                "tools": [t.to_dict() for t in self.backend.tools],
                "metadata": self.backend.metadata.to_dict(),
            },
            "frontend": {
                "routes": [
                    {
                        "path": r.path,
                        "component": r.component,
                        "title": r.title,
                        "icon": r.icon,
                        "menu": r.menu,
                        "parent": r.parent,
                        "permission": r.permission,
                        "order": r.order,
                    }
                    for r in self.frontend.routes
                ],
                "settings": {
                    "component": self.frontend.settings.component if self.frontend.settings else "",
                    "fields": [
                        {
                            "key": f.key,
                            "type": f.type,
                            "label": f.label,
                            "default": f.default,
                            "placeholder": f.placeholder,
                            "options": f.options,
                            "source": f.source,
                            "multiple": f.multiple,
                            "required": f.required,
                            "help": f.help,
                        }
                        for f in (self.frontend.settings.fields if self.frontend.settings else [])
                    ],
                }
                if self.frontend.settings
                else None,
                "slots": [
                    {"target": s.target, "position": s.position, "component": s.component} for s in self.frontend.slots
                ],
                "content_profiles": self.frontend.content_profiles,
            },
        }


@dataclass
class PluginState:
    id: str = ""
    enabled: bool = False
    installed: bool = False
    healthy: bool = True
    message: str = ""
    last_error: str = ""
    manifest: PluginManifest | None = None
    config: dict[str, Any] = field(default_factory=dict)
    history_count: int = 0


# ==================== 共享 DTO ====================


@dataclass
class PluginFieldDTO:
    type: str = ""
    label: str = ""
    default: Any = None
    placeholder: str = ""
    options: Any = None
    multiple: bool = False
    required: bool = False
    help: str = ""


@dataclass
class PluginDTO:
    id: str = ""
    name: str = ""
    desc: str = ""
    icon: str = ""
    color: str = ""
    version: str = "1.0"
    author: str = ""
    author_url: str = ""
    category: str = "tool"
    tags: list[str] = field(default_factory=list)
    order: int = 0
    installed: bool = False
    enabled: bool = False
    state: bool = False
    readme: str = ""
    changelog: str = ""
    requires: list[str] = field(default_factory=list)


@dataclass
class InstalledPluginDTO(PluginDTO):
    config: dict[str, Any] = field(default_factory=dict)
    fields: dict[str, PluginFieldDTO] = field(default_factory=dict)
    history_count: int = 0


@dataclass
class PluginHistoryPageDTO:
    total: int = 0
    items: list[dict[str, Any]] = field(default_factory=list)

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ConfigField:
    id: str
    required: bool
    title: str
    type: str
    tooltip: str = ""
    placeholder: str = ""
    default: Any = None
    options: dict[str, str] = field(default_factory=dict)


@dataclass
class DownloaderConfigSchema:
    name: str
    icon_url: str | None = None
    monitor_enable: bool = True
    speedlimit_enable: bool = True
    fields: list[ConfigField] = field(default_factory=list)

    def to_dict(self) -> dict:
        result = {
            "name": self.name,
            "monitor_enable": self.monitor_enable,
            "speedlimit_enable": self.speedlimit_enable,
            "config": {},
        }
        if self.icon_url:
            result["icon_url"] = self.icon_url
        for cfg_field in self.fields:
            field_dict = {
                "id": cfg_field.id,
                "required": cfg_field.required,
                "title": cfg_field.title,
                "type": cfg_field.type,
            }
            if cfg_field.tooltip:
                field_dict["tooltip"] = cfg_field.tooltip
            if cfg_field.placeholder:
                field_dict["placeholder"] = cfg_field.placeholder
            if cfg_field.default is not None:
                field_dict["default"] = cfg_field.default
            if cfg_field.options:
                field_dict["options"] = cfg_field.options
            result["config"][cfg_field.id] = field_dict
        return result

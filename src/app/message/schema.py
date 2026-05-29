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
class MessageConfigSchema:
    name: str
    icon_url: str | None = None
    search_type: str | None = None
    max_length: int | None = None
    fields: list[ConfigField] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "name": self.name,
        }
        if self.icon_url:
            result["icon_url"] = self.icon_url
        if self.search_type:
            result["search_type"] = self.search_type
        if self.max_length is not None:
            result["max_length"] = self.max_length
        result["config"] = {}
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

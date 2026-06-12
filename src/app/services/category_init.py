"""分类配置初始化：从 YAML 模板加载默认分类到数据库"""

import os

import ruamel.yaml

import log
from app.core.root_path import get_project_root
from app.db.repositories.category_repo_adapter import CategoryConfigRepositoryAdapter
from app.db.session import Database


class CategoryInitializer:
    """负责从 default-category.yaml 模板初始化数据库中的分类配置"""

    _TEMPLATE_PATH = os.path.join(str(get_project_root()), "config", "default-category.yaml")

    def __init__(self, repo: CategoryConfigRepositoryAdapter | None = None):
        self._repo = repo or CategoryConfigRepositoryAdapter()

    def _ensure_tables(self) -> None:
        """确保分类配置表已创建"""
        try:
            db = Database()
            db.create_all()
            log.info("[CategoryInit]数据库表检查/创建完成")
        except Exception as e:
            log.warn(f"[CategoryInit]create_all 执行提示: {e}")

    def run(self) -> None:
        """若数据库中无分类配置，则从模板导入默认数据"""
        log.info("[CategoryInit]开始检查默认分类配置...")

        self._ensure_tables()

        try:
            existing = self._repo.get_all()
            log.info(f"[CategoryInit]数据库中已有 {len(existing)} 条分类配置")
            if existing:
                return
        except Exception as e:
            log.error(f"[CategoryInit]查询分类配置失败: {e}")
            return

        if not os.path.exists(self._TEMPLATE_PATH):
            log.warn(f"[CategoryInit]模板文件不存在: {self._TEMPLATE_PATH}")
            return

        try:
            with open(self._TEMPLATE_PATH, encoding="utf-8") as f:
                yaml = ruamel.yaml.YAML()
                data = yaml.load(f) or {}
        except Exception as e:
            log.error(f"[CategoryInit]读取模板失败: {e}")
            return

        sort_order = 0
        for media_type, categories in data.items():
            if not isinstance(categories, dict):
                continue
            for name, rules in categories.items():
                sort_order += 1
                is_default = 1 if rules is None else 0
                rule_dict = rules if isinstance(rules, dict) else {}
                try:
                    self._repo.save(
                        media_type=media_type,
                        name=name,
                        sort_order=sort_order,
                        is_default=is_default,
                        rules=rule_dict,
                    )
                except Exception as e:
                    log.error(f"[CategoryInit]保存分类 '{name}' 失败: {e}")

        log.info(f"[CategoryInit]已从模板导入 {sort_order} 条默认分类配置")

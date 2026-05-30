import os
import sys

from sqlalchemy import text

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_root, "src"))

os.environ["NEXUS_MEDIA_CONFIG"] = os.path.join(_root, "config", "config.yaml")

from app.db.engine import get_engine  # noqa: E402

# 删除有错误的插件框架v2表
tables = ["PLUGIN_MANIFEST", "PLUGIN_CONFIG", "PLUGIN_LOGS", "PLUGIN_HOOKS"]

engine = get_engine()
if not engine:
    print("数据库引擎未初始化")
    exit(1)

with engine.connect() as conn:
    for t in tables:
        try:
            conn.execute(text(f"DROP TABLE IF EXISTS {t}"))
            print(f"已删除表: {t}")
        except Exception as e:
            print(f"删除表 {t} 失败: {e}")
    conn.commit()

print("所有表已删除，重启应用后会自动重新创建。")

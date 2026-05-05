import sys
sys.path.insert(0, '/home/linyuan/python/nas-tools')

import os
os.environ['NASTOOL_CONFIG'] = '/home/linyuan/python/config/config.yaml'

from app.db.models.base import Base
from app.db.main_db import _Engine
from sqlalchemy import text

# 删除有错误的插件框架v2表
tables = ['PLUGIN_MANIFEST', 'PLUGIN_CONFIG', 'PLUGIN_LOGS', 'PLUGIN_HOOKS']

with _Engine.connect() as conn:
    for t in tables:
        try:
            conn.execute(text(f'DROP TABLE IF EXISTS {t}'))
            print(f'已删除表: {t}')
        except Exception as e:
            print(f'删除表 {t} 失败: {e}')
    conn.commit()

print('所有表已删除，重启应用后会自动重新创建。')

"""Debug anitopy parsing"""

import sys
from unittest.mock import MagicMock

sys.modules["log"] = MagicMock()

import os

os.environ["NASTOOL_CONFIG"] = "/home/linyuan/python/config/config.yaml"

import anitopy

title = "【关于我转生变成史莱姆这档事 Tensei Shitara Slime Datta Ken 】【12】【GB】【1080P】"

print("=" * 70)
print("测试标题:")
print(title)
print("=" * 70)

info = anitopy.parse(title)
print("\n【anitopy 解析结果】")
for k, v in info.items():
    print(f"  {k}: {v}")

# Also test with prepared title
from app.media.parser.anime.prepare import prepare_title

prepared = prepare_title(title)
print("\n【prepare_title 后】")
print(f"  {prepared}")

info2 = anitopy.parse(prepared)
print("\n【anitopy 解析 prepared 后】")
for k, v in info2.items():
    print(f"  {k}: {v}")

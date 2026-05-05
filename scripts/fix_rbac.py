#!/usr/bin/env python3
import re

path = "api/routers/rbac.py"
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Fix to_dict())) -> to_dict())
content = content.replace('to_dict()))', 'to_dict())')

# Also fix any remaining )))
content = content.replace('to_dict()))', 'to_dict())')

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print("Fixed rbac.py")

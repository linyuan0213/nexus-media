#!/usr/bin/env python3
"""
修复 data={key=value} 语法错误，改为 data={"key": value}
"""
import re
import os

ROUTERS_DIR = "api/routers"


def fix_data_dict(content: str) -> str:
    pattern = re.compile(r'data=\{(.*?)\}', re.DOTALL)

    def replacer(m):
        inner = m.group(1)
        result = []
        i = 0
        n = len(inner)
        in_str = None
        while i < n:
            ch = inner[i]
            if ch in '"\'':
                if in_str is None:
                    in_str = ch
                elif in_str == ch:
                    # 检查转义
                    bs = 0
                    j = i - 1
                    while j >= 0 and inner[j] == '\\':
                        bs += 1
                        j -= 1
                    if bs % 2 == 0:
                        in_str = None
                result.append(ch)
                i += 1
                continue
            if in_str is not None:
                result.append(ch)
                i += 1
                continue

            # 不在字符串内，尝试匹配 identifier=
            if ch.isalpha() or ch == '_':
                j = i
                while j < n and (inner[j].isalnum() or inner[j] == '_'):
                    j += 1
                if j < n and inner[j] == '=' and (j + 1 >= n or inner[j + 1] != '='):
                    key = inner[i:j]
                    result.append(f'"{key}":')
                    i = j + 1
                    continue
            result.append(ch)
            i += 1
        return 'data={' + ''.join(result) + '}'

    return pattern.sub(replacer, content)


def main():
    for fname in os.listdir(ROUTERS_DIR):
        if not fname.endswith('.py'):
            continue
        path = os.path.join(ROUTERS_DIR, fname)
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        new_content = fix_data_dict(content)
        if new_content != content:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(new_content)
            print(f'Fixed dict syntax: {path}')


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""
统一所有后端 router 中 success() 的调用方式，确保只使用 data=... 和 msg=... 参数。
"""

import os
import re

ROUTERS_DIR = "api/routers"


def fix_multiline_success(content: str) -> str:
    """
    将多参数 success(...) 统一为 success(data={...}) 或 success(data=...) 或 success()
    """
    # 正则匹配 success( ... ) 调用，跨越多行
    pattern = re.compile(r"return success\((.*?)\)", re.DOTALL)

    def replacer(m):
        args = m.group(1).strip()
        if not args:
            return "return success()"

        # 已经统一为 data=... 或 msg=... 的情况
        if args.startswith(("data=", "msg=")):
            # 如果只有 data=... 或 msg=...，保留
            # 但也可能有 data=... 后跟其他参数，需要进一步处理
            pass

        lines = args.split("\n")
        # 合并成单行并去掉多余空白
        single_line = " ".join(line.strip() for line in lines if line.strip())

        # 已经 data=... 且没有其他参数
        if single_line.startswith("data=") and "," not in single_line:
            return f"return success({single_line})"
        if single_line.startswith("msg=") and "," not in single_line:
            return f"return success({single_line})"

        # 处理 **result 的情况
        if single_line == "**result":
            return "return success(data=result)"

        # 处理多参数的情况：全部塞进 data={...}
        # 但 data=... 开头的，只保留 data
        if single_line.startswith("data="):
            # 提取 data= 后面的值
            rest = single_line[5:]  # 去掉 "data="
            # 如果后面有逗号，说明还有其他参数
            # 找到第一个逗号的位置（顶层逗号）
            comma_idx = find_top_level_comma(rest)
            if comma_idx != -1:
                data_val = rest[:comma_idx].strip()
                return f"return success(data={data_val})"
            else:
                return f"return success(data={rest})"

        # 其他多参数情况
        return f"return success(data={{{single_line}}})"

    return pattern.sub(replacer, content)


def find_top_level_comma(s: str) -> int:
    """找到顶层逗号的位置（不在括号内）"""
    depth = 0
    for i, ch in enumerate(s):
        if ch in "({[":
            depth += 1
        elif ch in ")}]":
            depth -= 1
        elif ch == "," and depth == 0:
            return i
    return -1


def process_file(path: str):
    with open(path, encoding="utf-8") as f:
        content = f.read()

    new_content = fix_multiline_success(content)

    if new_content != content:
        with open(path, "w", encoding="utf-8") as f:
            f.write(new_content)
        print(f"Fixed: {path}")
    else:
        print(f"No changes: {path}")


def main():
    for fname in os.listdir(ROUTERS_DIR):
        if fname.endswith(".py"):
            process_file(os.path.join(ROUTERS_DIR, fname))


if __name__ == "__main__":
    main()

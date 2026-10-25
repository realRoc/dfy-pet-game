"""python -m game.content check  —— 校验 content/ 下所有配置。"""
import sys

from .loader import CONTENT_DIR, check_all


def main(argv):
    if argv[:1] != ["check"]:
        print("用法：python -m game.content check")
        return 2
    ok, errors = check_all()
    print(f"内容目录：{CONTENT_DIR}")
    for line in ok:
        print("  ✓", line)
    for line in errors:
        print("  ✗", line)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

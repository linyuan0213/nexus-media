"""配置文件不被环境变量写回的回归测试（ADR 外修复：_apply_env_database_config 已移除）."""

import os
import subprocess
import sys


class TestEnvNotWrittenBack:
    def test_database_env_does_not_pollute_config_file(self, tmp_path):
        """带 DATABASE__* 环境变量启动时不得修改配置文件"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("database:\n  type: mysql\n  host: db.example.com\n", encoding="utf-8")

        env = dict(os.environ)
        env["NEXUS_MEDIA_CONFIG"] = str(config_file)
        env["DATABASE__TYPE"] = "sqlite"
        env["DATABASE__SQLITE_PATH"] = str(tmp_path / "x.db")

        code = (
            "from app.core.settings import settings\n"
            "assert settings.database.type == 'sqlite', settings.database.type\n"  # 运行时 env 覆盖生效
            "print('runtime-override-ok')\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=str(__import__("pathlib").Path(__file__).parents[3] / "src"),
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert "runtime-override-ok" in result.stdout, result.stderr
        # 配置文件内容不变
        assert config_file.read_text(encoding="utf-8") == "database:\n  type: mysql\n  host: db.example.com\n"

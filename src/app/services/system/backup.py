"""Backup services - 备份恢复业务."""

import os
import shutil
import tempfile
import time
from pathlib import Path

from sqlalchemy import create_engine

from app.core.exceptions import DomainError, RepositoryError, ServiceError
from app.core.settings import settings
from app.db.database_factory import DatabaseFactory
from app.db.migrate import export_database, export_to_file, import_database, import_from_file
from app.schemas.system import BackupRestoreResultDTO
from app.utils import ExceptionUtils
from app.utils.temp_manager import temp_manager


class BackupRestoreService:
    """
    备份恢复业务服务
    负责解压备份文件、恢复配置、跨数据库类型导入数据
    """

    def restore_from_backup(self, filename: str) -> BackupRestoreResultDTO:
        """
        从备份文件恢复
        :param filename: 上传的备份文件名
        """
        if not filename:
            return BackupRestoreResultDTO(success=False, message="文件不存在")

        config_path = settings.config_path
        file_path = temp_manager.get_temp_path(filename)
        temp_dir = None

        try:
            # 1. 解压到临时目录
            temp_dir = tempfile.mkdtemp(prefix="restore_")
            shutil.unpack_archive(file_path, temp_dir, format="zip")

            # 2. 恢复配置文件
            for cfg_name in ["config.yaml", "default-category.yaml"]:
                src = os.path.join(temp_dir, cfg_name)
                if os.path.exists(src):
                    shutil.copy(src, config_path)

            # 3. 判断备份中的数据库格式与当前数据库类型
            json_backup = os.path.join(temp_dir, "user_db_export.json")
            sqlite_backup = os.path.join(temp_dir, "user.db")

            target_engine = DatabaseFactory.create_engine()

            if os.path.exists(json_backup):
                import_from_file(target_engine, json_backup)
            elif os.path.exists(sqlite_backup):
                source_engine = create_engine(f"sqlite:///{sqlite_backup}?check_same_thread=False")
                migrate_data = export_database(source_engine)
                import_database(target_engine, migrate_data)
                source_engine.dispose()
            else:
                return BackupRestoreResultDTO(success=False, message="备份文件中未找到数据库文件")

            target_engine.dispose()
            return BackupRestoreResultDTO(success=True, message="恢复成功")

        except (ServiceError, RepositoryError, DomainError):
            raise
        except Exception as e:
            ExceptionUtils.exception_traceback(e)
            return BackupRestoreResultDTO(success=False, message=str(e))

        finally:
            if os.path.exists(file_path):
                os.remove(file_path)
            if temp_dir and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)


def backup(full_backup=False, bk_path=None):
    """
    @param full_backup  是否完整备份（保留参数兼容性，当前始终完整备份）
    @param bk_path     自定义备份路径
    """
    try:
        config_path = Path(settings.config_path)
        backup_file = f"bk_{time.strftime('%Y%m%d%H%M%S')}"
        if bk_path:
            backup_path = Path(bk_path) / backup_file
        else:
            backup_path = config_path / "backup_file" / backup_file
        backup_path.mkdir(parents=True)
        shutil.copy(f"{config_path}/config.yaml", backup_path)
        shutil.copy(f"{config_path}/default-category.yaml", backup_path)

        db_type = DatabaseFactory._get_config_db_type()
        engine = DatabaseFactory.create_engine()
        if db_type == DatabaseFactory.SQLITE:
            shutil.copy(f"{config_path}/user.db", backup_path)
        export_to_file(engine, str(backup_path / "user_db_export.json"))
        engine.dispose()

        zip_file = str(backup_path) + ".zip"
        if os.path.exists(zip_file):
            zip_file = str(backup_path) + ".zip"
        shutil.make_archive(str(backup_path), "zip", str(backup_path))
        shutil.rmtree(str(backup_path))
        return zip_file
    except (ServiceError, RepositoryError, DomainError):
        raise
    except Exception as e:
        ExceptionUtils.exception_traceback(e)
        return None

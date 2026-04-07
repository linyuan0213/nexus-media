"""
User Repository
Handles user management related database operations.
"""
from app.db import DbPersist
from app.db.models import CONFIGUSERS
from app.db.repositories.base_repository import BaseRepository


class UserRepository(BaseRepository):
    """
    用户管理仓储
    处理用户管理的数据库操作
    """

    def get_users(self, uid=None, name=None):
        """
        查询用户列表
        
        Args:
            uid: 用户ID
            name: 用户名
            
        Returns:
            用户对象或列表
        """
        if uid:
            return self._db.query(CONFIGUSERS).filter(CONFIGUSERS.ID == uid).first()
        elif name:
            return self._db.query(CONFIGUSERS).filter(CONFIGUSERS.NAME == name).first()
        return self._db.query(CONFIGUSERS).all()

    def is_user_exists(self, name):
        """
        判断用户是否存在
        
        Args:
            name: 用户名
            
        Returns:
            是否存在
        """
        if not name:
            return False
        count = self._db.query(CONFIGUSERS).filter(CONFIGUSERS.NAME == name).count()
        return count > 0

    @DbPersist(BaseRepository._db)
    def insert_user(self, name, password, pris):
        """
        新增用户
        
        Args:
            name: 用户名
            password: 密码
            pris: 权限
        """
        if not name or not password:
            return
        if self.is_user_exists(name):
            return

        self._db.insert(CONFIGUSERS(
            NAME=name,
            PASSWORD=password,
            PRIS=pris
        ))

    @DbPersist(BaseRepository._db)
    def delete_user(self, name):
        """
        删除用户
        
        Args:
            name: 用户名
        """
        self._db.query(CONFIGUSERS).filter(CONFIGUSERS.NAME == name).delete()

"""
安全工具 - 与框架无关的安全/认证工具
供 Flask 和 FastAPI 共用
"""
import base64
import copy
import datetime
import hashlib
import hmac
import json
import os
import secrets
from typing import Optional, Tuple

import jwt
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
from cryptography.fernet import Fernet
from base64 import b64encode

import log
from app.infrastructure.cache_system import TokenCache
from config import Config

from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher

_pwd_hash = PasswordHash([Argon2Hasher()])


def get_secret_key() -> str:
    """
    统一获取安全密钥。
    优先从配置 security.jwt_secret 读取，
    其次从 app.web_secret_key 读取，
    若均不存在则生成密码学安全随机密钥并持久化到配置文件。
    """
    cfg = Config()
    secret = cfg.get_config("security").get("jwt_secret")
    if secret:
        return secret
    secret = cfg.get_config("app").get("web_secret_key")
    if secret:
        return secret

    # 使用 secrets 生成密码学安全随机密钥并持久化到 security.jwt_secret
    secret = secrets.token_urlsafe(32)
    new_cfg = copy.deepcopy(cfg.get_config())
    if "security" not in new_cfg:
        new_cfg["security"] = {}
    new_cfg["security"]["jwt_secret"] = secret
    cfg.save_config(new_cfg)
    return secret


def generate_password_hash(password: str) -> str:
    """生成密码哈希"""
    return _pwd_hash.hash(password)


def check_password_hash(password_hash: str, password: str) -> bool:
    """验证密码哈希"""
    if not password_hash:
        return False
    try:
        return _pwd_hash.verify(password, password_hash)
    except Exception:
        return False


def generate_access_token(username: str, algorithm: str = 'HS256', exp: float = 2) -> str:
    """
    生成access_token
    :param username: 用户名(自定义部分)
    :param algorithm: 加密算法
    :param exp: 过期时间，默认2小时
    :return:token
    """
    now = datetime.datetime.utcnow()
    exp_datetime = now + datetime.timedelta(hours=exp)
    access_payload = {
        'exp': exp_datetime,
        'iat': now,
        'username': username
    }
    secret = get_secret_key()
    access_token = jwt.encode(access_payload, secret, algorithm=algorithm)
    return access_token


def decode_auth_token(token: str, algorithms: str = 'HS256') -> Tuple[bool, dict]:
    """
    解密token
    :param token:token字符串
    :return: 是否有效，payload
    """
    key = get_secret_key()
    try:
        payload = jwt.decode(token, key=key, algorithms=algorithms)
    except jwt.ExpiredSignatureError:
        return False, jwt.decode(token, key=key, algorithms=algorithms, options={'verify_exp': False})
    except (jwt.DecodeError, jwt.InvalidTokenError, jwt.ImmatureSignatureError):
        return False, {}
    else:
        return True, payload


def identify(auth_header: str) -> Tuple[bool, str]:
    """
    用户鉴权，返回是否有效、用户名
    """
    flag = False
    if auth_header:
        flag, payload = decode_auth_token(auth_header)
        if payload:
            return flag, payload.get("username") or ""
    return flag, ""


def encrypt_message(message: str, key: str) -> str:
    """
    使用给定的key对消息进行加密，并返回加密后的字符串
    """
    f = Fernet(key)
    encrypted_message = f.encrypt(message.encode())
    return encrypted_message.decode()


def hash_sha256(message: str) -> str:
    """
    对字符串做hash运算
    """
    return hashlib.sha256(message.encode()).hexdigest()


def aes_decrypt(data: str, key: str) -> str:
    """
    AES解密
    """
    if not data:
        return ""
    data = base64.b64decode(data)
    iv = data[:16]
    encrypted = data[16:]
    # 使用AES-256-CBC解密
    cipher = AES.new(key.encode('utf-8'), AES.MODE_CBC, iv)
    result = cipher.decrypt(encrypted)
    # 去除填充
    padding = result[-1]
    if padding < 1 or padding > AES.block_size:
        return ""
    result = result[:-padding]
    return result.decode('utf-8')


def aes_encrypt(data: str, key: str) -> str:
    """
    AES加密
    """
    if not data:
        return ""
    # 使用AES-256-CBC加密
    cipher = AES.new(key.encode('utf-8'), AES.MODE_CBC)
    # 填充
    padding = AES.block_size - len(data) % AES.block_size
    data += chr(padding) * padding
    result = cipher.encrypt(data.encode('utf-8'))
    # 使用base64编码
    return b64encode(cipher.iv + result).decode('utf-8')


def nexusphp_encrypt(data_str: str, key: str) -> str:
    """
    NexusPHP加密
    """
    key_bytes = key.encode('utf-8')
    data_bytes = data_str.encode('utf-8')
    # 使用HMAC-SHA1加密
    signature = hmac.new(key_bytes, data_bytes, hashlib.sha1).digest()
    # 返回base64编码的结果
    return base64.b64encode(signature).decode('utf-8')


class TokenManager:
    """
    Token管理类
    """

    @staticmethod
    def get(token_key: str) -> Optional[str]:
        """从缓存获取token"""
        return TokenCache.get(token_key)

    @staticmethod
    def set(token_key: str, token_value: str) -> None:
        """设置token到缓存"""
        TokenCache.set(token_key, token_value)

    @staticmethod
    def delete(token_key: str) -> None:
        """删除token"""
        TokenCache.delete(token_key)

"""
RKLLM NPU WebUI - 登录安全模块
RSA 密钥对生成、加密载荷解密、密钥轮转。

私钥/公钥/开关均持久化在 settings 表，运行时动态生成与替换，
因此开启/关闭/轮转均即时生效，无需重启服务。
"""

import base64
import json

from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import serialization

from database import get_setting, set_setting

KEY_ENCRYPT_LOGIN = "encrypt_login"
KEY_PRIVATE_PEM = "rsa_private_key_pem"
KEY_PUBLIC_PEM = "rsa_public_key_pem"

RSA_KEY_SIZE = 2048


def generate_keypair():
    """生成 RSA 密钥对，返回 (private_pem_bytes, public_pem_bytes)"""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=RSA_KEY_SIZE)
    public_key = private_key.public_key()
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption())
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo)
    return private_pem, public_pem


def is_encrypt_enabled() -> bool:
    return get_setting(KEY_ENCRYPT_LOGIN, "0") == "1"


def get_public_key_pem():
    """返回公钥 PEM 字符串；未生成则返回 None"""
    return get_setting(KEY_PUBLIC_PEM, None)


def ensure_keypair():
    """确保存在密钥对，不存在则生成并入库。返回公钥 PEM 字符串"""
    pub = get_public_key_pem()
    if pub:
        return pub
    private_pem, public_pem = generate_keypair()
    set_setting(KEY_PRIVATE_PEM, private_pem.decode("utf-8"))
    set_setting(KEY_PUBLIC_PEM, public_pem.decode("utf-8"))
    return public_pem.decode("utf-8")


def enable_encrypt(enabled: bool) -> bool:
    """开启/关闭加密登录。开启时若无密钥则先生成。返回最终状态"""
    if enabled:
        ensure_keypair()
    set_setting(KEY_ENCRYPT_LOGIN, "1" if enabled else "0")
    return is_encrypt_enabled()


def rotate_keypair():
    """轮转密钥：生成新密钥对替换旧私钥。返回新公钥 PEM 字符串"""
    private_pem, public_pem = generate_keypair()
    set_setting(KEY_PRIVATE_PEM, private_pem.decode("utf-8"))
    set_setting(KEY_PUBLIC_PEM, public_pem.decode("utf-8"))
    return public_pem.decode("utf-8")


def decrypt_payload(ciphertext_b64: str) -> dict:
    """用私钥解密 base64 加密载荷，返回 dict；失败抛异常

    前端使用 jsencrypt（PKCS#1 v1.5 填充），故此处用 PKCS1v15 解密。
    """
    private_pem = get_setting(KEY_PRIVATE_PEM, None)
    if not private_pem:
        raise RuntimeError("no private key")
    private_key = serialization.load_pem_private_key(
        private_pem.encode("utf-8"), password=None)
    plaintext = private_key.decrypt(
        base64.b64decode(ciphertext_b64),
        padding.PKCS1v15())
    return json.loads(plaintext.decode("utf-8"))

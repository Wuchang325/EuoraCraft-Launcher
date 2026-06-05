from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from typing import Callable
from cryptography.hazmat.primitives import hashes
from cryptography.fernet import Fernet
from dataclasses import dataclass
from pathlib import Path
import keyring.errors
import requests
import keyring
import base64
import msal
import uuid
import json
import os
import time
import webbrowser
import threading
from concurrent.futures import ThreadPoolExecutor, Future

from ..Core.logger import get_logger
logger = get_logger(__name__)


@dataclass
class MinecraftAccount:
    alias: str
    account_id: str
    email: str
    profile: dict
    cache_file: str
    account_type: str = "microsoft"

    def to_dict(self) -> dict:
        return {
            "alias": self.alias,
            "account_id": self.account_id,
            "email": self.email,
            "profile": self.profile,
            "cache_file": self.cache_file,
            "account_type": self.account_type
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MinecraftAccount":
        return cls(
            alias=data["alias"],
            account_id=data["account_id"],
            email=data.get("email", ""),
            profile=data["profile"],
            cache_file=data.get("cache_file", ""),
            account_type=data.get("account_type", "microsoft")
        )

    def get_display_name(self) -> str:
        return self.alias or self.profile.get("name", "Unknown")

    def get_uuid(self) -> str:
        return self.profile.get("id", "")

    def get_skin_url(self) -> str | None:
        if self.account_type == "microsoft" and self.profile:
            skins = self.profile.get("skins", [])
            if skins:
                return skins[0].get("url")
        return None


# 自动选择合适的密钥环后端
class SmartKeyringManager:
    def __init__(self, service_name: str = "ECLAuth", log_callback: Callable[[str], None] | None = None):
        self.service_name = service_name
        self.backend_type: str = "unknown"
        self.log_callback = log_callback or print
        self._setup_smart_keyring()

    def _log(self, msg: str) -> None:
        self.log_callback(msg)

    def _setup_smart_keyring(self) -> None:
        backends = [
            self._try_system_keyring,
            self._try_encrypted_file_keyring,
            self._try_json_file_keyring,
            self._try_custom_fallback
        ]
        for backend in backends:
            if backend():
                self._log(f"密钥环后端: {self.backend_type}")
                return
        raise RuntimeError("无法初始化任何密钥环后端")

    def _try_system_keyring(self) -> bool:
        try:
            test_key = f"test_key_{hash(self.service_name)}"
            keyring.set_password(self.service_name, test_key, "test_value")
            result = keyring.get_password(self.service_name, test_key)
            keyring.delete_password(self.service_name, test_key)
            if result == "test_value":
                self.backend_type = "system"
                self._log("使用系统密钥环")
                return True
        except Exception as e:
            self._log(f"系统密钥环不可用: {e}")
        return False

    def _try_encrypted_file_keyring(self) -> bool:
        try:
            from keyrings.alt.file import EncryptedKeyring
            keyring_obj = EncryptedKeyring()
            test_key = "test_encrypted"
            keyring_obj.set_password(self.service_name, test_key, "test")
            result = keyring_obj.get_password(self.service_name, test_key)
            keyring_obj.delete_password(self.service_name, test_key)
            if result == "test":
                keyring.set_keyring(keyring_obj)
                self.backend_type = "encrypted_file"
                self._log("使用加密文件密钥环")
                return True
        except Exception as e:
            self._log(f"加密文件密钥环失败: {e}")
        return False

    def _try_json_file_keyring(self) -> bool:
        try:
            from keyrings.alt.file import JSONKeyring
            keyring_obj = JSONKeyring()
            test_key = "test_json"
            keyring_obj.set_password(self.service_name, test_key, "test")
            result = keyring_obj.get_password(self.service_name, test_key)
            keyring_obj.delete_password(self.service_name, test_key)
            if result == "test":
                keyring.set_keyring(keyring_obj)
                self.backend_type = "json_file"
                self._log("使用 JSON 密钥环")
                return True
        except Exception as e:
            self._log(f"JSON 密钥环失败: {e}")
        return False

    def _try_custom_fallback(self) -> bool:
        try:
            class CustomFallbackKeyring:
                def __init__(self):
                    self.storage_file = os.path.expanduser("~/.ECLAuth/custom_keyring.bin")
                    os.makedirs(os.path.dirname(self.storage_file), exist_ok=True)
                    self.key = Fernet.generate_key()
                    self.fernet = Fernet(self.key)

                def set_password(self, service: str, username: str, password: str) -> None:
                    data = f"{service}|{username}|{password}"
                    encrypted = self.fernet.encrypt(data.encode())
                    with open(self.storage_file, "ab") as f:
                        f.write(encrypted + b"\n")

                def get_password(self, service: str, username: str) -> str | None:
                    try:
                        with open(self.storage_file, "rb") as f:
                            for line in f:
                                try:
                                    decrypted = self.fernet.decrypt(line.strip()).decode()
                                    s, u, p = decrypted.split("|", 2)
                                    if s == service and u == username:
                                        return p
                                except Exception:
                                    continue
                    except FileNotFoundError:
                        pass
                    return None

            keyring.set_keyring(CustomFallbackKeyring())
            self.backend_type = "custom_fallback"
            self._log("使用自定义回退密钥环")
            return True
        except Exception as e:
            self._log(f"自定义回退失败: {e}")
        return False

    def get_backend_info(self) -> dict:
        return {
            "type": self.backend_type,
            "service": self.service_name,
            "secure": self.backend_type not in ["plaintext_file", "custom_fallback"]
        }


# 基于密码的 Fernet 加密，密钥存储在系统密钥环
class EncryptionManager:
    def __init__(self, service_name: str = "ECLAuth", log_callback: Callable[[str], None] | None = None,
                 first_launch_callback: Callable[[], str] | None = None):
        self.service_name = service_name
        self.data_dir = Path(os.path.expanduser("~/.ECLAuth"))
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.salt_file = self.data_dir / "encryption_salt.bin"
        self.log_callback = log_callback or print
        self.first_launch_callback = first_launch_callback or self._set_password
        self.keyring_manager = SmartKeyringManager(service_name, self._log)
        self.fernet: Fernet | None = None
        self._ensure_encryption_key()

    def _log(self, msg: str) -> None:
        self.log_callback(msg)

    def _set_password(self):
        while True:
            password = input("请输入主密码: ")
            confirm = input("请确认主密码: ")
            if password != confirm:
                self._log("两次输入的密码不一致，请重新输入")
                continue
            return password

    def _ensure_encryption_key(self) -> None:
        encryption_key = keyring.get_password(self.service_name, "encryption_key")
        if encryption_key:
            self.fernet = Fernet(encryption_key.encode())
            return
        self._log("请设置主密码")
        self._log(f"密钥环后端: {self.keyring_manager.backend_type}")
        while True:
            password = self.first_launch_callback()
            if len(password) < 8:
                self._log("密码长度至少8位")
                continue
            break
        self._generate_and_store_key(password)

    def change_password(self, new_password: str) -> Fernet:
        if not self.fernet:
            raise RuntimeError("加密管理器未初始化")
        old_fernet = self.fernet
        salt = self.salt_file.read_bytes() if self.salt_file.exists() else os.urandom(16)
        if not self.salt_file.exists():
            self.salt_file.write_bytes(salt)
        kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=100000)
        new_key = base64.urlsafe_b64encode(kdf.derive(new_password.encode()))
        keyring.set_password(self.service_name, "encryption_key", new_key.decode())
        self.fernet = Fernet(new_key)
        self._log("主密码已更新")
        return old_fernet

    def _generate_and_store_key(self, password: str) -> None:
        if self.salt_file.exists():
            salt = self.salt_file.read_bytes()
        else:
            salt = os.urandom(16)
            self.salt_file.write_bytes(salt)
        kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=100000)
        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        keyring.set_password(self.service_name, "encryption_key", key.decode())
        self.fernet = Fernet(key)
        backend_info = self.keyring_manager.get_backend_info()
        self._log("加密设置完成")
        if not backend_info["secure"]:
            self._log("当前使用安全性较低的后端")

    def encrypt_data(self, data: str) -> str:
        if not self.fernet:
            raise RuntimeError("加密管理器未初始化")
        encrypted = self.fernet.encrypt(data.encode())
        return base64.urlsafe_b64encode(encrypted).decode()

    def decrypt_data(self, encrypted_data: str) -> str:
        if not self.fernet:
            raise RuntimeError("加密管理器未初始化")
        try:
            encrypted_bytes = base64.urlsafe_b64decode(encrypted_data.encode())
            decrypted = self.fernet.decrypt(encrypted_bytes)
            return decrypted.decode()
        except Exception as e:
            raise ValueError(f"解密失败: {e}") from e


# 微软 OAuth + Xbox 认证链，支持多账户管理和加密存储
class MultiAccountMinecraftAuth:
    def __init__(self, client_id: str, data_dir: str = "~/.ECLAuth"):
        self.client_id = client_id
        self.data_dir = Path(os.path.expanduser(data_dir))
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._log_callback: Callable[[str], None] = logger.info
        self._login_log_callback: Callable[[str], None] = logger.info
        self._login_callback: Callable[[dict], None] = self._login_print
        self._first_launch_callback: Callable[[], str] | None = None
        self.encryption: EncryptionManager | None = None
        self.accounts: dict[str, MinecraftAccount] = {}
        self.current_account: MinecraftAccount | None = None
        self.accounts_file = self.data_dir / "accounts.json"
        self.current_account_file = self.data_dir / "current_account.txt"
        self._initialized = False

    def set_output_log(self, func: Callable[[str], None]) -> None:
        self._log_callback = func

    def set_output_login_log(self, func: Callable[[str], None]) -> None:
        self._login_log_callback = func

    def set_login_callback(self, func: Callable[[dict], None]) -> None:
        self._login_callback = func

    def set_first_launch_callback(self, func: Callable[[], str]) -> None:
        self._first_launch_callback = func

    def _log(self, msg: str) -> None:
        self._log_callback(msg)

    @staticmethod
    def _login_print(flow: dict):
        print(flow)
        print(f"请在浏览器访问：{flow['verification_uri']}，并在其中输入：{flow['user_code']}")

    # 初始化加密管理器并加载账户数据
    def initialize(self) -> bool:
        if self._initialized:
            self._log("已经初始化过，跳过")
            return True
        try:
            self.encryption = EncryptionManager(log_callback=self._log_callback, first_launch_callback=self._first_launch_callback)
            self._load_accounts()
            self._initialized = True
            self._log("初始化成功")
            return True
        except Exception as e:
            self._log(f"初始化失败: {e}")
            return False

    def _ensure_initialized(self) -> None:
        if not self._initialized:
            raise RuntimeError("请先调用 initialize()")

    # 从加密文件加载账户列表
    def _load_accounts(self) -> None:
        if not self.accounts_file.exists():
            return
        try:
            with open(self.accounts_file, "r") as f:
                accounts_data = json.load(f)
                for account_id, enc_data in accounts_data.items():
                    if isinstance(enc_data, str):
                        decrypted_data = self.encryption.decrypt_data(enc_data)
                        account_dict = json.loads(decrypted_data)
                        self.accounts[account_id] = MinecraftAccount.from_dict(account_dict)
            self._log(f"已加载 {len(self.accounts)} 个账户")
        except Exception as e:
            self._log(f"加载账户数据失败: {e}")
        if self.current_account_file.exists():
            try:
                with open(self.current_account_file, "r") as f:
                    current_id = f.read().strip()
                    if current_id in self.accounts:
                        self.current_account = self.accounts[current_id]
                        self._log(f"当前选中账户: {self.current_account.alias}")
            except Exception as e:
                self._log(f"加载当前账户失败: {e}")

    def _save_accounts(self) -> None:
        accounts_data = {}
        for account_id, account in self.accounts.items():
            encrypted = self.encryption.encrypt_data(json.dumps(account.to_dict()))
            accounts_data[account_id] = encrypted
        try:
            with open(self.accounts_file, "w") as f:
                json.dump(accounts_data, f, indent=2)
        except Exception as e:
            self._log(f"保存账户数据失败: {e}")

    # 设置当前活动账户并持久化
    def _set_current_account(self, account: MinecraftAccount) -> None:
        self.current_account = account
        try:
            with open(self.current_account_file, "w") as f:
                f.write(account.account_id)
        except Exception as e:
            self._log(f"保存当前账户设置失败: {e}")

    # 加载或创建加密的 MSAL 令牌缓存
    def _build_persistence_cache(self, cache_file: str) -> msal.SerializableTokenCache:
        cache_path = self.data_dir / "cache" / f"{cache_file}.bin"
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        token_cache = msal.SerializableTokenCache()
        if cache_path.exists():
            try:
                with open(cache_path, "r") as f:
                    encrypted = f.read()
                    decrypted = self.encryption.decrypt_data(encrypted)
                    token_cache.deserialize(decrypted)
            except Exception as e:
                self._log(f"加载加密缓存失败: {e}")
        token_cache.cache_path = str(cache_path)
        return token_cache

    # 持久化加密令牌缓存
    def _save_cache(self, token_cache: msal.SerializableTokenCache) -> None:
        if not hasattr(token_cache, "cache_path") or not token_cache.cache_path:
            return
        try:
            cache_data = token_cache.serialize()
            encrypted = self.encryption.encrypt_data(cache_data)
            with open(token_cache.cache_path, "w") as f:
                f.write(encrypted)
        except Exception as e:
            self._log(f"保存加密缓存失败: {e}")

    # 微软 OAuth 设备流：尝试静默刷新，否则引导浏览器登录
    def _get_microsoft_token(self, cache_file: str) -> tuple[str | None, str | None, str | None]:
        scope = ["XboxLive.signin"]
        token_cache = self._build_persistence_cache(cache_file)
        app = msal.PublicClientApplication(
            client_id=self.client_id,
            authority="https://login.microsoftonline.com/consumers",
            token_cache=token_cache
        )
        accounts = app.get_accounts()
        result = None
        account_info = None
        email = None
        if accounts:
            self._login_log_callback("尝试静默获取令牌...")
            account_info = accounts[0]
            result = app.acquire_token_silent(scopes=scope, account=account_info)
        if not result:
            self._login_log_callback("开始设备代码流登录...")
            try:
                flow = app.initiate_device_flow(scopes=scope)
                if "user_code" not in flow:
                    raise ValueError("未能创建设备流")
                self._login_callback(flow)
                result = app.acquire_token_by_device_flow(flow)
                if result and "id_token_claims" in result:
                    id_claims = result["id_token_claims"]
                    email = id_claims.get("preferred_username") or id_claims.get("email")
            except Exception as e:
                self._login_log_callback(f"设备代码流失败: {e}")
                return None, None, None
        if "access_token" in result:
            self._login_log_callback("微软令牌获取成功")
            self._save_cache(token_cache)
            account_id = account_info.get("home_account_id") if account_info else None
            return result["access_token"], account_id, email
        else:
            self._login_log_callback(f"认证失败: {result.get('error')}")
            return None, None, None

    # Xbox Live -> XSTS 令牌链，获取用户哈希
    def _get_xbox_chain_tokens(self, msft_access_token: str) -> tuple[str | None, str | None]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        try:
            resp = requests.post(
                "https://user.auth.xboxlive.com/user/authenticate",
                json={
                    "Properties": {"AuthMethod": "RPS", "SiteName": "user.auth.xboxlive.com", "RpsTicket": f"d={msft_access_token}"},
                    "RelyingParty": "http://auth.xboxlive.com",
                    "TokenType": "JWT"
                },
                headers=headers
            )
            if resp.status_code != 200:
                self._login_log_callback(f"Xbox Live 令牌获取失败: {resp.status_code}")
                return None, None
            xbox_live_data = resp.json()
            xbox_live_token = xbox_live_data["Token"]
            user_hash = xbox_live_data["DisplayClaims"]["xui"][0]["uhs"]
            self._login_log_callback("Xbox Live 令牌获取成功")
            resp = requests.post(
                "https://xsts.auth.xboxlive.com/xsts/authorize",
                json={
                    "Properties": {"SandboxId": "RETAIL", "UserTokens": [xbox_live_token]},
                    "RelyingParty": "rp://api.minecraftservices.com/",
                    "TokenType": "JWT"
                },
                headers=headers
            )
            if resp.status_code != 200:
                self._login_log_callback(f"XSTS 令牌获取失败: {resp.status_code}")
                return None, None
            xsts_token = resp.json()["Token"]
            self._login_log_callback("XSTS 令牌获取成功")
            return xsts_token, user_hash
        except Exception as e:
            self._login_log_callback(f"Xbox 认证链失败: {e}")
            return None, None

    # 用 XSTS 令牌换取 Minecraft 访问令牌
    def _get_minecraft_token(self, xsts_token: str, user_hash: str) -> str | None:
        try:
            resp = requests.post(
                "https://api.minecraftservices.com/authentication/login_with_xbox",
                json={"identityToken": f"XBL3.0 x={user_hash};{xsts_token}"},
                headers={"Content-Type": "application/json"}
            )
            if resp.status_code != 200:
                self._login_log_callback(f"Minecraft 令牌获取失败: {resp.status_code}")
                return None
            self._login_log_callback("Minecraft 令牌获取成功")
            return resp.json()["access_token"]
        except Exception as e:
            self._login_log_callback(f"Minecraft 令牌获取失败: {e}")
            return None

    # 验证账户是否拥有 Minecraft Java 版
    def _check_minecraft_ownership(self, mc_access_token: str) -> tuple[bool, dict | None]:
        try:
            resp = requests.get(
                "https://api.minecraftservices.com/minecraft/profile",
                headers={"Authorization": f"Bearer {mc_access_token}"}
            )
            if resp.status_code == 200:
                profile = resp.json()
                self._login_log_callback(f"Minecraft 所有权验证成功: {profile['name']}")
                return True, profile
            elif resp.status_code == 404:
                self._login_log_callback("该账户未购买 Minecraft Java 版")
                return False, None
            else:
                self._login_log_callback(f"验证失败: {resp.status_code}")
                return False, None
        except Exception as e:
            self._login_log_callback(f"验证失败: {e}")
            return False, None

    # 完整微软登录流程：OAuth -> Xbox -> Minecraft -> 验证所有权
    def add_account(self) -> bool:
        self._ensure_initialized()
        cache_file = f"account_{uuid.uuid4().hex[:8]}"
        ms_token, account_id, email = self._get_microsoft_token(cache_file)
        if not ms_token:
            return False
        xsts_token, user_hash = self._get_xbox_chain_tokens(ms_token)
        if not xsts_token:
            return False
        mc_token = self._get_minecraft_token(xsts_token, user_hash)
        if not mc_token:
            return False
        has_minecraft, profile = self._check_minecraft_ownership(mc_token)
        if not has_minecraft:
            cache_path = self.data_dir / "cache" / f"{cache_file}.bin"
            if cache_path.exists():
                cache_path.unlink()
            return False
        alias = profile["name"]
        if not account_id:
            account_id = f"account_{len(self.accounts) + 1}"
        
        # 重复检测：检查是否已存在相同的微软账户（account_id 相同）
        if account_id in self.accounts:
            self._log(f"微软账户 '{alias}' 已存在")
            # 清理临时缓存文件
            cache_path = self.data_dir / "cache" / f"{cache_file}.bin"
            if cache_path.exists():
                cache_path.unlink()
            return False
        
        # 重复检测：检查是否已存在相同玩家名的微软账户
        for existing_account in self.accounts.values():
            if existing_account.account_type == "microsoft" and existing_account.alias == alias:
                self._log(f"玩家名 '{alias}' 的微软账户已存在")
                # 清理临时缓存文件
                cache_path = self.data_dir / "cache" / f"{cache_file}.bin"
                if cache_path.exists():
                    cache_path.unlink()
                return False
        
        account = MinecraftAccount(
            alias=alias,
            account_id=account_id,
            email=email or "未知",
            profile=profile,
            cache_file=cache_file
        )
        self.accounts[account_id] = account
        self._save_accounts()
        if len(self.accounts) == 1:
            self._set_current_account(account)
        self._log(f"账户 '{alias}' 添加成功")
        return True

    # 添加离线账户（无需微软认证，用于单机游玩）
    def add_offline_account(self, username: str) -> dict:
        """添加离线账户，返回包含详细信息的字典"""
        self._ensure_initialized()
        if not username or not username.strip():
            self._log("用户名不能为空")
            return {"success": False, "message": "用户名不能为空"}
        username = username.strip()
        
        # 重复检测：检查是否已存在相同玩家名的账户（任何类型）
        for account in self.accounts.values():
            if account.alias == username:
                if account.account_type == "offline":
                    msg = f"离线账户 '{username}' 已存在"
                else:
                    msg = f"玩家名 '{username}' 已被微软账户使用"
                self._log(msg)
                return {"success": False, "message": msg}
        
        import hashlib
        offline_uuid_str = hashlib.md5(f"OfflinePlayer:{username}".encode("utf-8")).hexdigest()
        formatted_uuid = f"{offline_uuid_str[:8]}-{offline_uuid_str[8:12]}-{offline_uuid_str[12:16]}-{offline_uuid_str[16:20]}-{offline_uuid_str[20:32]}"
        account_id = f"offline_{uuid.uuid4().hex[:8]}"
        profile = {"name": username, "id": formatted_uuid, "offline": True}
        account = MinecraftAccount(
            alias=username,
            account_id=account_id,
            email="",
            profile=profile,
            cache_file="",
            account_type="offline"
        )
        self.accounts[account_id] = account
        self._save_accounts()
        if len(self.accounts) == 1:
            self._set_current_account(account)
        self._log(f"离线账户 '{username}' 添加成功")
        return {"success": True, "message": f"离线账户 '{username}' 添加成功"}

    # 获取所有已保存账户
    def list_accounts(self) -> list | None:
        self._ensure_initialized()
        if not self.accounts:
            self._log("暂无已保存的账户")
            return None
        return list(self.accounts.items())

    def get_current_account(self) -> MinecraftAccount | None:
        return self.current_account

    # 切换到指定账户
    def switch_account(self, account_id: str) -> bool:
        self._ensure_initialized()
        if account_id in self.accounts:
            account = self.accounts[account_id]
            self._set_current_account(account)
            self._log(f"已切换到账户: {account.alias}")
            return True
        self._log(f"未找到账户: {account_id}")
        return False

    # 删除账户并清理缓存文件
    def remove_account(self, account_id: str) -> bool:
        self._ensure_initialized()
        if account_id not in self.accounts:
            self._log(f"未找到账户: {account_id}")
            return False
        target_account = self.accounts[account_id]
        if target_account.account_type == "microsoft" and target_account.cache_file:
            cache_path = self.data_dir / "cache" / f"{target_account.cache_file}.bin"
            if cache_path.exists():
                cache_path.unlink()
        del self.accounts[account_id]
        self._save_accounts()
        if self.current_account and self.current_account.account_id == account_id:
            self.current_account = None
            if self.current_account_file.exists():
                self.current_account_file.unlink()
        self._log(f"账户 '{target_account.alias}' 已移除")
        return True

    def get_account_id_by_alias(self, alias: str) -> str | None:
        self._ensure_initialized()
        for account_id, account in self.accounts.items():
            if account.alias == alias:
                return account_id
        return None

    def switch_account_by_alias(self, account_alias: str) -> bool:
        account_id = self.get_account_id_by_alias(account_alias)
        if account_id:
            return self.switch_account(account_id)
        self._log(f"未找到账户: {account_alias}")
        return False

    def remove_account_by_alias(self, account_alias: str) -> bool:
        account_id = self.get_account_id_by_alias(account_alias)
        if account_id:
            return self.remove_account(account_id)
        self._log(f"未找到账户: {account_alias}")
        return False

    def get_account_by_id(self, account_id: str) -> MinecraftAccount | None:
        self._ensure_initialized()
        return self.accounts.get(account_id)

    # 获取当前账户的 Minecraft 令牌（实时刷新，离线账户返回 OFFLINE）
    def get_current_account_token(self) -> str | None:
        self._ensure_initialized()
        if not self.current_account:
            self._log("未选择任何账户")
            return None
        if self.current_account.account_type == "offline":
            self._log(f"离线账户 '{self.current_account.alias}' 无需获取令牌")
            return "OFFLINE"
        self._log(f"正在为账户 {self.current_account.alias} 获取 Minecraft 令牌...")
        ms_token, _, _ = self._get_microsoft_token(self.current_account.cache_file)
        if not ms_token:
            self._login_log_callback("获取微软令牌失败")
            return None
        xsts_token, user_hash = self._get_xbox_chain_tokens(ms_token)
        if not xsts_token:
            self._login_log_callback("Xbox 认证链失败")
            return None
        mc_token = self._get_minecraft_token(xsts_token, user_hash)
        if not mc_token:
            self._login_log_callback("获取 Minecraft 令牌失败")
            return None
        is_valid, profile = self._check_minecraft_ownership(mc_token)
        if not is_valid:
            self._login_log_callback("Minecraft 令牌验证失败")
            return None
        if profile and profile["name"] != self.current_account.alias:
            self._log(f"玩家 ID 变化: {self.current_account.alias} -> {profile['name']}")
            self.current_account.alias = profile["name"]
            self.current_account.profile = profile
            self._save_accounts()
        return mc_token

    # 刷新指定账户的玩家档案（检测改名等变化）
    def refresh_account_profile(self, account_alias: str) -> bool:
        self._ensure_initialized()
        for account in self.accounts.values():
            if account.alias != account_alias:
                continue
            self._log(f"刷新账户档案: {account.alias}")
            ms_token, _, _ = self._get_microsoft_token(account.cache_file)
            if not ms_token:
                self._login_log_callback("获取微软令牌失败")
                return False
            xsts_token, user_hash = self._get_xbox_chain_tokens(ms_token)
            if not xsts_token:
                return False
            mc_token = self._get_minecraft_token(xsts_token, user_hash)
            if not mc_token:
                return False
            is_valid, profile = self._check_minecraft_ownership(mc_token)
            if not is_valid:
                return False
            old_alias = account.alias
            account.profile = profile
            if profile["name"] != old_alias:
                self._log(f"更新账户别名: {old_alias} -> {profile['name']}")
                account.alias = profile["name"]
            self._save_accounts()
            self._log(f"{old_alias} 档案已更新")
            return True
        self._log(f"未找到账户: {account_alias}")
        return False

    # 刷新所有账户档案
    def refresh_all_account_profiles(self) -> None:
        self._ensure_initialized()
        updated = 0
        for account in list(self.accounts.values()):
            self._log(f"刷新账户档案: {account.alias}")
            if self.refresh_account_profile(account.alias):
                updated += 1
            else:
                self._log(f"{account.alias} 档案刷新失败")
        self._log(f"档案刷新完成，成功更新 {updated}/{len(self.accounts)} 个账户")

    # 修改主密码并重新加密所有数据
    def change_master_password(self, new_password: str) -> bool:
        if len(new_password) < 8:
            self._log("密码长度至少8位")
            return False
        self._ensure_initialized()
        old_fernet = self.encryption.fernet
        try:
            new_fernet = self.encryption.change_password(new_password)
        except Exception as e:
            self._log(f"更改密码失败: {e}")
            return False
        self._log("重新加密缓存文件...")
        success = 0
        total = len(self.accounts)
        for account in self.accounts.values():
            cache_path = self.data_dir / "cache" / f"{account.cache_file}.bin"
            if cache_path.exists():
                try:
                    with open(cache_path, "r") as f:
                        encrypted_data = f.read()
                    decrypted_bytes = old_fernet.decrypt(base64.urlsafe_b64decode(encrypted_data.encode()))
                    decrypted_data = decrypted_bytes.decode()
                    new_encrypted = new_fernet.encrypt(decrypted_data.encode())
                    new_encrypted_b64 = base64.urlsafe_b64encode(new_encrypted).decode()
                    with open(cache_path, "w") as f:
                        f.write(new_encrypted_b64)
                    success += 1
                except Exception as e:
                    self._log(f"重新加密账户 {account.alias} 的缓存失败: {e}")
        self._save_accounts()
        self._log(f"主密码更改完成，成功重新加密 {success}/{total} 个账户")
        return True

    # 获取当前账户档案（可选实时刷新）
    def get_current_account_profile(self, refresh: bool = False) -> dict | None:
        self._ensure_initialized()
        if not self.current_account:
            self._log("未选择任何账户")
            return None
        if refresh:
            if self.refresh_account_profile(self.current_account.alias):
                return self.current_account.profile
            return None
        return self.current_account.profile

    # 获取所有账户档案映射
    def get_all_accounts_profiles(self, refresh: bool = False) -> dict[str, dict]:
        self._ensure_initialized()
        profiles = {}
        if refresh:
            self.refresh_all_account_profiles()
        for alias, account in self.accounts.items():
            profiles[alias] = account.profile
        return profiles

    # 获取供前端展示的账户信息列表（含当前选中状态）
    def get_all_accounts_info(self) -> list[dict]:
        self._ensure_initialized()
        accounts_info = []
        current_id = self.current_account.account_id if self.current_account else None
        for account_id, account in self.accounts.items():
            info = {
                "id": account_id,
                "alias": account.alias,
                "type": account.account_type,
                "email": account.email if account.account_type == "microsoft" else "",
                "uuid": account.get_uuid(),
                "isCurrent": account_id == current_id,
                "skinUrl": account.get_skin_url()
            }
            accounts_info.append(info)
        accounts_info.sort(key=lambda x: (not x["isCurrent"], x["type"] == "offline", x["alias"].lower()))
        return accounts_info

    # 开始异步微软登录，返回设备代码供前端显示
    def start_microsoft_login(self) -> dict:
        self._ensure_initialized()
        cache_file = f"account_{uuid.uuid4().hex[:8]}"
        scope = ["XboxLive.signin"]
        token_cache = self._build_persistence_cache(cache_file)
        app = msal.PublicClientApplication(
            client_id=self.client_id,
            authority="https://login.microsoftonline.com/consumers",
            token_cache=token_cache
        )
        accounts = app.get_accounts()
        if accounts:
            result = app.acquire_token_silent(scopes=scope, account=accounts[0])
            if result and "access_token" in result:
                self._save_cache(token_cache)
                return {"status": "success", "cache_file": cache_file}
        flow = app.initiate_device_flow(scopes=scope)
        if "user_code" not in flow:
            return {"status": "error", "message": "创建设备流失败"}
        self._pending_flow = flow
        self._pending_cache_file = cache_file
        self._pending_app = app
        # 重置轮询状态
        self._poll_interval = flow.get("interval", 5)
        self._poll_expires_at = flow.get("expires_at", 0)
        return {
            "status": "pending",
            "userCode": flow["user_code"],
            "verificationUri": flow["verification_uri"],
            "message": flow.get("message", ""),
            "interval": self._poll_interval
        }

    # 轮询检测微软登录状态（非阻塞检查）
    def poll_microsoft_login(self) -> dict:
        """检查登录状态，返回是否已完成授权（不消耗 device_code）"""
        self._ensure_initialized()
        if not hasattr(self, "_pending_flow") or not self._pending_flow:
            return {"status": "error", "message": "没有待处理的登录流程"}
        
        # 检查是否已过期
        if hasattr(self, "_poll_expires_at") and time.time() > self._poll_expires_at:
            self._cleanup_pending_login()
            return {"status": "error", "message": "登录超时，请重试"}
        
        # 检查是否已有结果（之前已成功获取token）
        if hasattr(self, "_poll_result") and self._poll_result:
            return {"status": "ready", "message": "授权完成，等待完成登录"}
        
        # 检查后台任务状态
        if hasattr(self, "_poll_future") and self._poll_future:
            if self._poll_future.done():
                try:
                    result = self._poll_future.result()
                    
                    # 检查错误类型
                    error = result.get("error")
                    if error == "authorization_pending":
                        # 用户还未授权，重置 future 允许下次重新尝试
                        self._poll_future = None
                        return {"status": "pending", "message": "等待用户授权..."}
                    elif error:
                        # 其他错误
                        self._cleanup_poll()
                        return {"status": "error", "message": result.get("error_description", f"登录失败: {error}")}
                    
                    # 成功获取访问令牌，保存结果
                    if "access_token" in result:
                        self._poll_result = result
                        return {"status": "ready", "message": "授权完成，等待完成登录"}
                    
                    # 重置 future 允许下次重新尝试
                    self._poll_future = None
                    return {"status": "pending", "message": "等待用户授权..."}
                    
                except Exception as e:
                    error_str = str(e)
                    if "authorization_pending" in error_str or "AADSTS70016" in error_str:
                        # 用户还未授权，重置 future 允许下次重新尝试
                        self._poll_future = None
                        return {"status": "pending", "message": "等待用户授权..."}
                    # 其他错误
                    self._cleanup_poll()
                    return {"status": "error", "message": f"轮询出错: {error_str}"}
            else:
                # 任务仍在运行
                return {"status": "pending", "message": "等待用户授权..."}
        
        # 没有正在运行的任务，启动新的后台任务
        try:
            if not hasattr(self, "_poll_executor") or self._poll_executor is None:
                self._poll_executor = ThreadPoolExecutor(max_workers=1)
            
            # 提交后台任务执行 MSAL 的阻塞调用
            self._poll_future = self._poll_executor.submit(
                self._pending_app.acquire_token_by_device_flow,
                self._pending_flow
            )
            
            # 立即返回等待状态
            return {"status": "pending", "message": "等待用户授权..."}
            
        except Exception as e:
            error_str = str(e)
            logger.error(f"启动轮询任务失败: {error_str}")
            return {"status": "pending", "message": "等待用户授权..."}
    
    def _cleanup_poll(self):
        """清理轮询状态"""
        if hasattr(self, "_poll_future"):
            if self._poll_future and not self._poll_future.done():
                self._poll_future.cancel()
            self._poll_future = None
            delattr(self, "_poll_future")
        if hasattr(self, "_poll_executor") and self._poll_executor is not None:
            self._poll_executor.shutdown(wait=False)
            self._poll_executor = None
            delattr(self, "_poll_executor")
    
    def _cleanup_pending_login(self):
        """清理待处理的登录状态"""
        self._cleanup_poll()
        self._pending_flow = None
        self._pending_app = None
        self._poll_result = None
        if hasattr(self, "_pending_cache_file"):
            self._pending_cache_file = None
    
    def open_browser_for_auth(self, url: str) -> bool:
        """使用系统默认浏览器打开授权页面"""
        try:
            webbrowser.open(url)
            return True
        except Exception as e:
            logger.error(f"打开浏览器失败: {e}")
            return False

    # 完成异步微软登录（用户已在浏览器授权后调用）
    def complete_microsoft_login(self) -> dict:
        self._ensure_initialized()
        if not hasattr(self, "_pending_flow") or not self._pending_flow:
            return {"success": False, "message": "没有待处理的登录流程"}
        try:
            # 优先使用轮询过程中保存的结果
            if hasattr(self, "_poll_result") and self._poll_result:
                result = self._poll_result
                self._poll_result = None
            else:
                result = self._pending_app.acquire_token_by_device_flow(self._pending_flow)
            
            if "access_token" not in result:
                return {"success": False, "message": f"登录失败: {result.get('error_description', '未知错误')}"}
            email = ""
            if "id_token_claims" in result:
                id_claims = result["id_token_claims"]
                email = id_claims.get("preferred_username") or id_claims.get("email", "")
            ms_token = result["access_token"]
            xsts_token, user_hash = self._get_xbox_chain_tokens(ms_token)
            if not xsts_token:
                return {"success": False, "message": "Xbox 认证失败"}
            mc_token = self._get_minecraft_token(xsts_token, user_hash)
            if not mc_token:
                return {"success": False, "message": "Minecraft 认证失败"}
            has_minecraft, profile = self._check_minecraft_ownership(mc_token)
            if not has_minecraft:
                cache_path = self.data_dir / "cache" / f"{self._pending_cache_file}.bin"
                if cache_path.exists():
                    cache_path.unlink()
                return {"success": False, "message": "该账户未购买 Minecraft Java 版"}
            alias = profile["name"]
            account_id = result.get("id_token_claims", {}).get("home_account_id") or f"account_{len(self.accounts) + 1}"
            
            # 重复检测：检查是否已存在相同的微软账户（account_id 相同）
            if account_id in self.accounts:
                cache_path = self.data_dir / "cache" / f"{self._pending_cache_file}.bin"
                if cache_path.exists():
                    cache_path.unlink()
                self._cleanup_pending_login()
                return {"success": False, "message": f"微软账户 '{alias}' 已存在"}
            
            # 重复检测：检查是否已存在相同玩家名的微软账户
            for existing_account in self.accounts.values():
                if existing_account.account_type == "microsoft" and existing_account.alias == alias:
                    cache_path = self.data_dir / "cache" / f"{self._pending_cache_file}.bin"
                    if cache_path.exists():
                        cache_path.unlink()
                    self._cleanup_pending_login()
                    return {"success": False, "message": f"玩家名 '{alias}' 的微软账户已存在"}
            
            account = MinecraftAccount(
                alias=alias,
                account_id=account_id,
                email=email or "未知",
                profile=profile,
                cache_file=self._pending_cache_file,
                account_type="microsoft"
            )
            self.accounts[account_id] = account
            self._save_accounts()
            self._save_cache(self._pending_app.token_cache)
            if len(self.accounts) == 1:
                self._set_current_account(account)
            self._cleanup_pending_login()
            return {
                "success": True,
                "message": f"账户 '{alias}' 添加成功",
                "account": {"id": account_id, "alias": alias, "type": "microsoft", "email": email}
            }
        except Exception as e:
            return {"success": False, "message": f"登录过程出错: {e}"}



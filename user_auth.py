import os
import json
import re
import hashlib
import hmac
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List


class AuthError(Exception):
    pass


class UserAuth:
    """
    Файловая аутентификация с PBKDF2-HMAC и ролями. Пароли сохраняются в явном виде
    для просмотра администратором (по требованию), а также в виде хэшей для проверки.

    - Данные хранятся в JSON: {"users": {"username": {...}}}
    - Пароль хранится в открытом виде в поле "password" и верифицируется по хэшу.
    - Первый пользователь получает роль admin.
    - Создание пользователей выполняет только администратор (кроме самого первого).
    - API: create_user, authenticate, list_users, delete_user, set_admin
    """

    def __init__(self, users_file: Optional[str] = None):
        base_dir = os.path.dirname(__file__)
        if users_file is None:
            users_file = os.path.join(base_dir, "auth", "users.json")
        self.users_file = users_file
        os.makedirs(os.path.dirname(self.users_file), exist_ok=True)
        if not os.path.exists(self.users_file):
            with open(self.users_file, "w", encoding="utf-8") as f:
                json.dump({"users": {}}, f, ensure_ascii=False, indent=2)

        # Параметры PBKDF2
        self._algo = "sha256"
        self._iterations = 200_000
        self._salt_bytes = 16

        # Разрешённый паттерн логина
        self._re_username = re.compile(r"^[A-Za-z0-9_.-]{3,64}$")

    # ===== Внутренние утилиты =====
    def _load(self) -> Dict[str, Any]:
        with open(self.users_file, "r", encoding="utf-8") as f:
            return json.load(f)

    def _save(self, data: Dict[str, Any]):
        tmp = self.users_file + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.users_file)

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _new_salt(self) -> bytes:
        return os.urandom(self._salt_bytes)

    def _hash_password(self, password: str, salt: bytes) -> str:
        dk = hashlib.pbkdf2_hmac(self._algo, password.encode("utf-8"), salt, self._iterations)
        return dk.hex()

    def _verify_password(self, password: str, salt_hex: str, hash_hex: str) -> bool:
        salt = bytes.fromhex(salt_hex)
        calc = self._hash_password(password, salt)
        return hmac.compare_digest(calc, hash_hex)

    # ===== Публичное API =====
    def create_user(self, username: str, password: str, by_username: Optional[str] = None) -> Dict[str, Any]:
        """Создать пользователя. Требует прав администратора, кроме случая, когда в системе нет ни одного пользователя."""
        if not self._re_username.match(username or ""):
            raise AuthError("Некорректное имя пользователя. Разрешены буквы/цифры/._-, длина 3-64.")
        if not password or len(password) < 6:
            raise AuthError("Слишком короткий пароль (минимум 6 символов).")

        data = self._load()
        users = data.get("users", {})
        if username in users:
            raise AuthError("Пользователь уже существует.")

        is_first_user = (len(users) == 0)
        if not is_first_user:
            # Проверка прав инициатора
            actor = users.get(by_username or "")
            if not actor or not actor.get("is_admin"):
                raise AuthError("Создавать пользователей может только администратор.")

        salt = self._new_salt()
        created_at = self._now_iso()
        users[username] = {
            "salt": salt.hex(),
            "hash": self._hash_password(password, salt),
            "password": password,  # хранение открытого пароля — по требованию
            "is_admin": bool(is_first_user),
            "created_at": created_at,
            "disabled": False,
        }
        data["users"] = users
        self._save(data)
        return {"username": username, "is_admin": users[username]["is_admin"], "created_at": created_at}

    def authenticate(self, username: str, password: str) -> Dict[str, Any]:
        data = self._load()
        users = data.get("users", {})
        info = users.get(username)
        if not info or info.get("disabled"):
            raise AuthError("Неверные учетные данные.")
        if not self._verify_password(password, info["salt"], info["hash"]):
            raise AuthError("Неверные учетные данные.")
        return {"username": username, "is_admin": bool(info.get("is_admin"))}

    def list_users(self) -> List[Dict[str, Any]]:
        data = self._load()
        result = []
        for name, info in sorted(data.get("users", {}).items()):
            result.append({
                "username": name,
                "is_admin": bool(info.get("is_admin")),
                "disabled": bool(info.get("disabled")),
                "created_at": info.get("created_at"),
                "password": info.get("password"),
            })
        return result

    def delete_user(self, target_username: str, by_username: str):
        data = self._load()
        users = data.get("users", {})
        actor = users.get(by_username)
        if not actor or not actor.get("is_admin"):
            raise AuthError("Недостаточно прав для удаления пользователя.")
        if target_username == by_username:
            raise AuthError("Нельзя удалить самого себя.")
        if target_username not in users:
            raise AuthError("Пользователь не найден.")

        # Запретим удалять единственного администратора
        admins = [u for u, inf in users.items() if inf.get("is_admin")]
        if target_username in admins and len(admins) == 1:
            raise AuthError("Нельзя удалить единственного администратора.")

        del users[target_username]
        data["users"] = users
        self._save(data)

    def set_admin(self, target_username: str, is_admin: bool, by_username: str):
        data = self._load()
        users = data.get("users", {})
        actor = users.get(by_username)
        if not actor or not actor.get("is_admin"):
            raise AuthError("Недостаточно прав для изменения ролей.")
        if target_username not in users:
            raise AuthError("Пользователь не найден.")
        users[target_username]["is_admin"] = bool(is_admin)
        self._save(data)

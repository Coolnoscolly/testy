import json
import os
import threading
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any


class SessionAuditManager:
    """
    Структурированный аудит/лог в формате JSONL с единым контекстом.

    Особенности:
    - Каждая запись обогащается контекстом: session_id, user_id, client_uid.
    - Поддержка request_id для корреляции связанных событий (например, один вопрос/ответ).
    - Потокобезопасная запись. Ошибки логирования не прерывают работу приложения.
    - Минимальные зависимости (только стандартная библиотека).
    """

    def __init__(self, log_file: str = "audit.log"):
        self.log_file = log_file
        base_dir = os.path.dirname(self.log_file)
        if base_dir:
            os.makedirs(base_dir, exist_ok=True)
        self._lock = threading.Lock()
        # Контекст добавляется к каждой записи
        self._context: Dict[str, Any] = {
            "session_id": None,
            "user_id": None,
            "client_uid": None,
        }

    # ===== Внутренние утилиты =====
    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _append_jsonl(self, record: Dict[str, Any]) -> None:
        # слить с контекстом, но не перетирать уже заданные поля в record
        enriched = {**self._context, **record}
        enriched.setdefault("timestamp", self._now_iso())
        try:
            with self._lock:
                with open(self.log_file, "a", encoding="utf-8") as f:
                    f.write(json.dumps(enriched, ensure_ascii=False) + "\n")
        except Exception:
            # Не нарушаем ход программы из-за ошибок логирования
            pass

    # ===== API контекста =====
    def set_context(self, session_id: Optional[str] = None, user_id: Optional[str] = None, client_uid: Optional[str] = None):
        """Установка/обновление контекста, который будет добавляться ко всем событиям."""
        if session_id is not None:
            self._context["session_id"] = session_id
        if user_id is not None:
            self._context["user_id"] = user_id
        if client_uid is not None:
            self._context["client_uid"] = client_uid

    def clear_context(self):
        """Сброс контекста (например, при logout)."""
        self._context.update({
            "session_id": None,
            "user_id": None,
            "client_uid": None,
        })

    def new_request_id(self) -> str:
        """Генерирует новый request_id для корреляции событий одного запроса."""
        return str(uuid.uuid4())

    # ===== События =====
    def heartbeat(self):
        self._append_jsonl({
            "kind": "heartbeat",
            "level": "info",
        })

    def log_event(self, name: str, payload: Optional[Dict[str, Any]] = None, level: str = "info", request_id: Optional[str] = None):
        self._append_jsonl({
            "kind": "event",
            "event": name,
            "level": level,
            "request_id": request_id,
            "data": payload or {},
        })

    def log_error(self, name: str, payload: Optional[Dict[str, Any]] = None, request_id: Optional[str] = None):
        self.log_event(name=name, payload=payload, level="error", request_id=request_id)

    def log_warning(self, name: str, payload: Optional[Dict[str, Any]] = None, request_id: Optional[str] = None):
        self.log_event(name=name, payload=payload, level="warning", request_id=request_id)

    # Сервисные события для обратной совместимости вызовов
    def remove_session_from_registry(self, session_id: Optional[str]):
        # Исторический вызов теперь просто логирует событие
        self._append_jsonl({
            "kind": "event",
            "event": "session_removed",
            "level": "info",
            "data": {"session_id": session_id},
        })

    def cleanup_expired_sessions(self, vector_manager=None):
        # Регистра больше нет — только разовый лог вызова
        self._append_jsonl({
            "kind": "event",
            "event": "cleanup_skipped",
            "level": "info",
            "data": {"reason": "registry_removed"},
        })

import streamlit as st
try:
    st.set_page_config(page_title="RAG Admin", layout="wide")
except Exception:
    pass
import logging
import os
import hashlib
import uuid
import string
import json
from typing import Optional
from document_manager import DocumentManager
from vector_store_manager import VectorStoreManager
from rag_chain import RAGChainManager
from audit import SessionAuditManager
from user_auth import UserAuth, AuthError

# Конфигурация приложения
MAX_UPLOADS = int(os.getenv("MAX_UPLOADS", "5"))


class ChatInterface:
    def __init__(self):
        self.document_manager = DocumentManager()
        self.vector_manager = VectorStoreManager()
        self.rag_manager = RAGChainManager()
        self.audit = SessionAuditManager()
        self.auth = UserAuth()

        # Инициализация состояния сессии
        if "uploaded_files" not in st.session_state:
            st.session_state.uploaded_files = {}

        if "saved_collections" not in st.session_state:
            st.session_state.saved_collections = set()

        if "active_collections" not in st.session_state:
            st.session_state.active_collections = set()

        if "rag_chain" not in st.session_state:
            st.session_state.rag_chain = None

        if "chat_history" not in st.session_state:
            st.session_state.chat_history = []
        if "active_collection" not in st.session_state:
            st.session_state.active_collection = None
        if "session_id" not in st.session_state:
            st.session_state.session_id = str(uuid.uuid4())
        if "user_id" not in st.session_state:
            st.session_state.user_id = None  # username после входа
        if "is_admin" not in st.session_state:
            st.session_state.is_admin = False
        if "client_uid" not in st.session_state:
            st.session_state.client_uid = None
        if "show_admin" not in st.session_state:
            st.session_state.show_admin = False

        # Устанавливаем persistent client ID из query param, если он есть
        try:
            # Streamlit API может отличаться между версиями
            qp = {}
            try:
                # для новых версий (property)
                qp = st.query_params  # type: ignore[attr-defined]
            except Exception:
                pass
            if not isinstance(qp, dict):
                try:
                    # старый способ
                    qp = st.query_params()
                except Exception:
                    qp = {}
            qp_uid: Optional[str] = None
            if isinstance(qp, dict) and "uid" in qp and len(qp["uid"]) > 0:
                val = qp["uid"]
                qp_uid = val[0] if isinstance(val, list) else val
            if qp_uid and not st.session_state.get("client_uid"):
                st.session_state.client_uid = qp_uid
        except Exception:
            pass

        # Установим контекст аудита до первого события
        self.audit.set_context(
            session_id=st.session_state.session_id,
            user_id=st.session_state.user_id,
            client_uid=st.session_state.client_uid,
        )

        # Heartbeat (уже с контекстом)
        self.audit.heartbeat()

    def get_file_hash(self, uploaded_file):
        """Генерирует хэш файла для предотвращения дублирования"""
        uploaded_file.seek(0)
        file_hash = hashlib.md5(uploaded_file.read()).hexdigest()
        uploaded_file.seek(0)
        return file_hash

    # ===== Аутентификация =====

    def render_auth_gate(self) -> bool:
        """Если пользователь не аутентифицирован, показать форму входа. Возвращает True, если уже аутентифицирован."""
        if st.session_state.user_id:
            return True

        st.title("Требуется авторизация")
        st.subheader("Вход")
        login_user = st.text_input("Имя пользователя", key="login_user")
        login_pass = st.text_input("Пароль", type="password", key="login_pass")
        if st.button("Войти"):
            try:
                info = self.auth.authenticate(login_user.strip(), login_pass)
                st.session_state.user_id = info["username"]
                st.session_state.is_admin = bool(info.get("is_admin"))
                self.audit.set_context(
                    session_id=st.session_state.session_id,
                    user_id=st.session_state.user_id,
                    client_uid=st.session_state.client_uid,
                )
                self.audit.log_event("login_success", {"username": st.session_state.user_id})
                st.success("Успешный вход")
                st.rerun()
            except AuthError as e:
                self.audit.log_warning("login_failed", {"username": login_user, "reason": str(e)})
                st.error(str(e))

        return False

    def render_admin_panel(self):
        if not st.session_state.is_admin:
            return
        st.divider()
        st.subheader("Администрирование")

        tabs = st.tabs(["Пользователи", "Создать пользователя", "Журнал", "Результаты"]) 

        # --- Вкладка Пользователи ---
        with tabs[0]:
            try:
                users = self.auth.list_users()
                filter_text = st.text_input("Фильтр по имени пользователя", key="user_filter")
                if filter_text:
                    users = [u for u in users if filter_text.lower() in u["username"].lower()]

                with st.form("users_bulk_edit"):
                    # Заголовок
                    h1, h2, h3, h4 = st.columns([2, 2, 1, 1])
                    h1.write("Пользователь")
                    h2.write("Пароль")
                    h3.write("Роль")
                    h4.write("Удаление")

                    for u in users:
                        c1, c2, c3, c4 = st.columns([2, 2, 1, 1])
                        c1.write(u["username"])
                        c2.write(u.get("password", "") if u.get("password") else "<не задан>")
                        role_key = f"role_admin_{u['username']}"
                        delete_key = f"delete_user_{u['username']}"
                        is_admin_now = c3.checkbox("admin", value=bool(u["is_admin"]), key=role_key)
                        can_delete = (u["username"] != st.session_state.user_id)
                        c4.checkbox("удалить", value=False, key=delete_key, disabled=not can_delete)

                    if st.form_submit_button("Сохранить изменения"):
                        errors = []
                        changes_made = False
                        # Сначала применим изменения ролей
                        for u in users:
                            uname = u["username"]
                            new_admin = bool(st.session_state.get(f"role_admin_{uname}", u["is_admin"]))
                            if new_admin != bool(u["is_admin"]):
                                try:
                                    self.auth.set_admin(uname, new_admin, by_username=st.session_state.user_id)
                                    self.audit.log_event("user_role_changed", {"target": uname, "is_admin": new_admin, "by": st.session_state.user_id})
                                    changes_made = True
                                except AuthError as e:
                                    errors.append(str(e))
                        # Теперь удаление пользователей
                        for u in users:
                            uname = u["username"]
                            if st.session_state.get(f"delete_user_{uname}"):
                                try:
                                    self.auth.delete_user(uname, by_username=st.session_state.user_id)
                                    self.audit.log_event("user_deleted", {"target": uname, "by": st.session_state.user_id})
                                    changes_made = True
                                except AuthError as e:
                                    errors.append(str(e))
                        if errors:
                            for err in errors:
                                st.error(err)
                        if changes_made and not errors:
                            st.success("Изменения сохранены")
                        if changes_made:
                            st.rerun()
            except Exception as e:
                st.error(f"Ошибка загрузки пользователей: {e}")

        # --- Вкладка Создать пользователя ---
        with tabs[1]:
            st.write("Создать пользователя")
            new_user = st.text_input("Имя пользователя", key="admin_new_user")
            new_pass = st.text_input("Пароль", type="password", key="admin_new_pass")
            new_pass2 = st.text_input("Повторите пароль", type="password", key="admin_new_pass2")
            make_admin = st.checkbox("Назначить админом", key="admin_new_make_admin")
            if st.button("Создать пользователя", key="btn_create_user"):
                if new_pass != new_pass2:
                    st.error("Пароли не совпадают")
                else:
                    try:
                        res = self.auth.create_user(new_user.strip(), new_pass, by_username=st.session_state.user_id)
                        if make_admin:
                            try:
                                self.auth.set_admin(new_user.strip(), True, by_username=st.session_state.user_id)
                            except AuthError:
                                pass
                        self.audit.log_event("user_created", {"username": res["username"], "by": st.session_state.user_id})
                        st.success(f"Создан пользователь: {res['username']}")
                        st.rerun()
                    except AuthError as e:
                        self.audit.log_warning("user_create_failed", {"username": new_user, "reason": str(e)})
                        st.error(str(e))

        # --- Вкладка Журнал ---
        with tabs[2]:
            st.write("Журнал аудита")
            level = st.selectbox("Уровень", ["all", "info", "warning", "error"], index=0, key="audit_level")
            f_user = st.text_input("Фильтр по user_id", key="audit_f_user")
            f_session = st.text_input("Фильтр по session_id", key="audit_f_session")
            f_request = st.text_input("Фильтр по request_id", key="audit_f_request")
            limit = st.number_input("Показать последние N событий", min_value=10, max_value=5000, value=200, step=10, key="audit_limit")

            rows = []
            try:
                if os.path.exists("audit.log"):
                    with open("audit.log", "r", encoding="utf-8") as f:
                        lines = f.read().splitlines()
                    count = 0
                    for line in reversed(lines):
                        try:
                            rec = json.loads(line)
                        except Exception:
                            continue
                        # Применим фильтры
                        if level != "all" and rec.get("level") != level:
                            continue
                        if f_user and (rec.get("user_id") or "").lower().find(f_user.lower()) == -1:
                            continue
                        if f_session and (rec.get("session_id") or "").find(f_session) == -1:
                            continue
                        if f_request and (rec.get("request_id") or "").find(f_request) == -1:
                            continue
                        rows.append({
                            "time": rec.get("timestamp"),
                            "level": rec.get("level"),
                            "event": rec.get("event") or rec.get("kind"),
                            "user_id": rec.get("user_id"),
                            "session_id": rec.get("session_id"),
                            "request_id": rec.get("request_id"),
                        })
                        count += 1
                        if count >= int(limit):
                            break
                else:
                    st.info("Файл audit.log отсутствует")
            except Exception as e:
                st.error(f"Ошибка чтения журнала: {e}")

            if rows:
                st.dataframe(rows, use_container_width=True)

            # Скачивание аудита
            try:
                if os.path.exists("audit.log"):
                    with open("audit.log", "rb") as f:
                        st.download_button("Скачать audit.log", f, file_name="audit.log")
            except Exception:
                pass

    # --- Вкладка Результаты ---
        with tabs[3]:
            st.write("Результаты вопросов и ответов")
            f_user_q = st.text_input("Фильтр по пользователю", key="qa_f_user")
            limit_q = st.number_input("Показать последние N диалогов", min_value=10, max_value=1000, value=100, step=10, key="qa_limit")
            results = []
            if os.path.exists("audit.log"):
                try:
                    with open("audit.log", "r", encoding="utf-8") as f:
                        lines = f.read().splitlines()
                    by_req = {}
                    added = set()
                    for line in reversed(lines):
                        try:
                            rec = json.loads(line)
                        except Exception:
                            continue
                        ev = rec.get("event") or rec.get("kind")
                        if ev not in ("rag_query_input", "rag_query_output"):
                            continue
                        rid = rec.get("request_id")
                        if not rid:
                            continue
                        item = by_req.setdefault(rid, {
                            "request_id": rid,
                            "user_id": rec.get("user_id"),
                            "session_id": rec.get("session_id"),
                            "client_uid": rec.get("client_uid"),
                            "time": rec.get("timestamp"),
                            "question": None,
                            "response": None,
                        })
                        data = rec.get("data") or {}
                        if ev == "rag_query_input":
                            item["question"] = data.get("question", item.get("question"))
                        elif ev == "rag_query_output":
                            item["response"] = data.get("response", item.get("response"))
                        if item.get("question") and item.get("response") and rid not in added:
                            if not f_user_q or (item.get("user_id") or "").lower().find(f_user_q.lower()) != -1:
                                results.append(item.copy())
                                added.add(rid)
                                if len(results) >= int(limit_q):
                                    break
                except Exception as e:
                    st.error(f"Ошибка чтения результатов: {e}")
            else:
                st.info("Файл audit.log отсутствует")

            if results:
                for r in results:
                    st.markdown(f"Вопрос: {r.get('question')}")
                    st.markdown(f"Ответ: {r.get('response')}")
                    with st.expander("Дополнительная информация"):
                        st.json({
                            "request_id": r.get("request_id"),
                            "user_id": r.get("user_id"),
                            "session_id": r.get("session_id"),
                            "client_uid": r.get("client_uid"),
                            "timestamp": r.get("time"),
                        })
                    st.divider()
            else:
                st.info("Нет данных для отображения по заданным фильтрам")

    # ===== Служебные методы управления сессией и аудитом =====

    def end_session(self):
        """Завершение сессии: удаление коллекций и временных файлов, сброс состояния и выход пользователя."""
        sid = st.session_state.get("session_id")
        # Удаляем коллекции этой сессии
        to_delete = list(st.session_state.get("saved_collections", set()))
        for c in to_delete:
            try:
                if self.vector_manager.delete_collection(c):
                    logging.info(f"Удалена коллекция {c} при завершении сессии")
            except Exception as e:
                logging.error(f"Ошибка удаления коллекции {c} при завершении сессии: {e}")
        self.audit.log_event("session_ended", {"session_id": sid, "collections_deleted": to_delete})
        # Очищаем несохранённые файлы на всякий случай
        self.cleanup_unsaved_files()
        # Логируем намерение удаления сессии (регистра нет)
        self.audit.remove_session_from_registry(sid)
        # Сбрасываем состояние и генерируем новый session_id
        st.session_state.uploaded_files = {}
        st.session_state.saved_collections = set()
        st.session_state.active_collections = set()
        st.session_state.rag_chain = None
        st.session_state.chat_history = []
        st.session_state.session_id = str(uuid.uuid4())
        # Выход пользователя и сброс контекста аудита
        st.session_state.user_id = None
        st.session_state.is_admin = False
        self.audit.clear_context()
        self.audit.set_context(
            session_id=st.session_state.session_id,
            client_uid=st.session_state.client_uid,
        )
        st.success("Сессия завершена, пользователь вышел")
        st.rerun()

    def render_sidebar(self):
        """Отрисовывает боковую панель для управления документами"""
        with st.sidebar:
            st.header("Управление документами")

            # Профиль
            if st.session_state.user_id:
                st.info(f"Пользователь: {st.session_state.user_id} ({'admin' if st.session_state.is_admin else 'user'})")

            # Загрузка новых файлов с учетом лимита
            current_count = len(st.session_state.uploaded_files)
            slots_left = max(0, MAX_UPLOADS - current_count)
            if slots_left == 0:
                st.info(f"Достигнут лимит файлов: {MAX_UPLOADS}. Удалите файл, чтобы загрузить новый.")
            new_files = st.file_uploader(
                "Загрузите документы (.txt, .pdf, .docx)",
                accept_multiple_files=True,
                type=["txt", "pdf", "docx"],
                key="file_uploader",
                disabled=slots_left == 0,
            )
            st.caption(f"Можно загрузить еще: {slots_left}")

            if new_files:
                to_process = list(new_files)[:slots_left]
                for uploaded_file in to_process:
                    try:
                        # 1) Проверка дубликатов
                        file_hash = self.get_file_hash(uploaded_file)
                        already_exists = any(
                            info.get("hash") == file_hash
                            for info in st.session_state.uploaded_files.values()
                        )
                        if already_exists:
                            st.warning(f"Файл {uploaded_file.name} уже загружен (дубликат по содержимому)")
                            self.audit.log_event("file_duplicate_skipped", {"file_name": uploaded_file.name, "hash": file_hash})
                            continue

                        # 2) Сразу сохраняем файл во временное хранилище
                        file_path, file_id = self.document_manager.process_uploaded_file(uploaded_file)
                        st.session_state.uploaded_files[file_id] = {
                            "name": uploaded_file.name,
                            "path": file_path,
                            "hash": file_hash,
                            "saved": False,
                        }
                        self.audit.log_event("file_uploaded", {"file_id": file_id, "file_name": uploaded_file.name, "hash": file_hash, "path": file_path})

                        # 3) Автосохранение в векторную БД
                        self.save_document(file_id)

                    except Exception as e:
                        st.error(f"Ошибка обработки файла {uploaded_file.name}: {str(e)}")
                        self.audit.log_error("file_upload_error", {"file_name": uploaded_file.name, "error": str(e)})

            # Управление загруженными файлами
            if st.session_state.uploaded_files:
                st.subheader("Загруженные документы")
                files_to_remove = []

                for file_id, file_info in st.session_state.uploaded_files.items():
                    col1, col2 = st.columns([3, 1])
                    with col1:
                        status = (
                            "✅ Сохранён" if file_info["saved"] else "⚠️ Не сохранён"
                        )
                        st.write(f"{file_info['name']} - {status}")
                    with col2:
                        if st.button("Удалить", key=f"delete_{file_id}"):
                            files_to_remove.append(file_id)

                # Удаляем файлы после итерации
                for file_id in files_to_remove:
                    self.remove_file(file_id)

            # Управление сохранёнными коллекциями
            if st.session_state.saved_collections:
                st.subheader("Сохранённые документы")
                saved_list = sorted(list(st.session_state.saved_collections))
                current_idx = 0
                if st.session_state.get("active_collection") in saved_list:
                    current_idx = saved_list.index(st.session_state.get("active_collection"))
                choice = st.selectbox(
                    "Текущий документ:",
                    saved_list,
                    index=current_idx if saved_list else 0,
                    key="active_collection_selector",
                )
                if choice and choice != st.session_state.get("active_collection"):
                    st.session_state.active_collection = choice
                    self.initialize_rag_chain()

            # Кнопка показа/скрытия панели администратора
            if st.session_state.is_admin:
                if not st.session_state.show_admin:
                    if st.button("Открыть панель администратора"):
                        st.session_state.show_admin = True
                        st.rerun()
                else:
                    if st.button("Скрыть панель администратора"):
                        st.session_state.show_admin = False
                        st.rerun()
                    st.info("Панель администратора открыта в основном окне")

            # Разделитель и кнопка выхода в самом низу, совмещённая с завершением сессии
            st.divider()
            if st.session_state.user_id:
                if st.button("Выйти и завершить сессию"):
                    # Логируем logout и завершаем сессию (с очищением пользователя)
                    self.audit.log_event("logout", {"username": st.session_state.user_id})
                    self.end_session()

    def save_document(self, file_id):
        """Сохраняет документ в векторную БД"""
        if file_id not in st.session_state.uploaded_files:
            st.error("Файл не найден")
            return

        file_info = st.session_state.uploaded_files[file_id]
        try:
            # Загружаем и разбиваем документ
            chunks = self.document_manager.load_and_split_document(file_info["path"])

            # Имя коллекции = префикс сессии + имя файла без расширения + хэш (санитизация)
            session_short = st.session_state.session_id.split("-")[0]
            base_name = os.path.splitext(file_info["name"])[0]
            allowed = set(string.ascii_letters + string.digits + "-_.")
            safe_base = "".join(ch for ch in base_name if ch in allowed)[:64]
            if not safe_base:
                safe_base = "doc"
            collection_name = f"{session_short}__{safe_base}_{file_info['hash'][:8]}"

            # Добавляем в Векторную БД
            if self.vector_manager.add_documents_to_collection(collection_name, chunks):
                file_info["saved"] = True
                file_info["collection_name"] = collection_name
                st.session_state.saved_collections.add(collection_name)
                st.session_state.active_collection = collection_name
                st.success(f"Документ сохранён в коллекцию: {collection_name}")
                self.audit.log_event("document_saved", {"collection": collection_name, "chunks": len(chunks), "file_id": file_id, "file_name": file_info["name"]})

                # Переинициализируем цепочку RAG
                self.initialize_rag_chain()

                # Удаляем временный файл после успешного сохранения
                if file_info.get("path") and os.path.exists(file_info["path"]):
                    os.remove(file_info["path"])
                    logging.info(f"Удалён временный файл: {file_info['path']}")
                    file_info["path"] = None
            else:
                st.error("Ошибка сохранения документа")
        except Exception as e:
            st.error(f"Ошибка сохранения документа: {str(e)}")
            logging.error(f"Ошибка сохранения документа {file_info['name']}: {str(e)}")

    def remove_file(self, file_id):
        """Удаляет файл из списка и с диска"""
        if file_id not in st.session_state.uploaded_files:
            return

        file_info = st.session_state.uploaded_files[file_id]

        # Если файл сохранён в БД, удаляем коллекцию
        if file_info["saved"] and "collection_name" in file_info:
            collection_name = file_info["collection_name"]
            if self.vector_manager.delete_collection(collection_name):
                st.session_state.saved_collections.discard(collection_name)
                if st.session_state.get("active_collection") == collection_name:
                    st.session_state.active_collection = None
                st.success(f"Коллекция {collection_name} удалена")

        # Удаляем файл с диска
        if file_info.get("path") and os.path.exists(file_info["path"]):
            try:
                os.remove(file_info["path"])
                logging.info(f"Удалён файл: {file_info['path']}")
                file_info["path"] = None
            except Exception as e:
                logging.error(f"Ошибка удаления файла {file_info['path']}: {str(e)}")

        # Удаляем из состояния сес��ии
        del st.session_state.uploaded_files[file_id]
        st.success(f"Файл {file_info['name']} удалён")
        self.audit.log_event("file_removed", {"file_id": file_id, "file_name": file_info.get("name"), "collection": file_info.get("collection_name")})

        # Обновляем RAG цепочку
        self.initialize_rag_chain()
        st.rerun()

    def clear_all_collections(self):
        """Удаляет все коллекции"""
        collections_to_remove = list(st.session_state.saved_collections)
        for collection_name in collections_to_remove:
            if self.vector_manager.delete_collection(collection_name):
                st.session_state.saved_collections.discard(collection_name)
                if st.session_state.get("active_collection") == collection_name:
                    st.session_state.active_collection = None

        # Обновляем статус файлов
        for file_info in st.session_state.uploaded_files.values():
            if file_info["saved"]:
                file_info["saved"] = False
                if "collection_name" in file_info:
                    del file_info["collection_name"]

        st.session_state.rag_chain = None
        self.audit.log_event("all_collections_cleared", {"count": len(collections_to_remove)})
        st.success("Все коллекции удалены")
        st.rerun()

    def initialize_rag_chain(self):
        """Инициализирует цепочку RAG с текущей коллекцией"""
        active = st.session_state.get("active_collection")
        if active:
            try:
                retriever = self.vector_manager.get_retriever([active])
                st.session_state.rag_chain = self.rag_manager.create_rag_chain(retriever)
                st.session_state.chat_history = []
                self.audit.log_event("rag_initialized", {"active_collection": active})
                st.success(f"Цепочка RAG инициализирована для документа: {active}")
            except Exception as e:
                st.error(f"Ошибка инициализации RAG: {str(e)}")
                st.session_state.rag_chain = None
        else:
            st.session_state.rag_chain = None
            st.warning("Выберите документ для активации RAG")

    def render_chat_interface(self):
        """Отрисовывает основной чат-интерфейс"""
        st.title("RAG Чат-бот для анализа документов")

        # Информация о статусе
        if st.session_state.get("active_collection"):
            st.info(f"Текущий документ: {st.session_state.active_collection}")
        else:
            st.warning("Нет активного документа. Загрузите и выберите документ.")

        # Кнопка очистки истории чата
        if st.session_state.chat_history:
            if st.button("Очистить историю чата"):
                st.session_state.chat_history = []
                st.rerun()

        # Чат-интерфейс
        user_input = st.chat_input("Задайте ваш вопрос:")

        if user_input:
            if not st.session_state.rag_chain:
                st.warning("Пожалуйста, сначала загрузите и сохраните документы")
                return
            # Корреляция запроса
            request_id = self.audit.new_request_id()

            # Выполняем запрос
            with st.spinner("Обрабатываю запрос..."):
                self.audit.log_event(
                    "rag_query_input",
                    {"question": user_input, "mode": st.session_state.get("query_mode"), "target": st.session_state.get("target_collection")},
                    request_id=request_id,
                )
                response = self.rag_manager.invoke_chain(
                    st.session_state.rag_chain,
                    user_input,
                    session_id=st.session_state.session_id,
                )
                self.audit.log_event(
                    "rag_query_output",
                    {"question": user_input, "response": response, "mode": st.session_state.get("query_mode"), "target": st.session_state.get("target_collection")},
                    request_id=request_id,
                )

            # Сохраняем в историю
            st.session_state.chat_history.append({"user": user_input, "bot": response})

        # Отображение истории чата
        for message in st.session_state.chat_history:
            with st.chat_message("user"):
                st.write(message["user"])
            with st.chat_message("assistant"):
                st.write(message["bot"])

    def cleanup_unsaved_files(self):
        """Очищает несохранённые файлы"""
        files_to_remove = []
        for file_id, file_info in st.session_state.uploaded_files.items():
            if not file_info["saved"] and file_info.get("path") and os.path.exists(file_info["path"]):
                try:
                    os.remove(file_info["path"])
                    logging.info(f"Удалён несохранённый файл: {file_info['path']}")
                    self.audit.log_event("temp_file_removed", {"file_id": file_id, "path": file_info["path"]})
                    file_info["path"] = None
                    files_to_remove.append(file_id)
                except Exception as e:
                    logging.error(
                        f"Ошибка удаления файла {file_info['path']}: {str(e)}"
                    )

        # Удаляем из состояния сессии
        for file_id in files_to_remove:
            del st.session_state.uploaded_files[file_id]

    def run(self):
        """Запуск приложения"""
        # Обновить контекст аудита каждый рендер (на случай смены сессии/юзера)
        self.audit.set_context(
            session_id=st.session_state.session_id,
            user_id=st.session_state.user_id,
            client_uid=st.session_state.client_uid,
        )
        self.audit.heartbeat()
        self.audit.cleanup_expired_sessions(self.vector_manager)

        # Гейт аутентификации
        if not self.render_auth_gate():
            return

        self.render_sidebar()
        # Панель администратора в полном окне
        if st.session_state.is_admin and st.session_state.show_admin:
            self.render_admin_panel()
            return

        self.render_chat_interface()

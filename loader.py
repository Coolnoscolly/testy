import os
import random
from typing import List, Tuple, Optional
from minio import Minio
from minio.error import S3Error
from config.settings import settings


class MinioLoader:
    """Загружает документы из MinIO/S3 bucket с возможностью:
    - фильтра по расширениям
    - фильтра по 'папке' (prefix)
    - выборки только части документов (по умолчанию 25%)
    """

    def __init__(self):
        self.client = Minio(
            settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=settings.MINIO_SECURE,
            region=settings.MINIO_REGION,
        )
        self.bucket_name = settings.MINIO_BUCKET_NAME
        self.allowed_extensions = [ext.strip().lower() for ext in settings.ALLOWED_EXTENSIONS]

        # Настройки выборки: читаем из settings, если есть; иначе берем дефолты.
        # Если в вашем проекте нет таких полей в settings — getattr вернет дефолты и все будет работать.
        self.sample_fraction: float = float(getattr(settings, "MINIO_SAMPLE_FRACTION", 1))
        self.randomize_sampling: bool = bool(getattr(settings, "MINIO_SAMPLE_RANDOM", True))
        self.sampling_seed: Optional[int] = getattr(settings, "MINIO_SAMPLE_SEED", None)
        self.default_folder_prefix: Optional[str] = getattr(settings, "MINIO_FOLDER_PREFIX", None)

        # Подготовим генератор случайных чисел, если задан seed
        self._rnd = random.Random(self.sampling_seed) if self.sampling_seed is not None else random

    def check_connection(self) -> bool:
        """Проверяет подключение к MinIO"""
        try:
            self.client.list_buckets()
            return True
        except Exception as e:
            print(f"Ошибка подключения к MinIO: {e}")
            return False

    def list_files(self, prefix: Optional[str] = None) -> List[str]:
        """Возвращает список всех файлов с разрешенными расширениями в указанном prefix (папке).
        prefix=None — корень бакета.
        """
        try:
            objects = self.client.list_objects(self.bucket_name, prefix=prefix, recursive=True)
            files: List[str] = []

            for obj in objects:
                if any(obj.object_name.lower().endswith(ext) for ext in self.allowed_extensions):
                    files.append(obj.object_name)

            return sorted(files)
        except S3Error as e:
            print(f"Ошибка при получении списка файлов: {e}")
            return []

    def _sample_files(self, files: List[str]) -> List[str]:
        """Вернуть только часть файлов согласно sample_fraction. По умолчанию ~25%.
        - Минимум 1 файл, если список не пустой.
        - Если fraction <= 0 или >= 1, возвращаем весь список (без выборки).
        """
        if not files:
            return files

        fraction = self.sample_fraction
        if fraction <= 0 or fraction >= 1:
            return files

        count = max(1, int(len(files) * fraction))
        if count >= len(files):
            return files

        if self.randomize_sampling:
            # Случайная выборка
            return self._rnd.sample(files, count)
        else:
            # Детерминированно — первые N (файлы уже отсортированы)
            return files[:count]

    def read_file(self, object_name: str) -> str:
        """Читает содержимое файла из MinIO"""
        try:
            response = self.client.get_object(self.bucket_name, object_name)
            content = response.read().decode("utf-8", errors="ignore")
            response.close()
            response.release_conn()
            return content
        except S3Error as e:
            print(f"Ошибка при чтении файла {object_name}: {e}")
            raise
        except UnicodeDecodeError:
            # Пробуем другую кодировку
            try:
                response = self.client.get_object(self.bucket_name, object_name)
                content = response.read().decode("cp1251", errors="ignore")
                response.close()
                response.release_conn()
                return content
            except Exception:
                raise ValueError(f"Не удалось декодировать файл: {object_name}")

    def load_documents(self, folder_prefix: Optional[str] = None) -> List[Tuple[str, str]]:
        """Загружает документы из MinIO:
        - если задан folder_prefix — берем только файлы из этой 'папки' (prefix)
        - применяем выборку файлов согласно sample_fraction (по умолчанию ~25%)
        """
        if not self.check_connection():
            raise ConnectionError("Не удалось подключиться к MinIO")

        effective_prefix = folder_prefix if folder_prefix is not None else self.default_folder_prefix
        files = self.list_files(prefix=effective_prefix)

        # Берем только 25% (или другой fraction из настроек)
        files = self._sample_files(files)

        documents: List[Tuple[str, str]] = []
        for file_name in files:
            try:
                content = self.read_file(file_name).strip()
                if content:
                    documents.append((file_name, content))
            except Exception as e:
                print(f"Ошибка при обработке файла {file_name}: {e}")

        return documents


class HybridLoader:
    """Гибридный загрузчик: поддерживает как локальные файлы, так и MinIO"""

    def __init__(self):
        self.minio_loader = MinioLoader()

    def load_documents(self, folder_prefix: Optional[str] = None) -> List[Tuple[str, str]]:
        """Загружает документы из MinIO или локальной папки.
        - Для MinIO можно указать folder_prefix, чтобы читать только из нужной 'папки'.
        - Из MinIO будет взято только 25% документов (или fraction из настроек).
        """
        try:
            # Пробуем загрузить из MinIO
            minio_docs = self.minio_loader.load_documents(folder_prefix=folder_prefix)
            if minio_docs:
                print(f"Загружено {len(minio_docs)} документов из MinIO")
                return minio_docs
        except Exception as e:
            print(f"Не удалось загрузить из MinIO: {e}")

        # Здесь может быть логика для локальных файлов (если нужна).
        return []
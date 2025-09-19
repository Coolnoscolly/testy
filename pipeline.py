from typing import List, Tuple, Optional

from config.settings import settings
from core.loader import HybridLoader
from core.chunker import SmartChunker
from core.summarizer import OllamaSummarizer
from core.merger import HierarchicalMerger
from utils.helpers import format_final_summary


class SummaryPipeline:
    """
    Высокоуровневый, переиспользуемый пайплайн суммаризации.

    Назначение:
      - Дать единый, простой интерфейс для суммаризации контента
        из MinIO (или других источников через HybridLoader),
        без дублирования кода по проектам.

    Пример использования в любом проекте:
        from tesr_summary.core.pipeline import SummaryPipeline

        pipeline = SummaryPipeline()
        result = pipeline.run()  # загрузит документы, обработает и сохранит в settings.OUTPUT_FILE

        # или без записи в файл:
        result = pipeline.run(save_to=None)

        # суммаризация произвольных текстов (без MinIO):
        texts = ["текст 1", "текст 2"]
        result = pipeline.summarize_texts(texts, save_to="./my_summary.txt")

        # суммаризация заранее подготовленных документов (path, content):
        docs = [("file1.txt", "content1"), ("file2.txt", "content2")]
        result = pipeline.summarize_documents(docs)
    """

    def __init__(
        self,
        settings_obj=None,
        loader: Optional[HybridLoader] = None,
        chunker: Optional[SmartChunker] = None,
        summarizer: Optional[OllamaSummarizer] = None,
        merger: Optional[HierarchicalMerger] = None,
    ) -> None:
        # Конфигурация
        self.settings = settings_obj or settings

        # Составные компоненты с безопасными значениями по умолчанию
        self.loader = loader or HybridLoader()
        self.chunker = chunker or SmartChunker(
            max_chunk_size=self.settings.MAX_CHUNK_SIZE,
            overlap=self.settings.CHUNK_OVERLAP,
        )
        self.summarizer = summarizer or OllamaSummarizer()
        self.merger = merger or HierarchicalMerger(
            self.summarizer, max_workers=self.settings.MAX_WORKERS
        )

    # Унифицированная точка входа
    def run(self, save_to: Optional[str] = None) -> str:
        """Загрузить документы из источника (через HybridLoader) и вернуть итоговую суммаризацию.

        save_to: путь для сохранения результата. По умолчанию берётся settings.OUTPUT_FILE.
        """
        return self.summarize_minio(save_to=save_to)

    # Источник: MinIO/локальные (через HybridLoader)
    def summarize_minio(self, save_to: Optional[str] = None) -> str:
        documents = self.loader.load_documents()
        return self._summarize_documents(documents, save_to=save_to)

    # Источник: произвольные сырые тексты
    def summarize_texts(self, texts: List[str], save_to: Optional[str] = None) -> str:
        documents: List[Tuple[str, str]] = [
            ("", t) for t in texts if t and isinstance(t, str) and t.strip()
        ]
        return self._summarize_documents(documents, save_to=save_to)

    # Источник: заранее подготовленные документы (path, content)
    def summarize_documents(
        self, documents: List[Tuple[str, str]], save_to: Optional[str] = None
    ) -> str:
        return self._summarize_documents(documents, save_to=save_to)

    # Внутренняя логика пайплайна без дублирования кода
    def _summarize_documents(
        self, documents: List[Tuple[str, str]], save_to: Optional[str] = None
    ) -> str:
        if not documents:
            return ""

        # Чанкирование
        all_chunks: List[str] = []
        for _, content in documents:
            chunks = self.chunker.chunk_document(content)
            if chunks:
                all_chunks.extend(chunks)

        if not all_chunks:
            return ""

        # Иерархическое объединение
        final_summary = self.merger.merge_documents(all_chunks)

        # Форматирование
        formatted = format_final_summary(final_summary, self.settings.FINAL_STYLE)

        # Сохранение
        if save_to is None and getattr(self.settings, "OUTPUT_FILE", None):
            save_to = self.settings.OUTPUT_FILE
        if save_to:
            with open(save_to, "w", encoding="utf-8") as f:
                f.write(formatted)

        return formatted

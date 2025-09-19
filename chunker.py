import re
from typing import List

try:
    from chonkie import Chonkie

    CHONKIE_AVAILABLE = True
except ImportError:
    CHONKIE_AVAILABLE = False


class SmartChunker:
    """Умный чанкер с сохранением смысловых границ"""

    def __init__(self, max_chunk_size: int = 5000, overlap: int = 200):
        self.max_chunk_size = max_chunk_size
        self.overlap = overlap

        if CHONKIE_AVAILABLE:
            self.chonkie = Chonkie(chunk_size=max_chunk_size, chunk_overlap=overlap)
        else:
            self.chonkie = None

    def chunk_text(self, text: str) -> List[str]:
        """Разбивает текст на чанки с сохранением смысловых границ"""
        # Очищаем текст
        cleaned_text = re.sub(r"\s+", " ", text.strip())

        if self.chonkie is not None:
            # Используем chonkie если доступен
            return self.chonkie.split_text(cleaned_text)
        else:
            # Альтернативная реализация если chonkie не установлен
            return self._split_text_manual(cleaned_text)

    def _split_text_manual(self, text: str) -> List[str]:
        """Ручная реализация разбиения текста на чанки"""
        chunks = []
        start = 0
        text_length = len(text)

        # Приоритетные разделители для разбиения
        separators = ["\n\n", "\n", ". ", "! ", "? ", "; ", ", ", " "]

        while start < text_length:
            # Определяем конец текущего чанка
            end = min(start + self.max_chunk_size, text_length)

            if end == text_length:
                # Последний чанк
                chunk = text[start:end]
                chunks.append(chunk)
                break

            # Ищем лучшую позицию для разрыва
            best_break_pos = end
            for separator in separators:
                # Ищем разделитель в обратном направлении от конца чанка
                pos = text.rfind(separator, start, end)
                if pos != -1 and pos > start + (self.max_chunk_size * 0.6):
                    best_break_pos = pos + len(separator)
                    break

            chunk = text[start:best_break_pos]
            chunks.append(chunk)
            start = (
                best_break_pos - self.overlap
                if best_break_pos > self.overlap
                else best_break_pos
            )

        return chunks

    def _filter_chunks(self, chunks: List[str]) -> List[str]:
        """Фильтрует чанки, оставляя максимум 3: первый, средний и предпоследний"""
        if len(chunks) <= 3:
            return chunks

        # Берем первый чанк
        first_chunk = chunks[0]

        # Берем предпоследний чанк
        second_to_last_chunk = chunks[-2]

        # Берем средний чанк между первым и предпоследним
        middle_index = len(chunks) // 2
        middle_chunk = chunks[middle_index]

        return [first_chunk, middle_chunk, second_to_last_chunk]

    def chunk_document(self, content: str, min_chunk_size: int = 100) -> List[str]:
        """Разбивает документ на чанки, избегая слишком мелких фрагментов"""
        chunks = self.chunk_text(content)

        # Объединяем слишком мелкие чанки
        merged_chunks = []
        current_chunk = ""

        for chunk in chunks:
            chunk = chunk.strip()
            if not chunk:
                continue

            if len(current_chunk) + len(chunk) <= self.max_chunk_size:
                current_chunk += " " + chunk if current_chunk else chunk
            else:
                if current_chunk and len(current_chunk) >= min_chunk_size:
                    merged_chunks.append(current_chunk)
                current_chunk = chunk

        if current_chunk and len(current_chunk) >= min_chunk_size:
            merged_chunks.append(current_chunk)

        # Применяем фильтрацию чанков
        filtered_chunks = self._filter_chunks(merged_chunks)

        return filtered_chunks

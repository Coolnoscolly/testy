import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List
from config.settings import settings
from core.summarizer import OllamaSummarizer

class HierarchicalMerger:
    """Класс для иерархического объединения документов"""
    
    def __init__(self, summarizer: OllamaSummarizer, max_workers: int = None):
        self.summarizer = summarizer
        self.max_workers = max_workers or settings.MAX_WORKERS
    
    def merge_documents(self, documents: List[str]) -> str:
        """Иерархически объединяет документы"""
        if not documents:
            return ""
        
        if len(documents) == 1:
            return documents[0]
        
        # Перемешиваем документы для лучшего объединения
        if settings.SHUFFLE_CHUNKS:
            random.shuffle(documents)
        
        # Рекурсивное объединение
        current_level = documents
        
        while len(current_level) > 1:
            next_level = []
            pairs = self._create_pairs(current_level)
            
            # Многопоточная обработка пар
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                future_to_pair = {
                    executor.submit(self._merge_pair, pair): pair 
                    for pair in pairs
                }
                
                for future in as_completed(future_to_pair):
                    try:
                        merged = future.result()
                        next_level.append(merged)
                    except Exception as e:
                        print(f"Ошибка при объединении пары: {e}")
            
            # Если остался непарный документ, добавляем его как есть
            if len(current_level) % 2 == 1:
                next_level.append(current_level[-1])
            
            current_level = next_level
        
        return current_level[0] if current_level else ""
    
    def _create_pairs(self, documents: List[str]) -> List[List[str]]:
        """Создает пары документов для объединения"""
        pairs = []
        for i in range(0, len(documents) - 1, 2):
            pairs.append([documents[i], documents[i + 1]])
        return pairs
    
    def _merge_pair(self, pair: List[str]) -> str:
        """Объединяет пару документов"""
        combined = "\n\n".join(pair)
        return self.summarizer.summarize(combined)
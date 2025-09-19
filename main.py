import time
from config.settings import settings
from core.loader import HybridLoader
from core.chunker import SmartChunker
from core.summarizer import OllamaSummarizer
from core.merger import HierarchicalMerger
from utils.helpers import format_final_summary

def main():
    print("Запуск процесса суммаризации...")
    start_time = time.time()
    
    # Загрузка документов
    print("Загрузка документов...")
    loader = HybridLoader()
    documents = loader.load_documents()
    
    if not documents:
        print("Не найдено документов для обработки.")
        return
    
    print(f"Загружено {len(documents)} документов.")
    
    # Чанкирование документов
    print("Чанкирование документов...")
    chunker = SmartChunker(
        max_chunk_size=settings.MAX_CHUNK_SIZE,
        overlap=settings.CHUNK_OVERLAP
    )
    
    all_chunks = []
    for path, content in documents:
        chunks = chunker.chunk_document(content)
        all_chunks.extend(chunks)
        print(f"Документ {path} разбит на {len(chunks)} чанков")
    
    print(f"Всего создано {len(all_chunks)} чанков.")
    
    # Инициализация суммаризатора
    print("Инициализация суммаризатора...")
    summarizer = OllamaSummarizer()
    
    # Иерархическое объединение
    print("Начало иерархического объединения...")
    merger = HierarchicalMerger(summarizer, max_workers=settings.MAX_WORKERS)
    final_summary = merger.merge_documents(all_chunks)
    
    # Форматирование финального результата
    print("Форматирование результата...")
    formatted_summary = format_final_summary(final_summary, settings.FINAL_STYLE)
    
    # Сохранение результата
    print("Сохранение результата...")
    with open(settings.OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(formatted_summary)
    
    execution_time = time.time() - start_time
    print(f"Процесс завершен за {execution_time:.2f} секунд.")
    print(f"Результат сохранен в: {settings.OUTPUT_FILE}")

if __name__ == "__main__":
    main()
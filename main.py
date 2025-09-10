from rag_chain import create_rag_chain, invoke_chain
from test_Qdrant import initialize_vector_store
import logging

# Настройка логирования
logging.basicConfig(filename='app.log', level=logging.INFO, 
                    format='%(asctime)s - %(levelname)s - %(message)s')

# Пример тестового запуска
if __name__ == "__main__":
    # Тестовые файлы для отладки
    test_files = ["sample.txt"]  # Замените на реальные файлы
    vector_store = initialize_vector_store(test_files)
    rag_chain = create_rag_chain(vector_store)
    response = invoke_chain(rag_chain, "Что такое ПДД?")
    print(response)
import logging
from langchain_ollama import ChatOllama
from langchain_core.exceptions import LangChainException
from config import LLM_MODEL

class OllamaClient:
    def __init__(self):
        try:
            self.llm = ChatOllama(
                model=LLM_MODEL,
                base_url="http://a6000.ml.c.com:11434",
                temperature=0.4
            )
            logging.info("Успешное подключение к Ollama")
        except LangChainException as e:
            logging.error(f"Ошибка подключения к Ollama: {str(e)}")
            raise Exception("Не удалось подключиться к Ollama. Проверьте, запущен ли сервер.")
            
# Глобальный экземпляр клиента
ollama_client = OllamaClient()
llm = ollama_client.llm

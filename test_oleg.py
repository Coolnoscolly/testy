import requests
import json
from qdrant_client import QdrantClient
from qdrant_client.http import models

class SimpleRAGClient:
    def __init__(self, qdrant_url: str, qdrant_api_key: str = None, 
                 collection_name: str = "", 
                 ollama_url: str = "http://", 
                 ollama_model: str = "",
                 embed_model: str = ""):
        """
        Инициализация RAG клиента с Qdrant по URL
        
        Args:
            qdrant_url: URL Qdrant сервера (например, "http://localhost:6333")
            qdrant_api_key: API ключ Qdrant (опционально)
            collection_name: Название коллекции
            ollama_url: URL Ollama сервера
            ollama_model: Модель для генерации ответов
            embed_model: Модель для эмбеддингов
        """
        # Инициализация Qdrant клиента
        self.client = QdrantClient(
            url=qdrant_url,
            api_key=qdrant_api_key,
            timeout=60  # Увеличиваем таймаут
        )
        self.collection_name = collection_name
        
        # Настройки Ollama
        self.ollama_url = ollama_url
        self.ollama_model = ollama_model
        self.embed_model = embed_model
        
        # Проверка соединений
        self._check_connections()
    
    def _check_connections(self):
        """Проверка соединений с Qdrant и Ollama"""
        # Проверка Qdrant
        try:
            health = self.client.get_liveness()
            print(f"✅ Qdrant подключен: {health}")
            
            # Проверка существования коллекции
            collections = self.client.get_collections()
            collection_names = [col.name for col in collections.collections]
            if self.collection_name in collection_names:
                print(f"✅ Коллекция '{self.collection_name}' найдена")
            else:
                print(f"❌ Коллекция '{self.collection_name}' не найдена")
                print(f"Доступные коллекции: {collection_names}")
                
        except Exception as e:
            print(f"❌ Ошибка подключения к Qdrant: {e}")
        
        # Проверка Ollama
        try:
            response = requests.get(f"{self.ollama_url}/api/tags", timeout=10)
            if response.status_code == 200:
                models = response.json().get('models', [])
                print(f"✅ Ollama подключен. Модели: {[m['name'] for m in models]}")
            else:
                print("❌ Ошибка подключения к Ollama")
        except Exception as e:
            print(f"❌ Не удалось подключиться к Ollama: {e}")
    
    def get_embedding(self, text: str):
        """
        Получение эмбеддинга из Ollama
        """
        payload = {
            "model": self.embed_model,
            "prompt": text
        }
        
        try:
            response = requests.post(
                f"{self.ollama_url}/api/embeddings",
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                return response.json().get('embedding', [])
            else:
                print(f"Ошибка получения эмбеддинга: {response.status_code}")
                return []
                
        except Exception as e:
            print(f"Ошибка подключения к Ollama для эмбеддингов: {e}")
            return []
    
    def search_similar(self, query: str, limit: int = 5, score_threshold: float = 0.5):
        """Поиск похожих документов в Qdrant с эмбеддингами из Ollama"""
        query_embedding = self.get_embedding(query)
        
        if not query_embedding:
            print("❌ Не удалось получить эмбеддинг для запроса")
            return []
        
        try:
            search_result = self.client.search(
                collection_name=self.collection_name,
                query_vector=query_embedding,
                limit=limit,
                score_threshold=score_threshold
            )
            
            return search_result
            
        except Exception as e:
            print(f"❌ Ошибка поиска в Qdrant: {e}")
            return []
    
    def retrieve_context(self, query: str, limit: int = 3, min_score: float = 0.6):
        """Получение контекста из векторной базы"""
        results = self.search_similar(query, limit, min_score)
        
        if not results:
            print("⚠️  Не найдено релевантных документов")
            return ""
        
        context_parts = []
        for result in results:
            if result.payload and result.score >= min_score:
                # Поддерживаем разные форматы хранения текста
                text = (result.payload.get('text') or 
                        result.payload.get('content') or 
                        result.payload.get('document') or 
                        str(result.payload))
                if text:
                    source = result.payload.get('source', 'Unknown')
                    score = f"{result.score:.3f}"
                    context_parts.append(f"[Источник: {source}, схожесть: {score}] {text}")
        
        return "\n\n".join(context_parts)
    
    def generate_with_ollama(self, prompt: str, context: str = ""):
        """Генерация ответа с помощью Ollama"""
        if not context:
            return "❌ Не удалось найти достаточно информации для ответа на этот вопрос."
        
        full_prompt = f"""Используй следующий контекст для ответа на вопрос. Отвечай точно и информативно.

Контекст:
{context}

Вопрос: {prompt}

Ответ:"""
        
        payload = {
            "model": self.ollama_model,
            "prompt": full_prompt,
            "stream": False,
            "options": {
                "temperature": 0.1,
                "top_p": 0.9,
                "num_ctx": 4096
            }
        }
        
        try:
            response = requests.post(
                f"{self.ollama_url}/api/generate",
                json=payload,
                timeout=120
            )
            
            if response.status_code == 200:
                return response.json().get('response', 'Ошибка генерации ответа')
            else:
                return f"Ошибка Ollama: {response.status_code}"
                
        except Exception as e:
            return f"Ошибка подключения к Ollama: {e}"
    
    def ask_question(self, query: str, limit_context: int = 3, min_score: float = 0.6):
        """
        Полный цикл RAG: поиск контекста + генерация ответа
        """
        print(f"🔍 Поиск контекста для: '{query}'")
        context = self.retrieve_context(query, limit_context, min_score)
        
        if not context:
            return {
                "question": query,
                "answer": "❌ Не удалось найти релевантный контекст для ответа на вопрос.",
                "context": "",
                "context_sources": [],
                "found_documents": 0
            }
        
        print("🧠 Генерация ответа с Ollama...")
        answer = self.generate_with_ollama(query, context)
        
        return {
            "question": query,
            "answer": answer,
            "context": context,
            "context_sources": self._extract_sources(context),
            "found_documents": len(context.split('\n\n')) if context else 0
        }
    
    def _extract_sources(self, context: str):
        """Извлечение источников из контекста"""
        sources = []
        lines = context.split('\n')
        for line in lines:
            if line.startswith('[Источник:'):
                source = line.split(',')[0].replace('[Источник:', '').strip()
                if source and source not in sources:
                    sources.append(source)
        return sources

# Упрощенная версия для быстрого использования
class QuickRAG:
    def __init__(self, qdrant_url: str, qdrant_api_key: str = None,
                 ollama_model: str = "llama2",
                 embed_model: str = "mxbai-embed-large"):
        self.client = QdrantClient(url=qdrant_url, api_key=qdrant_api_key)
        self.ollama_url = "http://localhost:11434"
        self.ollama_model = ollama_model
        self.embed_model = embed_model
    
    def get_embedding(self, text: str):
        """Получение эмбеддинга из Ollama"""
        try:
            response = requests.post(
                f"{self.ollama_url}/api/embeddings",
                json={"model": self.embed_model, "prompt": text},
                timeout=30
            )
            return response.json().get('embedding', []) if response.status_code == 200 else []
        except:
            return []
    
    def ask(self, question: str, top_k: int = 3):
        """Быстрый вопрос-ответ"""
        # Получение эмбеддинга и поиск
        embedding = self.get_embedding(question)
        if not embedding:
            return "❌ Ошибка получения эмбеддинга"
        
        try:
            results = self.client.search(
                collection_name="my_collection",
                query_vector=embedding,
                limit=top_k,
                score_threshold=0.5
            )
            
            # Формирование контекста
            context = "\n".join([
                f"- {hit.payload.get('text', hit.payload.get('content', ''))} (схожесть: {hit.score:.3f})" 
                for hit in results if hit.payload and hit.score > 0.5
            ])
            
            if not context:
                return "❌ Не найдено релевантной информации"
            
            # Генерация ответа
            prompt = f"""Ответь на вопрос используя только предоставленный контекст:

Контекст:
{context}

Вопрос: {question}

Ответ:"""
            
            response = requests.post(
                f"{self.ollama_url}/api/generate",
                json={
                    "model": self.ollama_model,
                    "prompt": prompt,
                    "stream": False
                },
                timeout=60
            )
            
            if response.status_code == 200:
                answer = response.json().get('response', 'Не удалось получить ответ')
                return f"🤖 Ответ: {answer}\n\n📚 Найдено фрагментов: {len(results)}"
            else:
                return f"❌ Ошибка генерации: {response.status_code}"
                
        except Exception as e:
            return f"❌ Ошибка Qdrant: {e}"

# Пример использования
if __name__ == "__main__":
    # Инициализация клиента с Qdrant по URL
    rag_client = SimpleRAGClient(
        qdrant_url="http://",  # или ваш URL Qdrant
        collection_name="",
        ollama_model="",
        embed_model=""
    )
    
    # Пример вопроса
    question = "какая фирма производит 'Дугогасний реактор 35 кВ типу ASRC 2500'"
    
    # Получение ответа
    result = rag_client.ask_question(question)
    
    print("=" * 60)
    print(f"❓ Вопрос: {result['question']}")
    print("=" * 60)
    print(f"🤖 Ответ: {result['answer']}")
    print("=" * 60)
    print(f"📚 Найдено документов: {result['found_documents']}")
    if result['context']:
        print("Контекст (первые 300 символов):")
        print(result['context'][:300] + "..." if len(result['context']) > 300 else result['context'])
    print("=" * 60)
    print(f"🔗 Источники: {result['context_sources']}")

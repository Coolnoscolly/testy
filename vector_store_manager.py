import logging
from qdrant_client import QdrantClient
from qdrant_client.http import models
from langchain_qdrant import QdrantVectorStore
from langchain_ollama import OllamaEmbeddings
from tqdm import tqdm
from config import EMBEDDING_MODEL, PERSISTENT_STORAGE

class VectorStoreManager:
    def __init__(self):
        self.client = QdrantClient("localhost", port=6333)
        self.embeddings = OllamaEmbeddings(model=EMBEDDING_MODEL, base_url="http://a6000.ml.c.com:11434")
        self.collections = {}
        
    def create_collection(self, collection_name):
        """Создаёт новую коллекцию в Qdrant"""
        try:
            if not self.client.collection_exists(collection_name):
                self.client.create_collection(
                    collection_name=collection_name,
                    vectors_config=models.VectorParams(
                        size=1024,
                        distance=models.Distance.COSINE
                    )
                )
                logging.info(f"Коллекция создана: {collection_name}")
            return True
        except Exception as e:
            logging.error(f"Ошибка создания коллекции {collection_name}: {str(e)}")
            return False
            
    def add_documents_to_collection(self, collection_name, documents):
        """Добавляет документы в указанную коллекцию"""
        if not self.create_collection(collection_name):
            return False
            
        try:
            # Создаём хранилище для коллекции
            vector_store = QdrantVectorStore(
                client=self.client,
                collection_name=collection_name,
                embedding=self.embeddings,
            )
            
            # Добавляем документы батчами
            batch_size = 64
            for i in tqdm(range(0, len(documents), batch_size), 
                         desc=f"Загрузка в {collection_name}"):
                batch = documents[i:i+batch_size]
                vector_store.add_documents(batch)
                
            logging.info(f"Добавлено {len(documents)} чанков в коллекцию {collection_name}")
            self.collections[collection_name] = vector_store
            return True
        except Exception as e:
            logging.error(f"Ошибка добавления в {collection_name}: {str(e)}")
            return False
            
    def get_retriever(self, collection_names):
        """Создаёт retriever для указанных коллекций"""
        if not collection_names:
            return None
            
        # Создаём мульти-коллекционный retriever
        retrievers = []
        for name in collection_names:
            if name in self.collections:
                retrievers.append(self.collections[name].as_retriever(search_kwargs={"k": 8}))
            else:
                vector_store = QdrantVectorStore(
                    client=self.client,
                    collection_name=name,
                    embedding=self.embeddings,
                )
                retrievers.append(vector_store.as_retriever(search_kwargs={"k": 8}))
                self.collections[name] = vector_store
                
        # Комбинируем несколько retriever'ов
        from langchain.retrievers import EnsembleRetriever
        return EnsembleRetriever(retrievers=retrievers, weights=[1.0]*len(retrievers))
        
    def delete_collection(self, collection_name):
        """Удаляет коллекцию из Qdrant"""
        try:
            self.client.delete_collection(collection_name)
            if collection_name in self.collections:
                del self.collections[collection_name]
            logging.info(f"Коллекция удалена: {collection_name}")
            return True
        except Exception as e:
            logging.error(f"Ошибка удаления коллекции {collection_name}: {str(e)}")
            return False

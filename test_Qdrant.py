import logging
from langchain_qdrant import QdrantVectorStore
from langchain_ollama import OllamaEmbeddings
from langchain_core.documents import Document
from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams
import os
from config import ALLOWED_EXTENSIONS

# Настройка логирования
logging.basicConfig(filename='app.log', level=logging.INFO, 
                    format='%(asctime)s - %(levelname)s - %(message)s')

embeddings = OllamaEmbeddings(model="mxbai-embed-large:latest", base_url="http://a6000.ml.c.com:11434")

client = QdrantClient("localhost", port=6333)

collection_name = "rag-knowledge-base"

def create_collection():
    try:
        client.get_collection(collection_name=collection_name)
        logging.info("Коллекция существует")
    except:
        client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=1024, distance=Distance.COSINE),
        )
        logging.info("Коллекция создана")

def load_documents(file_paths):
    documents = []
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    for file_path in file_paths:
        ext = os.path.splitext(file_path)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            logging.warning(f"Неподдерживаемый формат файла: {file_path}")
            continue
        try:
            if ext == '.pdf':
                loader = PyPDFLoader(file_path, extract_images=False)
                raw_docs = loader.load()
            elif ext == '.txt':
                loader = TextLoader(file_path)
                raw_docs = loader.load()
            # Разбиваем документ на чанки
            chunked_docs = text_splitter.split_documents(raw_docs)
            for i, doc in enumerate(chunked_docs):
                doc.metadata["source"] = file_path
                doc.metadata["chunk_id"] = f"{file_path}_{i}"
            documents.extend(chunked_docs)
            logging.info(f"Документ загружен и разбит на {len(chunked_docs)} чанков: {file_path}")
        except Exception as e:
            logging.error(f"Ошибка при загрузке {file_path}: {str(e)}")
    return documents

def initialize_vector_store(file_paths):
    create_collection()
    vector_store = QdrantVectorStore(
        embedding=embeddings,
        client=client,
        collection_name=collection_name,
    )
    documents = load_documents(file_paths)
    if documents:
        # Загружаем документы пачками
        batch_size = 32
        for i in range(0, len(documents), batch_size):
            batch = documents[i:i + batch_size]
            try:
                vector_store.add_documents(batch)
                logging.info(f"Добавлено {len(batch)} чанков в векторное хранилище")
            except Exception as e:
                logging.error(f"Ошибка при добавлении чанков: {str(e)}")
        logging.info(f"Всего добавлено {len(documents)} чанков в векторное хранилище")
    else:
        logging.warning("Не удалось загрузить документы для индексации")
    return vector_store
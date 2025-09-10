import os
import uuid
import logging
from langchain_community.document_loaders import PyPDFLoader, TextLoader, Docx2txtLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from config import ALLOWED_EXTENSIONS, PERSISTENT_STORAGE, CHUNK_SIZE, CHUNK_OVERLAP

class DocumentManager:
    def __init__(self):
        os.makedirs(PERSISTENT_STORAGE, exist_ok=True)
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=CHUNK_SIZE,
            chunk_overlap=CHUNK_OVERLAP
        )
        
    def process_uploaded_file(self, uploaded_file):
        """Обрабатывает загруженный файл и сохраняет на диск"""
        file_ext = os.path.splitext(uploaded_file.name)[1].lower()
        if file_ext not in ALLOWED_EXTENSIONS:
            raise ValueError(f"Неподдерживаемый формат файла: {file_ext}")
            
        # Генерируем уникальное имя файла
        file_id = str(uuid.uuid4())
        filename = f"{file_id}{file_ext}"
        file_path = os.path.join(PERSISTENT_STORAGE, filename)
        
        # Сохраняем файл
        with open(file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
            
        return file_path, file_id
    
    def load_and_split_document(self, file_path):
        """Загружает и разбивает документ на чанки"""
        file_ext = os.path.splitext(file_path)[1].lower()
        
        try:
            if file_ext == '.pdf':
                loader = PyPDFLoader(file_path)
            elif file_ext == '.txt':
                loader = TextLoader(file_path)
            elif file_ext == '.docx':
                loader = Docx2txtLoader(file_path)
            else:
                raise ValueError(f"Неподдерживаемый формат файла: {file_ext}")
                
            document = loader.load()
            chunks = self.text_splitter.split_documents(document)
            
            # Добавляем метаданные
            for i, chunk in enumerate(chunks):
                chunk.metadata["chunk_id"] = f"{os.path.basename(file_path)}_{i}"
                chunk.metadata["source"] = os.path.basename(file_path)
                
            return chunks
        except Exception as e:
            logging.error(f"Ошибка обработки файла {file_path}: {str(e)}")
            raise

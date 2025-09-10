import os

# Разрешённые форматы файлов
ALLOWED_EXTENSIONS = {'.txt', '.pdf', '.docx'}

# Путь к постоянному хранилищу документов
PERSISTENT_STORAGE = "persistent_storage"

# Настройки обработки документов
CHUNK_SIZE = 2000
CHUNK_OVERLAP = 100
EMBEDDING_MODEL = "mxbai-embed-large:latest"
LLM_MODEL = "qwen2.5:32b"
import logging
import re
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough, RunnableLambda
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_core.chat_history import InMemoryChatMessageHistory
from client_for_ollama import llm

class RAGChainManager:
    def __init__(self):
        self.template = """Используй контекст для ответа на вопрос. Если контекста нет, отвечай "Я не знаю". Отвечай на русском языке.

Context:
{context}

Question:
{question}

Answer in markdown format: """
        self.prompt = ChatPromptTemplate.from_template(self.template)
        self.history_store = {}
        
    def is_safe_input(self, text):
        """Фильтрация вредоносных запросов"""
        dangerous_patterns = [
            r'(\b(SELECT|INSERT|DELETE|UPDATE|DROP|TRUNCATE)\b.*\b(FROM|INTO)\b)',
            r'(<script>|javascript:)',
            r'(\bexec\b|\brm\b|\bdel\b|\bsudo\b)',
        ]
        for pattern in dangerous_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                logging.warning(f"Обнаружен подозрительный запрос: {text}")
                return False
        return True
        
    def create_rag_chain(self, retriever):
        """Создаёт цепочку RAG с историей сообщений"""
        def format_docs(docs):
            return "\n\n".join(doc.page_content for doc in docs)
            
        def get_question(x):
            return x["question"]
            
        chain = (
            RunnablePassthrough.assign(
                context=RunnableLambda(get_question) | retriever | format_docs
            )
            | self.prompt
            | llm
            | StrOutputParser()
        )
        
        return RunnableWithMessageHistory(
            chain,
            self.get_session_history,
            input_messages_key="question",
            history_messages_key="history",
        )
        
    def get_session_history(self, session_id: str) -> InMemoryChatMessageHistory:
        """Возвращает историю сообщений для сессии"""
        if session_id not in self.history_store:
            self.history_store[session_id] = InMemoryChatMessageHistory()
        return self.history_store[session_id]
        
    def invoke_chain(self, chain, question, session_id="default"):
        """Выполняет запрос к цепочке RAG"""
        if not self.is_safe_input(question):
            logging.error(f"Вредоносный запрос отклонён: {question}")
            return "Ошибка: запрос содержит недопустимое содержимое."
            
        try:
            response = chain.invoke(
                {"question": question},
                config={"configurable": {"session_id": session_id}}
            )
            logging.info(f"Вопрос: {question}, Ответ: {response}")
            return response
        except Exception as e:
            logging.error(f"Ошибка в цепочке: {str(e)}")
            return f"Произошла ошибка: {str(e)}"

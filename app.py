import logging
from chat_interface import ChatInterface

# Настройка логирования
logging.basicConfig(
    filename="app.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)


# Запуск приложения
if __name__ == "__main__":
    app = ChatInterface()
    app.run()

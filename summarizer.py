import ollama
from dataclasses import dataclass
from typing import Optional
from config.settings import settings


@dataclass
class OllamaConfig:
    host: str = settings.OLLAMA_HOST
    model: str = settings.OLLAMA_MODEL
    temperature: float = settings.OLLAMA_TEMPERATURE
    top_p: float = settings.OLLAMA_TOP_P
    num_predict_pair: int = settings.OLLAMA_NUM_PREDICT_PAIR
    num_predict_final: int = settings.OLLAMA_NUM_PREDICT_FINAL


class OllamaSummarizer:
    """Класс для взаимодействия с Ollama API"""

    def __init__(self, cfg: OllamaConfig = None):
        self.cfg = cfg or OllamaConfig()
        self.client = ollama.Client(host=self.cfg.host)

        # Проверяем доступность модели
        try:
            models_response = self.client.list()

            # Безопасное извлечение имен моделей
            model_names = []
            if hasattr(models_response, "models") and models_response.models:
                for model in models_response.models:
                    if hasattr(model, "name"):
                        model_names.append(model.name)
                    elif hasattr(model, "model"):
                        model_names.append(model.model)
                    elif isinstance(model, dict):
                        model_names.append(
                            model.get("name", model.get("model", str(model)))
                        )
                    else:
                        model_names.append(str(model))
            elif isinstance(models_response, dict) and "models" in models_response:
                for model in models_response["models"]:
                    if isinstance(model, dict):
                        model_names.append(
                            model.get("name", model.get("model", str(model)))
                        )
                    else:
                        model_names.append(str(model))

            # Проверяем наличие нужной модели
            if model_names and self.cfg.model not in model_names:
                print(
                    f"Предупреждение: Модель {self.cfg.model} не найдена в списке доступных."
                )
                print(f"Доступные модели: {', '.join(model_names)}")
                print("Попытаемся использовать указанную модель...")

        except Exception as e:
            print(f"Предупреждение: Не удалось получить список моделей: {e}")
            print("Попытаемся использовать указанную модель напрямую...")

    def summarize(self, text: str, is_final: bool = False) -> str:
        """Суммаризирует текст с использованием Ollama"""
        prompt = self._build_prompt(text, is_final)

        try:
            response = self.client.generate(
                model=self.cfg.model,
                prompt=prompt,
                options={
                    "temperature": self.cfg.temperature,
                    "top_p": self.cfg.top_p,
                    "num_predict": (
                        self.cfg.num_predict_final
                        if is_final
                        else self.cfg.num_predict_pair
                    ),
                },
            )

            return response.get("response", "").strip()
        except Exception as e:
            raise RuntimeError(f"Ошибка при генерации ответа: {e}")

    def _build_prompt(self, text: str, is_final: bool = False) -> str:
        """Создает промпт для суммаризации"""
        if is_final:
            # Используем вынесенный в настройки FINAL_PROMPT
            return f"""{settings.SYSTEM_PROMPT}

{settings.FINAL_PROMPT}

Промежуточные суммаризации:
{text}

Финальный резумирующий документ:"""
        else:
            return f"""{settings.SYSTEM_PROMPT}

{settings.MERGE_PROMPT}

Фрагменты для объединения:
{text}

Объединённый резумирующий документ:"""

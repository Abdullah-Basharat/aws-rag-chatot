from langchain_openai import ChatOpenAI
from dotenv import load_dotenv


load_dotenv()


class LanguageModel:
    def __init__(self, model_name: str = "gpt-4o", temperature: float = 0, fake_model: bool = False):
        if fake_model:
            # Simple fake model for tests / offline usage
            self.llm = type(
                "FakeLLM",
                (),
                {"invoke": lambda self, prompt: type("FakeResponse", (), {"content": f"FAKE RESPONSE: {prompt}"})()},
            )()
        else:
            self.llm = ChatOpenAI(model=model_name, temperature=temperature)

    def predict(self, prompt: str) -> str:
        return self.llm.invoke(prompt).content


LLM = LanguageModel()



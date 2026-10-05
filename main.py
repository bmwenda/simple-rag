from typing import Protocol

from src.chat import create_chat_service
from src.config import Settings
from src.domain import ChatResponse, RAGError


class AnswerService(Protocol):
    def answer(self, query: str) -> ChatResponse: ...


def chat(query: str, service: AnswerService) -> str:
    try:
        return service.answer(query).text
    except RAGError:
        return "Sorry, I couldn't answer that right now. Please try again."


def main() -> None:
    service = create_chat_service(Settings.from_env())
    print(
        "Hello new joiner! Welcome to Aetheris! Ask me any question regarding "
        "us, such as policies and other useful information.\nTo exit, type 'q', "
        "'quit', or 'exit'."
    )

    while True:
        user_input = input("> ")
        if user_input.strip().lower() in {"q", "quit", "exit"}:
            print("See you soon!!")
            break

        print(chat(user_input, service))


if __name__ == "__main__":
    main()

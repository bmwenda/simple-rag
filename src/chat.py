import re
from collections.abc import Callable
from typing import Protocol

from langchain_core.prompts import ChatPromptTemplate

from .config import Settings
from .domain import Answer, AnswerGenerationError, Citation, RetrievedChunk
from .model import get_chat_model
from .retriever import retrieve_documents

ABSTENTION_MESSAGE = "The available documents do not contain that information."
CITATION_PATTERN = re.compile(r"\[(\d+)\]")
SYSTEM_PROMPT = (
    "You are a helpful assistant. Answer questions concisely using only the "
    "provided company context. Cite every factual claim with one or more of the "
    "numbered citations exactly as written, for example [1]. Never invent a "
    "citation number. If the context does not contain the answer, respond "
    f'exactly: "{ABSTENTION_MESSAGE}"\n\nContext:\n{{context}}'
)


class Message(Protocol):
    @property
    def text(self) -> str: ...


class Chain(Protocol):
    def invoke(self, input: dict[str, str]) -> Message: ...


class ChatService:
    def __init__(
        self,
        chain: Chain,
        retrieve: Callable[[str], list[RetrievedChunk]] = retrieve_documents,
    ) -> None:
        self._chain = chain
        self._retrieve = retrieve

    def answer(self, query: str) -> Answer:
        chunks = self._retrieve(query)
        if not chunks:
            return Answer(text=ABSTENTION_MESSAGE, citations=())

        try:
            response = self._chain.invoke(
                {"context": format_context(chunks), "query": query}
            )
        except Exception as exc:
            raise AnswerGenerationError("Answer generation failed") from exc

        return build_answer(response.text, chunks)


def format_context(chunks: list[RetrievedChunk]) -> str:
    return "\n\n".join(
        f"[{chunk.citation_id}] Source: {format_source(chunk)}\n{chunk.text}"
        for chunk in chunks
    )


def format_source(chunk: RetrievedChunk | Citation) -> str:
    if chunk.page_number is not None:
        return f"{chunk.display_name}, page {chunk.page_number}"
    return f"{chunk.display_name}, chunk {chunk.chunk_index + 1}"


def build_answer(text: str, chunks: list[RetrievedChunk]) -> Answer:
    if text.strip() == ABSTENTION_MESSAGE:
        return Answer(text=ABSTENTION_MESSAGE, citations=())

    chunks_by_id = {chunk.citation_id: chunk for chunk in chunks}
    citation_ids = list(
        dict.fromkeys(int(match) for match in CITATION_PATTERN.findall(text))
    )
    unknown_ids = [
        citation_id for citation_id in citation_ids if citation_id not in chunks_by_id
    ]

    if unknown_ids:
        raise AnswerGenerationError("Answer contains an unknown citation")
    if not citation_ids:
        raise AnswerGenerationError("Answer does not cite its sources")

    citations = tuple(
        _to_citation(chunks_by_id[citation_id]) for citation_id in citation_ids
    )
    return Answer(text=text, citations=citations)


def _to_citation(chunk: RetrievedChunk) -> Citation:
    return Citation(
        citation_id=chunk.citation_id,
        document_id=chunk.document_id,
        display_name=chunk.display_name,
        page_number=chunk.page_number,
        chunk_index=chunk.chunk_index,
        excerpt=chunk.text,
    )


def create_chat_service(settings: Settings) -> ChatService:
    prompt = ChatPromptTemplate.from_messages(
        [("system", SYSTEM_PROMPT), ("human", "{query}")]
    )
    chain = prompt | get_chat_model(settings)
    return ChatService(
        chain=chain,
        retrieve=lambda query: retrieve_documents(query, settings=settings),
    )

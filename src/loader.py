import glob
import os

from langchain_community.document_loaders import TextLoader
from langchain_core.documents import Document
from langchain_docling.loader import DoclingLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

SOURCES_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "sources")
)


def _load_file(file_path: str) -> list[Document]:
    """Pick a loader based on file type."""
    if file_path.endswith(".txt"):
        return TextLoader(file_path).load()
    return DoclingLoader(file_path=file_path).load()


def load_and_chunk_sources(
    sources_dir: str = SOURCES_DIR,
) -> tuple[list[Document], list[str]]:
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)

    file_paths = sorted(
        path for path in glob.glob(os.path.join(sources_dir, "*"))
        if os.path.isfile(path)
    )

    all_chunks: list[Document] = []
    all_ids: list[str] = []

    for file_path in file_paths:
        documents = _load_file(file_path)
        split_chunks = text_splitter.split_documents(documents)
        source_id = os.path.basename(file_path).replace(".", "_")

        for index, chunk in enumerate(split_chunks):
            all_chunks.append(
                Document(
                    page_content=chunk.page_content,
                    metadata={"source": file_path, "chunk_index": index},
                )
            )
            all_ids.append(f"{source_id}-{index}")

    return all_chunks, all_ids

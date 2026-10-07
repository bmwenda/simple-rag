import glob
import os

from langchain_community.document_loaders import PyPDFium2Loader, TextLoader
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

SOURCES_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "sources"))


def _load_file(file_path: str) -> list[Document] | None:
    """Pick a loader based on file type."""
    file_extension = os.path.splitext(file_path)[1].lower()
    if file_extension == ".txt":
        return TextLoader(file_path).load()
    if file_extension == ".pdf":
        return PyPDFium2Loader(file_path).load()
    else:
        raise RuntimeError("Unsupported document type. More coming soon!")


def load_and_chunk_sources(
    sources_dir: str = SOURCES_DIR,
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
) -> tuple[list[Document], list[str], list[str]]:
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )

    file_paths = sorted(
        path
        for path in glob.glob(os.path.join(sources_dir, "*"))
        if os.path.isfile(path)
    )

    all_chunks: list[Document] = []
    all_ids: list[str] = []
    source_files: list[str] = []

    for file_path in file_paths:
        base_name = os.path.basename(file_path)
        source_id = base_name.replace(".", "_")
        chunks, chunk_ids = load_and_chunk_file(
            file_path,
            document_id=source_id,
            index_version=0,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            text_splitter=text_splitter,
        )
        if chunks:
            all_chunks.extend(chunks)
            all_ids.extend(chunk_ids)
            source_files.append(base_name)

    return all_chunks, all_ids, source_files


def load_and_chunk_file(
    file_path: str,
    *,
    document_id: str,
    index_version: int,
    source_uri: str | None = None,
    display_name: str | None = None,
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
    text_splitter: RecursiveCharacterTextSplitter | None = None,
) -> tuple[list[Document], list[str]]:
    """Load one file into versioned chunks while preserving source provenance."""
    documents = _load_file(file_path)
    if not documents:
        return [], []

    splitter = text_splitter or RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    split_chunks = splitter.split_documents(documents)
    base_name = display_name or os.path.basename(file_path)
    chunks: list[Document] = []
    chunk_ids: list[str] = []

    for index, chunk in enumerate(split_chunks):
        metadata = {
            **chunk.metadata,
            "document_id": document_id,
            "display_name": base_name,
            "source": source_uri or file_path,
            "index_version": index_version,
            "chunk_index": index,
        }
        page = metadata.get("page")
        if isinstance(page, int):
            metadata["page_number"] = page + 1

        chunks.append(Document(page_content=chunk.page_content, metadata=metadata))
        chunk_ids.append(f"{document_id}:{index_version}:{index}")

    return chunks, chunk_ids

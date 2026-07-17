import glob
import os

from langchain_community.document_loaders import PyPDFium2Loader, TextLoader
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

SOURCES_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "sources")
)


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
) -> tuple[list[Document], list[str], list[str]]:
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)

    file_paths = sorted(
        path for path in glob.glob(os.path.join(sources_dir, "*"))
        if os.path.isfile(path)
    )

    all_chunks: list[Document] = []
    all_ids: list[str] = []
    source_files: list[str] = []

    for file_path in file_paths:
        documents = _load_file(file_path)
        if not documents: continue

        split_chunks = text_splitter.split_documents(documents)
        base_name = os.path.basename(file_path)
        source_id = base_name.replace(".", "_")
        source_files.append(base_name)

        for index, chunk in enumerate(split_chunks):
            all_chunks.append(
                Document(
                    page_content=chunk.page_content,
                    metadata={"source": file_path, "chunk_index": index},
                )
            )
            all_ids.append(f"{source_id}-{index}")

    return all_chunks, all_ids, source_files

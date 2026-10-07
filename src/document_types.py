from pathlib import Path

# Formats supported by the Docling integration and allowed from S3.
SUPPORTED_DOCUMENT_EXTENSIONS = frozenset(
    {
        ".csv",
        ".docx",
        ".epub",
        ".html",
        ".htm",
        ".json",
        ".md",
        ".odt",
        ".pdf",
        ".pptx",
        ".rtf",
        ".rst",
        ".tsv",
        ".txt",
        ".xml",
        ".yaml",
        ".yml",
    }
)


def is_supported_document(path: str | Path) -> bool:
    return Path(path).suffix.lower() in SUPPORTED_DOCUMENT_EXTENSIONS

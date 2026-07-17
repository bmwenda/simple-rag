## Description

This is a simple Retrieval-Augmented Generation (RAG) command line application that enables you to load documents, process them into searchable chunks, and retrieve relevant information using semantic search. It combines document ingestion, embedding, and intelligent retrieval to provide context-aware responses.

## Key Technologies

- **LangChain** - LLM framework for building RAG pipelines
- **OpenAI Embeddings** - Semantic text embeddings for understanding document meaning
- **Chroma** - Vector database for efficient document storage and retrieval
- **DoclingLoader** - Extracts content from PDF and document files
- **RecursiveCharacterTextSplitter** - Intelligent document chunking with overlap

## How It Works

1. **Load Documents** - Place your documents (`.txt` or `.pdf` files) in the `sources/` folder
2. **Process & Chunk** - Documents are automatically split into overlapping chunks for better retrieval
3. **Generate Embeddings** - Each chunk is converted into semantic embeddings using OpenAI
4. **Store in Vector DB** - Embeddings are stored in Chroma for fast similarity search
5. **Retrieve & Query** - Search for relevant documents using natural language queries

## Installation

### Prerequisites
- Python 3.12
- OpenAI API key

### Steps

1. **Clone the repository and navigate to the project:**
   ```bash
   cd simple-rag
   ```

2. **Install dependencies using uv:**
   ```bash
   uv sync
   ```

3. **Set up environment variables:**
   Create a `.env` file in the project root:
   ```
   OPENAI_API_KEY=your-api-key-here
   OPENAI_MODEL=gpt-4-turbo
   ```

4. **Add documents:**
   Place your `.txt` or `.pdf` files in the `sources/` folder

5. **Ingest documents:**
   ```bash
   uv run python ingest_sources.py
   ```

## Usage

### Ingest Documents
```bash
uv run python src/embedding.py
```

### Query Documents
```bash
uv run python main.py
```

This opens a chat interface that you can use to fire your questions.

## Development

Run type checking:
```bash
uv run mypy src/
```


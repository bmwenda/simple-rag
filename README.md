## Description

This is a simple Retrieval-Augmented Generation (RAG) command line application that enables you to load documents, process them into searchable chunks, and retrieve relevant information using semantic search. It combines document ingestion, embedding, and intelligent retrieval to provide context-aware responses.

The implemented capabilities, deployment constraints, and remaining delivery
tasks are maintained in the [product and delivery specification](docs/specification.md).

## Key Technologies

- **LangChain** - LLM framework for building RAG pipelines
- **OpenAI Embeddings** - Semantic text embeddings for understanding document meaning
- **Chroma** - Vector database for efficient document storage and retrieval
- **SQLAlchemy** - ORM persistence for document identity and ingestion state
- **DoclingLoader** - Parses PDF, text, Markdown, HTML, Office, and other
  supported document formats
- **RecursiveCharacterTextSplitter** - Intelligent document chunking with overlap

## How It Works

1. **Load Documents** - Place supported documents, such as PDF, text, Markdown,
   HTML, or Office files, in the `sources/` folder
2. **Process & Chunk** - Documents are automatically split into overlapping chunks for better retrieval
3. **Generate Embeddings** - Each chunk is converted into semantic embeddings using OpenAI
4. **Store in Vector DB** - Embeddings are stored in Chroma for fast similarity search
5. **Retrieve & Query** - Search for relevant documents using natural language queries

## Installation

### Prerequisites
- Python 3.12
- OpenAI API key
- PostgreSQL database for the document registry

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
   DATABASE_URL=postgresql+psycopg://rag_user:change_me@localhost:5432/simple_rag
   ```

   For local development, use a PostgreSQL role with permission to create
   databases. See `.env.example` for optional embedding, Chroma, retrieval, and
   chunking settings.

   Prepare the local database and apply pending schema migrations:
   ```bash
   uv run db prepare
   ```

4. **Add documents:**
   Place supported documents, such as PDF, text, Markdown, HTML, or Office
   files, in the `sources/` folder

5. **Ingest documents:**
   ```bash
   uv run python ingest_sources.py
   ```

## Usage

### Ingest Documents

```bash
uv run python ingest_sources.py
```

Each source receives a persistent document identity and checksum in the
PostgreSQL registry. Re-running ingestion skips unchanged documents; changing a
file writes a new index version and removes the old chunks after the replacement
succeeds.
Failures are isolated to the affected document and retried according to
`INGESTION_MAX_ATTEMPTS`.

The `db` command provides local development tasks: `uv run db create` creates
the configured database, `uv run db migrate` applies pending Alembic migrations,
and `uv run db drop` asks for the database name before dropping it.
`uv run db prepare` creates the database if needed and applies migrations.
These commands require a local PostgreSQL URL; the role must have permission
to create or drop the database when using those commands. For an existing
database whose schema already matches the initial migration, run
`uv run alembic stamp head` once to establish its migration baseline. To
inspect the migration version, run `uv run alembic current`.

Before ingestion, the registry connects to PostgreSQL and checks that its
document table has the expected columns. To probe database connectivity without
an OpenAI key, run
`uv run python healthcheck.py`; it exits nonzero if the database query fails.

### Ingest from an S3 source bucket

Set `S3_SOURCE_BUCKET`, optionally limit it with `S3_SOURCE_PREFIX`, and deploy
`src.s3_ingestion_handler.lambda_handler` behind an S3-to-SQS-to-Lambda
notification. The handler accepts only SQS-delivered S3 object-created events,
then streams each object to a bounded temporary file and ingests it under its
stable `s3://bucket/key` identity. See
[S3 source-bucket ingestion](docs/s3-ingestion.md) for IAM, event, and retry
guidance.

### Query Documents

```bash
uv run python main.py
```

This opens a chat interface for asking questions about the ingested documents.
Answers include numbered sources with PDF page numbers when available. If no
retrieved content meets the configured relevance threshold, the application
returns an explicit no-answer response instead of calling the chat model.

## Development

Run the complete local check suite:

```bash
uv run ruff check .
uv run mypy src/ main.py ingest_sources.py
uv run pytest
```

Run an individual check:

```bash
uv run pytest tests/test_retriever.py
```

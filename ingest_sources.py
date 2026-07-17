#!/usr/bin/env python3
from src.embedding import save_documents


def main() -> None:
    files = save_documents()
    print("The following files were ingested:")
    for file in files:
        print(file)


if __name__ == "__main__":
    main()

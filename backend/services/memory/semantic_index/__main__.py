"""Explicit manifest-based indexing: python -m ...semantic_index manifest.json."""

import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
from uuid import UUID

from sqlalchemy import create_engine

from backend.database.sessions import create_session_factory
from backend.services.memory.semantic_index import (
    EmbeddingDocument, EmbeddingSpec, OpenAIEmbeddingProvider, SemanticIndex,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--model", default="text-embedding-3-large")
    parser.add_argument("--dimensions", type=int, default=3072)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--execute", action="store_true", help="Explicitly allow paid embedding calls and derived index writes")
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    documents = tuple(EmbeddingDocument(
        version_id=UUID(row["version_id"]), document_text=row["document_text"],
        content_hash=row["content_hash"], builder_version=row["builder_version"],
    ) for row in manifest["documents"])
    engine = create_engine(os.environ["AIDAM_DATABASE_URL"])
    spec = EmbeddingSpec(model=args.model, dimensions=args.dimensions)
    index = SemanticIndex(create_session_factory(engine), UUID(manifest["competition_id"]), OpenAIEmbeddingProvider(spec))
    try:
        index.validate_documents(documents)
        result = (
            asdict(index.index_missing(documents, batch_size=args.batch_size))
            if args.execute else {
                "mode": "validated_preview", "documents": len(documents),
                "input_characters": sum(len(row.document_text) for row in documents),
                "spec": asdict(spec), "provider_calls": 0,
            }
        )
        print(json.dumps(result, sort_keys=True))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()

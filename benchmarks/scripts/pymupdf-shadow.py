#!/usr/bin/env python3
"""Count PyMuPDF table candidates without emitting tender text.

PyMuPDF is an optional evaluation dependency and is not part of product runtime.
Example:
  python3 benchmarks/scripts/pymupdf-shadow.py \
    gandhinagar=/path/to/tender.pdf iisc=/path/to/example.pdf
"""

import argparse
import hashlib
import json
import os
import time


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inspect_document(document_id, path, strategies):
    try:
        import fitz
    except ImportError as error:
        raise SystemExit("Install PyMuPDF 1.26.5 in an isolated evaluation environment first.") from error

    started = time.perf_counter()
    result = {
        "id": document_id,
        "filename": os.path.basename(path),
        "bytes": os.path.getsize(path),
        "sha256": sha256_file(path),
    }
    document = fitz.open(path)
    try:
        result["pages"] = document.page_count
        result["nativeTextPages"] = 0
        result["strategies"] = {
            strategy: {"pagesWithTables": 0, "tables": 0, "rows": 0}
            for strategy in strategies
        }
        for page in document:
            if page.get_text("text").strip():
                result["nativeTextPages"] += 1
            for strategy in strategies:
                try:
                    tables = page.find_tables(strategy=strategy).tables
                except Exception as error:  # Keep per-page parser limitations visible.
                    result.setdefault("pageErrors", []).append({
                        "page": page.number + 1,
                        "strategy": strategy,
                        "errorType": type(error).__name__,
                    })
                    continue
                counts = result["strategies"][strategy]
                if tables:
                    counts["pagesWithTables"] += 1
                counts["tables"] += len(tables)
                counts["rows"] += sum(len(table.rows) for table in tables)
    finally:
        document.close()
    result["elapsedSeconds"] = round(time.perf_counter() - started, 3)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--strategies",
        nargs="+",
        choices=("lines", "lines_strict", "text"),
        default=("lines", "lines_strict", "text"),
    )
    parser.add_argument("documents", nargs="+", metavar="ID=PDF_PATH")
    args = parser.parse_args()
    documents = []
    for value in args.documents:
        document_id, separator, path = value.partition("=")
        if not separator or not document_id or not path or not os.path.isfile(path):
            parser.error("each document must be ID=PATH and PATH must exist")
        documents.append(inspect_document(document_id, path, args.strategies))
    print(json.dumps({"pymupdfVersion": __import__("fitz").VersionBind, "documents": documents}, indent=2))


if __name__ == "__main__":
    main()

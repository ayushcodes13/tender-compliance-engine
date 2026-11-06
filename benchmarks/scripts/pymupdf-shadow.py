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
import math
import os
import time


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def round_box(box):
    if not box or len(box) != 4:
        return None
    return [round(float(value), 2) for value in box]


def pretty_inventory_json(value, depth=0):
    """Keep records readable while compacting numeric bounds and cell grids."""
    indent = "  " * depth
    if isinstance(value, dict):
        if not value:
            return "{}"
        entries = [
            f'{"  " * (depth + 1)}{json.dumps(key)}: {pretty_inventory_json(item, depth + 1)}'
            for key, item in value.items()
        ]
        return "{\n" + ",\n".join(entries) + f"\n{indent}}}"
    if isinstance(value, list):
        if not value:
            return "[]"
        if all(item is None or isinstance(item, (str, int, float, bool)) for item in value):
            return json.dumps(value, separators=(",", ": "))
        if all(
            item is None or (isinstance(item, list) and len(item) == 4
                             and all(isinstance(part, (int, float)) and math.isfinite(part) for part in item))
            for item in value
        ):
            return "[" + ", ".join(pretty_inventory_json(item, depth + 1) for item in value) + "]"
        entries = [f'{"  " * (depth + 1)}{pretty_inventory_json(item, depth + 1)}' for item in value]
        return "[\n" + ",\n".join(entries) + f"\n{indent}]"
    return json.dumps(value, separators=(",", ": "))


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
        result["pageInventory"] = []
        result["strategies"] = {
            strategy: {"pagesWithTables": 0, "tables": 0, "rows": 0}
            for strategy in strategies
        }
        for page in document:
            native_text = page.get_text("text")
            if native_text.strip():
                result["nativeTextPages"] += 1
            text_dict = page.get_text("dict")
            text_blocks = [block for block in text_dict.get("blocks", []) if block.get("type") == 0]
            words = page.get_text("words")
            image_regions = page.get_image_info(xrefs=True)
            page_area = max(page.rect.width * page.rect.height, 0)
            image_area = 0
            image_inventory = []
            for image in image_regions:
                bbox = image.get("bbox")
                if bbox:
                    area = max(0, bbox[2] - bbox[0]) * max(0, bbox[3] - bbox[1])
                    image_area += area
                    image_inventory.append({
                        "id": f"{document_id}:page:{page.number + 1}:image:{len(image_inventory) + 1}",
                        "bbox": round_box(bbox),
                        "pixelWidth": image.get("width"),
                        "pixelHeight": image.get("height"),
                        "areaRatio": round(min(1, area / page_area), 6) if page_area else 0,
                    })
            text_inventory = []
            for index, block in enumerate(text_blocks):
                block_text = "".join(span.get("text", "") for line in block.get("lines", []) for span in line.get("spans", []))
                text_inventory.append({
                    "id": f"{document_id}:page:{page.number + 1}:text:{index + 1}",
                    "parserBlockOrder": index + 1,
                    "bbox": round_box(block.get("bbox")),
                    "characterCount": len(block_text),
                })
            result["pageInventory"].append({
                "page": page.number + 1,
                "width": round(page.rect.width, 2),
                "height": round(page.rect.height, 2),
                "rotation": page.rotation,
                "coordinateSystem": "pymupdf-page-points",
                "geometryPrecision": "parser-reported",
                "nativeTextChars": len(native_text.strip()),
                "nativeWords": len(words),
                "nativeTextBlocks": len(text_blocks),
                "imageRegions": len(image_regions),
                "textRegionInventory": text_inventory,
                "imageRegionInventory": image_inventory,
                "imageAreaRatio": round(min(1, image_area / page_area), 4) if page_area else 0,
                "vectorDrawingCount": len(page.get_drawings()),
            })
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
                counts.setdefault("candidates", []).extend({
                    "id": f"{document_id}:page:{page.number + 1}:{strategy}:table:{table_index + 1}",
                    "bbox": round_box(table.bbox),
                    "rowCount": len(table.rows),
                    "columnCount": table.col_count,
                    **({"cellBboxes": [
                        [round_box(cell) for cell in row.cells]
                        for row in table.rows
                    ]} if strategy in ("lines", "lines_strict") else {}),
                } for table_index, table in enumerate(tables))
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
    output = {
        "schemaVersion": 2,
        "pymupdfVersion": __import__("fitz").VersionBind,
        "sourceTextIncluded": False,
        "documents": documents,
    }
    print(pretty_inventory_json(output))


if __name__ == "__main__":
    main()

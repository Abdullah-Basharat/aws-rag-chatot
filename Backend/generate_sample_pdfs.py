"""
Utility script to generate synthetic PDF files for RAG testing.

Each generated user gets 5 PDF files with 3 pages of simple textual content.
This avoids committing binary PDF files to the repository while still
fulfilling the requirement to provide sample documents.
"""

import os
from pathlib import Path
from typing import List

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas


def _make_pdf(path: Path, title: str, body_lines: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(path), pagesize=A4)
    width, height = A4

    for page_idx in range(3):
        c.setFont("Helvetica-Bold", 14)
        c.drawString(72, height - 72, f"{title} - Page {page_idx + 1}")
        c.setFont("Helvetica", 11)
        y = height - 120
        for line in body_lines:
            if y < 72:
                break
            c.drawString(72, y, line)
            y -= 16
        c.showPage()

    c.save()


def generate_user_pdfs(output_dir: str, user_id: str, count: int = 5) -> None:
    base = Path(output_dir) / user_id
    for i in range(1, count + 1):
        filename = base / f"{user_id}_doc_{i}.pdf"
        lines = [
            f"This is synthetic PDF document {i} for user {user_id}.",
            "It is intended for testing the RAG ingestion pipeline.",
            "The content includes simple paragraphs and table-like text:",
            "TABLE: Item | Quantity | Price",
            f"Row 1: Widget-{i} | {i * 10} | ${i * 3.5:.2f}",
            f"Row 2: Gadget-{i} | {i * 5} | ${i * 4.0:.2f}",
            "Only textual content will be used for embeddings.",
        ]
        _make_pdf(filename, f"Sample PDF {i} for {user_id}", lines)
        print(f"Created {filename}")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Generate synthetic PDFs for RAG chatbot testing."
    )
    parser.add_argument(
        "--output-dir",
        default="sample_pdfs",
        help="Directory where generated PDFs will be stored.",
    )
    parser.add_argument(
        "--user-id",
        action="append",
        dest="user_ids",
        help="User ID to generate PDFs for (can be specified multiple times).",
    )
    args = parser.parse_args()

    user_ids = args.user_ids or ["user1"]
    for uid in user_ids:
        generate_user_pdfs(args.output_dir, uid)


if __name__ == "__main__":
    main()



"""
Document Parser — The lowest-level input layer of the NLP pipeline.

Reads chapter files (PDF, DOCX, TXT) and returns raw text.
This is the very first step in the evidence extraction chain:

  File → Raw Text → (cleaner → segmenter → NLP → NER → coref → ...) → ChapterData

The parser does NOT interpret content. It merely extracts text from containers.
All understanding happens downstream in the Narrative State Engine.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("NarrativeEngine.Pipeline.Parser")


class DocumentParser:
    """
    Extracts raw text from document files.

    Supports:
      - .txt  (plain text)
      - .pdf  (via PyMuPDF / fitz)
      - .docx (via python-docx)

    Usage:
        parser = DocumentParser()
        text = parser.parse("chapter_01.pdf")
    """

    # Supported file extensions and their handler methods
    SUPPORTED_EXTENSIONS = {".txt", ".pdf", ".docx"}

    def parse(self, file_path: str) -> str:
        """
        Parse a document file and return its raw text content.

        Args:
            file_path: Path to the document file.

        Returns:
            The extracted raw text as a string.

        Raises:
            FileNotFoundError: If the file does not exist.
            ValueError: If the file extension is not supported.
            RuntimeError: If parsing fails for any reason.
        """
        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        extension = path.suffix.lower()
        if extension not in self.SUPPORTED_EXTENSIONS:
            raise ValueError(
                f"Unsupported file format: '{extension}'. "
                f"Supported formats: {', '.join(sorted(self.SUPPORTED_EXTENSIONS))}"
            )

        logger.info(f"Parsing {extension} file: {path.name}")

        try:
            if extension == ".txt":
                return self._parse_txt(path)
            elif extension == ".pdf":
                return self._parse_pdf(path)
            elif extension == ".docx":
                return self._parse_docx(path)
        except Exception as e:
            raise RuntimeError(f"Failed to parse {path.name}: {e}") from e

    def _parse_txt(self, path: Path) -> str:
        """Parse a plain text file."""
        # Try UTF-8 first, then fall back to system encoding
        for encoding in ["utf-8", "utf-8-sig", "latin-1", "cp1252"]:
            try:
                text = path.read_text(encoding=encoding)
                logger.debug(f"Successfully read with encoding: {encoding}")
                return text
            except UnicodeDecodeError:
                continue

        raise RuntimeError(f"Could not decode {path.name} with any supported encoding")

    def _parse_pdf(self, path: Path) -> str:
        """
        Parse a PDF file using PyMuPDF (fitz).

        Extracts text page by page and joins them with newlines.
        """
        try:
            import fitz  # PyMuPDF
        except ImportError:
            raise ImportError(
                "PyMuPDF is required for PDF parsing. "
                "Install it with: pip install pymupdf"
            )

        doc = fitz.open(str(path))
        pages = []
        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text("text")
            if text.strip():
                pages.append(text)
            logger.debug(f"Extracted page {page_num + 1}/{len(doc)}")

        doc.close()

        full_text = "\n\n".join(pages)
        logger.info(f"Extracted {len(pages)} pages, {len(full_text)} characters from PDF")
        return full_text

    def _parse_docx(self, path: Path) -> str:
        """
        Parse a DOCX file using python-docx.

        Extracts text from all paragraphs and joins them with newlines.
        """
        try:
            import docx
        except ImportError:
            raise ImportError(
                "python-docx is required for DOCX parsing. "
                "Install it with: pip install python-docx"
            )

        doc = docx.Document(str(path))
        paragraphs = []
        for para in doc.paragraphs:
            text = para.text.strip()
            if text:
                paragraphs.append(text)

        full_text = "\n\n".join(paragraphs)
        logger.info(
            f"Extracted {len(paragraphs)} paragraphs, "
            f"{len(full_text)} characters from DOCX"
        )
        return full_text

    def get_file_info(self, file_path: str) -> dict:
        """
        Get basic metadata about a document file without fully parsing it.

        Returns:
            Dict with keys: name, extension, size_bytes, exists
        """
        path = Path(file_path)
        return {
            "name": path.name,
            "extension": path.suffix.lower(),
            "size_bytes": path.stat().st_size if path.exists() else 0,
            "exists": path.exists(),
            "supported": path.suffix.lower() in self.SUPPORTED_EXTENSIONS,
        }

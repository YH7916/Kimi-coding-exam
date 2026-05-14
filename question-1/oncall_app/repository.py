"""Document repository for loading and reading SOP files."""

from pathlib import Path

from oncall_app.html_parser import parse_html_document
from oncall_app.models import Document


FORBIDDEN_FILE_NAME_CHARS = {"*", "?", "[", "]"}


class DocumentRepository:
    """In-memory repository backed by the local data directory."""

    def __init__(self, data_dir: Path | str):
        self.data_dir = Path(data_dir)
        self._documents: dict[str, Document] = {}
        self.reload()

    def reload(self):
        """Reload all HTML SOP files from the data directory."""
        self._documents = {}
        for path in sorted(self.data_dir.glob("*.html")):
            doc_id = path.stem
            self.add_document(doc_id, path.read_text(encoding="utf-8"))

    def add_document(self, doc_id: str, html: str) -> Document:
        """Add or replace a parsed document by id."""
        document = parse_html_document(doc_id, html)
        self._documents[doc_id] = document
        return document

    def all_documents(self) -> list[Document]:
        """Return all parsed documents sorted by document id."""
        return [self._documents[key] for key in sorted(self._documents)]

    def get(self, doc_id: str) -> Document:
        """Return one parsed document by id."""
        return self._documents[doc_id]

    def read_file(self, fname: str) -> str:
        """Read a direct file name from the data directory.

        This backs the Agent's required readFile(fname) tool. It accepts direct
        file names only: no paths, no parent traversal, and no wildcard syntax.
        """
        path = Path(fname)
        if path.name != fname or any(char in fname for char in FORBIDDEN_FILE_NAME_CHARS):
            raise ValueError("readFile only accepts a direct file name")

        candidate = self.data_dir / fname
        if not candidate.is_file():
            raise FileNotFoundError(fname)
        return candidate.read_text(encoding="utf-8")

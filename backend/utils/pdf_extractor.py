"""Extract text from PDF bytes using pdfplumber."""
import io
import logging

logger = logging.getLogger(__name__)


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Extract plain text from PDF bytes. Returns empty string on failure."""
    if not pdf_bytes or len(pdf_bytes) < 100:
        return ""
    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            parts = []
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    parts.append(text)
            return "\n\n".join(parts) if parts else ""
    except Exception as e:
        logger.warning("pdf_extractor: failed to extract text: %s", e)
        return ""

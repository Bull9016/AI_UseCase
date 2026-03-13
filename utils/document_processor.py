"""
Document processing utilities for RAG.
Handles parsing uploaded files into text chunks for the vector store.
"""


def chunk_text(text, chunk_size=500, overlap=50):
    """Split text into overlapping chunks for better retrieval."""
    chunks = []
    start = 0
    text = text.strip()

    if not text:
        return chunks

    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        if chunk.strip():
            chunks.append(chunk.strip())
        start += chunk_size - overlap

    return chunks


def parse_txt(file_bytes):
    """Parse a .txt file into text."""
    try:
        return file_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return file_bytes.decode("latin-1")


def parse_csv(file_bytes):
    """Parse a .csv file into text (row-by-row)."""
    import csv
    import io

    text = file_bytes.decode("utf-8")
    reader = csv.reader(io.StringIO(text))
    rows = []
    for row in reader:
        rows.append(", ".join(row))
    return "\n".join(rows)


def parse_pdf(file_bytes):
    """Parse a .pdf file into text. Uses PyPDF2 if available."""
    try:
        import PyPDF2
        import io

        reader = PyPDF2.PdfReader(io.BytesIO(file_bytes))
        text_parts = []
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)
        return "\n".join(text_parts)

    except ImportError:
        # Fallback: try to extract readable text from bytes
        try:
            return file_bytes.decode("utf-8", errors="ignore")
        except Exception:
            return ""

    except Exception as e:
        print(f"[PDF PARSE ERROR] {e}")
        return ""


def process_uploaded_file(uploaded_file):
    """
    Process an uploaded Streamlit file and return text chunks.
    Returns (chunks, error_msg) tuple.
    """
    try:
        file_bytes = uploaded_file.read()
        filename = uploaded_file.name.lower()

        if filename.endswith(".txt"):
            text = parse_txt(file_bytes)
        elif filename.endswith(".csv"):
            text = parse_csv(file_bytes)
        elif filename.endswith(".pdf"):
            text = parse_pdf(file_bytes)
        else:
            return [], f"Unsupported file type: {uploaded_file.name}"

        if not text.strip():
            return [], "File appears to be empty or could not be read."

        chunks = chunk_text(text)

        if not chunks:
            return [], "No text content could be extracted from the file."

        return chunks, None

    except Exception as e:
        return [], f"Error processing file: {e}"

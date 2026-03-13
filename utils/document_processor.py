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
    """Parse a .csv file and return (raw_text, schema_summary)."""
    import csv
    import io
    
    text_content = file_bytes.decode("utf-8")
    f = io.StringIO(text_content)
    reader = csv.reader(f)
    
    headers = next(reader, None)
    if not headers:
        return text_content, "No headers found."
    
    # Get first few rows for type inference/preview
    sample_rows = []
    for _ in range(5):
        try:
            sample_rows.append(next(reader))
        except StopIteration:
            break
            
    schema_summary = f"Columns: {', '.join(headers)}\nSample Rows: {len(sample_rows)}"
    
    f.seek(0)
    rows = []
    reader = csv.reader(f)
    for row in reader:
        rows.append(", ".join(row))
    
    return "\n".join(rows), schema_summary


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
    Process an uploaded Streamlit file and return (text_chunks, schema_info, error_msg).
    """
    try:
        file_bytes = uploaded_file.read()
        filename = uploaded_file.name.lower()
        schema_info = None

        if filename.endswith(".txt"):
            text = parse_txt(file_bytes)
        elif filename.endswith(".csv"):
            text, schema_info = parse_csv(file_bytes)
        elif filename.endswith(".pdf"):
            text = parse_pdf(file_bytes)
        else:
            return [], None, f"Unsupported file type: {uploaded_file.name}"

        if not text.strip():
            return [], None, "File appears to be empty or could not be read."

        chunks = chunk_text(text)

        if not chunks:
            return [], None, "No text content could be extracted from the file."

        return chunks, schema_info, None

    except Exception as e:
        return [], None, f"Error processing file: {e}"

"""
Document processing utilities for RAG.
Handles parsing uploaded files into text chunks for the vector store.
Supports: TXT, CSV, PDF, SQL, DAX, RDL, PBIX, TWB, TWBX, TDS, HYPER, TDE
"""
import io
import re
import csv
import xml.etree.ElementTree as ET


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


def parse_sql(file_bytes):
    """Parse a .sql file – extract queries, table definitions, comments."""
    try:
        raw = file_bytes.decode("utf-8")
    except UnicodeDecodeError:
        raw = file_bytes.decode("latin-1")

    # Build a structured summary
    lines = raw.splitlines()
    tables_created = []
    queries = []
    comments = []

    for line in lines:
        stripped = line.strip().upper()
        if stripped.startswith("--"):
            comments.append(line.strip())
        elif "CREATE TABLE" in stripped or "CREATE OR REPLACE" in stripped:
            # Try to capture the table name
            match = re.search(r'CREATE\s+(?:OR\s+REPLACE\s+)?(?:TEMP(?:ORARY)?\s+)?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([\w\."]+)', line, re.IGNORECASE)
            if match:
                tables_created.append(match.group(1).strip('"'))
        elif any(kw in stripped for kw in ["SELECT", "INSERT", "UPDATE", "DELETE", "ALTER", "DROP"]):
            queries.append(line.strip())

    schema_info = ""
    if tables_created:
        schema_info = f"SQL Tables defined: {', '.join(tables_created)}"

    return raw, schema_info or None


def parse_dax(file_bytes):
    """Parse a .dax file – DAX queries/measures used in Power BI."""
    try:
        raw = file_bytes.decode("utf-8")
    except UnicodeDecodeError:
        raw = file_bytes.decode("latin-1")

    # Extract measure names and named expressions
    measures = re.findall(r'(?:DEFINE\s+)?MEASURE\s+([\w\[\]\.\']+)', raw, re.IGNORECASE)
    variables = re.findall(r'VAR\s+(\w+)', raw, re.IGNORECASE)
    tables_ref = re.findall(r"'([^']+)'", raw)
    # Deduplicate table references
    unique_tables = list(dict.fromkeys(tables_ref))

    schema_parts = []
    if measures:
        schema_parts.append(f"DAX Measures: {', '.join(measures)}")
    if variables:
        schema_parts.append(f"DAX Variables: {', '.join(variables)}")
    if unique_tables:
        schema_parts.append(f"Referenced Tables: {', '.join(unique_tables[:20])}")

    schema_info = "\n".join(schema_parts) if schema_parts else None
    return raw, schema_info


def parse_rdl(file_bytes):
    """Parse a .rdl file – Report Definition Language (XML-based, used by SSRS/Power BI paginated reports)."""
    try:
        raw = file_bytes.decode("utf-8")
    except UnicodeDecodeError:
        raw = file_bytes.decode("latin-1")

    extracted_parts = []
    schema_parts = []

    try:
        root = ET.fromstring(raw)
        # RDL uses namespaces, strip them for easier parsing
        ns = ""
        if root.tag.startswith("{"):
            ns = root.tag.split("}")[0] + "}"

        # Extract DataSets
        for ds in root.iter(f"{ns}DataSet"):
            ds_name = ds.get("Name", "Unnamed")
            schema_parts.append(f"DataSet: {ds_name}")
            # Extract query text
            for qt in ds.iter(f"{ns}CommandText"):
                if qt.text:
                    extracted_parts.append(f"-- DataSet: {ds_name}\n{qt.text.strip()}")
            # Extract field names
            fields = [f.get("Name", "") for f in ds.iter(f"{ns}Field") if f.get("Name")]
            if fields:
                schema_parts.append(f"  Fields: {', '.join(fields)}")

        # Extract DataSources
        for dsrc in root.iter(f"{ns}DataSource"):
            dsrc_name = dsrc.get("Name", "")
            for conn in dsrc.iter(f"{ns}ConnectString"):
                if conn.text:
                    extracted_parts.append(f"-- DataSource: {dsrc_name}\nConnection: {conn.text.strip()}")

        # Extract report parameters
        for param in root.iter(f"{ns}ReportParameter"):
            p_name = param.get("Name", "")
            if p_name:
                schema_parts.append(f"Parameter: {p_name}")

    except ET.ParseError:
        # If XML parsing fails, just use the raw text
        pass

    text = "\n\n".join(extracted_parts) if extracted_parts else raw
    schema_info = "\n".join(schema_parts) if schema_parts else None
    return text, schema_info


def parse_pbix(file_bytes):
    """
    Parse a .pbix file – Power BI Desktop file (ZIP archive).
    Extracts DataModel schema, DAX measures, and metadata.
    """
    import zipfile
    import json

    extracted_parts = []
    schema_parts = []

    try:
        zf = zipfile.ZipFile(io.BytesIO(file_bytes))
        file_list = zf.namelist()
        extracted_parts.append(f"PBIX Archive Contents: {', '.join(file_list)}")

        # Try to read DataModelSchema (JSON representation of the model)
        for name in file_list:
            lower = name.lower()
            if "datamodelschema" in lower:
                try:
                    raw_data = zf.read(name)
                    # DataModelSchema is often UTF-16 LE encoded
                    try:
                        model_text = raw_data.decode("utf-16-le")
                    except (UnicodeDecodeError, UnicodeError):
                        model_text = raw_data.decode("utf-8", errors="ignore")

                    # Try to parse as JSON for structured extraction
                    try:
                        model_json = json.loads(model_text)
                        # Extract tables and columns
                        tables = model_json.get("model", {}).get("tables", [])
                        for table in tables:
                            t_name = table.get("name", "Unknown")
                            columns = [col.get("name", "") for col in table.get("columns", [])]
                            measures = [m.get("name", "") for m in table.get("measures", [])]
                            schema_parts.append(f"Table: {t_name}")
                            if columns:
                                schema_parts.append(f"  Columns: {', '.join(columns)}")
                            if measures:
                                schema_parts.append(f"  Measures: {', '.join(measures)}")
                                # Also extract DAX expressions
                                for m in table.get("measures", []):
                                    expr = m.get("expression", "")
                                    m_name = m.get("name", "")
                                    if expr:
                                        extracted_parts.append(f"-- Measure: {m_name}\n{expr}")
                    except (json.JSONDecodeError, KeyError):
                        # Not valid JSON, just use raw text
                        extracted_parts.append(model_text[:5000])
                except Exception:
                    pass

            # Try to read DiagramLayout or Report/Layout for report metadata
            elif "report/layout" in lower or "diagramlayout" in lower:
                try:
                    raw_data = zf.read(name)
                    try:
                        layout_text = raw_data.decode("utf-16-le")
                    except (UnicodeDecodeError, UnicodeError):
                        layout_text = raw_data.decode("utf-8", errors="ignore")
                    # Extract page/visual names if JSON
                    try:
                        layout_json = json.loads(layout_text)
                        sections = layout_json.get("sections", [])
                        for sec in sections:
                            page_name = sec.get("displayName", "Unnamed Page")
                            visuals = sec.get("visualContainers", [])
                            extracted_parts.append(f"Report Page: {page_name} ({len(visuals)} visuals)")
                    except (json.JSONDecodeError, KeyError):
                        pass
                except Exception:
                    pass

    except zipfile.BadZipFile:
        return "Error: This .pbix file appears to be corrupted or not a valid Power BI file.", None
    except Exception as e:
        return f"Error reading .pbix file: {e}", None

    text = "\n\n".join(extracted_parts) if extracted_parts else "PBIX file processed but no readable content could be extracted."
    schema_info = "\n".join(schema_parts) if schema_parts else None
    return text, schema_info


def parse_twb(file_bytes):
    """
    Parse a .twb file – Tableau Workbook (XML-based).
    Extracts data sources, connections, calculated fields, and worksheets.
    """
    try:
        raw = file_bytes.decode("utf-8")
    except UnicodeDecodeError:
        raw = file_bytes.decode("latin-1")

    extracted_parts = []
    schema_parts = []

    try:
        root = ET.fromstring(raw)

        # Extract datasources
        for ds in root.iter("datasource"):
            ds_name = ds.get("name", ds.get("caption", "Unnamed"))
            schema_parts.append(f"DataSource: {ds_name}")

            # Extract connection info
            for conn in ds.iter("connection"):
                conn_class = conn.get("class", "")
                db_name = conn.get("dbname", "")
                server = conn.get("server", "")
                if conn_class:
                    info = f"  Connection: {conn_class}"
                    if server:
                        info += f" @ {server}"
                    if db_name:
                        info += f" db={db_name}"
                    schema_parts.append(info)

            # Extract columns/fields
            for col in ds.iter("column"):
                col_name = col.get("name", col.get("caption", ""))
                col_type = col.get("datatype", "")
                role = col.get("role", "")
                if col_name:
                    schema_parts.append(f"  Column: {col_name} (type={col_type}, role={role})")

            # Extract calculated fields
            for calc in ds.iter("calculation"):
                formula = calc.get("formula", "")
                if formula:
                    extracted_parts.append(f"-- Calculated Field\n{formula}")

        # Extract worksheets
        for ws in root.iter("worksheet"):
            ws_name = ws.get("name", "Unnamed")
            extracted_parts.append(f"Worksheet: {ws_name}")

        # Extract dashboards
        for db in root.iter("dashboard"):
            db_name = db.get("name", "Unnamed")
            extracted_parts.append(f"Dashboard: {db_name}")

        # Extract custom SQL
        for rel in root.iter("relation"):
            rel_type = rel.get("type", "")
            if rel_type == "text" and rel.text:
                extracted_parts.append(f"-- Custom SQL\n{rel.text.strip()}")

    except ET.ParseError:
        pass

    text = "\n\n".join(extracted_parts) if extracted_parts else raw
    schema_info = "\n".join(schema_parts) if schema_parts else None
    return text, schema_info


def parse_twbx(file_bytes):
    """
    Parse a .twbx file – Tableau Packaged Workbook (ZIP containing .twb + data extracts).
    """
    import zipfile

    try:
        zf = zipfile.ZipFile(io.BytesIO(file_bytes))
        file_list = zf.namelist()

        # Find the .twb file inside
        twb_file = None
        for name in file_list:
            if name.lower().endswith(".twb"):
                twb_file = name
                break

        if twb_file:
            twb_bytes = zf.read(twb_file)
            text, schema_info = parse_twb(twb_bytes)
            # Add info about packaged data extracts
            extract_files = [f for f in file_list if f.lower().endswith((".hyper", ".tde", ".csv"))]
            if extract_files:
                extra = f"\n\nPackaged Data Extracts: {', '.join(extract_files)}"
                text += extra
            return text, schema_info
        else:
            return f"TWBX archive contents: {', '.join(file_list)}", None

    except zipfile.BadZipFile:
        return "Error: This .twbx file appears to be corrupted.", None
    except Exception as e:
        return f"Error reading .twbx file: {e}", None


def parse_tds(file_bytes):
    """Parse a .tds file – Tableau Data Source (XML-based, similar to TWB datasource section)."""
    try:
        raw = file_bytes.decode("utf-8")
    except UnicodeDecodeError:
        raw = file_bytes.decode("latin-1")

    extracted_parts = []
    schema_parts = []

    try:
        root = ET.fromstring(raw)

        # TDS is essentially a datasource element
        for ds in root.iter("datasource"):
            ds_name = ds.get("name", ds.get("caption", "Unnamed"))
            schema_parts.append(f"DataSource: {ds_name}")

            for conn in ds.iter("connection"):
                conn_class = conn.get("class", "")
                db_name = conn.get("dbname", "")
                server = conn.get("server", "")
                if conn_class:
                    info = f"  Connection: {conn_class}"
                    if server:
                        info += f" @ {server}"
                    if db_name:
                        info += f" db={db_name}"
                    schema_parts.append(info)

            for col in ds.iter("column"):
                col_name = col.get("name", col.get("caption", ""))
                col_type = col.get("datatype", "")
                if col_name:
                    schema_parts.append(f"  Column: {col_name} (type={col_type})")

        # Also check root level if it IS the datasource
        if root.tag == "datasource":
            ds_name = root.get("name", root.get("caption", "Unnamed"))
            if f"DataSource: {ds_name}" not in schema_parts:
                schema_parts.insert(0, f"DataSource: {ds_name}")

    except ET.ParseError:
        pass

    text = "\n\n".join(extracted_parts) if extracted_parts else raw
    schema_info = "\n".join(schema_parts) if schema_parts else None
    return text, schema_info


def process_uploaded_file(uploaded_file):
    """
    Process an uploaded Streamlit file and return (text_chunks, schema_info, error_msg).
    Supports: TXT, CSV, PDF, SQL, DAX, RDL, PBIX, TWB, TWBX, TDS
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
        elif filename.endswith(".sql"):
            text, schema_info = parse_sql(file_bytes)
        elif filename.endswith(".dax"):
            text, schema_info = parse_dax(file_bytes)
        elif filename.endswith(".rdl"):
            text, schema_info = parse_rdl(file_bytes)
        elif filename.endswith(".pbix"):
            text, schema_info = parse_pbix(file_bytes)
        elif filename.endswith(".twb"):
            text, schema_info = parse_twb(file_bytes)
        elif filename.endswith(".twbx"):
            text, schema_info = parse_twbx(file_bytes)
        elif filename.endswith(".tds"):
            text, schema_info = parse_tds(file_bytes)
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

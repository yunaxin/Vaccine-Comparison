"""
extract_requirements_form_parser.py

Uses Document AI's Form Parser to extract text and tables from a state's
school immunization requirement PDF. Intended to speed up the manual
extraction step used to build files like data/state_requirements/California.json --
this pulls out the raw text and table structure so dose-count numbers and
grade/age ranges are easier to find and transcribe, rather than replacing
manual verification entirely.

Requires a Form Parser processor created in Document AI (see setup steps).
"""

from google.cloud import documentai_v1 as documentai

PROJECT_ID = "vaccine-genie"
LOCATION = "us"  # matches the region chosen when creating the processor
PROCESSOR_ID = ""  # paste your processor ID here after creating it


def process_document(file_path: str, mime_type: str = "application/pdf") -> documentai.Document:
    client = documentai.DocumentProcessorServiceClient()
    processor_name = client.processor_path(PROJECT_ID, LOCATION, PROCESSOR_ID)

    with open(file_path, "rb") as f:
        file_content = f.read()

    raw_document = documentai.RawDocument(content=file_content, mime_type=mime_type)
    request = documentai.ProcessRequest(name=processor_name, raw_document=raw_document)

    result = client.process_document(request=request)
    return result.document


def print_extracted_text(document: documentai.Document):
    print("=== FULL TEXT ===")
    print(document.text)


def print_extracted_tables(document: documentai.Document):
    print("\n=== TABLES ===")
    for page_num, page in enumerate(document.pages):
        for table_num, table in enumerate(page.tables):
            print(f"\n--- Page {page_num + 1}, Table {table_num + 1} ---")
            for row in table.header_rows:
                cells = [get_text(cell.layout, document.text) for cell in row.cells]
                print(" | ".join(cells))
            print("-" * 40)
            for row in table.body_rows:
                cells = [get_text(cell.layout, document.text) for cell in row.cells]
                print(" | ".join(cells))


def get_text(layout, full_text: str) -> str:
    """Pulls the substring of full_text covered by a layout's text anchor."""
    if not layout.text_anchor.text_segments:
        return ""
    start = int(layout.text_anchor.text_segments[0].start_index)
    end = int(layout.text_anchor.text_segments[0].end_index)
    return full_text[start:end].strip()


if __name__ == "__main__":
    document = process_document("data/state_requirements/California.pdf")
    print_extracted_text(document)
    print_extracted_tables(document)
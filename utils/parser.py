import PyPDF2
import re

# EXTRACT TEXT FROM PDF
def extract_pdf_text(filepath):
    text = ""
    with open(filepath, "rb") as pdf_file:
        reader = PyPDF2.PdfReader(pdf_file)
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
    return text

# CLEAN TEXT
def clean_text(text):

    # remove extra spaces
    text = re.sub(r"\s+", " ", text)

    # remove leading/trailing spaces
    text = text.strip()

    return text

# SPLIT TEXT INTO CHUNKS
def chunk_text(text, chunk_size=500):

    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        chunks.append(chunk)
        start = end
    return chunks

# FULL PIPELINE
def parse_resume(filepath):

    raw_text = extract_pdf_text(filepath)
    clean_resume = clean_text(raw_text)
    chunks = chunk_text(clean_resume)
    return clean_resume, chunks

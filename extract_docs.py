from pathlib import Path
from docx import Document
root = Path(r'c:/Users/RG Saran Vishakan/Desktop/Narrative_Engine')
out = root / 'doc_extract.txt'
texts = []
for name in ['Project Vision.docx', 'Project Structure.docx']:
    p = root / name
    doc = Document(p)
    texts.append(f'---{name}---')
    texts.extend([para.text for para in doc.paragraphs])
out.write_text('\n'.join(texts), encoding='utf-8')
print(out)


import asyncio
import random
import docx
import re
from io import BytesIO

def _parse_logic(file_bytes: bytes) -> list[dict]:
    doc = docx.Document(BytesIO(file_bytes))
    savollar = []
    joriy_savol = None
    for p in doc.paragraphs:
        text = p.text.strip()
        if not text:
            continue
            
        if text[0].isdigit() and ("." in text[:4] or ")" in text[:4]):
            if joriy_savol and len(joriy_savol['variantlar']) >= 2:
                savollar.append(joriy_savol)
            
            clean_text = re.sub(r'^(\d+[\.\)]\s*)+', '', text)
            joriy_savol = {"savol": clean_text, "variantlar": [], "togri": 0}
            
        elif joriy_savol:
            if text.startswith('*'):
                joriy_savol['togri'] = len(joriy_savol['variantlar'])
                joriy_savol['variantlar'].append(text.replace('*', '', 1).strip())
            elif text.startswith('#'):
                joriy_savol['variantlar'].append(text.replace('#', '', 1).strip())
    
    if joriy_savol and len(joriy_savol['variantlar']) >= 2:
        savollar.append(joriy_savol)
        
    for q in savollar:
        v_copy = q['variantlar'].copy()
        correct_text = v_copy[q['togri']]
        random.shuffle(v_copy)
        q['variantlar'] = v_copy
        q['togri'] = v_copy.index(correct_text)
        
    return savollar

async def async_parse_docx(file_bytes: bytes) -> list[dict]:
    return await asyncio.to_thread(_parse_logic, file_bytes)
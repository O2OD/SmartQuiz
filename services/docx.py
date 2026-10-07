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
        text = p.text.replace('\xa0', ' ').strip()
        if not text:
            continue
            
        is_question = False
        clean_text = text
        
        if re.match(r'^\d+[\.\)]', text):
            is_question = True
            clean_text = re.sub(r'^\d+[\.\)]\s*', '', text).strip()
        elif text.endswith('?') and (not joriy_savol or len(joriy_savol['variantlar']) >= 2):
            is_question = True
            
        if is_question:
            if joriy_savol and len(joriy_savol['variantlar']) >= 2:
                savollar.append(joriy_savol)
            joriy_savol = {"savol": clean_text, "variantlar": [], "togri": 0}
            
        elif joriy_savol is not None:
            is_correct = False
            if text.startswith('*'):
                is_correct = True
                text = text.lstrip('*').strip()
            elif text.startswith('-') or text.startswith('+'):
                text = text.lstrip('-+').strip()
                
            if text:
                if is_correct:
                    joriy_savol['togri'] = len(joriy_savol['variantlar'])
                joriy_savol['variantlar'].append(text)
    
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
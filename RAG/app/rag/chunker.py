import re
import pymupdf


PDF_PATH = "data/manuals/manufacturing_rag_corpus_ko.pdf"

TITLE_SIZE = 21.0
HEADING_SIZE = 12.0
BODY_SIZE = 10.5

WRAP_MARGIN = 30
DOC_ID_RE = re.compile(r"[A-Z]+-\d+")
FOREVER = 99991231

def parse_meta(meta_line):
    """ 'QC-210 | REV.2 | 발효 2026-06-01 | 폐기 2026-08-15' → 딕셔너리 """
    info = {"doc_id": None, "rev": None, "kind": None, "date": None,
            "expire": None, "extra": []}
    
    for part in meta_line.split("|"):
        part = part.strip()
        if part.startswith("Rev."):
            info["rev"] = int(part[4:])
        elif part.startswith(("발효", "기록")):
            info["kind"], info["date"] = part.split()
        elif part.startswith("폐기"):
            info["expire"] = part.split()[1]
        elif DOC_ID_RE.fullmatch(part):
            info["doc_id"] = part
        else:
            info["extra"].append(part)
    return info
            
def to_int(date_str):
    """'2026-08-15' -> 20260815"""
    return int(date_str.replace("-", ""))

def validity(info):
    """(유효 시작일, 유효 종료일, 상태) 반환. 종료일 당일은 이미 무효"""
    if info["kind"] == "기록":
        return 0, FOREVER, "기록"
    valid_from = to_int(info["date"])
    if info["expire"]:
        return valid_from, to_int(info["expire"]), "폐기"
    return valid_from, FOREVER, " 유효"
    
def build_chunks(doc):
    right_edge = find_right_edge(doc)
    chunks = []
    for pno in range(1, len(doc)):
        page_no = pno + 1
        title, meta_line, sections = parse_page(doc[pno])
        info = parse_meta(meta_line)
        valid_from, valid_to, status =validity(info)
        scope = "/".join(info["extra"])
        if info["kind"] == "기록":
            period = f"기록 {info['date']}"
        elif info["expire"]:
            period = f"발효 {info['date']} / 폐기 {info['expire']}"
        else:
            period = f"발효 {info['date']}"
        
        for i, sec in enumerate(sections):
            body = join_lines(sec["lines"], right_edge)
            header = f"[{info['doc_id']} Rev.{info['rev']} | {title} | {scope} | {period}]"
            chunks.append({
                 "id": f"{info['doc_id']}-r{info['rev']}-{i}",
                "text": f"{header}\n{sec['heading']}\n{body}",
                "metadata": {
                    "doc_id": info["doc_id"],
                    "rev": info["rev"],
                    "title": title,
                    "page": page_no,
                    "section": sec["heading"],
                    "status": status,
                    "valid_from": valid_from,
                    "valid_to": valid_to,
                },
            })
    return chunks

def find_right_edge(doc):
    """문서 전체 본문 줄 중 가장 오른쪽 X1 = 본문영역의 오른쪽 """
    edge = 0
    for page in doc: 
        for block in page.get_text("dict")["blocks"]:
            for line in block.get("lines",[]):
                if round(line["spans"][0]["size"], 1) == BODY_SIZE:
                    edge = max(edge, line["bbox"][2])
    
    return edge

def join_lines(lines, right_edge):
    out = ""
    for text, x1 in lines:
        out += text
        if x1 < right_edge - WRAP_MARGIN:
            out += "\n"
    
    return out.strip()

def parse_page(page):
    title = None
    meta_line = None
    sections = []
    
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            
            text = "".join(span["text"] for span in line["spans"])
            size = round(line["spans"][0]["size"], 1)
            
            if not text.strip():
                continue
            
            if size == TITLE_SIZE:
                title = text.strip()
            elif size == HEADING_SIZE:
                
                sections.append({"heading": text.strip(), "lines": []})
            
            elif size == BODY_SIZE:
                if meta_line is None and not sections:
                    meta_line = text.strip()
                elif sections:
                    sections[-1]["lines"].append((text, line["bbox"][2]))
    
    return title, meta_line, sections             

if __name__ == "__main__":
    doc = pymupdf.open(PDF_PATH)
    chunks = build_chunks(doc)

    print(f"청크 {len(chunks)}개")
    for c in chunks:
        m = c["metadata"]
        print(f"{c['id']:14} {m['status']:2} {m['valid_from']:>8}~{m['valid_to']} | {m['section']}")

    print("\n--- 예시 청크 ---")
    for c in chunks:
        if c["id"] == "QC-210-r3-0":
            print(c["text"])

    print("\n--- 경계일 검사 ---")
    for asof in (20260814, 20260815):
        revs = set()
        for c in chunks:
            m = c["metadata"]
            if m["doc_id"] == "QC-210" and m["valid_from"] <= asof < m["valid_to"]:
                revs.add(m["rev"])
        print(asof, "→ 유효한 QC-210 개정:", sorted(revs))
        
            
            
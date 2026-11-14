import re
import sys
from datetime import date

import ollama

from app.rag.store import search 

LLM_MODEL = "qwen3:8b"

SYSTEM_PROMPT = """당신은 제조 문서 질의응답 도우미입니다. 다음 규칙을 반드시 지키세요.
1. [근거 문서]에 있는 내용만으로 답합니다. 일반 지식이나 추측으로 빈칸을 채우지 않습니다.
2. 근거가 없으면 "제공된 문서에서 근거를 찾을 수 없습니다"라고 답하고, 무엇이 없는지 밝힙니다.
3. 근거 문서는 [질문 기준일]에 유효했던 문서만 골라 둔 것입니다. 폐기일이 적혀 있어도 기준일이 그 전이면 그대로 사용합니다.
4. 제품·설비·로트가 다른 문서의 수치를 서로 대신 쓰지 않습니다. (예: VH-30 기준을 VH-20에 쓰지 않음)
5. 수치는 문서에 적힌 그대로 단위와 함께 옮깁니다.
6. 계산이 필요하면 문서의 정의와 계산 규칙을 따르고 식과 중간값을 보여 줍니다.
7. 답의 각 문장 끝에 근거를 [문서 ID, Rev.N, N쪽] 형식으로 붙입니다.
8. 한국어로 간결하게 답합니다."""


ISO_DATE_RE = re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})")
KO_DATE_RE = re.compile(r"(?:(\d{4})\s*년\s*)?(\d{1,2})\s*월\s*(\d{1,2})\s*일")


def parse_asof(question):
    
    m= ISO_DATE_RE.search(question) or KO_DATE_RE.search(question)
    if not m:
        return int(date.today().strftime("%Y%m%d"))
    y, mo, d = m.groups()
    y= int(y) if y else date.today().year
    return y *  10000 + int(mo) * 100 +int(d)


def ask(question, k=5, think=False):
    asof = parse_asof(question)
    hits = search(question, asof, k=k)
    
    context = "\n\n---\n\n".join(
        f"[{h['meta']['doc_id']}, Rev.{h['meta']['rev']}, {h['meta']['page']}쪽]\n{h['text']}"
        for h in hits
    )
    
    asof_str = f"{asof // 10000}-{asof // 100 % 100:02d}-{asof % 100:02d}"
    user_msg = f"[질문 기준일] {asof_str}\n\n[근거문서]\n{context}\n\n[질문]\n{question}"
    
    resp = ollama.chat(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        think=think,
        options={"temperature":0, "num_ctx": 8192},
    )
    return resp.message.content, hits, asof_str

if __name__ == "__main__":
    think = "--think" in sys.argv
    print(f"제조 문서 RAG (추론 모드: {'켜짐' if think else '꺼짐'} . 종료: exit")
    while True:
        q = input("\n질문>").strip()
        #한글 입력 중 지우다 남은 깨진 바이트를 버린다. 
        q= q.encode("utf-8", "surrogateescape").decode("utf-8", "ignore")
        if q in ("exit", "quit", "q"):
            break
        if not q:
            continue
        answer, hits, asof_str = ask(q, think=think)
        print(f"\n(기준일 {asof_str})  검색된 근거: ")
        for h in hits:
            m = h["meta"]
            print(f" {h['dist']: .3f} {m['doc_id']} Rev.{m['rev']} {m['page']}쪽 . {m['section']}")
        print(f"\n답변: \n{answer}")
    
    
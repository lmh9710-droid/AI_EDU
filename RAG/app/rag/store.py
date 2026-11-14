import chromadb
import ollama
import pymupdf

from app.rag.chunker import PDF_PATH, build_chunks

DB_PATH = "data/chroma"

COLLECTION = "factory_docs"
EMBED_MODEL = "bge-m3"

client = chromadb.PersistentClient(path = DB_PATH)

def embed(texts):
    """문장 목록 -> 벡터 목록(Ollama bge -m3)"""
    return ollama.embed(model = EMBED_MODEL, input = texts).embeddings

def get_collection():
    return client.get_or_create_collection(
        COLLECTION, embedding_function=None, metadata = {"hnsw:space": "cosine" }
        
    )    

def build_index():
    chunks = build_chunks(pymupdf.open(PDF_PATH))
    
    if COLLECTION in [c.name for c in client.list_collections()]:
        client.delete_collection(COLLECTION)
    col = get_collection()
    
    texts = [c["text"] for c in chunks]
    col.add(
        ids = [c["id"] for c in chunks],
        documents= texts,
        metadatas= [c["metadata"] for c in chunks],
        embeddings= embed(texts),
    )
    return col

def search(question, asof =None, k=4):
    """asof(예: 20260810)가 있으면 날 유효한 문서만 검색"""
    where = None
    if asof:
        where = {"$and" : [
            {"valid_from": {"$lte": asof}},
            {"valid_to": {"$gt": asof }}
        ]}
    res = get_collection().query(
        query_embeddings=embed([question]),
        n_results=k,
        where=where,
        include=["documents","metadatas", "distances"],
    )
    
    return [
        {"id": i, "dist": d, "text": t, "meta": m}
        for i, d, t, m in zip(res["ids"][0], res["distances"][0],
                              res["documents"][0], res["metadatas"][0])
    ]

if __name__ == "__main__":
    col = build_index()
    print(f"저장완료: {col.count()}개\n")
    
    question = "VH-20 내경 합격 범위는?"
    for label, asof in [("필터 없음", None),
                        ("기준일 2026-08-10", 20260810),
                        ("기준일 2026-11-14", 20261114)]:
        print(f"=== {question} [{label} ===]")
        for r in search(question, asof):
            m = r["meta"]
            print(f" {r['dist']:.3f} {r['id']:14} {m['status']:2} | {m['title']} . {m['section']}")
            


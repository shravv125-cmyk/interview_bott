from sentence_transformers import SentenceTransformer
import faiss
import numpy as np

# LOAD EMBEDDING MODEL (ONCE)
model = SentenceTransformer("all-MiniLM-L6-v2")

# GLOBAL MEMORY
stored_chunks = []
index = None

# CREATE VECTOR STORE
def create_vector_store(chunks):

    global stored_chunks
    global index

    stored_chunks = chunks
    embeddings = model.encode(chunks)
    embeddings = np.array(embeddings, dtype="float32")
    dimension = embeddings.shape[1]
    index = faiss.IndexFlatL2(dimension)
    index.add(embeddings)   # type: ignore

# SEARCH MOST RELEVANT CHUNKS
def search_chunks(query, top_k=3):

    global index
    global stored_chunks

    if index is None:
        return []
    query_embedding = model.encode([query])
    query_embedding = np.array(query_embedding, dtype="float32")
    distances, labels = index.search(query_embedding, top_k)   # type: ignore
    results = []
    for idx in labels[0]:
        if idx != -1 and idx < len(stored_chunks):
            results.append(stored_chunks[idx])
    return results

# BUILD CONTEXT FOR LLM
def build_context(query):
    results = search_chunks(query)
    context = "\n\n".join(results)
    return context

# CHECK IF VECTOR STORE READY
def is_ready():
    global index
    return index is not None

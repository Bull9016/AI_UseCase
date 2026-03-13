import faiss
import numpy as np
from models.embeddings import embed_text


class VectorStore:

    def __init__(self):

        self.index = faiss.IndexFlatL2(384)
        self.documents = []

    def add_document(self, text, metadata=None):

        vector = embed_text(text)

        self.index.add(np.array([vector]).astype("float32"))
        
        doc = {
            "text": text,
            "metadata": metadata or {}
        }
        self.documents.append(doc)

    def search(self, query, k=3):

        if not self.documents:
            return []

        query_vec = embed_text(query)

        D, I = self.index.search(np.array([query_vec]).astype("float32"), k)

        results = []

        for idx in I[0]:

            if 0 <= idx < len(self.documents):

                results.append(self.documents[idx])

        return results
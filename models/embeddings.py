from sentence_transformers import SentenceTransformer
import warnings
from transformers import logging as transformers_logging

# Suppress the harmless "embeddings.position_ids | UNEXPECTED" warning
transformers_logging.set_verbosity_error()
warnings.filterwarnings("ignore")

def _load_model():
    """Load the embedding model with error handling."""
    try:
        return SentenceTransformer("all-MiniLM-L6-v2")
    except Exception as e:
        print(f"[EMBEDDINGS ERROR] Failed to load model: {e}")
        return None


model = _load_model()


def embed_text(text):
    """
    Generate a vector embedding for the given text.
    Uses all-MiniLM-L6-v2 (384-dimensional output).
    """
    try:
        if model is None:
            raise RuntimeError("Embedding model is not loaded.")

        embedding = model.encode(text)
        return embedding

    except Exception as e:
        print(f"[EMBED ERROR] {e}")
        raise
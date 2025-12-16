import logging
import numpy as np
import ollama
from typing import List, Tuple

logger = logging.getLogger(__name__)

class LocalEmbedder:
    """
    Handles local text embedding, chunking, and similarity filtering using Ollama.
    Designed to be reusable across the backend.
    """
    def __init__(self, model_name: str = 'nomic-embed-text'):
        self.model_name = model_name

    def get_embedding(self, text: str) -> List[float]:
        """Generates an embedding vector for the given text."""
        try:
            response = ollama.embeddings(model=self.model_name, prompt=text)
            return response.get('embedding', [])
        except Exception as e:
            logger.error(f"Embedding failed for model {self.model_name}: {e}")
            return []

    def cosine_similarity(self, v1: List[float], v2: List[float]) -> float:
        """Computes cosine similarity between two vectors."""
        if not v1 or not v2:
            return 0.0
        
        # Convert to numpy arrays for efficiency if they aren't already
        a = np.array(v1)
        b = np.array(v2)
        
        dot_product = np.dot(a, b)
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        
        return dot_product / (norm_a * norm_b) if norm_a > 0 and norm_b > 0 else 0.0

    def chunk_text(self, text: str, chunk_size: int = 500) -> List[str]:
        """Splits text into chunks of specified size."""
        if not text:
            return []
        return [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]

    def rag_filter(self, content_chunks: List[str], query: str, top_k: int = 5) -> str:
        """
        Filters the provided text chunks based on semantic similarity to the query.
        Returns a formatted string of the top K relevant chunks.
        """
        if not query or not content_chunks:
            # Fallback: just return the first few chunks if no query
            return "\n".join(content_chunks[:top_k])

        logger.info(f"--- Running Local RAG Filter for: '{query}' on {len(content_chunks)} chunks ---")
        query_emb = self.get_embedding(query)
        if not query_emb:
            logger.warning("Could not generate query embedding. Returning unfiltered chunks.")
            return "\n".join(content_chunks[:top_k])
        
        scored_chunks = []
        for chunk in content_chunks:
            chunk_emb = self.get_embedding(chunk)
            score = self.cosine_similarity(query_emb, chunk_emb)
            scored_chunks.append((score, chunk))
        
        # Sort by score descending
        scored_chunks.sort(key=lambda x: x[0], reverse=True)
        
        # Select Top K
        top_chunks = [c for s, c in scored_chunks[:top_k]]
        
        relevant_text = "\n\n[...]\n\n".join(top_chunks)
        return f"[RAG Filtered Results (Top {top_k} matches for '{query}')]:\n{relevant_text}"

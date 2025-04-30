"""
memory/embedding_store.py - Vector database interface for storing embeddings
"""

import logging
import os
import json
import time
import numpy as np
from typing import List, Dict, Any, Optional, Tuple

# Optional imports (will be imported only if needed)
try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False

try:
    import faiss
    FAISS_AVAILABLE = True
except ImportError:
    FAISS_AVAILABLE = False

logger = logging.getLogger(__name__)

class EmbeddingGenerator:
    """Generates embeddings from text"""
    
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        """
        Initialize the embedding generator
        
        Args:
            model_name (str, optional): Name of the embedding model
        """
        if not SENTENCE_TRANSFORMERS_AVAILABLE:
            logger.warning("sentence-transformers not available, embeddings will be mocked")
            self.model = None
        else:
            try:
                self.model = SentenceTransformer(model_name)
                logger.info(f"Loaded embedding model: {model_name}")
            except Exception as e:
                logger.error(f"Failed to load embedding model: {e}")
                self.model = None
    
    def generate(self, text: str) -> np.ndarray:
        """
        Generate embedding for text
        
        Args:
            text (str): Text to embed
        
        Returns:
            np.ndarray: Embedding vector
        """
        if self.model is None:
            # Mock embedding with consistent dimensionality
            return np.random.rand(384)
        
        return self.model.encode(text)


class MemoryEntry:
    """Entry in the memory store"""
    
    def __init__(
        self, 
        text: str, 
        embedding: Optional[np.ndarray] = None,
        metadata: Optional[Dict[str, Any]] = None,
        timestamp: Optional[float] = None
    ):
        """
        Initialize a memory entry
        
        Args:
            text (str): Text content of the memory
            embedding (np.ndarray, optional): Embedding vector
            metadata (Dict[str, Any], optional): Additional metadata
            timestamp (float, optional): Timestamp of the memory
        """
        self.text = text
        self.embedding = embedding
        self.metadata = metadata or {}
        self.timestamp = timestamp or time.time()
        self.id = f"mem_{int(self.timestamp * 1000)}"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation"""
        return {
            "id": self.id,
            "text": self.text,
            "metadata": self.metadata,
            "timestamp": self.timestamp
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any], embedding: Optional[np.ndarray] = None) -> 'MemoryEntry':
        """Create from dictionary representation"""
        entry = cls(
            text=data["text"],
            embedding=embedding,
            metadata=data["metadata"],
            timestamp=data["timestamp"]
        )
        entry.id = data["id"]
        return entry


class VectorStore:
    """Vector database for storing and retrieving embeddings"""
    
    def __init__(self, embedding_model: str = "all-MiniLM-L6-v2", data_dir: str = "./data"):
        """
        Initialize the vector store
        
        Args:
            embedding_model (str, optional): Name of the embedding model
            data_dir (str, optional): Directory to store data
        """
        self.embedding_generator = EmbeddingGenerator(embedding_model)
        self.data_dir = data_dir
        self.index_path = os.path.join(data_dir, "faiss_index.bin")
        self.entries_path = os.path.join(data_dir, "entries.json")
        
        # Create data directory if it doesn't exist
        os.makedirs(data_dir, exist_ok=True)
        
        # Initialize entries and index
        self.entries: Dict[str, MemoryEntry] = {}
        self.index = None
        
        # Load existing data if available
        self._load()
    
    def add(self, text: str, metadata: Optional[Dict[str, Any]] = None) -> str:
        """
        Add a text entry to the store
        
        Args:
            text (str): Text to add
            metadata (Dict[str, Any], optional): Additional metadata
        
        Returns:
            str: ID of the added entry
        """
        # Generate embedding
        embedding = self.embedding_generator.generate(text)
        
        # Create entry
        entry = MemoryEntry(text, embedding, metadata)
        self.entries[entry.id] = entry
        
        # Update index
        self._update_index()
        
        # Save
        self._save()
        
        return entry.id
    
    def search(
        self, 
        query: str, 
        k: int = 5, 
        filter_fn: Optional[callable] = None
    ) -> List[Tuple[MemoryEntry, float]]:
        """
        Search for similar entries
        
        Args:
            query (str): Query text
            k (int, optional): Number of results to return
            filter_fn (callable, optional): Function to filter results
        
        Returns:
            List[Tuple[MemoryEntry, float]]: List of (entry, similarity) tuples
        """
        # If no entries or no FAISS, return empty list
        if not self.entries or not FAISS_AVAILABLE or self.index is None:
            return []
        
        # Generate query embedding
        query_embedding = self.embedding_generator.generate(query)
        
        # Search
        D, I = self.index.search(np.array([query_embedding], dtype=np.float32), k)
        
        # Convert indices to entries
        entry_ids = list(self.entries.keys())
        results = []
        
        for i, (dist, idx) in enumerate(zip(D[0], I[0])):
            if idx < len(entry_ids) and idx >= 0:  # Valid index
                entry_id = entry_ids[idx]
                entry = self.entries[entry_id]
                
                # Apply filter if provided
                if filter_fn is None or filter_fn(entry):
                    # Convert distance to similarity (cosine similarity is in [-1, 1])
                    similarity = 1.0 - min(1.0, max(0.0, dist / 2.0))
                    results.append((entry, similarity))
        
        return results
    
    def get(self, entry_id: str) -> Optional[MemoryEntry]:
        """
        Get an entry by ID
        
        Args:
            entry_id (str): ID of the entry
        
        Returns:
            Optional[MemoryEntry]: Entry if found, None otherwise
        """
        return self.entries.get(entry_id)
    
    def delete(self, entry_id: str) -> bool:
        """
        Delete an entry
        
        Args:
            entry_id (str): ID of the entry
        
        Returns:
            bool: True if deleted, False if not found
        """
        if entry_id in self.entries:
            del self.entries[entry_id]
            self._update_index()
            self._save()
            return True
        
        return False
    
    def clear(self) -> None:
        """Clear all entries"""
        self.entries = {}
        self._update_index()
        self._save()
    
    def _update_index(self) -> None:
        """Update the FAISS index"""
        if not FAISS_AVAILABLE or not self.entries:
            return
        
        try:
            # Get all embeddings
            embeddings = []
            for entry in self.entries.values():
                if entry.embedding is not None:
                    embeddings.append(entry.embedding)
            
            if not embeddings:
                return
            
            # Convert to numpy array
            embeddings_array = np.array(embeddings, dtype=np.float32)
            
            # Create or update index
            dimension = embeddings_array.shape[1]
            new_index = faiss.IndexFlatL2(dimension)
            new_index.add(embeddings_array)
            
            self.index = new_index
            
        except Exception as e:
            logger.error(f"Failed to update index: {e}")
    
    def _save(self) -> None:
        """Save entries and index to disk"""
        try:
            # Save entries
            entries_data = {}
            for entry_id, entry in self.entries.items():
                entries_data[entry_id] = entry.to_dict()
            
            with open(self.entries_path, "w") as f:
                json.dump(entries_data, f)
            
            # Save index if available
            if FAISS_AVAILABLE and self.index is not None:
                faiss.write_index(self.index, self.index_path)
            
            logger.debug("Saved vector store")
        
        except Exception as e:
            logger.error(f"Failed to save vector store: {e}")
    
    def _load(self) -> None:
        """Load entries and index from disk"""
        try:
            # Load entries if file exists
            if os.path.exists(self.entries_path):
                with open(self.entries_path, "r") as f:
                    entries_data = json.load(f)
                
                for entry_id, entry_dict in entries_data.items():
                    # Re-generate embeddings (not stored in JSON)
                    embedding = self.embedding_generator.generate(entry_dict["text"])
                    entry = MemoryEntry.from_dict(entry_dict, embedding)
                    self.entries[entry_id] = entry
                
                logger.info(f"Loaded {len(self.entries)} entries from disk")
            
            # Load index if available
            if FAISS_AVAILABLE and os.path.exists(self.index_path):
                self.index = faiss.read_index(self.index_path)
                logger.info("Loaded FAISS index from disk")
            else:
                # Create new index
                self._update_index()
        
        except Exception as e:
            logger.error(f"Failed to load vector store: {e}")


"""
memory/context_manager.py - Manages conversation context
"""

import logging
import time
from typing import List, Dict, Any, Optional, Tuple

from .embedding_store import VectorStore, MemoryEntry

logger = logging.getLogger(__name__)

class ContextManager:
    """Manages conversation context using a vector store"""
    
    def __init__(
        self, 
        embedding_model: str = "all-MiniLM-L6-v2", 
        data_dir: str = "./data",
        max_history: int = 10,
        max_context_items: int = 5
    ):
        """
        Initialize the context manager
        
        Args:
            embedding_model (str, optional): Name of the embedding model
            data_dir (str, optional): Directory to store data
            max_history (int, optional): Maximum number of recent messages to keep
            max_context_items (int, optional): Maximum number of context items to include
        """
        self.vector_store = VectorStore(embedding_model, data_dir)
        self.max_history = max_history
        self.max_context_items = max_context_items
        self.conversation_history = []
    
    def add_user_message(self, message: str) -> None:
        """
        Add a user message to the conversation history
        
        Args:
            message (str): User message
        """
        self.conversation_history.append({
            "role": "user",
            "content": message,
            "timestamp": time.time()
        })
        
        # Trim history if needed
        if len(self.conversation_history) > self.max_history:
            self.conversation_history = self.conversation_history[-self.max_history:]
        
        # Add to vector store for long-term memory
        self.vector_store.add(
            message,
            metadata={
                "role": "user",
                "conversation_id": self._get_conversation_id()
            }
        )
    
    def add_assistant_message(self, message: str) -> None:
        """
        Add an assistant message to the conversation history
        
        Args:
            message (str): Assistant message
        """
        self.conversation_history.append({
            "role": "assistant",
            "content": message,
            "timestamp": time.time()
        })
        
        # Trim history if needed
        if len(self.conversation_history) > self.max_history:
            self.conversation_history = self.conversation_history[-self.max_history:]
        
        # Add to vector store for long-term memory
        self.vector_store.add(
            message,
            metadata={
                "role": "assistant",
                "conversation_id": self._get_conversation_id()
            }
        )
    
    def get_context(self, query: str) -> Dict[str, Any]:
        """
        Get context for a query
        
        Args:
            query (str): Query to get context for
        
        Returns:
            Dict[str, Any]: Context including history and relevant memories
        """
        # Get conversation history
        conversation = self.get_conversation_history()
        
        # Get relevant memories
        memories = self.get_relevant_memories(query)
        
        return {
            "conversation": conversation,
            "relevant_memories": memories
        }
    
    def get_conversation_history(self) -> List[Dict[str, str]]:
        """
        Get the recent conversation history
        
        Returns:
            List[Dict[str, str]]: List of recent messages
        """
        return [
            {"role": msg["role"], "content": msg["content"]}
            for msg in self.conversation_history
        ]
    
    def get_relevant_memories(self, query: str) -> List[str]:
        """
        Get memories relevant to a query
        
        Args:
            query (str): Query to find relevant memories for
        
        Returns:
            List[str]: List of relevant memory texts
        """
        # Search for relevant memories
        results = self.vector_store.search(query, k=self.max_context_items)
        
        # Extract text from results
        memories = []
        for entry, similarity in results:
            if similarity > 0.7:  # Only include reasonably similar memories
                memories.append(entry.text)
        
        return memories
    
    def add_memory(self, text: str, metadata: Optional[Dict[str, Any]] = None) -> str:
        """
        Add a memory to the vector store
        
        Args:
            text (str): Memory text
            metadata (Dict[str, Any], optional): Additional metadata
        
        Returns:
            str: ID of the added memory
        """
        return self.vector_store.add(text, metadata)
    
    def clear_conversation_history(self) -> None:
        """Clear the conversation history"""
        self.conversation_history = []
    
    def _get_conversation_id(self) -> str:
        """
        Get a unique ID for the current conversation
        
        Returns:
            str: Conversation ID
        """
        if not self.conversation_history:
            return f"conv_{int(time.time() * 1000)}"
        
        return f"conv_{int(self.conversation_history[0].get('timestamp', time.time()) * 1000)}"


"""
memory/retrieval.py - Retrieval mechanisms for conversation context
"""

import logging
from typing import List, Dict, Any, Optional

from .context_manager import ContextManager

logger = logging.getLogger(__name__)

class ContextRetriever:
    """Retrieves and formats context for the LLM"""
    
    def __init__(self, context_manager: ContextManager):
        """
        Initialize the context retriever
        
        Args:
            context_manager (ContextManager): Context manager
        """
        self.context_manager = context_manager
    
    def get_prompt_with_context(
        self, 
        system_prompt_template: str,
        query: str
    ) -> Dict[str, Any]:
        """
        Get a prompt with context for the LLM
        
        Args:
            system_prompt_template (str): System prompt template
            query (str): User query
        
        Returns:
            Dict[str, Any]: Prompt data including system prompt and conversation history
        """
        # Get context for the query
        context = self.context_manager.get_context(query)
        
        # Format memories if available
        memories_formatted = ""
        if context["relevant_memories"]:
            memories_formatted = "Previous relevant information:\n" + "\n".join(
                f"- {memory}" for memory in context["relevant_memories"]
            )
        
        # Build system prompt with context
        system_prompt = system_prompt_template.format(
            memories=memories_formatted
        )
        
        # Build message history
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(context["conversation"])
        
        return {
            "system_prompt": system_prompt,
            "messages": messages
        }
    
    def format_context_for_prompt(self, context: Dict[str, Any]) -> str:
        """
        Format context for inclusion in a prompt
        
        Args:
            context (Dict[str, Any]): Context data
        
        Returns:
            str: Formatted context
        """
        formatted = []
        
        # Format memories
        if context.get("relevant_memories"):
            formatted.append("Previous relevant information:")
            for memory in context["relevant_memories"]:
                formatted.append(f"- {memory}")
            formatted.append("")
        
        # Format recent conversation
        if context.get("conversation"):
            formatted.append("Recent conversation:")
            for msg in context["conversation"]:
                role = "You" if msg["role"] == "assistant" else "User"
                formatted.append(f"{role}: {msg['content']}")
        
        return "\n".join(formatted)
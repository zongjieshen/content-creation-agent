import logging
import os
import chromadb
from chromadb.config import Settings
import threading
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Literal
import numpy as np
from .resource_path import get_resource_path, get_app_data_dir, is_bundled

# Configure logging
logger = logging.getLogger(__name__)

# Global ChromaDB variables
_chroma_client = None
_chroma_initialized = False
_chroma_init_lock = threading.Lock()

# Collection name for unified embedding database
EMBEDDING_COLLECTION_NAME = "unified_embeddings"

# Embedding types
EMBEDDING_TYPES = ["caption", "transcript"]


# Caption subtypes
CAPTION_SUBTYPES = ["ad", "non-ad"]

# Default embedding type
DEFAULT_EMBEDDING_TYPE = "caption"

def get_chroma_path():
    """Get the ChromaDB storage path, initializing it if necessary.
    
    Returns:
        Path: The ChromaDB storage directory path
    """
    # Use the same logic as db_client.py for consistency
    if os.environ.get('DOCKER_ENV') == 'true':
        data_dir = Path('/app/data')
    elif is_bundled():
        data_dir = Path(get_app_data_dir())
    else:
        data_dir = Path(get_resource_path('data'))
    
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "chroma_db"

def initialize_embedding_client(force_reset=False):
    """Initialize ChromaDB client for unified embedding database.
    
    Args:
        force_reset (bool, optional): Whether to reset the embedding collections
        
    Returns:
        bool: True if initialization was successful, False otherwise
    """
    global _chroma_client, _chroma_initialized
    
    try:
        chroma_path = get_chroma_path()
        
        # Initialize ChromaDB client with persistent storage
        _chroma_client = chromadb.PersistentClient(
            path=str(chroma_path),
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=True
            )
        )
        
        if force_reset:
            logger.info("Force reset enabled. Resetting ChromaDB collections...")
            _chroma_client.reset()
        
        # Create or get the unified collection
        try:
            collection = _chroma_client.get_collection(name=EMBEDDING_COLLECTION_NAME)
            logger.info(f"Loaded existing ChromaDB collection: {EMBEDDING_COLLECTION_NAME}")
        except:
            collection = _chroma_client.create_collection(
                name=EMBEDDING_COLLECTION_NAME,
                metadata={"hnsw:space": "cosine"}
            )
            logger.info(f"Created new ChromaDB collection: {EMBEDDING_COLLECTION_NAME}")
        
        _chroma_initialized = True
        logger.info(f"Embedding client initialized at {chroma_path}")
        return True
        
    except Exception as e:
        logger.error(f"Error initializing embedding client: {str(e)}")
        return False

class EmbeddingConnection:
    """Context manager for ChromaDB embedding operations - similar to DatabaseConnection"""
    def __init__(self):
        self.client = None
        self.collection = None

    def __enter__(self):
        # Ensure ChromaDB is initialized
        ensure_embedding_initialized()
        self.client = _chroma_client
        self.collection = self.client.get_collection(name=EMBEDDING_COLLECTION_NAME)
        return self.client, self.collection

    def __exit__(self, exc_type, exc_val, exc_tb):
        # ChromaDB handles persistence automatically
        if exc_type is not None:
            logger.error(f"Embedding operation failed: {exc_val}")

def get_embedding_context():
    """Get an embedding context manager - similar to get_db_context()"""
    return EmbeddingConnection()

def ensure_embedding_initialized(force_reset=False):
    """Ensure ChromaDB client is initialized - similar to ensure_db_initialized()"""
    global _chroma_initialized
    
    # Use a lock to prevent concurrent initialization
    with _chroma_init_lock:
        if force_reset:
            logger.info("Force reset requested, initializing embedding client with reset...")
            _chroma_initialized = False
            initialize_embedding_client(force_reset=True)
            return
            
        # If already initialized and not forcing reset, skip
        if _chroma_initialized:
            return
            
        try:
            # Check if ChromaDB path exists
            chroma_path = get_chroma_path()
            if not chroma_path.exists():
                logger.info("ChromaDB path not found, initializing embedding client...")
                initialize_embedding_client()
                return
            
            # Try to initialize client
            initialize_embedding_client()
            
        except Exception as e:
            logger.info(f"Embedding client not accessible, initializing: {str(e)}")

def save_embeddings_batch(embeddings_data: List[Dict[str, Any]], embedding_type: str = DEFAULT_EMBEDDING_TYPE) -> bool:
    """Save multiple embeddings to the unified database.
    
    Args:
        embeddings_data: List of dicts with keys: id, embedding, metadata, document
        embedding_type: Type of embedding ("caption" or "transcript")
        
    Returns:
        bool: True if successful, False otherwise
    """
    if not embeddings_data:
        logger.warning("No embedding data provided for batch save")
        return False
    
    if embedding_type not in EMBEDDING_TYPES:
        logger.warning(f"Invalid embedding type: {embedding_type}. Must be one of {EMBEDDING_TYPES}")
        return False
    
    try:
        with get_embedding_context() as (client, collection):
            # Extract data for batch insert
            ids = [item["id"] for item in embeddings_data]
            embeddings = [item["embedding"] for item in embeddings_data]
            metadatas = [item["metadata"] for item in embeddings_data]
            documents = [item["document"] for item in embeddings_data]
            
            # Add embedding_type to all metadata entries
            for metadata in metadatas:
                metadata["embedding_type"] = embedding_type
            
            collection.add(
                ids=ids,
                embeddings=embeddings,
                metadatas=metadatas,
                documents=documents
            )
            
            logger.info(f"Saved {len(embeddings_data)} {embedding_type} embeddings to unified collection")
            return True
            
    except Exception as e:
        logger.error(f"Error saving embeddings batch: {str(e)}")
        return False

def search_similar_embeddings(
    query_embedding: np.ndarray,
    embedding_type: str,
    tag_filters: Optional[Dict[str, Any]] = None,
    n_results: int = 5
) -> List[Dict[str, Any]]:
    """Search for similar embeddings with type, label and tag filtering.
    
    Args:
        query_embedding: The embedding to search against
        embedding_type: Type of embedding to search ("caption" or "transcript")
        tag_filters: Optional additional metadata filters
        n_results: Number of results to return
        
    Returns:
        List[Dict[str, Any]]: Search results with metadata and documents
    """
    if embedding_type not in EMBEDDING_TYPES:
        logger.warning(f"Invalid embedding type: {embedding_type}. Must be one of {EMBEDDING_TYPES}")
        return []
    
    try:
        with get_embedding_context() as (client, collection):
            # Prepare query filter - ChromaDB requires proper logical operators for multiple filters
            filters_list = [{"embedding_type": embedding_type}]
            
            if tag_filters:
                # Add each tag filter as a separate condition
                for key, value in tag_filters.items():
                    filters_list.append({key: value})
            
            # Use $and operator for multiple filters, or single filter if only one
            if len(filters_list) == 1:
                where_filter = filters_list[0]
            else:
                where_filter = {"$and": filters_list}
            
            logger.debug(f"ChromaDB where filter: {where_filter}")
            
            # Query ChromaDB
            results = collection.query(
                query_embeddings=[query_embedding.tolist()],
                n_results=min(n_results, collection.count()),
                where=where_filter,
                include=["metadatas", "documents", "distances"]
            )
            
            # Format results
            formatted_results = []
            if results["documents"] and results["documents"][0]:
                for i in range(len(results["documents"][0])):
                    result = {
                        "document": results["documents"][0][i],
                        "metadata": results["metadatas"][0][i],
                        "distance": results["distances"][0][i] if results["distances"] else None
                    }
                    formatted_results.append(result)
            
            return formatted_results
            
    except Exception as e:
        logger.error(f"Error searching embeddings: {str(e)}")
        return []

def get_collection_stats() -> Dict[str, Any]:
    """Get statistics about the unified embedding collection."""
    try:
        with get_embedding_context() as (client, collection):
            stats = {
                "total_count": collection.count(),
                "collection_name": collection.name
            }
            
            # Get embedding type and label distribution
            try:
                all_data = collection.get(include=["metadatas"])
                
                # Track embedding type distribution
                type_counts = {}
                for metadata in all_data["metadatas"]:
                    embedding_type = metadata.get("embedding_type", "unknown")
                    type_counts[embedding_type] = type_counts.get(embedding_type, 0) + 1
                stats["embedding_type_distribution"] = type_counts
                
                # Track label distribution
                label_counts = {}
                caption_subtype_counts = {}
                
                for metadata in all_data["metadatas"]:
                    # Overall label counts
                    label = metadata.get("label", "unknown")
                    label_counts[label] = label_counts.get(label, 0) + 1
                    
                    # Caption subtype counts
                    if metadata.get("embedding_type") == "caption":
                        caption_type = metadata.get("label", "unknown")
                        caption_subtype_counts[caption_type] = caption_subtype_counts.get(caption_type, 0) + 1
                
                stats["label_distribution"] = label_counts
                stats["caption_subtype_distribution"] = caption_subtype_counts
                
            except Exception as e:
                logger.warning(f"Could not get distribution statistics: {str(e)}")
            
            return stats
            
    except Exception as e:
        logger.error(f"Error getting collection stats: {str(e)}")
        return {}

def delete_embeddings_by_filter(
    embedding_type: Optional[str] = None,
    label_filter: Optional[str] = None, 
    tag_filters: Optional[Dict[str, Any]] = None
) -> int:
    """Delete embeddings matching specific filters.
    
    Args:
        embedding_type: Optional embedding type to filter by
        label_filter: Optional label to filter by
        tag_filters: Optional additional metadata filters
        
    Returns:
        int: Number of embeddings deleted
    """
    try:
        with get_embedding_context() as (client, collection):
            # Prepare delete filter
            where_filter = {}
            
            if embedding_type:
                where_filter["embedding_type"] = embedding_type
            
            if label_filter:
                where_filter["label"] = label_filter
            
            if tag_filters:
                where_filter.update(tag_filters)
            
            # Get matching IDs
            results = collection.get(
                where=where_filter if where_filter else None,
                include=[]
            )
            
            ids_to_delete = results["ids"]
            
            if ids_to_delete:
                collection.delete(ids=ids_to_delete)
                logger.info(f"Deleted {len(ids_to_delete)} embeddings")
                return len(ids_to_delete)
            
            return 0
            
    except Exception as e:
        logger.error(f"Error deleting embeddings: {str(e)}")
        return 0

# Helper functions for transcript embeddings
def save_transcript_embeddings_batch(transcript_data_list: List[Dict[str, Any]]) -> bool:
    """Save transcript embeddings to the unified database.
    
    Args:
        transcript_data_list: List of transcript embedding data
        
    Returns:
        bool: True if successful, False otherwise
    """
    return save_embeddings_batch(transcript_data_list, embedding_type="transcript")

def search_similar_transcripts(
    query_embedding: np.ndarray,
    tag_filters: Optional[Dict[str, Any]] = None,
    n_results: int = 5
) -> List[Dict[str, Any]]:
    """Search for similar transcript embeddings.
    
    Args:
        query_embedding: The embedding to search against
        tag_filters: Optional metadata filters
        n_results: Number of results to return
        
    Returns:
        List[Dict[str, Any]]: Search results with metadata and documents
    """
    return search_similar_embeddings(
        query_embedding=query_embedding,
        embedding_type="transcript",
        tag_filters=tag_filters,
        n_results=n_results
    )

def load_all_text_hashes():
    try:
        with get_embedding_context() as (client, collection):
            results = collection.get(
                include=["metadatas"],
            )
            # Collect both caption_hash and transcript_hash values
            hashes = set()
            for meta in results["metadatas"]:
                if "caption_hash" in meta:
                    hashes.add(meta.get("caption_hash"))
                if "transcript_hash" in meta:
                    hashes.add(meta.get("transcript_hash"))
            return hashes
    except Exception as e:
        logger.error(f"Error loading text hashes: {str(e)}")
        return set()


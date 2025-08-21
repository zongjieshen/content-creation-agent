import json
import hashlib
import logging
import os
from typing import List, Dict, Any, Optional, Tuple
import numpy as np
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
from src.utils.gemini_client import get_client
from src.utils.embedding_client import (
    EMBEDDING_TYPES,
    ensure_embedding_initialized, 
    save_embeddings_batch, search_similar_embeddings, 
    get_collection_stats as get_embedding_stats,
    load_all_text_hashes
)
from src.utils.config_loader import get_config

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

config = get_config()
CLUSTERING_CONFIG = config.get('caption_clustering', {})
LABELS = ["ad", "non-ad"]

def get_caption_hash(caption: str) -> str:
    """Generate a hash for a caption."""
    return hashlib.md5(caption.encode('utf-8')).hexdigest()

# Global embeddings cache (kept for performance) with thread lock
embeddings_cache = {}
cache_lock = threading.Lock()

def get_embedding(text: str) -> np.ndarray:
    """Get embedding for text, using cache if available."""
    # Initialize client
    client = get_client()
    if not client:
        raise ValueError("Failed to initialize Gemini client")
    
    text_hash = get_caption_hash(text)
    
    # Thread-safe cache access
    with cache_lock:
        if text_hash in embeddings_cache:
            return np.array(embeddings_cache[text_hash], dtype=np.float32)
    
    # Generate new embedding
    embedding_model = CLUSTERING_CONFIG.get('embedding_model', 'text-embedding-004')
    result = client.models.embed_content(
        model=embedding_model,
        contents=text
    )
    embedding = np.array(result.embeddings[0].values, dtype=np.float32)
    
    # Thread-safe cache update
    with cache_lock:
        embeddings_cache[text_hash] = embedding.tolist()
    
    return embedding

def save_caption_embeddings_batch(caption_data_list: List[Tuple[str, str, np.ndarray]], 
                                tags_list: Optional[List[Dict[str, Any]]] = None) -> bool:
    """Save multiple captions with their embeddings to the unified database.
    
    Args:
        caption_data_list: List of tuples containing (caption_text, label, embedding)
        tags_list: Optional list of metadata dictionaries for each caption
    
    Returns:
        bool: True if successful, False otherwise
    """
    if not caption_data_list:
        logger.warning("No caption data provided for batch save")
        return False
    
    try:
        ensure_embedding_initialized()
        
        # Prepare data for unified collection
        embeddings_data = []
        skipped_count = 0
        existing_hashes = load_all_text_hashes()
        
        for i, (caption_text, embedding) in enumerate(caption_data_list):
                
            caption_hash = get_caption_hash(caption_text)
            if caption_hash in existing_hashes:
                logger.info(f"Skipping duplicate caption with hash {caption_hash}")
                skipped_count += 1
                continue
            
            # Prepare metadata with label and tags
            metadata = {
                "caption_hash": caption_hash
            }
            
            # Add custom tags if provided
            if tags_list and i < len(tags_list):
                metadata.update(tags_list[i])
            
            # Get post_url from tags if available, otherwise use caption_hash as fallback
            post_id = tags_list[i].get("post_url", caption_hash) if tags_list and i < len(tags_list) else caption_hash
            
            embeddings_data.append({
                "id": post_id,  # Use post_url as ID instead of caption_hash
                "embedding": embedding.tolist(),
                "metadata": metadata,
                "document": caption_text
            })
        
        # Save to unified collection if we have any non-duplicate entries
        if embeddings_data:
            success = save_embeddings_batch(embeddings_data)
            
            if success:
                logger.info(f"Saved {len(embeddings_data)} caption embeddings to unified collection (skipped {skipped_count} duplicates)")
            
            return success
        else:
            logger.info(f"No new captions to save (skipped {skipped_count} duplicates)")
            return True
        
    except Exception as e:
        logger.error(f"Error saving caption embeddings batch: {str(e)}")
        return False

def generate_similar_embeddings_wrapper(content_to_style: str, 
                            embedding_type: str,
                            num_examples: int = 3, 
                            filter_tags: Optional[Dict[str, Any]] = None) -> List[str]:
    """Generate captions similar to the given content using unified database.
    
    Args:
        content_to_style: The content to find similar captions for
        num_examples: Number of similar captions to return
        filter_tags: Optional metadata filters for more targeted search
    
    Returns:
        List[str]: List of similar caption texts
    """
    
    try:
        # Get embedding for the content
        content_embedding = get_embedding(content_to_style)
        if (embedding_type == "transcript"):
            if "label" in filter_tags:
                del filter_tags["label"]

        # Search with tag filtering
        results = search_similar_embeddings(
            query_embedding=content_embedding,
            embedding_type=embedding_type,
            tag_filters=filter_tags,
            n_results=num_examples
        )
        
        # Extract caption texts from results
        similar_captions = [result["document"] for result in results]
        
        logger.info(f"Found {len(similar_captions)} similar captions")
        return similar_captions
        
    except Exception as e:
        logger.error(f"Error generating similar captions: {str(e)}")
        return []

def generate_content_in_style(label: str, content_to_style: str, embedding_type: str,  examples: List[str] = None) -> str:
    """Generate new content based on the specified label style (ad or non-ad)."""
    logger.info(f"Generating {embedding_type} content")
    
    # Initialize client
    client = get_client()
    if not client:
        raise ValueError("Failed to initialize Gemini client")
    
    # Validate label
    if label not in LABELS:
        raise ValueError(f"Invalid label: {label}. Must be one of {LABELS}")
    
    try:
        # Get the appropriate clustering config based on embedding type
        if embedding_type == "transcript":
            clustering_config = config.get('transcript_clustering', {})
            # For transcripts, use the single template (no ad/non-ad distinction)
            prompt_template = clustering_config.get('template', "")
        else:
            # For captions, use the existing logic with ad/non-ad templates
            clustering_config = config.get('caption_clustering', {})
            prompt_key = f"{label.replace('-', '_')}_prompt_template"
            prompt_template = clustering_config.get(prompt_key, "")
        
        if not prompt_template:
            raise ValueError(f"No prompt template found for {embedding_type}")
                    
        # Format examples if available
        examples_text = ""
        if examples:
            examples_text = "\n\n"
            for i, example in enumerate(examples):
                examples_text += f"Example {i+1}: {example}\n"
        
        # Create the prompt for content generation
        generation_prompt = prompt_template.format(
            label=label,
            examples_text=examples_text,
            content=content_to_style
        )
        
        # Generate content
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=generation_prompt,
        )
        
        return response.text
        
    except Exception as e:
        logger.error(f"Error generating content: {str(e)}", exc_info=True)
        return f"Error generating content: {str(e)}"

def apply_style_to_content(content: str, embedding_type: EMBEDDING_TYPES, num_examples: int = 3, 
                         filter_tags: Optional[Dict[str, Any]] = None) -> str:
    """Apply the specified style to content using similar examples from unified database."""
    
    # Initialize filter_tags if None
    if filter_tags is None:
        filter_tags = {}
    
    custom_filters = load_custom_filters(embedding_type)
    if custom_filters:
        filter_tags.update(custom_filters)
    
    target_label = filter_tags.get("label", "non-ad")
    # Get similar examples
    examples = None
    try:
        examples = generate_similar_embeddings_wrapper(content, embedding_type, num_examples, filter_tags)

        logger.info(f"Found {len(examples)} similar examples for styling")
    except Exception as e:
        logger.warning(f"Could not find similar examples: {str(e)}. Proceeding without examples.")
    
    # Generate styled content
    styled_content = generate_content_in_style(target_label, content, embedding_type, examples)
    
    return styled_content

def get_collection_stats() -> Dict[str, Any]:
    """Get statistics about the unified embedding collection."""
    try:
        return get_embedding_stats()
    except Exception as e:
        logger.error(f"Error getting collection stats: {str(e)}")
        return {}

def initialize_caption_utils():
    """Initialize caption utils by ensuring embedding client is ready."""
    logger.info("Initializing caption utils with unified embedding database...")
    
    ensure_embedding_initialized()
    stats = get_collection_stats()
    logger.info(f"Caption utils initialized with unified collection: {stats}")
    return stats

def process_captions(posts_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Complete pipeline: generate embeddings and store in unified database.
    
    Args:
        - posts_dict: Dictionary with post_url as keys and post data as values
    
    Returns:
        Dict[str, Any]: Summary of processing results
    """
    
    logger.info(f"Processing {len(posts_dict)} posts with unified database")
    
    # Collect caption data for batch processing
    caption_data_list = []
    transcript_data_list = []
    tags_list = []
    
    # Prepare data for multithreaded processing
    caption_tasks = []
    transcript_tasks = []
    
    for post_url, post_data in posts_dict.items():
        caption = post_data.get('caption', '')
        transcript = post_data.get('transcript', '')
        tags = post_data.get('tags', {})
        
        tags_list.append(tags)
        
        if caption:
            caption_tasks.append((caption, len(caption_tasks)))
        
        if transcript:
            transcript_tasks.append((transcript, len(transcript_tasks)))
    
    # Process embeddings with multithreading
    max_workers = min(32, (len(caption_tasks) + len(transcript_tasks)) or 1)
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit caption embedding tasks
        caption_futures = {}
        for caption, index in caption_tasks:
            future = executor.submit(get_embedding, caption)
            caption_futures[future] = (caption, index)
        
        # Submit transcript embedding tasks
        transcript_futures = {}
        for transcript, index in transcript_tasks:
            future = executor.submit(get_embedding, transcript)
            transcript_futures[future] = (transcript, index)
        
        # Collect caption results
        caption_results = [None] * len(caption_tasks)
        for future in as_completed(caption_futures):
            try:
                embedding = future.result()
                caption, index = caption_futures[future]
                caption_results[index] = (caption, embedding)
            except Exception as e:
                caption, index = caption_futures[future]
                logger.error(f"Error processing caption embedding: {e}")
                # Skip failed embeddings
        
        # Collect transcript results
        transcript_results = [None] * len(transcript_tasks)
        for future in as_completed(transcript_futures):
            try:
                embedding = future.result()
                transcript, index = transcript_futures[future]
                transcript_results[index] = (transcript, embedding)
            except Exception as e:
                transcript, index = transcript_futures[future]
                logger.error(f"Error processing transcript embedding: {e}")
                # Skip failed embeddings
    
    # Filter out None results (failed embeddings)
    caption_data_list = [result for result in caption_results if result is not None]
    transcript_data_list = [result for result in transcript_results if result is not None]
    
    # Save all caption embeddings to unified collection in a single batch operation
    caption_success = save_caption_embeddings_batch(caption_data_list, tags_list)
    transcript_success = save_transcript_embeddings_batch(transcript_data_list, tags_list)
    
    # Get collection stats
    stats = get_collection_stats()
    
    # Return summary
    result = {
        'total_posts': len(posts_dict),
        'total_captions': len(caption_data_list),
        'total_transcripts': len(transcript_data_list),
        'collection_stats': stats,
        'caption_success': caption_success,
        'transcript_success': transcript_success,
        'success': caption_success and transcript_success
    }
    
    logger.info(f"Processing complete: {result}")
    return result

def save_transcript_embeddings_batch(transcript_data_list: List[Tuple[str, str, np.ndarray]], 
                                   tags_list: Optional[List[Dict[str, Any]]] = None) -> bool:
    """Save multiple transcripts with their embeddings to the unified database.
    
    Args:
        transcript_data_list: List of tuples containing (transcript_text, label, embedding)
        tags_list: Optional list of metadata dictionaries for each transcript
    
    Returns:
        bool: True if successful, False otherwise
    """
    if not transcript_data_list:
        logger.warning("No transcript data provided for batch save")
        return False
    
    try:
        ensure_embedding_initialized()
        
        # Prepare data for unified collection
        embeddings_data = []
        skipped_count = 0
        existing_hashes = load_all_text_hashes()
        
        for i, (transcript_text, embedding) in enumerate(transcript_data_list):
                
            transcript_hash = get_caption_hash(transcript_text)
            if transcript_hash in existing_hashes:
                logger.info(f"Skipping duplicate transcript with hash {transcript_hash}")
                skipped_count += 1
                continue
            
            # Prepare metadata with label and tags
            metadata = {
                "transcript_hash": transcript_hash
            }
            
            # Add custom tags if provided
            if tags_list and i < len(tags_list):
                metadata.update(tags_list[i])
            
            # Get post_url from tags if available, otherwise use transcript_hash as fallback
            post_id = tags_list[i].get("post_url", transcript_hash) if tags_list and i < len(tags_list) else transcript_hash
            
            embeddings_data.append({
                "id": f"transcript_{post_id}",  # Prefix with transcript_ to distinguish from captions
                "embedding": embedding.tolist(),
                "metadata": metadata,
                "document": transcript_text
            })
        
        # Save to unified collection if we have any non-duplicate entries
        if embeddings_data:
            # Use embedding_type="transcript" for transcript embeddings
            success = save_embeddings_batch(embeddings_data, embedding_type="transcript")
            
            if success:
                logger.info(f"Saved {len(embeddings_data)} transcript embeddings to unified collection (skipped {skipped_count} duplicates)")
            
            return success
        else:
            logger.info(f"No new transcripts to save (skipped {skipped_count} duplicates)")
            return True
        
    except Exception as e:
        logger.error(f"Error saving transcript embeddings batch: {str(e)}")
        return False

def load_custom_filters(embedding_type: EMBEDDING_TYPES) -> Dict[str, Any]:
    """
    Load custom filters from config.yaml and convert them to ChromaDB format.
    
    Returns:
        Dict[str, Any]: Formatted filters ready for ChromaDB operations
    """
    logger.info("Loading custom filters from config")
    
    try:
        # Get configuration
        config = get_config()
        
        # Extract custom filters from caption_clustering section
        custom_filters_config = config.get(f"{embedding_type}_clustering", {}).get('custom_filters', {})
        
        # Initialize ChromaDB-compatible filter dict
        chroma_filters = {}
        
        # Process username filters if available
        if 'username' in custom_filters_config and custom_filters_config['username']:
            usernames = custom_filters_config['username']
            if len(usernames) == 1:
                # Single value filter
                chroma_filters['username'] = usernames[0]
            elif len(usernames) > 1:
                # Multiple values filter (OR condition in ChromaDB)
                chroma_filters['username'] = {"$in": usernames}
        return chroma_filters

    except Exception as e:
        logger.error(f"Error loading custom filters: {str(e)}")
        return {}
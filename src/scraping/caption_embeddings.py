import json
import hashlib
import logging
from typing import List, Dict, Any, Optional, Tuple
import numpy as np
import faiss
from src.utils.gemini_client import get_client
from src.utils.db_client import get_db_context, ensure_db_initialized
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

# Global variables for FAISS indices
faiss_indices = {}
embeddings_cache = {}

def save_caption_embeddings_batch(caption_data_list: List[Tuple[str, str, np.ndarray]]):
    """Save multiple captions with their embeddings to the database in a single transaction.
    
    Args:
        caption_data_list: List of tuples containing (caption_text, label, embedding)
    
    Returns:
        bool: True if successful, False otherwise
    """
    if not caption_data_list:
        logger.warning("No caption data provided for batch save")
        return False
        
    try:
        # Prepare data for batch insert
        batch_data = []
        for caption_text, label, embedding in caption_data_list:
            caption_hash = get_caption_hash(caption_text)
            embedding_json = json.dumps(embedding.tolist())
            batch_data.append((caption_hash, caption_text, label, embedding_json))
        
        # Execute batch insert
        with get_db_context() as (conn, cursor):
            cursor.executemany(
                "INSERT OR REPLACE INTO caption_embeddings (caption_hash, caption_text, label, embedding_json) VALUES (?, ?, ?, ?)",
                batch_data
            )
        
        logger.info(f"Saved {len(batch_data)} caption embeddings to database in batch")
        return True
        
    except Exception as e:
        logger.error(f"Error saving caption embeddings batch to database: {str(e)}")
        return False

def get_embedding(text: str) -> np.ndarray:
    """Get embedding for text, using cache if available."""
    # Initialize client
    client = get_client()
    if not client:
        raise ValueError("Failed to initialize Gemini client")
    
    text_hash = get_caption_hash(text)
    
    if text_hash in embeddings_cache:
        return np.array(embeddings_cache[text_hash], dtype=np.float32)
    
    # Generate new embedding
    embedding_model = CLUSTERING_CONFIG.get('embedding_model', 'text-embedding-004')
    result = client.models.embed_content(
        model=embedding_model,
        contents=text
    )
    embedding = np.array(result.embeddings[0].values, dtype=np.float32)
    
    # Cache the embedding (but don't save to DB yet as we don't have a label)
    embeddings_cache[text_hash] = embedding.tolist()
    
    return embedding

def build_in_memory_faiss_indices(caption_data_list=None):
    """
    Build in-memory FAISS indices for each label.
    
    Args:
        caption_data_list: Optional list of tuples containing (caption_text, label, embedding)
                          If provided, builds indices from this data instead of loading from database
    """
    logger.info("Building in-memory FAISS indices" + 
               (" from provided data" if caption_data_list else " from database"))
    
    global faiss_indices, embeddings_cache
    
    # Initialize empty dictionaries
    faiss_indices = {}
    embeddings_cache = {}
    label_captions = {label: [] for label in LABELS}  # Now a local variable
    
    try:
        # Group embeddings by label
        label_embeddings = {label: [] for label in LABELS}
        
        if caption_data_list:
            # Use provided caption data
            for caption_text, label, embedding in caption_data_list:
                if label in LABELS:
                    # Add caption to the appropriate label group
                    label_captions[label].append(caption_text)
                    
                    # Add embedding to the appropriate label group
                    label_embeddings[label].append(embedding)
                    #embeddings_cache[get_caption_hash(caption_text)] = embedding
        else:
            # Load all caption data from database
            with get_db_context() as (conn, cursor):
                cursor.execute("SELECT caption_hash, caption_text, label, embedding_json FROM caption_embeddings")
                rows = cursor.fetchall()
                
                for row in rows:
                    caption_hash, caption_text, label, embedding_json = row
                    
                    if label in LABELS:
                        # Add caption to the appropriate label group
                        label_captions[label].append(caption_text)
                        
                        # Add embedding to the appropriate label group
                        embedding = np.array(json.loads(embedding_json), dtype=np.float32)
                        label_embeddings[label].append(embedding)
                        embeddings_cache[caption_hash] = embedding
        
        # Build FAISS index for each label
        for label in LABELS:
            if len(label_embeddings[label]) > 0:
                embeddings = np.array(label_embeddings[label])
                
                # Create FAISS index
                dimension = embeddings.shape[1]
                index = faiss.IndexFlatL2(dimension)
                index.add(embeddings)
                
                # Store in memory
                faiss_indices[label] = {
                    'index': index,
                    'captions': label_captions[label]
                }
                
                logger.info(f"Built in-memory FAISS index for '{label}' with {len(label_captions[label])} captions")
    
    except Exception as e:
        logger.error(f"Error building in-memory FAISS indices: {str(e)}")
    
    return faiss_indices


def generate_similar_captions(content_to_style: str, target_label: str, num_examples: int = 3) -> List[str]:
    """Generate captions similar to the given content for a specific label."""
    logger.info(f"Generating {num_examples} similar captions for label '{target_label}'")
    
    # Load FAISS indices from memory or build them if not available
    global faiss_indices
    if not faiss_indices:
        faiss_indices = build_in_memory_faiss_indices()
    
    if target_label not in faiss_indices:
        raise ValueError(f"No FAISS index found for label '{target_label}'. Available labels: {list(faiss_indices.keys())}")
    
    # Get embedding for the content
    content_embedding = get_embedding(content_to_style)
    content_embedding = content_embedding.reshape(1, -1)
    
    # Search in the target label's FAISS index
    index_data = faiss_indices[target_label]
    index = index_data['index']
    captions = index_data['captions']
    
    # Perform similarity search
    k = min(num_examples, index.ntotal)  # Use index.ntotal instead of len(captions)
    if k == 0:
        return []
        
    distances, indices = index.search(content_embedding, k)
    
    # Return the most similar captions
    similar_captions = [captions[idx] for idx in indices[0]]
    
    logger.info(f"Found {len(similar_captions)} similar captions for '{target_label}'")
    return similar_captions

def generate_content_in_style(label: str, content_to_style: str, examples: List[str] = None) -> str:
    """Generate new content based on the specified label style (ad or non-ad)."""
    logger.info(f"Generating content in {label} style")
    
    # Initialize client
    client = get_client()
    if not client:
        raise ValueError("Failed to initialize Gemini client")
    
    # Validate label
    if label not in LABELS:
        raise ValueError(f"Invalid label: {label}. Must be one of {LABELS}")
    
    try:
        # Get prompt template from config
        prompt_key = f"{label.replace('-', '_')}_prompt_template"
        prompt_template = CLUSTERING_CONFIG.get(prompt_key, "")
                    
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

def apply_style_to_content(content: str, target_label: str, num_examples: int = 3) -> str:
    """Apply the specified style to content using similar examples from FAISS vector search."""
    logger.info(f"Applying {target_label} style to content")
    
    # Ensure database is initialized
    ensure_db_initialized()
    
    # Validate label
    if target_label not in LABELS:
        raise ValueError(f"Invalid label: {target_label}. Must be one of {LABELS}")
    
    # Load FAISS indices
    faiss_indices = load_faiss_indices()
    
    if not faiss_indices:
        raise ValueError("No FAISS indices available. Please process captions first.")
    
    if target_label not in faiss_indices:
        raise ValueError(f"No FAISS index found for label '{target_label}'. Available labels: {list(faiss_indices.keys())}")
    
    # Get similar examples
    examples = None
    try:
        examples = generate_similar_captions(content, target_label, num_examples)
        logger.info(f"Found {len(examples)} similar examples for styling")
    except Exception as e:
        logger.warning(f"Could not find similar examples: {str(e)}. Proceeding without examples.")
    
    # Generate styled content
    styled_content = generate_content_in_style(target_label, content, examples)
    
    return styled_content

# Add this new function
def load_faiss_indices():
    """Load FAISS indices from database."""
    global faiss_indices
    
    # If indices are already loaded, return them
    if faiss_indices:
        return faiss_indices
    
    # Otherwise, build them from database
    return build_in_memory_faiss_indices()

# Add this new function to initialize everything
def initialize_caption_utils():
    """Initialize caption utils by loading embeddings cache and building FAISS indices."""
    logger.info("Initializing caption utils...")
    
    # Ensure database is initialized
    ensure_db_initialized()
    
    # Load FAISS indices
    global faiss_indices
    faiss_indices = load_faiss_indices()
    
    logger.info(f"Caption utils initialized with {len(faiss_indices)} FAISS indices")
    return faiss_indices


def process_captions(caption_tuples: List[Tuple[str, bool]]) -> Dict[str, Any]:
    """Complete pipeline: cluster, label, and build indices."""
    logger.info(f"Processing {len(caption_tuples)} captions")

    # Collect caption data for batch processing
    caption_data_list = []
    
    # Initialize label_captions dictionary
    label_captions = {label: [] for label in LABELS}
    
    # Populate label_captions based on is_ad flag
    for caption, is_ad in caption_tuples:
        label = "ad" if is_ad else "non-ad"
        
        # Get embedding
        embedding = get_embedding(caption)
        
        # Add to batch data
        caption_data_list.append((caption, label, embedding))
        
        # Add to label_captions for in-memory index
        if label in label_captions:
            label_captions[label].append(caption)
        else:
            label_captions[label] = [caption]
    
    # Save all embeddings in a single batch operation
    save_caption_embeddings_batch(caption_data_list)
    faiss_indices = build_in_memory_faiss_indices(caption_data_list)
    
    # Return summary
    result = {
        'total_captions': len(caption_tuples),
        'labels_distribution': {label: len(label_captions[label]) for label in LABELS if label in label_captions},
        'faiss_indices_built': list(faiss_indices.keys())
    }
    
    logger.info(f"Processing complete: {result}")
    return result
// Video Analysis Functionality
document.addEventListener('DOMContentLoaded', () => {
    // Video upload area
    const videoUploadArea = document.getElementById('video-upload-area');
    const videoFileInput = document.getElementById('video-file');
    const videoUploadBtn = document.getElementById('video-upload-btn');
    const videoStatus = document.getElementById('video-status');
    const analyzeBtn = document.getElementById('generate-captions-btn');
    const copyResultsBtn = document.getElementById('copy-results-btn');
    
    // Add toggle switch functionality for target style
    const targetLabelToggle = document.getElementById('target_label');
    if (targetLabelToggle) {
        const toggleLabel = targetLabelToggle.parentElement.nextElementSibling;
        // Set initial label
        toggleLabel.textContent = targetLabelToggle.checked ? 'Non-Ad' : 'Ad';
        
        targetLabelToggle.addEventListener('change', function() {
            toggleLabel.textContent = this.checked ? 'Non-Ad' : 'Ad';
        });
        
        // Create and append location input
        const locationContainer = document.createElement('div');
        locationContainer.className = 'location-input-container';
        
        const locationInput = document.createElement('input');
        locationInput.type = 'text';
        locationInput.id = 'location-input';
        locationInput.className = 'location-input';
        locationInput.placeholder = 'Enter location (optional)';
        
        locationContainer.appendChild(locationInput);
        targetLabelToggle.parentElement.parentElement.appendChild(locationContainer);
    }
    
    if (videoFileInput) {
        videoFileInput.addEventListener('change', handleVideoUpload);
    }
    
    if (videoUploadBtn) {
        videoUploadBtn.addEventListener('click', () => {
            videoFileInput.click();
        });
    }
    
    if (analyzeBtn) {
        analyzeBtn.addEventListener('click', analyzeVideo);
    }
    
    if (copyResultsBtn) {
        copyResultsBtn.addEventListener('click', copyResults);
    }
});

// Video Upload Functionality
async function handleVideoUpload(e) {
    e.preventDefault();
    e.stopPropagation();
    
    console.log('Video upload handler triggered');
    
    const file = e.target.files[0];
    if (!file) {
        console.log('No file selected');
        return;
    }
    
    // Check if file is a video
    const allowedTypes = ['video/mp4', 'video/quicktime', 'video/avi', 'video/x-matroska', 'video/webm'];
    if (!allowedTypes.includes(file.type)) {
        alert('Please select a video file (mp4, mov, avi, mkv, webm).');
        e.target.value = ''; // Clear the input
        return;
    }
    
    // Ensure we're on the video analysis tab
    switchTab('video');
    
    // Remove existing video container if it exists
    const existingContainer = document.getElementById('video-container');
    if (existingContainer) {
        existingContainer.remove();
    }

    // Create new video container
    const videoContainer = document.createElement('div');
    videoContainer.id = 'video-container';
    videoContainer.className = 'video-thumbnail-container';
    // Append to the video-upload-section instead of video-upload-area
    const uploadSection = document.querySelector('.video-upload-section');
    uploadSection.appendChild(videoContainer);
    
    // Create play button
    const playButton = document.createElement('div');
    playButton.className = 'play-button';
    videoContainer.appendChild(playButton);
    
    // Create video preview
    const videoPreview = document.createElement('video');
    videoPreview.id = 'video-preview';
    videoPreview.controls = false;
    videoPreview.style.width = '100%';
    videoPreview.preload = 'metadata';
    videoPreview.crossOrigin = 'anonymous'; // Allow cross-origin video loading
    videoPreview.playsInline = true; // Better mobile support
    
    // Add loading indicator
    const loadingIndicator = document.createElement('div');
    loadingIndicator.className = 'video-loading';
    loadingIndicator.textContent = 'Loading video...';
    videoContainer.appendChild(loadingIndicator);
    
    // Handle video loading states
    videoPreview.addEventListener('loadstart', () => {
        loadingIndicator.style.display = 'block';
    });
    
    videoPreview.addEventListener('canplay', () => {
        loadingIndicator.style.display = 'none';
    });
    
    videoPreview.addEventListener('error', (e) => {
        console.error('Video loading error:', videoPreview.error);
        loadingIndicator.textContent = 'Error loading video';
        loadingIndicator.classList.add('error');
    });
    
    videoContainer.appendChild(videoPreview);
    
    // Function to handle play state
    const handlePlay = () => {
        videoPreview.controls = true;
        videoPreview.play()
            .then(() => {
                videoPreview.classList.add('playing');
                playButton.style.display = 'none';
            })
            .catch(error => {
                console.error('Error playing video:', error);
            });
    };
    
    // Add click events
    playButton.addEventListener('click', (e) => {
        e.stopPropagation();
        handlePlay();
    });
    
    videoContainer.addEventListener('click', () => {
        if (videoPreview.paused) {
            handlePlay();
        } else {
            videoPreview.pause();
        }
    });
    
    // Add video event listeners
    videoPreview.addEventListener('pause', () => {
        playButton.style.display = 'flex';
        videoPreview.classList.remove('playing');
    });
    
    videoPreview.addEventListener('play', () => {
        playButton.style.display = 'none';
        videoPreview.classList.add('playing');
    });
    
    videoPreview.addEventListener('ended', () => {
        playButton.style.display = 'flex';
        videoPreview.classList.remove('playing');
        videoPreview.controls = false;
    });
    
    // Set video source and show preview
    videoPreview.src = URL.createObjectURL(file);
    videoPreview.style.display = 'block';

    
    // Enable analyze button
    const analyzeBtn = document.getElementById('generate-captions-btn');
    if (analyzeBtn) {
        analyzeBtn.disabled = false;
    }
    
    // Upload the video file
    await uploadVideo(file);
}

async function uploadVideo(file) {
    showLoading(true);
    currentOperation = 'video_upload';
    isCancelled = false;
    
    // Revoke the previous video preview URL to free up memory
    const videoPreview = document.getElementById('video-preview');
    if (videoPreview && videoPreview.src) {
        URL.revokeObjectURL(videoPreview.src);
    }
    
    try {
        const formData = new FormData();
        formData.append('file', file);
        
        const response = await fetch(`${CAPTIONS_API_URL}/upload_video`, {
            method: 'POST',
            body: formData
        });
        
        // Check if operation was cancelled
        if (isCancelled) {
            console.log('Video upload was cancelled, ignoring response');
            return;
        }
        
        if (response.ok) {
            const data = await response.json();
            console.log('Upload response:', data);
            
            // Create or update status message in video container
            let videoStatus = document.querySelector('.video-thumbnail-container .video-status');
            if (!videoStatus) {
                videoStatus = document.createElement('div');
                videoStatus.className = 'video-status';
                document.querySelector('.video-thumbnail-container').appendChild(videoStatus);
            }
            videoStatus.textContent = `Ready to analyze: ${file.name}`;
            videoStatus.classList.add('success');

            // Ensure video preview is visible and properly styled
            const videoPreview = document.getElementById('video-preview');
            if (videoPreview) {
                // Update video source to use the video endpoint
                const videoUrl = `${CAPTIONS_API_URL}/video/${encodeURIComponent(file.name)}`;
                console.log('Loading video from:', videoUrl);
                
                // Load the video
                videoPreview.src = videoUrl;
                videoPreview.load(); // Force reload with new source
                
                // Handle video loading
                videoPreview.addEventListener('loadeddata', () => {
                    videoPreview.style.display = 'block';
                    videoPreview.classList.add('ready');
                    document.getElementById('video-upload-area').style.padding = '12px';
                    
                    // Reset video to thumbnail state
                    videoPreview.controls = false;
                    videoPreview.currentTime = 0;
                    videoPreview.classList.remove('playing');
                });
                
                // Handle video loading error
                videoPreview.addEventListener('error', () => {
                    console.error('Error loading video:', videoPreview.error);
                    alert('Error loading video. Please try again.');
                });
                
                // Show play button
                const playButton = document.querySelector('.play-button');
                if (playButton) {
                    playButton.style.display = 'flex';
                }
                
                // Generate thumbnail
                videoPreview.addEventListener('loadeddata', () => {
                    videoPreview.currentTime = 1; // Set to 1 second to get a good thumbnail
                });
            }
            
        } else {
            throw new Error('Failed to upload video');
        }
    } catch (error) {
        console.error('Error uploading video:', error);
        
        // Update status
        const videoStatus = document.getElementById('video-status');
        if (videoStatus) {
            videoStatus.textContent = `Error: ${error.message}`;
            videoStatus.classList.add('error');
        }
    } finally {
        showLoading(false);
        currentOperation = null;
    }
}

async function analyzeVideo() {
    // Get the current state of the toggle
    const targetLabelToggle = document.getElementById('target_label');
    const targetLabel = targetLabelToggle && targetLabelToggle.checked ? 'non-ad' : 'ad';
    
    // Get location value if provided
    const locationInput = document.getElementById('location-input');
    const location = locationInput ? locationInput.value.trim() : '';
    
    // Set current operation
    currentOperation = 'video_analysis';
    isCancelled = false;
    
    // Clear previous results
    document.getElementById('analysis-content').textContent = '';
    
    showLoading(true);
    
    try {
        const response = await fetch(`${CAPTIONS_API_URL}/analyze_video`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                location: location ? `${location}` : '',
                target_label: targetLabel
            })
        });
        
        // Check if operation was cancelled
        if (isCancelled) {
            console.log('Video analysis was cancelled, ignoring response');
            return;
        }
        
        if (response.ok) {
            const data = await response.json();
            console.log('Analysis response:', data);
            
            if (data.status === 'completed') {
                // Parse the report to extract title and hashtags
                const report = data.report || '';
                const lines = report.split('\n');
                const title = lines[0] || 'No title generated';
                
                // Try to find the location line (starts with 📍 location:)
                const locationLine = lines.find(line => line.trim().startsWith('📍 location:'));

                // Extract hashtags (starting from line 2, skipping the empty line after title)
                const hashtags = lines.slice(2)
                    .filter(line => line.trim().startsWith('- '))
                    .map(line => line.trim().substring(2)) // Remove the '- ' prefix
                    .join(' ');
                

                // Build the output string
                let output = `${title}\n\n`;
                if (locationLine) {
                    output += `${locationLine}\n\n`;
                }
                output += hashtags;    
                document.getElementById('analysis-content').textContent = output;
            
                // Show results container
                document.getElementById('analysis-results').style.display = 'block';
            } else {
                // Show error
                alert(`Analysis failed: ${data.error_message || 'Unknown error'}`);
            }
        } else {
            throw new Error('Failed to analyze video');
        }
    } catch (error) {
        console.error('Error analyzing video:', error);
        alert(`Error analyzing video: ${error.message}`);
    } finally {
        showLoading(false);
        currentOperation = null;
    }
}

function copyResults() {
    const content = document.getElementById('analysis-content').textContent;
    const copyBtn = document.getElementById('copy-results-btn');
    const originalText = copyBtn.innerHTML;
    
    // Create a temporary textarea element
    const textarea = document.createElement('textarea');
    textarea.value = content;
    textarea.style.cssText = 'position:fixed;top:0;left:0;opacity:0;z-index:-1;pointer-events:none;';
    // Ensure the element is visible on iOS but not disturbing the layout
    textarea.style.width = '1px';
    textarea.style.height = '1px';
    document.body.appendChild(textarea);
    
    // Handle iOS devices
    if (navigator.userAgent.match(/ipad|ipod|iphone/i)) {
        textarea.contentEditable = true;
        textarea.readOnly = false;
        
        // Create range and select
        const range = document.createRange();
        range.selectNodeContents(textarea);
        const selection = window.getSelection();
        selection.removeAllRanges();
        selection.addRange(range);
        textarea.setSelectionRange(0, 999999);
        textarea.focus();
    } else {
        textarea.select();
    }
    
    try {
        document.execCommand('copy');
        copyBtn.innerHTML = '<i class="fas fa-check"></i> Copied!';
        
        setTimeout(() => {
            copyBtn.innerHTML = originalText;
        }, 2000);
    } catch (err) {
        console.error('Failed to copy text: ', err);
    } finally {
        document.body.removeChild(textarea);
    }
}

// Cancel video analysis
function cancelVideoAnalysis() {
    if (currentOperation === 'video_analysis') {
        fetch(`${API_BASE_URL}/cancel_operation`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                operation_type: 'video_analysis'
            })
        })
        .then(response => {
            if (response.ok) {
                console.log('Video analysis cancelled successfully');
            } else {
                console.error('Failed to cancel video analysis');
            }
        })
        .catch(error => {
            console.error('Error cancelling video analysis:', error);
        });
    }
}
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
    
    // Update status
    const videoStatus = document.getElementById('video-status');
    if (videoStatus) {
        videoStatus.textContent = `Selected: ${file.name}`;
    }
    
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
            
            // Update status
            const videoStatus = document.getElementById('video-status');
            if (videoStatus) {
                videoStatus.textContent = `Ready to analyze: ${file.name}`;
                videoStatus.classList.add('success');
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
                user_input: 'analyze video',
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
                
                // Extract hashtags (starting from line 2, skipping the empty line after title)
                const hashtags = lines.slice(2)
                    .filter(line => line.trim().startsWith('- '))
                    .map(line => line.trim().substring(2)) // Remove the '- ' prefix
                    .join(' ');
                
                // Display combined results
                document.getElementById('analysis-content').textContent = `${title}\n\n${hashtags}`;
                
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
    
    // Copy to clipboard
    navigator.clipboard.writeText(content)
        .then(() => {
            // Show success message
            const copyBtn = document.getElementById('copy-results-btn');
            const originalText = copyBtn.innerHTML;
            
            copyBtn.innerHTML = '<i class="fas fa-check"></i> Copied!';
            
            setTimeout(() => {
                copyBtn.innerHTML = originalText;
            }, 2000);
        })
        .catch(err => {
            console.error('Failed to copy text: ', err);
            alert('Failed to copy to clipboard');
        });
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
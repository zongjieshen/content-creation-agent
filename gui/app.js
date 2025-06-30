// API Configuration
const API_BASE_URL = 'http://localhost:8001';

// Global state
let sessionId = null;
let searchResults = null;
let currentCsvData = null;
let currentOperation = null; // Track the current operation
let isCancelled = false; // Flag to track if operation was cancelled

// Initialize the application
document.addEventListener('DOMContentLoaded', async () => {
    await initializeSession();
    setupEventListeners();
    updateSessionStatus('Connected');
});

// Session Management
async function initializeSession() {
    // Check if we already have a session ID in localStorage
    const storedSessionId = localStorage.getItem('sessionId');
    
    // Always validate the session with the server, even if we have a stored ID
    try {
        if (storedSessionId) {
            // Validate the existing session
            const validateResponse = await fetch(`${API_BASE_URL}/session/${storedSessionId}/status`);
            if (validateResponse.ok) {
                // Session is valid, use it
                sessionId = storedSessionId;
                console.log('Using validated stored session:', sessionId);
                updateSessionStatus('Connected (Existing Session)');
                return true;
            } else {
                console.log('Stored session is invalid, creating new session');
                // Fall through to create a new session
            }
        }
        
        // Create a new session
        const response = await fetch(`${API_BASE_URL}/create_session`);
        if (response.ok) {
            const data = await response.json();
            sessionId = data.session_id;
            // Store the session ID for future use
            localStorage.setItem('sessionId', sessionId);
            console.log('Session created and stored:', sessionId);
            return true;
        } else {
            throw new Error('Failed to create session');
        }
    } catch (error) {
        console.error('Error managing session:', error);
        // Clear any stored session ID if we can't connect
        localStorage.removeItem('sessionId');
        updateSessionStatus('Connection Error');
        return false;
    }
}

function updateSessionStatus(status) {
    const statusElement = document.getElementById('session-status');
    if (statusElement) {
        statusElement.textContent = status;
    }
}

async function deleteSession() {
    if (!sessionId) {
        console.log('No active session to delete');
        return false;
    }
    
    try {
        const response = await fetch(`${API_BASE_URL}/delete_session?session_id=${sessionId}`, {
            method: 'DELETE'
        });
        if (response.ok) {
            // Clear the session ID from localStorage
            localStorage.removeItem('sessionId');
            sessionId = null;
            console.log('Session deleted successfully');
            updateSessionStatus('No Session');
            return true;
        } else {
            throw new Error('Failed to delete session');
        }
    } catch (error) {
        console.error('Error deleting session:', error);
        return false;
    }
}

// Function to refresh the page and start a new session
async function refreshSession() {
    try {
        // First delete the current session if it exists
        if (sessionId) {
            await deleteSession();
        }
        
        // Reload the page to start fresh
        window.location.reload();
    } catch (error) {
        console.error('Error refreshing session:', error);
        alert('Failed to refresh session. Please try again.');
    }
}

// Event Listeners Setup
function setupEventListeners() {
    console.log('Setting up event listeners');
    
    // Tab navigation
    document.querySelectorAll('.nav-item').forEach(item => {
        item.addEventListener('click', () => {
            const tabName = item.dataset.tab;
            switchTab(tabName);
        });
    });

    // Add refresh session button event listener
    const refreshBtn = document.getElementById('refresh-session-btn');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', refreshSession);
        console.log('Refresh session button event listener attached');
    }
    
    // Search form
    const searchForm = document.getElementById('search-form');
    if (searchForm) {
        searchForm.addEventListener('submit', handleSearchSubmit);
    }

    // CSV upload
    const csvFile = document.getElementById('csv-file');
    const csvUploadBtn = document.getElementById('csv-upload-btn');
    
    if (csvFile) {
        // Remove any existing event listeners
        csvFile.removeEventListener('change', handleCsvUpload);
        // Add the event listener
        csvFile.addEventListener('change', handleCsvUpload);
        console.log('CSV file input event listener attached');
    }
    
    if (csvUploadBtn) {
        // Remove any existing event listeners
        csvUploadBtn.removeEventListener('click', handleCsvUploadButtonClick);
        // Add the event listener
        csvUploadBtn.addEventListener('click', handleCsvUploadButtonClick);
        console.log('CSV upload button event listener attached');
    }

    // Add cancel button event listener
    const cancelBtn = document.getElementById('cancel-btn');
    if (cancelBtn) {
        cancelBtn.addEventListener('click', handleCancelOperation);
        console.log('Cancel button event listener attached');
    }

    // Chat input
    const messageInput = document.getElementById('message-input');
    const sendBtn = document.getElementById('send-btn');
    
    if (messageInput && sendBtn) {
        messageInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendMessage();
            }
        });
        
        sendBtn.addEventListener('click', sendMessage);
    }
    
    // Results actions
    const downloadBtn = document.getElementById('download-csv');
    const useForMessagingBtn = document.getElementById('use-for-messaging');
    
    if (downloadBtn) {
        downloadBtn.addEventListener('click', downloadSearchResults);
    }
    
    if (useForMessagingBtn) {
        useForMessagingBtn.addEventListener('click', useResultsForMessaging);
    }
    
    // Setup Config Editor
    setupConfigEditor();
    
    // Log that all event listeners have been set up
    console.log('All event listeners have been set up');
}

// Separate function for the upload button click to avoid closure issues
function handleCsvUploadButtonClick(e) {
    e.preventDefault();
    e.stopPropagation();
    console.log('CSV upload button clicked');
    
    // First switch to the message tab
    switchTab('message');
    
    // Delay the file dialog slightly to ensure tab switch completes
    setTimeout(() => {
        // Clear any existing file selection
        const fileInput = document.getElementById('csv-file');
        if (fileInput) {
            // Clear the input to ensure change event fires even if selecting the same file
            fileInput.value = '';
            fileInput.click();
        }
    }, 150);
}

// Tab Management
function switchTab(tabName) {
    console.log('Switching to tab:', tabName);
    
    // Update navigation
    document.querySelectorAll('.nav-item').forEach(item => {
        item.classList.remove('active');
    });
    
    const targetNavItem = document.querySelector(`[data-tab="${tabName}"]`);
    if (targetNavItem) {
        targetNavItem.classList.add('active');
    } else {
        console.error('Nav item not found for tab:', tabName);
    }

    // Update content
    document.querySelectorAll('.tab-content').forEach(content => {
        content.classList.remove('active');
    });
    
    const targetTab = document.getElementById(`${tabName}-tab`);
    if (targetTab) {
        targetTab.classList.add('active');
    } else {
        console.error('Tab content not found for tab:', tabName);
    }
}

// Cancel Operation
function handleCancelOperation() {
    console.log('Cancel button clicked');
    
    if (!currentOperation) {
        console.log('No operation to cancel');
        return;
    }
    
    isCancelled = true;
    
    // Cancel the current operation based on type
    if (currentOperation === 'search') {
        cancelSearch();
    } else if (currentOperation === 'csv_upload') {
        cancelCsvUpload();
    } else if (currentOperation === 'message') {
        cancelMessageSend();
    }
    
    // Hide loading overlay
    showLoading(false);
    
    // Reset operation tracking
    currentOperation = null;
}

async function cancelSearch() {
    try {
        if (!sessionId) return;
        
        // Call the cancel endpoint if it exists
        const response = await fetch(`${API_BASE_URL}/cancel_operation`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                session_id: sessionId,
                operation_type: 'search'
            })
        });
        
        if (response.ok) {
            console.log('Search cancelled successfully');
            // Show message to user
            alert('Search operation cancelled.');
        }
    } catch (error) {
        console.error('Error cancelling search:', error);
    }
}

async function cancelCsvUpload() {
    // For CSV upload, we can just stop the UI processing
    // since the upload might have already completed on the server
    console.log('CSV upload cancelled');
    
    // Clear the file input
    const fileInput = document.getElementById('csv-file');
    if (fileInput) fileInput.value = '';
    
    // Update CSV status
    const csvStatus = document.getElementById('csv-status');
    if (csvStatus) {
        csvStatus.className = 'csv-status';
        csvStatus.textContent = 'Operation cancelled';
    }
    
    // Show message to user
    alert('CSV upload cancelled.');
}

async function cancelMessageSend() {
    try {
        if (!sessionId) return;
        
        // Call the cancel endpoint if it exists
        const response = await fetch(`${API_BASE_URL}/cancel_operation`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                session_id: sessionId,
                operation_type: 'message'
            })
        });
        
        if (response.ok) {
            console.log('Message send cancelled successfully');
            // Show message to user
            alert('Message operation cancelled.');
        }
    } catch (error) {
        console.error('Error cancelling message send:', error);
    }
}

// Search Functionality
async function handleSearchSubmit(e) {
    e.preventDefault();
    
    if (!sessionId) {
        alert('Session not initialized. Please refresh the page.');
        return;
    }

    // Set current operation
    currentOperation = 'search';
    isCancelled = false;

    const formData = new FormData(e.target);
    const searchParams = {
        niche: formData.get('niche'),
        location: formData.get('location') || '',
        max_results: parseInt(formData.get('max_results')) || 50,
        max_pages: parseInt(formData.get('max_pages')) || 5
    };

    // Construct search query
    let query = `niche: ${searchParams.niche}`;
    if (searchParams.location) {
        query += `; location: ${searchParams.location}`;
    }
    query += `; max_results: ${searchParams.max_results}`;
    query += `; max_pages: ${searchParams.max_pages}`;

    showLoading(true);
    
    try {
        const response = await fetch(`${API_BASE_URL}/generate`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                messages: [
                    {
                        role: 'user',
                        content: query
                    }
                ],
                session_id: sessionId,
                workflow_type: 'collaboration',
                parameters: searchParams
            })
        });

        // Check if operation was cancelled during the fetch
        if (isCancelled) {
            console.log('Search was cancelled, ignoring response');
            return;
        }

        if (response.ok) {
            const data = await response.json();
            handleSearchResponse(data);
        } else {
            throw new Error('Search request failed');
        }
    } catch (error) {
        if (!isCancelled) { // Only show error if not cancelled
            console.error('Search error:', error);
            alert('Search failed. Please try again.');
        }
    } finally {
        // Reset operation tracking if not cancelled elsewhere
        if (!isCancelled) {
            currentOperation = null;
            showLoading(false);
        }
    }
}

function handleSearchResponse(data) {
    console.log('Search response:', data);
    
    if (data.workflow_status === 'awaiting_human_input') {
        // Handle interrupt - continue polling or show options
        handleWorkflowInterrupt(data);
    } else if (data.interrupt_data && data.interrupt_data.collaboration_result) {
        // Search completed successfully
        searchResults = data.interrupt_data.collaboration_result;
        displaySearchResults(searchResults);
    } else {
        // Show the assistant's message
        const message = data.choices[0]?.message?.content || 'Search completed';
        alert(message);
    }
}

function handleWorkflowInterrupt(data) {
    // For collaboration workflow, we might need to handle interrupts
    // For now, we'll poll for completion
    setTimeout(() => {
        pollSearchStatus();
    }, 2000);
}

async function pollSearchStatus() {
    try {
        const response = await fetch(`${API_BASE_URL}/session/${sessionId}/status`);
        if (response.ok) {
            const status = await response.json();
            console.log('Session status:', status);
            // Continue polling or handle completion based on status
        }
    } catch (error) {
        console.error('Status polling error:', error);
    }
}

function displaySearchResults(results) {
    const resultsContainer = document.getElementById('search-results');
    const tableContainer = document.getElementById('results-table-container');
    
    if (!results || (!results.profiles) || 
        (results.profiles && results.profiles.length === 0)) {
        tableContainer.innerHTML = '<p>No results found.</p>';
        resultsContainer.style.display = 'block';
        return;
    }

    // Store the data for the CSV editor
    // Use profiles if available, otherwise use opportunities
    currentCsvData = results.profiles;
    
    // Pagination variables
    const entriesPerPage = 10;
    let currentPage = 1;
    const totalPages = Math.ceil(currentCsvData.length / entriesPerPage);
    
    // Function to render the current page
    function renderPage(page) {
        // Clear the container
        tableContainer.innerHTML = '';
        
        // Create table
        const table = document.createElement('table');
        table.className = 'results-table';
        
        // Table header
        const thead = document.createElement('thead');
        const headerRow = document.createElement('tr');
        const headers = ['Profile URL', 'Username', 'Bio'];
        
        headers.forEach(header => {
            const th = document.createElement('th');
            th.textContent = header;
            headerRow.appendChild(th);
        });
        thead.appendChild(headerRow);
        table.appendChild(thead);
        
        // Table body
        const tbody = document.createElement('tbody');
        
        // Calculate start and end indices for the current page
        const startIndex = (page - 1) * entriesPerPage;
        const endIndex = Math.min(startIndex + entriesPerPage, currentCsvData.length);
        
        // Add only the profiles for the current page
        for (let i = startIndex; i < endIndex; i++) {
            const profile = currentCsvData[i];
            const row = document.createElement('tr');
            
            const cells = [
                profile.profile_url || '',
                profile.handle || profile.username || '',
                profile.bio || profile.description || ''
            ];
            
            cells.forEach(cellData => {
                const td = document.createElement('td');
                if (cellData.toString().startsWith('http')) {
                    const link = document.createElement('a');
                    link.href = cellData;
                    link.textContent = cellData;
                    link.target = '_blank';
                    td.appendChild(link);
                } else {
                    td.textContent = cellData;
                }
                row.appendChild(td);
            });
            
            tbody.appendChild(row);
        }
        table.appendChild(tbody);
        
        // Add the table to the container
        tableContainer.appendChild(table);
        
        // Create pagination controls
        const paginationContainer = document.createElement('div');
        paginationContainer.className = 'pagination-controls';
        
        // Previous button
        const prevButton = document.createElement('button');
        prevButton.textContent = 'Previous';
        prevButton.className = 'btn btn-secondary pagination-btn';
        prevButton.disabled = page === 1;
        prevButton.addEventListener('click', () => {
            if (currentPage > 1) {
                currentPage--;
                renderPage(currentPage);
            }
        });
        
        // Page indicator
        const pageIndicator = document.createElement('span');
        pageIndicator.textContent = `Page ${page} of ${totalPages}`;
        pageIndicator.className = 'pagination-indicator';
        
        // Next button
        const nextButton = document.createElement('button');
        nextButton.textContent = 'Next';
        nextButton.className = 'btn btn-secondary pagination-btn';
        nextButton.disabled = page === totalPages;
        nextButton.addEventListener('click', () => {
            if (currentPage < totalPages) {
                currentPage++;
                renderPage(currentPage);
            }
        });
        
        // Add pagination controls to the container
        paginationContainer.appendChild(prevButton);
        paginationContainer.appendChild(pageIndicator);
        paginationContainer.appendChild(nextButton);
        tableContainer.appendChild(paginationContainer);
    }
    
    // Initial render
    renderPage(currentPage);
    resultsContainer.style.display = 'block';
    
}

function downloadSearchResults() {
    if (!searchResults || (!searchResults.profiles && !searchResults.opportunities)) {
        alert('No search results to download.');
        return;
    }

    const csvContent = convertToCSV(searchResults.profiles || searchResults.opportunities);
    const blob = new Blob([csvContent], { type: 'text/csv' });
    const url = window.URL.createObjectURL(blob);
    
    const a = document.createElement('a');
    a.href = url;
    a.download = `collaboration_results_${new Date().toISOString().split('T')[0]}.csv`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.URL.revokeObjectURL(url);
}

function convertToCSV(data) {
    if (!data || data.length === 0) return '';
    
    const headers = Object.keys(data[0]);
    const csvRows = [headers.join(',')];
    
    data.forEach(row => {
        const values = headers.map(header => {
            const value = row[header] || '';
            return `"${value.toString().replace(/"/g, '""')}"`;
        });
        csvRows.push(values.join(','));
    });
    
    return csvRows.join('\n');
}

function useResultsForMessaging() {
    if (!searchResults || (!searchResults.profiles && !searchResults.opportunities)) {
        alert('No search results available to use for messaging.');
        return;
    }
    
    // Set the current CSV data to the search results
    currentCsvData = searchResults.profiles || searchResults.opportunities;
    
    // Switch to the message tab
    switchTab('message');
    
    // Show loading while we upload the CSV silently
    showLoading(true);
    
    // Convert the search results to CSV format
    const csvContent = convertToCSV(currentCsvData);
    
    // Create a File object from the CSV content
    const filename = `search_results_${new Date().toISOString().split('T')[0]}.csv`;
    const file = new File([csvContent], filename, { type: 'text/csv' });
    
    // Silently upload the CSV file to the server
    const formData = new FormData();
    formData.append('file', file);
    
    fetch(`${API_BASE_URL}/upload_csv`, {
        method: 'POST',
        body: formData
    })
    .then(response => {
        if (response.ok) {
            return response.json();
        } else {
            throw new Error('Failed to upload search results');
        }
    })
    .then(data => {
        console.log('Search results uploaded successfully:', data);
        
        // Delay the rest of the process to ensure tab switch completes
        setTimeout(() => {
            // Update CSV status with the actual filename that was uploaded
            const csvStatus = document.getElementById('csv-status');
            csvStatus.className = 'csv-status success';
            csvStatus.textContent = `Using search results: "${filename}" ${currentCsvData.length} profiles loaded`;
            
            // Enable chat input
            enableChatInput();
            
            // Add system message
            addChatMessage('assistant', `Search results loaded! ${currentCsvData.length} profiles are ready for messaging. How would you like to proceed?`);
            
            // Display the View/Edit CSV button
            displayViewEditCsvButton();
            
            // Display the Start button
            displayStartButton();
            
            // Hide loading
            showLoading(false);
        }, 100);
    })
    .catch(error => {
        console.error('Error uploading search results:', error);
        showLoading(false);
        alert('Failed to upload search results. Please try again.');
    });
}

// CSV Upload Functionality
async function handleCsvUpload(e) {
    // Prevent default behavior and stop propagation
    e.preventDefault();
    e.stopPropagation();
    
    console.log('CSV upload handler triggered');
    
    const file = e.target.files[0];
    if (!file) {
        console.log('No file selected');
        return;
    }
    
    if (!file.name.endsWith('.csv')) {
        alert('Please select a CSV file.');
        e.target.value = ''; // Clear the input
        return;
    }
    
    // Ensure we're on the message tab and force it to stay there
    switchTab('message');
    
    // Delay processing slightly to ensure UI updates properly
    setTimeout(() => {
        processCsvUpload(file);
    }, 50);
}

async function processCsvUpload(file) {
    showLoading(true);
    console.log('Uploading CSV file:', file.name);
    
    try {
        const formData = new FormData();
        formData.append('file', file);
        
        const response = await fetch(`${API_BASE_URL}/upload_csv`, {
            method: 'POST',
            body: formData
        });
        
        // Check if operation was cancelled during the fetch
        if (isCancelled) {
            console.log('CSV upload was cancelled, ignoring response');
            return;
        }
        
        if (response.ok) {
            const data = await response.json();
            console.log('Upload response:', data);
            handleCsvUploadSuccess(file.name);
            
            // Parse CSV for local use
            const text = await file.text();
            currentCsvData = parseCSV(text);
            console.log('Parsed CSV data:', currentCsvData.length, 'profiles');
            
            // Make sure we're still on the message tab
            switchTab('message');
            
            enableChatInput();
            addChatMessage('assistant', `CSV file "${file.name}" uploaded successfully! ${currentCsvData.length} profiles loaded. Click the Start button to begin messaging.`);
            
            // Display the Start button
            displayStartButton();
        } else {
            const error = await response.json();
            throw new Error(error.detail || 'Upload failed');
        }
    } catch (error) {
        if (!isCancelled) { // Only show error if not cancelled
            console.error('CSV upload error:', error);
            handleCsvUploadError(error.message);
            // Clear the file input
            const fileInput = document.getElementById('csv-file');
            if (fileInput) fileInput.value = '';
        }
    } finally {
        // Reset operation tracking if not cancelled elsewhere
        if (!isCancelled) {
            currentOperation = null;
            showLoading(false);
        }
        // Ensure we're on the message tab
        switchTab('message');
    }
}

function handleCsvUploadSuccess(filename) {
    const csvStatus = document.getElementById('csv-status');
    csvStatus.className = 'csv-status success';
    csvStatus.textContent = `File "${filename}" uploaded successfully!`;
    console.log('CSV upload successful:', filename);
    
    // Display the start button after successful upload
    displayStartButton();
    
    // Add View/Edit CSV button
    displayViewEditCsvButton();
}

// Function to display the View/Edit CSV button
function displayViewEditCsvButton() {
    const csvUploadSection = document.querySelector('.csv-upload-section');
    
    // Remove existing button if any
    const existingButton = document.getElementById('view-edit-csv-btn');
    if (existingButton) {
        existingButton.remove();
    }
    
    // Create View/Edit CSV button
    const button = document.createElement('button');
    button.id = 'view-edit-csv-btn';
    button.className = 'btn btn-secondary view-edit-btn';
    button.innerHTML = '<i class="fas fa-table"></i> View/Edit CSV';
    button.addEventListener('click', openCsvEditor);
    
    // Append button to the CSV upload section
    csvUploadSection.appendChild(button);
}

// Function to display the Start button
function displayStartButton() {
    const interruptOptions = document.getElementById('interrupt-options');
    
    // Clear any existing options
    interruptOptions.innerHTML = '';
    
    // Add header
    const optionsHeader = document.createElement('h4');
    optionsHeader.textContent = 'Ready to proceed:';
    interruptOptions.appendChild(optionsHeader);
    
    // Create Start button
    const button = document.createElement('button');
    button.className = 'interrupt-btn start-btn';
    button.textContent = 'Start';
    button.addEventListener('click', () => {
        selectInterruptOption('Start');
    });
    interruptOptions.appendChild(button);
    
    // Display the interrupt options container
    interruptOptions.style.display = 'block';
}

// Update the selectInterruptOption function to handle the Start option
function selectInterruptOption(option) {
    const messageInput = document.getElementById('message-input');
    
    // Check if this is the Edit option
    if (option === 'Edit') {
        // Get the message_text from the interrupt data
        const messageText = document.querySelector('.message-preview p')?.textContent;
        if (messageText) {
            // Set the message text in the input field for editing
            messageInput.value = messageText;
        } else {
            // Fallback if message text isn't found in the DOM
            messageInput.value = '';
        }
    } else if (option === 'Start') {
        // For Start option, set a specific message to initiate the workflow
        messageInput.value = 'Start messaging workflow';
        // Automatically send the message
        sendMessage();
    } else {
        // For other options, use the original behavior
        messageInput.value = option;
    }
    
    messageInput.focus();
    
    // Hide interrupt options
    document.getElementById('interrupt-options').style.display = 'none';
}

function handleCsvUploadError(message) {
    const csvStatus = document.getElementById('csv-status');
    csvStatus.className = 'csv-status error';
    csvStatus.textContent = `Upload error: ${message}`;
    console.error('CSV upload error:', message);
}

function parseCSV(text) {
    const lines = text.split('\n');
    if (lines.length < 2) return [];
    
    const headers = lines[0].split(',').map(h => h.trim().replace(/"/g, ''));
    const data = [];
    
    for (let i = 1; i < lines.length; i++) {
        const line = lines[i].trim();
        if (!line) continue;
        
        const values = line.split(',').map(v => v.trim().replace(/"/g, ''));
        const row = {};
        
        headers.forEach((header, index) => {
            row[header] = values[index] || '';
        });
        
        data.push(row);
    }
    
    return data;
}

// Chat Functionality
function enableChatInput() {
    const messageInput = document.getElementById('message-input');
    const sendBtn = document.getElementById('send-btn');
    
    messageInput.disabled = false;
    sendBtn.disabled = false;
    messageInput.placeholder = 'Type your message...';
}

function addChatMessage(role, content) {
    const chatMessages = document.getElementById('chat-messages');
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${role}`;
    
    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';
    contentDiv.textContent = content;
    
    messageDiv.appendChild(contentDiv);
    chatMessages.appendChild(messageDiv);
    
    // Scroll to bottom
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

async function sendMessage() {
    const messageInput = document.getElementById('message-input');
    const message = messageInput.value.trim();
    
    if (!message || !sessionId) return;
    
    // Add user message to chat
    addChatMessage('user', message);
    messageInput.value = '';
    
    // Set current operation
    currentOperation = 'message';
    isCancelled = false;
    
    showLoading(true);
    
    try {
        const response = await fetch(`${API_BASE_URL}/generate`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                messages: [
                    {
                        role: 'user',
                        content: message
                    }
                ],
                session_id: sessionId,
                workflow_type: 'messaging',
                parameters: {}
            })
        });
        
        // Check if operation was cancelled during the fetch
        if (isCancelled) {
            console.log('Message send was cancelled, ignoring response');
            return;
        }
        
        if (response.ok) {
            const data = await response.json();
            handleChatResponse(data);
        } else {
            throw new Error('Message sending failed');
        }
    } catch (error) {
        if (!isCancelled) { // Only show error if not cancelled
            console.error('Chat error:', error);
            addChatMessage('assistant', 'Sorry, there was an error processing your message. Please try again.');
        }
    } finally {
        // Reset operation tracking if not cancelled elsewhere
        if (!isCancelled) {
            currentOperation = null;
            showLoading(false);
        }
    }
}

function handleChatResponse(data) {
    console.log('Chat response:', data);
    
    const assistantMessage = data.choices[0]?.message?.content || 'No response received';
    addChatMessage('assistant', assistantMessage);
    
    // Handle workflow interrupts
    if (data.workflow_status === 'awaiting_human_input') {
        handleChatInterrupt(data);
    }
}

function handleChatInterrupt(data) {
    const interruptOptions = document.getElementById('interrupt-options');
    
    // Check if there are options in the response
    const options = data.choices[0]?.options || data.interrupt_data?.data?.options;
    
    // Extract message_text from interrupt data if available
    const messageText = data.interrupt_data?.data?.message_text;
    if (messageText) {
        // Display the message text in the UI
        const messageContainer = document.createElement('div');
        messageContainer.className = 'message-preview';
        messageContainer.innerHTML = `<h4>Message Preview:</h4><p>${messageText}</p>`;
        
        // Add the message preview before the options
        interruptOptions.innerHTML = '';
        interruptOptions.appendChild(messageContainer);
    }
    
    if (options && options.length > 0) {
        // If we added a message preview, add options after it
        // Otherwise create the container from scratch
        if (!messageText) {
            interruptOptions.innerHTML = '<h4>Quick Options:</h4>';
        } else {
            const optionsHeader = document.createElement('h4');
            optionsHeader.textContent = 'Quick Options:';
            interruptOptions.appendChild(optionsHeader);
        }
        
        options.forEach(option => {
            const button = document.createElement('button');
            button.className = 'interrupt-btn';
            button.textContent = option;
            button.addEventListener('click', () => {
                selectInterruptOption(option);
            });
            interruptOptions.appendChild(button);
        });
    }
    
    // Display the interrupt options container if we have either message text or options
    if ((messageText || (options && options.length > 0)) && interruptOptions) {
        interruptOptions.style.display = 'block';
    }
}

function displayInterruptOptions(options) {
    const interruptContainer = document.getElementById('interrupt-options');
    
    interruptContainer.innerHTML = '<h4>Quick Options:</h4>';
    
    options.forEach(option => {
        const button = document.createElement('button');
        button.className = 'interrupt-btn';
        button.textContent = option;
        button.addEventListener('click', () => {
            selectInterruptOption(option);
        });
        interruptContainer.appendChild(button);
    });
    
    interruptContainer.style.display = 'block';
}

function selectInterruptOption(option) {
    const messageInput = document.getElementById('message-input');
    
    // Check if this is the Edit option
    if (option === 'Edit') {
        // Get the message_text from the interrupt data
        const messageText = document.querySelector('.message-preview p')?.textContent;
        if (messageText) {
            // Set the message text in the input field for editing
            messageInput.value = messageText;
        } else {
            // Fallback if message text isn't found in the DOM
            messageInput.value = '';
        }
    } else {
        // For other options, use the original behavior
        messageInput.value = option;
    }
    
    messageInput.focus();
    
    // Hide interrupt options
    document.getElementById('interrupt-options').style.display = 'none';
}

// Add View/Edit CSV button to search results
function addViewEditCsvButtonToSearchResults() {
    const resultsContainer = document.getElementById('search-results');
    
    // Remove existing button if any
    const existingButton = document.getElementById('search-view-edit-csv-btn');
    if (existingButton) {
        existingButton.remove();
    }
    
    // Create button container
    const buttonContainer = document.createElement('div');
    buttonContainer.className = 'search-results-actions';
    
    // Create View/Edit CSV button
    const button = document.createElement('button');
    button.id = 'search-view-edit-csv-btn';
    button.className = 'btn btn-secondary view-edit-btn';
    button.innerHTML = '<i class="fas fa-table"></i> View/Edit CSV';
    button.addEventListener('click', openCsvEditor);
    
    buttonContainer.appendChild(button);
    
    // Add to results container before the existing buttons
    const downloadBtn = document.getElementById('download-csv');
    if (downloadBtn && downloadBtn.parentNode) {
        downloadBtn.parentNode.insertBefore(buttonContainer, downloadBtn);
    } else {
        resultsContainer.appendChild(buttonContainer);
    }
}

// Utility Functions
function showLoading(show) {
    const loadingOverlay = document.getElementById('loading-overlay');
    loadingOverlay.style.display = show ? 'flex' : 'none';
}

// Error Handling
window.addEventListener('error', (e) => {
    console.error('Global error:', e.error);
});

window.addEventListener('unhandledrejection', (e) => {
    console.error('Unhandled promise rejection:', e.reason);
});

// Handle page unload events
// Note: We don't delete the session on page unload/refresh
// This allows the session to persist across page refreshes
// The session will only be deleted when explicitly called or on critical errors

// Chat input auto-resize
const messageInput = document.getElementById('message-input');
if (messageInput) {
    // Initial setup
    messageInput.setAttribute('style', 'height: auto;');
    
    // Function to resize the textarea
    const resizeTextarea = () => {
        messageInput.style.height = 'auto';
        messageInput.style.height = messageInput.scrollHeight + 'px';
    };
    
    // Add event listeners for input changes
    messageInput.addEventListener('input', resizeTextarea);
    messageInput.addEventListener('focus', resizeTextarea);
}

// CSV Editor Functionality
function openCsvEditor() {
    if (!currentCsvData || currentCsvData.length === 0) {
        alert('No CSV data available to edit.');
        return;
    }
    
    // Show the modal
    const modal = document.getElementById('csv-editor-modal');
    modal.style.display = 'flex';
    
    // Render the CSV data in the editor
    renderCsvEditorTable(currentCsvData);
    
    // Set up event listeners
    setupCsvEditorEventListeners();
}

function renderCsvEditorTable(data) {
    const tableContainer = document.getElementById('csv-editor-table-container');
    tableContainer.innerHTML = '';
    
    // Create table
    const table = document.createElement('table');
    table.className = 'csv-editor-table';
    
    // Get all headers from the data
    const headers = Object.keys(data[0]);
    
    // Table header
    const thead = document.createElement('thead');
    const headerRow = document.createElement('tr');
    
    // Add Skip column header
    const skipHeader = document.createElement('th');
    skipHeader.textContent = 'Skip';
    headerRow.appendChild(skipHeader);
    
    // Add other column headers
    headers.forEach(header => {
        const th = document.createElement('th');
        th.textContent = header;
        headerRow.appendChild(th);
    });
    
    thead.appendChild(headerRow);
    table.appendChild(thead);
    
    // Table body
    const tbody = document.createElement('tbody');
    data.forEach((row, rowIndex) => {
        const tr = document.createElement('tr');
        
        // Add Skip checkbox
        const skipCell = document.createElement('td');
        const skipCheckbox = document.createElement('input');
        skipCheckbox.type = 'checkbox';
        skipCheckbox.className = 'skip-checkbox';
        skipCheckbox.dataset.rowIndex = rowIndex;
        skipCheckbox.checked = row.skip === 'true' || row.skip === true;
        skipCell.appendChild(skipCheckbox);
        tr.appendChild(skipCell);
        
        // Add other cells
        headers.forEach(header => {
            const td = document.createElement('td');
            
            // Make profile_url a link
            if (header === 'profile_url' && row[header]) {
                const link = document.createElement('a');
                link.href = row[header];
                link.textContent = row[header];
                link.target = '_blank';
                td.appendChild(link);
            } 
            // Make other cells editable except for profile_url
            else if (header !== 'profile_url') {
                const input = document.createElement('input');
                input.type = 'text';
                input.value = row[header] || '';
                input.dataset.rowIndex = rowIndex;
                input.dataset.column = header;
                td.appendChild(input);
            } else {
                td.textContent = row[header] || '';
            }
            
            tr.appendChild(td);
        });
        
        tbody.appendChild(tr);
    });
    
    table.appendChild(tbody);
    tableContainer.appendChild(table);
}

function setupCsvEditorEventListeners() {
    // Close modal button
    const closeBtn = document.querySelector('.modal-close');
    closeBtn.addEventListener('click', closeCsvEditor);
    
    // Save changes button
    const saveBtn = document.getElementById('save-csv-changes');
    saveBtn.addEventListener('click', saveCsvChanges);
    
    // Search filter
    const searchInput = document.getElementById('csv-search');
    searchInput.addEventListener('input', filterCsvTable);
    
    // Close when clicking outside the modal content
    const modal = document.getElementById('csv-editor-modal');
    modal.addEventListener('click', (e) => {
        if (e.target === modal) {
            closeCsvEditor();
        }
    });
}

function filterCsvTable() {
    const searchInput = document.getElementById('csv-search');
    const searchTerm = searchInput.value.toLowerCase();
    const rows = document.querySelectorAll('.csv-editor-table tbody tr');
    
    rows.forEach(row => {
        const text = row.textContent.toLowerCase();
        if (text.includes(searchTerm)) {
            row.style.display = '';
        } else {
            row.style.display = 'none';
        }
    });
}

function saveCsvChanges() {
    // Get all input fields and checkboxes
    const inputs = document.querySelectorAll('.csv-editor-table input[type="text"]');
    const checkboxes = document.querySelectorAll('.csv-editor-table .skip-checkbox');
    
    // Update the currentCsvData with edited values
    inputs.forEach(input => {
        const rowIndex = parseInt(input.dataset.rowIndex);
        const column = input.dataset.column;
        currentCsvData[rowIndex][column] = input.value;
    });
    
    // Update skip status
    checkboxes.forEach(checkbox => {
        const rowIndex = parseInt(checkbox.dataset.rowIndex);
        // Add or update the skip property
        currentCsvData[rowIndex].skip = checkbox.checked.toString();
    });
    
    // Save changes to the server
    saveChangesToServer();
    
    // Close the editor
    closeCsvEditor();
}

function closeCsvEditor() {
    const modal = document.getElementById('csv-editor-modal');
    modal.style.display = 'none';
}

async function saveChangesToServer() {
    try {
        showLoading(true);
        
        // Get the current filename from the CSV status
        const csvStatus = document.getElementById('csv-status');
        const statusText = csvStatus.textContent;
        const filenameMatch = statusText.match(/"([^"]+)"/); // Extract filename in quotes
        const filename = filenameMatch ? filenameMatch[1] : 'uploaded_profiles.csv';
        
        const response = await fetch(`${API_BASE_URL}/save_csv`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                csv_data: currentCsvData,
                filename: filename
            })
        });
        
        if (response.ok) {
            const data = await response.json();
            console.log('CSV saved successfully:', data);
            
            // Update the CSV status
            csvStatus.className = 'csv-status success';
            csvStatus.textContent = `CSV data updated: ${currentCsvData.length} profiles (${document.querySelectorAll('.csv-editor-table .skip-checkbox').length} profiles, ${Array.from(document.querySelectorAll('.csv-editor-table .skip-checkbox')).filter(cb => cb.checked).length} marked to skip)`;
            
            // Alert the user
            alert('CSV changes saved successfully!');
        } else {
            const error = await response.json();
            throw new Error(error.detail || 'Save failed');
        }
    } catch (error) {
        console.error('CSV save error:', error);
        alert(`Error saving CSV: ${error.message}`);
    } finally {
        showLoading(false);
    }
}

// Config Editor Functionality
function setupConfigEditor() {
    const configEditorBtn = document.getElementById('config-editor-btn');
    const configEditorModal = document.getElementById('config-editor-modal');
    const modalClose = configEditorModal.querySelector('.modal-close');
    const saveConfigBtn = document.getElementById('save-config-changes');
    
    // Initialize CodeMirror
    let editor = null;
    
    // Open modal and load config
    configEditorBtn.addEventListener('click', async () => {
        try {
            showLoading(true);
            const response = await fetch(`${API_BASE_URL}/get_config`);
            if (response.ok) {
                const data = await response.json();
                
                // Initialize CodeMirror if not already initialized
                if (!editor) {
                    editor = CodeMirror(document.getElementById('config-editor'), {
                        value: data.config_content,
                        mode: 'yaml',
                        theme: 'monokai',
                        lineNumbers: true,
                        indentUnit: 2,
                        tabSize: 2,
                        lineWrapping: true,
                        extraKeys: {
                            "Tab": function(cm) {
                                if (cm.somethingSelected()) {
                                    cm.indentSelection("add");
                                } else {
                                    cm.replaceSelection(" ".repeat(cm.getOption("indentUnit")));
                                }
                            }
                        }
                    });
                } else {
                    editor.setValue(data.config_content);
                }
                
                configEditorModal.style.display = 'block';
                // Refresh editor to ensure proper rendering
                setTimeout(() => editor.refresh(), 10);
            } else {
                throw new Error('Failed to load configuration');
            }
        } catch (error) {
            console.error('Error loading config:', error);
            alert('Failed to load configuration. Please try again.');
        } finally {
            showLoading(false);
        }
    });
    
    // Close modal
    modalClose.addEventListener('click', () => {
        configEditorModal.style.display = 'none';
    });
    
    // Close modal when clicking outside
    window.addEventListener('click', (event) => {
        if (event.target === configEditorModal) {
            configEditorModal.style.display = 'none';
        }
    });
    
    // Save config changes
    saveConfigBtn.addEventListener('click', async () => {
        try {
            if (!editor) {
                throw new Error('Editor not initialized');
            }
            
            showLoading(true);
            const response = await fetch(`${API_BASE_URL}/save_config`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    config_content: editor.getValue()
                })
            });
            
            if (response.ok) {
                alert('Configuration saved successfully!');
                configEditorModal.style.display = 'none';
            } else {
                const errorData = await response.json();
                throw new Error(errorData.detail || 'Failed to save configuration');
            }
        } catch (error) {
            console.error('Error saving config:', error);
            alert(`Failed to save configuration: ${error.message}`);
        } finally {
            showLoading(false);
        }
    });
}
// Messaging Functionality
document.addEventListener('DOMContentLoaded', () => {
    // CSV file upload
    const csvFileInput = document.getElementById('csv-file');
    const csvUploadBtn = document.getElementById('csv-upload-btn');
    
    if (csvFileInput) {
        csvFileInput.addEventListener('change', handleCsvUpload);
    }
    
    if (csvUploadBtn) {
        csvUploadBtn.addEventListener('click', () => {
            csvFileInput.click();
        });
    }
    
    // Chat input and send button
    const messageInput = document.getElementById('message-input');
    const sendBtn = document.getElementById('send-btn');
    
    if (messageInput && sendBtn) {
        // Send message on button click
        sendBtn.addEventListener('click', sendMessage);
        
        // Send message on Enter key (but allow Shift+Enter for new lines)
        messageInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendMessage();
            }
        });
        
        // Auto-resize textarea
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
});

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

function handleCsvUploadError(message) {
    const csvStatus = document.getElementById('csv-status');
    csvStatus.className = 'csv-status error';
    csvStatus.textContent = `Upload error: ${message}`;
    console.error('CSV upload error:', message);
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
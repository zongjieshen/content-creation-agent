// API Configuration
const API_BASE_URL = 'http://localhost:8001';
const SCRAPING_API_URL = 'http://localhost:8002';
const CAPTIONS_API_URL = 'http://localhost:8005';

// Global state
let sessionId = null;
let searchResults = null;
let scrapingResults = null;
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
// Add this to the setupEventListeners function
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
    
    // Add cancel button event listener
    const cancelBtn = document.getElementById('cancel-btn');
    if (cancelBtn) {
        cancelBtn.addEventListener('click', handleCancelOperation);
        console.log('Cancel button event listener attached');
    }
    
    
    // Log that all event listeners have been set up
    console.log('All event listeners have been set up');
    
    // Add sidebar toggle functionality
    const sidebarToggle = document.getElementById('sidebar-toggle');
    const sidebar = document.querySelector('.sidebar');
    const toggleIcon = document.getElementById('toggle-icon');
    
    // Check if sidebar state was saved in localStorage
    if (sidebarToggle && sidebar && toggleIcon) {
    // Load saved state
    const sidebarCollapsed = localStorage.getItem('sidebarCollapsed') === 'true';
    if (sidebarCollapsed) {
        sidebar.classList.add('collapsed');
        toggleIcon.classList.remove('fa-chevron-left');
        toggleIcon.classList.add('fa-chevron-right');
    }
    
    // Update the click handler to save state
    sidebarToggle.addEventListener('click', () => {
        sidebar.classList.toggle('collapsed');
        
        // Change the icon based on sidebar state
        if (sidebar.classList.contains('collapsed')) {
            toggleIcon.classList.remove('fa-chevron-left');
            toggleIcon.classList.add('fa-chevron-right');
            localStorage.setItem('sidebarCollapsed', 'true');
        } else {
            toggleIcon.classList.remove('fa-chevron-right');
            toggleIcon.classList.add('fa-chevron-left');
            localStorage.setItem('sidebarCollapsed', 'false');
        }
    });
    console.log('Sidebar toggle event listener attached with state persistence');
    }
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
// Add to the handleCancelOperation function
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
    } else if (currentOperation === 'scraping') {
        cancelScraping();
    } else if (currentOperation === 'video_analysis') {
        cancelVideoAnalysis();
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

async function cancelScraping() {
    try {
        const response = await fetch(`${SCRAPING_API_URL}/cancel_operation`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ operation_type: 'scraping' }) // No session/workflow ID
        });
        if (response.ok) {
            isCancelled = true;
            alert('Scraping operation cancelled.');
            showLoading(false);
            currentOperation = null;
            currentWorkflowId = null;
        } else {
            throw new Error('Failed to cancel scraping operation');
        }
    } catch (error) {
        console.error('Error cancelling scraping:', error);
        alert('Failed to cancel scraping. Please try again.');
    }
}

// Utility Functions
function showLoading(show) {
    const loadingOverlay = document.getElementById('loading-overlay');
    loadingOverlay.style.display = show ? 'flex' : 'none';
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

// Error Handling
window.addEventListener('error', (e) => {
    console.error('Global error:', e.error);
});

window.addEventListener('unhandledrejection', (e) => {
    console.error('Unhandled promise rejection:', e.reason);
});

// Add this function to save sidebar state to localStorage
function saveSidebarState() {
    const sidebar = document.querySelector('.sidebar');
    if (sidebar) {
        const isCollapsed = sidebar.classList.contains('collapsed');
        localStorage.setItem('sidebarCollapsed', isCollapsed);
    }
}

// Add this function to load sidebar state from localStorage
function loadSidebarState() {
    const sidebar = document.querySelector('.sidebar');
    const toggleIcon = document.getElementById('toggle-icon');
    
    if (sidebar && toggleIcon) {
        const isCollapsed = localStorage.getItem('sidebarCollapsed') === 'true';
        
        if (isCollapsed) {
            sidebar.classList.add('collapsed');
            toggleIcon.classList.remove('fa-chevron-left');
            toggleIcon.classList.add('fa-chevron-right');
        }
    }
}

// Modify the document.addEventListener('DOMContentLoaded') to include loading sidebar state
document.addEventListener('DOMContentLoaded', async () => {
    await initializeSession();
    setupEventListeners();
    loadSidebarState(); // Add this line
    updateSessionStatus('Connected');
});
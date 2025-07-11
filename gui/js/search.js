// Search Functionality
document.addEventListener('DOMContentLoaded', () => {
    // Search form
    const searchForm = document.getElementById('search-form');
    if (searchForm) {
        searchForm.addEventListener('submit', handleSearchSubmit);
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
});

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
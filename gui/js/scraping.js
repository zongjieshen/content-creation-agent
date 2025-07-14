// Scraping Functionality
document.addEventListener('DOMContentLoaded', () => {
    // Scraping form
    const scrapingForm = document.getElementById('scraping-form');
    if (scrapingForm) {
        scrapingForm.addEventListener('submit', handleScrapingSubmit);
    }
    
    // Load scraped users button
    const loadScrapedUsersBtn = document.getElementById('load-scraped-users');
    if (loadScrapedUsersBtn) {
        loadScrapedUsersBtn.addEventListener('click', () => {
            // Add active class to the button
            document.querySelectorAll('.action-buttons .btn').forEach(btn => {
                btn.classList.remove('active');
            });
            loadScrapedUsersBtn.classList.add('active');
            loadScrapedUsers();
        });
    }
    
    // Load brands button
    const loadBrandsBtn = document.getElementById('load-brands');
    if (loadBrandsBtn) {
        loadBrandsBtn.addEventListener('click', () => {
            // Add active class to the button
            document.querySelectorAll('.action-buttons .btn').forEach(btn => {
                btn.classList.remove('active');
            });
            loadBrandsBtn.classList.add('active');
            loadBrands();
        });
    }
    
    // Download CSV button
    const downloadScrapingCsvBtn = document.getElementById('download-scraping-csv');
    if (downloadScrapingCsvBtn) {
        downloadScrapingCsvBtn.addEventListener('click', downloadScrapingResults);
    }
    
    // Use for messaging button
    const useBrandsForMessagingBtn = document.getElementById('use-brands-for-messaging');
    if (useBrandsForMessagingBtn) {
        useBrandsForMessagingBtn.addEventListener('click', useBrandsForMessaging);
    }
});

async function handleScrapingSubmit(e) {
    e.preventDefault();
    
    // Set current operation
    currentOperation = 'scraping';
    isCancelled = false;

    const formData = new FormData(e.target);
    const usernames = formData.get('usernames').split(',').map(username => username.trim());
    const maxPosts = parseInt(formData.get('max_posts')) || 50;
    // Get the checked state of the toggle switch
    const forceReset = document.getElementById('force_reset').checked;

    if (usernames.length === 0 || usernames[0] === '') {
        alert('Please enter at least one username.');
        return;
    }

    showLoading(true);
    
    try {
        const response = await fetch(`${SCRAPING_API_URL}/run_workflow`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                usernames: usernames,
                max_posts: maxPosts,
                force_reset: forceReset
            })
        });

        // Check if operation was cancelled during the fetch
        if (isCancelled) {
            console.log('Scraping was cancelled, ignoring response');
            return;
        }

        if (response.ok) {
            const data = await response.json();
            handleScrapingResponse(data);
        } else {
            throw new Error('Scraping request failed');
        }
    } catch (error) {
        if (!isCancelled) { // Only show error if not cancelled
            console.error('Scraping error:', error);
            alert('Scraping failed. Please try again.');
        }
    } finally {
        // Reset operation tracking if not cancelled elsewhere
        if (!isCancelled) {
            currentOperation = null;
            showLoading(false);
        }
    }
}

function handleScrapingResponse(data) {
    console.log('Scraping response:', data);
    
    // Show success message
    alert('Scraping completed successfully!');
    
    // Load the scraped users
    loadScrapedUsers();
}

async function loadScrapedUsers() {
    showLoading(true);
    
    try {
        const response = await fetch(`${SCRAPING_API_URL}/scraped_users`);
        
        if (response.ok) {
            const data = await response.json();
            displayScrapedUsers(data.users);
        } else {
            throw new Error('Failed to load scraped users');
        }
    } catch (error) {
        console.error('Error loading scraped users:', error);
        alert('Failed to load scraped users. Please try again.');
    } finally {
        showLoading(false);
    }
}

function displayScrapedUsers(users) {
    const resultsContainer = document.getElementById('scraping-results');
    const tableContainer = document.getElementById('scraping-results-container');
    
    if (!users || users.length === 0) {
        tableContainer.innerHTML = '<p>No scraped users found.</p>';
        resultsContainer.style.display = 'block';
        return;
    }

    // Store the data for the CSV editor
    scrapingResults = users;
    currentCsvData = users.map(user => ({
        profile_url: `https://www.instagram.com/${user.username}/`,
        username: user.username,
        last_scraped: user.last_scraped || ''
    }));
    
    // Pagination variables
    const entriesPerPage = 10;
    let currentPage = 1;
    const totalPages = Math.ceil(currentCsvData.length / entriesPerPage);
    
    // Hide the "Use for Messaging" button when displaying scraped users
    const useBrandsForMessagingBtn = document.getElementById('use-brands-for-messaging');
    if (useBrandsForMessagingBtn) {
        useBrandsForMessagingBtn.style.display = 'none';
    }
    
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
        const headers = ['Profile URL', 'Username'];
        
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
        
        // Add only the users for the current page
        for (let i = startIndex; i < endIndex; i++) {
            const user = currentCsvData[i];
            const row = document.createElement('tr');
            
            const cells = [
                user.username || '',
                user.last_scraped || ''
            ];
            
            cells.forEach((cellData, index) => {
                const td = document.createElement('td');
                if (index === 0) { // Username column
                    const link = document.createElement('a');
                    link.href = `https://www.instagram.com/${cellData}/`;
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
    
    // Set the tableContainer to have a scrollbar if needed
    tableContainer.style.maxHeight = '500px';
    tableContainer.style.overflowY = 'auto';
    
    // Initial render
    renderPage(currentPage);
    resultsContainer.style.display = 'block';
}

async function loadBrands() {
    showLoading(true);
    
    try {
        const response = await fetch(`${SCRAPING_API_URL}/get_brands`);
        
        if (response.ok) {
            const data = await response.json();
            displayBrands(data.users);
        } else {
            throw new Error('Failed to load brands');
        }
    } catch (error) {
        console.error('Error loading brands:', error);
        alert('Failed to load brands. Please try again.');
    } finally {
        showLoading(false);
    }
}

function displayBrands(brands) {
    const resultsContainer = document.getElementById('scraping-results');
    const tableContainer = document.getElementById('scraping-results-container');
    
    if (!brands || brands.length === 0) {
        tableContainer.innerHTML = '<p>No brands found.</p>';
        resultsContainer.style.display = 'block';
        return;
    }

    // Store the data for the CSV editor
    scrapingResults = brands;
    currentCsvData = brands.map(brand => ({
        profile_url: brand.profile_url || `https://www.instagram.com/${brand.username}/`,
        username: brand.username || ''
    }));
    
    // Show the "Use for Messaging" button when displaying brands
    const useBrandsForMessagingBtn = document.getElementById('use-brands-for-messaging');
    if (useBrandsForMessagingBtn) {
        useBrandsForMessagingBtn.style.display = 'inline-flex';
    }
    
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
        const headers = ['Profile URL', 'Username', 'Mention Count'];
        
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
        
        // Add only the brands for the current page
        for (let i = startIndex; i < endIndex; i++) {
            const brand = currentCsvData[i];
            const row = document.createElement('tr');
            
            const cells = [
                brand.profile_url || '',
                brand.username || '',
                brand.mention_count || '0'
            ];
            
            cells.forEach((cellData, index) => {
                const td = document.createElement('td');
                if (index === 0 && cellData.toString().startsWith('http')) { // Profile URL column
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
    
    // Set the tableContainer to have a scrollbar if needed
    tableContainer.style.maxHeight = '500px';
    tableContainer.style.overflowY = 'auto';
    
    // Initial render
    renderPage(currentPage);
    resultsContainer.style.display = 'block';
}

function downloadScrapingResults() {
    if (!currentCsvData || currentCsvData.length === 0) {
        alert('No scraping results to download.');
        return;
    }

    const csvContent = convertToCSV(currentCsvData);
    const blob = new Blob([csvContent], { type: 'text/csv' });
    const url = window.URL.createObjectURL(blob);
    
    const a = document.createElement('a');
    a.href = url;
    a.download = `scraping_results_${new Date().toISOString().split('T')[0]}.csv`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.URL.revokeObjectURL(url);
}

function useBrandsForMessaging() {
    if (!currentCsvData || currentCsvData.length === 0) {
        alert('No brands available to use for messaging.');
        return;
    }
    
    // Switch to the message tab
    switchTab('message');
    
    // Show loading while we upload the CSV silently
    showLoading(true);
    
    // Convert the brands to CSV format
    const csvContent = convertToCSV(currentCsvData);
    
    // Create a File object from the CSV content
    const filename = `brands_${new Date().toISOString().split('T')[0]}.csv`;
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
            throw new Error('Failed to upload brands');
        }
    })
    .then(data => {
        console.log('Brands uploaded successfully:', data);
        
        // Delay the rest of the process to ensure tab switch completes
        setTimeout(() => {
            // Update CSV status with the actual filename that was uploaded
            const csvStatus = document.getElementById('csv-status');
            csvStatus.className = 'csv-status success';
            csvStatus.textContent = `Using brands: "${filename}" ${currentCsvData.length} profiles loaded`;
            
            // Enable chat input
            enableChatInput();
            
            // Add system message
            addChatMessage('assistant', `Brands loaded! ${currentCsvData.length} profiles are ready for messaging. How would you like to proceed?`);
            
            // Display the View/Edit CSV button
            displayViewEditCsvButton();
            
            // Display the Start button
            displayStartButton();
            
            // Hide loading
            showLoading(false);
        }, 100);
    })
    .catch(error => {
        console.error('Error uploading brands:', error);
        showLoading(false);
        alert('Failed to upload brands. Please try again.');
    });
}

// Add this at the end of the DOMContentLoaded event listener
document.addEventListener('DOMContentLoaded', () => {
    // Toggle switch functionality
    const forceResetToggle = document.getElementById('force_reset');
    const toggleLabel = forceResetToggle.parentElement.nextElementSibling;
    
    if (forceResetToggle) {
        forceResetToggle.addEventListener('change', function() {
            toggleLabel.textContent = this.checked ? 'On' : 'Off';
        });
    }
});
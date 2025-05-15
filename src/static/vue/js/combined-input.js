/**
 * Combined Input Methods JavaScript
 * Handles file upload, text paste, and URL input for citation analysis
 */

// Global state to track processing status
window.citationProcessing = {
    isProcessing: false,
    analysisId: null,
    startTime: null,
    totalCitations: 0,
    processedCitations: 0,
    progressInterval: null
};

document.addEventListener('DOMContentLoaded', function() {
    console.log('DOMContentLoaded event fired - initializing CaseStrainer JS');
    
    // Always use the /casestrainer/ prefix for API calls to work with Nginx proxy
    const basePath = window.location.pathname.includes('/casestrainer/') ? '/casestrainer' : '';
    console.log('Base path for API calls:', basePath);
    
    // Get form elements
    const uploadForm = document.getElementById('uploadForm');
    const pasteForm = document.getElementById('pasteForm');
    const urlForm = document.getElementById('urlForm');
    
    // Get input option elements
    const inputOptions = document.querySelectorAll('.input-option');
    const inputPanels = document.querySelectorAll('.input-panel');
    const closePanelButtons = document.querySelectorAll('.close-panel');
    
    // Handle input option selection
    inputOptions.forEach(option => {
        option.addEventListener('click', function() {
            const target = this.getAttribute('data-target');
            
            // Remove active class from all options
            inputOptions.forEach(opt => opt.classList.remove('active'));
            
            // Add active class to clicked option
            this.classList.add('active');
            
            // Hide all panels
            inputPanels.forEach(panel => panel.classList.remove('active'));
            
            // Show the selected panel
            document.getElementById(`${target}-panel`).classList.add('active');
        });
    });
    
    // Handle close panel buttons
    closePanelButtons.forEach(button => {
        button.addEventListener('click', function() {
            // Hide all panels
            inputPanels.forEach(panel => panel.classList.remove('active'));
            
            // Remove active class from all options
            inputOptions.forEach(opt => opt.classList.remove('active'));
        });
    });
    
    // Progress elements
    const uploadProgress = document.getElementById('uploadProgress');
    const uploadProgressBar = document.getElementById('uploadProgressBar');
    const pasteProgress = document.getElementById('pasteProgress');
    const pasteProgressBar = document.getElementById('pasteProgressBar');
    const urlProgress = document.getElementById('urlProgress');
    const urlProgressBar = document.getElementById('urlProgressBar');
    
    // Function to update progress bar
    function updateProgressBar(progressBar, progress) {
        progressBar.style.width = `${progress}%`;
        progressBar.setAttribute('aria-valuenow', progress);
        progressBar.textContent = `${progress}%`;
    }
    
    // Function to start progress polling
    function startProgressPolling(progressElement, progressBar) {
        // Show progress bar
        progressElement.style.display = 'block';
        
        // Reset progress
        updateProgressBar(progressBar, 0);
        
        // Initialize progress tracking
        window.citationProcessing = {
            isProcessing: true,
            startTime: new Date(),
            totalCitations: 100, // Default estimate
            processedCitations: 0,
            progressInterval: null
        };
        
        // Start progress polling
        const progressInterval = setInterval(() => {
            fetch(`${basePath}/api/processing_progress?total=${window.citationProcessing.totalCitations}`, {
                method: 'GET'
            })
            .then(response => response.json())
            .then(data => {
                if (data.status === 'success') {
                    window.citationProcessing.processedCitations = data.processed_citations;
                    
                    // Calculate progress percentage
                    const progress = data.total_citations > 0 ? 
                        Math.min(Math.round((data.processed_citations / data.total_citations) * 100), 100) : 0;
                    
                    // Update progress bar
                    updateProgressBar(progressBar, progress);
                    
                    // Check if processing is complete
                    if (data.is_complete) {
                        clearInterval(progressInterval);
                        window.citationProcessing.isProcessing = false;
                        progressBar.className = 'progress-bar bg-success';
                        progressBar.textContent = 'Complete!';
                        
                        // Switch to the appropriate results tab
                        switchToResultsTab();
                    }
                }
            })
            .catch(error => {
                console.error('Error checking progress:', error);
                clearInterval(progressInterval);
                progressBar.className = 'progress-bar bg-danger';
                progressBar.textContent = 'Error';
            });
        }, 1000);
        
        return progressInterval;
    }
    
    // Function to switch to the results tab
    function switchToResultsTab() {
        // First try CourtListener Citations tab
        const clCitationsTab = document.getElementById('cl-citations-tab');
        if (clCitationsTab) {
            clCitationsTab.click();
            return;
        }
        
        // Fall back to Verified Citations tab
        const multitoolTab = document.getElementById('multitool-tab');
        if (multitoolTab) {
            multitoolTab.click();
        }
    }
    
    // Create a results container for displaying citation results
    function createResultsContainer() {
        // Check if results container already exists
        let resultsContainer = document.getElementById('citation-results-container');
        if (!resultsContainer) {
            resultsContainer = document.createElement('div');
            resultsContainer.id = 'citation-results-container';
            resultsContainer.className = 'mt-5';
            document.querySelector('.input-panels').after(resultsContainer);
        }
        return resultsContainer;
    }
    
    // Display citation results
    function displayCitationResults(data) {
        const resultsContainer = createResultsContainer();
        
        // Create results HTML
        let html = `
            <div class="card mb-4 shadow-sm">
                <div class="card-header bg-primary text-white">
                    <h3 class="mb-0">Citation Analysis Results</h3>
                </div>
                <div class="card-body">
                    <div class="alert alert-success">
                        <i class="bi bi-check-circle-fill me-2"></i>
                        ${data.message}
                    </div>
                    <h4>Found Citations:</h4>
                    <div class="table-responsive">
                        <table class="table table-striped">
                            <thead>
                                <tr>
                                    <th>Citation</th>
                                    <th>Case Name</th>
                                    <th>Status</th>
                                </tr>
                            </thead>
                            <tbody>
        `;
        
        // Add each citation to the table
        data.citations.forEach(citation => {
            html += `
                <tr>
                    <td><strong>${citation.text}</strong></td>
                    <td>${citation.name}</td>
                    <td>
                        ${citation.valid ? 
                            '<span class="badge bg-success">Valid</span>' : 
                            '<span class="badge bg-danger">Invalid</span>'}
                    </td>
                </tr>
            `;
        });
        
        html += `
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        `;
        
        resultsContainer.innerHTML = html;
        
        // Scroll to results
        resultsContainer.scrollIntoView({ behavior: 'smooth' });
    }
    
    // Add immediate debug logging
    console.log('Document loaded, checking for uploadForm:', uploadForm ? 'Found' : 'Not found');
    if (uploadForm) {
        console.log('Adding event listener to uploadForm');
    } else {
        console.error('ERROR: uploadForm not found! DOM might not be properly loaded or form ID is incorrect');
        // Try to find the form by other means
        const possibleForms = document.querySelectorAll('form');
        console.log(`Found ${possibleForms.length} forms on the page:`);
        possibleForms.forEach((form, i) => {
            console.log(`Form ${i+1} ID: ${form.id}, Action: ${form.action}`);
        });
    }
    
    // Handle file upload form submission
    if (uploadForm) {
        uploadForm.addEventListener('submit', function(e) {
            console.log('Upload form submit event triggered!');
            e.preventDefault();
            
            const submitButton = this.querySelector('button[type="submit"]');
            const fileInput = document.getElementById('fileUpload');
            
            // Disable button during processing
            submitButton.disabled = true;
            submitButton.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Processing...';
            
            // Show progress bar
            const progressElement = document.getElementById('uploadProgress');
            const progressBar = document.getElementById('uploadProgressBar');
            
            // Start progress polling
            const progressInterval = startProgressPolling(progressElement, progressBar);
            
            // Create form data
            const formData = new FormData();
            const file = fileInput.files[0];
            formData.append('file', file);
            
            // Create debug div
            const debugDiv = document.createElement('div');
            debugDiv.className = 'alert alert-info mt-3';
            debugDiv.innerHTML = `<h5>Debug Information</h5>`;
            progressElement.parentNode.insertBefore(debugDiv, progressElement);
            
            // Function to add debug info
            function addDebugInfo(message) {
                const timestamp = new Date().toISOString();
                console.log(`[${timestamp}] ${message}`);
                const msgElement = document.createElement('p');
                msgElement.textContent = `[${timestamp}] ${message}`;
                debugDiv.appendChild(msgElement);
            }
            
            // Log file details for debugging
            addDebugInfo(`File upload initiated: ${file.name} (${file.size} bytes, ${file.type})`);
            
            // Send request to API
            addDebugInfo(`Sending file to ${basePath}/api/upload endpoint...`);
            fetch(`${basePath}/api/upload`, {
                method: 'POST',
                body: formData
            })
            .then(response => {
                // Log response details
                const responseInfo = {
                    status: response.status,
                    statusText: response.statusText,
                    headers: Object.fromEntries([...response.headers]),
                    timestamp: new Date().toISOString()
                };
                
                addDebugInfo(`Response received: ${response.status} ${response.statusText}`);
                addDebugInfo(`Content-Type: ${response.headers.get('Content-Type')}`);
                
                if (!response.ok) {
                    addDebugInfo(`ERROR: Server returned error status: ${response.status}`);
                    throw new Error(`Server responded with status: ${response.status}`);
                }
                
                addDebugInfo('Response OK, parsing JSON...');
                return response.json().catch(error => {
                    addDebugInfo(`ERROR: Failed to parse JSON response: ${error.message}`);
                    throw error;
                });
            })
            .then(data => {
                addDebugInfo('JSON parsed successfully!');
                addDebugInfo(`Found ${data.citations ? data.citations.length : 0} citations`);
                
                // Re-enable button
                submitButton.disabled = false;
                submitButton.innerHTML = '<i class="bi bi-upload me-2"></i>Upload and Verify';
                
                // Clear progress polling
                clearInterval(progressInterval);
                
                // Update progress to complete
                progressBar.style.width = '100%';
                progressBar.setAttribute('aria-valuenow', 100);
                progressBar.textContent = 'Complete!';
                progressBar.className = 'progress-bar bg-success';
                
                // Add more detailed debug info
                if (data.citations && data.citations.length > 0) {
                    addDebugInfo('Citation details:');
                    data.citations.forEach((citation, index) => {
                        addDebugInfo(`Citation ${index+1}: ${citation.text} (${citation.name})`);
                    });
                } else {
                    addDebugInfo('No citations found in the document.');
                }
                
                // Display results
                displayCitationResults(data);
            })
            .catch(error => {
                // Log error details
                const errorInfo = {
                    message: error.message,
                    stack: error.stack,
                    timestamp: new Date().toISOString()
                };
                console.error('File upload error:', errorInfo);
                
                // Add debug information
                addDebugInfo(`ERROR: ${error.message}`);
                addDebugInfo(`Error occurred at: ${new Date().toISOString()}`);
                
                // Try to get more details about the error
                if (error.name) addDebugInfo(`Error type: ${error.name}`);
                if (error.stack) {
                    const stackLines = error.stack.split('\n');
                    addDebugInfo(`Stack trace (first line): ${stackLines[0]}`);
                }
                
                submitButton.disabled = false;
                submitButton.innerHTML = '<i class="bi bi-upload me-2"></i>Upload and Verify';
                
                // Clear progress polling
                clearInterval(progressInterval);
                
                // Update progress to error
                progressBar.style.width = '100%';
                progressBar.setAttribute('aria-valuenow', 100);
                progressBar.textContent = 'Error!';
                progressBar.className = 'progress-bar bg-danger';
                
                // Create a more detailed error message
                const errorDetails = document.createElement('div');
                errorDetails.className = 'alert alert-danger mt-3';
                errorDetails.innerHTML = `
                    <h5>Error Processing File</h5>
                    <p>${error.message || 'Unknown error occurred'}</p>
                    <p>Please check the debug information above for more details.</p>
                    <p>Try using a different file format or a smaller file.</p>
                `;
                
                // Insert error details after the progress bar
                progressElement.parentNode.insertBefore(errorDetails, progressElement.nextSibling);
                
                // Add troubleshooting tips
                addDebugInfo('Troubleshooting tips:');
                addDebugInfo('1. Try a different file format (PDF, DOCX, TXT)');
                addDebugInfo('2. Make sure the file contains legal citations');
                addDebugInfo('3. Try a smaller file size');
                addDebugInfo('4. Check if the server is running properly');
            });
            
            // This section is now handled by the validation and API call above
        });
    }
    
    // Handle paste text form submission
    if (pasteForm) {
        pasteForm.addEventListener('submit', function(e) {
            e.preventDefault();
            
            const submitButton = this.querySelector('button[type="submit"]');
            const textArea = document.getElementById('textInput');
            
            // Validate input
            if (!textArea.value.trim()) {
                alert('Please enter text containing citations');
                return;
            }
            
            // Disable button during processing
            submitButton.disabled = true;
            submitButton.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Analyzing...';
            
            // Show progress bar
            const progressElement = document.getElementById('pasteProgress');
            const progressBar = document.getElementById('pasteProgressBar');
            
            // Start progress polling
            const progressInterval = startProgressPolling(progressElement, progressBar);
            
            // Send request to API
            fetch(`${basePath}/api/text`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    text: textArea.value
                })
            })
            .then(response => response.json())
            .then(data => {
                // Re-enable button
                submitButton.disabled = false;
                submitButton.innerHTML = '<i class="bi bi-check-circle me-2"></i>Verify Citations';
                
                // Clear progress polling
                clearInterval(progressInterval);
                
                // Update progress to complete
                progressBar.style.width = '100%';
                progressBar.setAttribute('aria-valuenow', 100);
                progressBar.textContent = 'Complete!';
                progressBar.className = 'progress-bar bg-success';
                
                // Display results
                displayCitationResults(data);
            })
            .catch(error => {
                console.error('Error:', error);
                submitButton.disabled = false;
                submitButton.innerHTML = '<i class="bi bi-check-circle me-2"></i>Verify Citations';
                
                // Clear progress polling
                clearInterval(progressInterval);
                
                // Update progress to error
                progressBar.style.width = '100%';
                progressBar.setAttribute('aria-valuenow', 100);
                progressBar.textContent = 'Error!';
                progressBar.className = 'progress-bar bg-danger';
                
                alert('An error occurred while analyzing your text. Please try again.');
            });
        });
    }
    
    // Handle URL form submission
    if (urlForm) {
        urlForm.addEventListener('submit', function(e) {
            e.preventDefault();
            
            const submitButton = this.querySelector('button[type="submit"]');
            const urlInput = document.getElementById('urlInput');
            
            // Validate input
            if (!urlInput.value.trim()) {
                alert('Please enter a valid URL');
                return;
            }
            
            // Disable button during processing
            submitButton.disabled = true;
            submitButton.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Analyzing...';
            
            // Show progress bar
            const progressElement = document.getElementById('urlProgress');
            const progressBar = document.getElementById('urlProgressBar');
            
            // Start progress polling
            const progressInterval = startProgressPolling(progressElement, progressBar);
            
            // Send request to API
            fetch(`${basePath}/api/url`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    url: urlInput.value
                })
            })
            .then(response => response.json())
            .then(data => {
                // Re-enable button
                submitButton.disabled = false;
                submitButton.innerHTML = '<i class="bi bi-globe me-2"></i>Fetch and Verify';
                
                // Clear progress polling
                clearInterval(progressInterval);
                
                // Update progress to complete
                progressBar.style.width = '100%';
                progressBar.setAttribute('aria-valuenow', 100);
                progressBar.textContent = 'Complete!';
                progressBar.className = 'progress-bar bg-success';
                
                // Display results
                displayCitationResults(data);
            })
            .catch(error => {
                console.error('Error:', error);
                submitButton.disabled = false;
                submitButton.innerHTML = '<i class="bi bi-globe me-2"></i>Fetch and Verify';
                
                // Clear progress polling
                clearInterval(progressInterval);
                
                // Update progress to error
                progressBar.style.width = '100%';
                progressBar.setAttribute('aria-valuenow', 100);
                progressBar.textContent = 'Error!';
                progressBar.className = 'progress-bar bg-danger';
                
                alert('An error occurred while analyzing the URL content. Please try again.');
            });
            
            // This section is now handled by the validation and API call above
        });
    }
    
    // Add direct event listeners to all submit buttons as a backup
    console.log('Adding direct event listeners to submit buttons');
    document.querySelectorAll('button[type="submit"]').forEach((button, index) => {
        console.log(`Found submit button ${index+1}: ${button.textContent.trim()}`);
        button.addEventListener('click', function(e) {
            console.log(`Button clicked: ${this.textContent.trim()}`);
            // Don't prevent default here, let the form handler do that
        });
    });
    
    // Add a manual file upload function as a last resort
    window.manualFileUpload = function() {
        console.log('Manual file upload function called');
        const fileInput = document.getElementById('fileUpload');
        if (!fileInput || !fileInput.files || !fileInput.files[0]) {
            console.error('No file selected or file input not found');
            alert('Please select a file first');
            return;
        }
        
        const file = fileInput.files[0];
        console.log(`Manually uploading file: ${file.name} (${file.size} bytes)`);
        
        const formData = new FormData();
        formData.append('file', file);
        
        fetch(`${basePath}/api/upload`, {
            method: 'POST',
            body: formData
        })
        .then(response => response.json())
        .then(data => {
            console.log('File upload successful:', data);
            alert(`File processed successfully! Found ${data.citations ? data.citations.length : 0} citations.`);
        })
        .catch(error => {
            console.error('Manual file upload error:', error);
            alert(`Error: ${error.message}`);
        });
    };
    
    // Add a manual upload button to the page
    const filePanel = document.getElementById('file-panel');
    if (filePanel) {
        const manualButton = document.createElement('button');
        manualButton.type = 'button';
        manualButton.className = 'btn btn-warning mt-2';
        manualButton.textContent = 'Manual Upload (Debug)';
        manualButton.onclick = window.manualFileUpload;
        filePanel.appendChild(manualButton);
        console.log('Added manual upload button to the page');
    }
});

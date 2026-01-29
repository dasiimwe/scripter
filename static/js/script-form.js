document.addEventListener('DOMContentLoaded', function() {
    // Copy to clipboard functionality
    const copyButton = document.getElementById('copy-output');
    if (copyButton) {
        copyButton.addEventListener('click', function() {
            const outputArea = document.querySelector('.output-area');
            const outputText = outputArea.innerText || outputArea.textContent;
            
            // Create a temporary textarea element to copy from
            const textarea = document.createElement('textarea');
            textarea.value = outputText;
            textarea.setAttribute('readonly', '');
            textarea.style.position = 'absolute';
            textarea.style.left = '-9999px';
            document.body.appendChild(textarea);
            
            // Select and copy the text
            textarea.select();
            document.execCommand('copy');
            
            // Remove the temporary element
            document.body.removeChild(textarea);
            
            // Show feedback
            const originalText = this.innerHTML;
            this.innerHTML = '<span class="icon"><i class="fas fa-check"></i></span><span>Copied!</span>';
            
            setTimeout(() => {
                this.innerHTML = originalText;
            }, 2000);
        });
    }
    
    // Handle conditional fields
    const formFields = document.querySelectorAll('#script-form input, #script-form select, #script-form textarea');
    
    formFields.forEach(field => {
        field.addEventListener('change', updateConditionalFields);
    });
    
    function updateConditionalFields() {
        const conditionalFields = document.querySelectorAll('[data-condition]');
        
        conditionalFields.forEach(field => {
            const condition = field.getAttribute('data-condition');
            const fieldContainer = field.closest('.field-col');
            
            if (evaluateCondition(condition)) {
                fieldContainer.style.display = '';
            } else {
                fieldContainer.style.display = 'none';
            }
        });
    }
    
    function evaluateCondition(condition) {
        // Simple condition evaluation - can be expanded for more complex logic
        if (!condition) return true;
        
        const parts = condition.split('=');
        if (parts.length !== 2) return true;
        
        const fieldName = parts[0].trim();
        const expectedValue = parts[1].trim().replace(/['"]/g, '');
        
        const field = document.querySelector(`[name="${fieldName}"]`);
        if (!field) return true;
        
        if (field.type === 'checkbox') {
            return field.checked === (expectedValue.toLowerCase() === 'true');
        } else if (field.type === 'radio') {
            const checkedRadio = document.querySelector(`[name="${fieldName}"]:checked`);
            return checkedRadio && checkedRadio.value === expectedValue;
        } else {
            return field.value === expectedValue;
        }
    }
    
    // Run once on page load to set initial state
    updateConditionalFields();

    // Auto-save functionality
    let autoSaveTimeout;
    const form = document.getElementById('script-form');
    const scriptId = window.location.pathname.split('/')[2]; // Extract script ID from URL

    // Function to save form data
    function saveFormDraft() {
        const formData = new FormData(form);
        const data = {};
        for (let [key, value] of formData.entries()) {
            data[key] = value;
        }
        
        console.log('Saving form data:', data); // Debug log
        
        fetch(`/scripts/${scriptId}/save-draft`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content
            },
            body: JSON.stringify(data)
        })
        .then(response => {
            console.log('Save response status:', response.status); // Debug log
            return response.json();
        })
        .then(data => {
            console.log('Save response data:', data); // Debug log
            if (data.status === 'success') {
                // Show a subtle notification
                const notification = document.createElement('div');
                notification.className = 'notification is-info is-light is-small';
                notification.style.position = 'fixed';
                notification.style.bottom = '1rem';
                notification.style.right = '1rem';
                notification.style.zIndex = '1000';
                notification.innerHTML = 'Draft saved';
                document.body.appendChild(notification);
                
                // Remove notification after 2 seconds
                setTimeout(() => {
                    notification.remove();
                }, 2000);
            }
        })
        .catch(error => {
            console.error('Error saving draft:', error); // Debug log
        });
    }

    // Add input event listeners to all form fields
    const formInputs = form.querySelectorAll('input, select, textarea');
    formInputs.forEach(field => {
        field.addEventListener('input', () => {
            // Clear existing timeout
            clearTimeout(autoSaveTimeout);
            // Set new timeout
            autoSaveTimeout = setTimeout(saveFormDraft, 1000);
        });
    });

    // Load draft functionality
    const loadDraftButton = document.getElementById('load-draft');
    if (loadDraftButton) {
        loadDraftButton.addEventListener('click', () => {
            console.log('Load draft button clicked'); // Debug log
            
            fetch(`/scripts/${scriptId}/load-draft`)
                .then(response => {
                    console.log('Response status:', response.status); // Debug log
                    return response.json();
                })
                .then(data => {
                    console.log('Received data:', data); // Debug log
                    
                    if (data.status === 'success' && data.data) {
                        // Fill form with saved values
                        Object.entries(data.data).forEach(([key, value]) => {
                            const field = form.querySelector(`[name="${key}"]`);
                            console.log(`Setting field ${key} to value:`, value); // Debug log
                            
                            if (field) {
                                if (field.type === 'checkbox') {
                                    field.checked = value === 'true';
                                } else if (field.type === 'radio') {
                                    const radio = form.querySelector(`[name="${key}"][value="${value}"]`);
                                    if (radio) radio.checked = true;
                                } else if (field.tagName === 'SELECT') {
                                    // Handle select elements
                                    const option = field.querySelector(`option[value="${value}"]`);
                                    if (option) {
                                        field.value = value;
                                    }
                                } else {
                                    field.value = value;
                                }
                            } else {
                                console.log(`Field not found: ${key}`); // Debug log
                            }
                        });
                        
                        // Show success notification
                        const notification = document.createElement('div');
                        notification.className = 'notification is-success is-light';
                        notification.innerHTML = 'Saved values loaded';
                        document.body.appendChild(notification);
                        
                        // Remove notification after 2 seconds
                        setTimeout(() => {
                            notification.remove();
                        }, 2000);
                    } else {
                        // Show no draft found notification
                        const notification = document.createElement('div');
                        notification.className = 'notification is-warning is-light';
                        notification.innerHTML = 'No saved values found';
                        document.body.appendChild(notification);
                        
                        // Remove notification after 2 seconds
                        setTimeout(() => {
                            notification.remove();
                        }, 2000);
                    }
                })
                .catch(error => {
                    console.error('Error loading draft:', error); // Debug log
                    
                    // Show error notification
                    const notification = document.createElement('div');
                    notification.className = 'notification is-danger is-light';
                    notification.innerHTML = 'Error loading saved values';
                    document.body.appendChild(notification);
                    
                    // Remove notification after 2 seconds
                    setTimeout(() => {
                        notification.remove();
                    }, 2000);
                });
        });
    }

    // Load previous submissions functionality
    const loadSubmissionSelect = document.getElementById('load-submission');
    if (loadSubmissionSelect) {
        // Fetch previous submissions when the page loads
        fetch(`/scripts/${scriptId}/submissions`)
            .then(response => response.json())
            .then(data => {
                // Add submissions to the dropdown
                data.submissions.forEach(submission => {
                    const option = document.createElement('option');
                    option.value = submission.id;
                    option.textContent = `Submission from ${submission.date}`;
                    option.dataset.values = JSON.stringify(submission.values);
                    loadSubmissionSelect.appendChild(option);
                });
            })
            .catch(error => {
                console.error('Error loading submissions:', error);
            });

        // Handle submission selection
        loadSubmissionSelect.addEventListener('change', function() {
            const selectedOption = this.options[this.selectedIndex];
            if (selectedOption.value) {
                const values = JSON.parse(selectedOption.dataset.values);
                
                // Fill form with selected submission values
                Object.entries(values).forEach(([key, value]) => {
                    const field = form.querySelector(`[name="${key}"]`);
                    if (field) {
                        if (field.type === 'checkbox') {
                            field.checked = value === 'true';
                        } else if (field.type === 'radio') {
                            const radio = form.querySelector(`[name="${key}"][value="${value}"]`);
                            if (radio) radio.checked = true;
                        } else if (field.tagName === 'SELECT') {
                            const option = field.querySelector(`option[value="${value}"]`);
                            if (option) {
                                field.value = value;
                            }
                        } else {
                            field.value = value;
                        }
                    }
                });

                // Show success notification
                const notification = document.createElement('div');
                notification.className = 'notification is-success is-light';
                notification.innerHTML = 'Previous submission loaded';
                document.body.appendChild(notification);
                
                // Remove notification after 2 seconds
                setTimeout(() => {
                    notification.remove();
                }, 2000);

                // Reset the dropdown
                this.value = '';
            }
        });
    }
}); 
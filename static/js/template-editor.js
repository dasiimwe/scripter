document.addEventListener('DOMContentLoaded', function() {
    // Initialize CodeMirror
    var editor = CodeMirror.fromTextArea(document.getElementById('template-editor'), {
        mode: 'jinja2',
        theme: 'monokai',
        lineNumbers: true,
        lineWrapping: true,
        indentUnit: 4
    });
    
    // Track if content has changed
    let hasUnsavedChanges = false;
    let originalContent = editor.getValue();
    
    // Set up change tracking
    editor.on('change', function() {
        hasUnsavedChanges = (originalContent !== editor.getValue());
    });
    
    // Add confirmation to navigation links
    const navigationLinks = document.querySelectorAll('.tabs:not(.template-tabs) a');
    navigationLinks.forEach(link => {
        link.addEventListener('click', function(e) {
            if (hasUnsavedChanges) {
                e.preventDefault();
                if (confirm('You have unsaved changes. Are you sure you want to leave this page?')) {
                    window.location.href = this.href;
                }
            }
        });
    });
    
    // Reset unsaved changes flag when form is submitted
    document.querySelector('form').addEventListener('submit', function() {
        hasUnsavedChanges = false;
    });
    
    // Tab switching
    const tabLinks = document.querySelectorAll('.template-tabs a');
    const tabContents = document.querySelectorAll('.tab-content');
    
    tabLinks.forEach(link => {
        link.addEventListener('click', function(e) {
            e.preventDefault();
            
            // Remove active class from all tabs
            tabLinks.forEach(tab => {
                tab.parentElement.classList.remove('is-active');
            });
            
            // Add active class to clicked tab
            this.parentElement.classList.add('is-active');
            
            // Hide all tab contents
            tabContents.forEach(content => {
                content.style.display = 'none';
            });
            
            // Show the selected tab content
            const targetId = this.getAttribute('data-target');
            document.getElementById(targetId).style.display = 'block';
            
            // Refresh CodeMirror if showing editor tab
            if (targetId === 'editor-tab') {
                editor.refresh();
            }
        });
    });
    
    // Dropdown toggle
    const dropdown = document.getElementById('snippet-dropdown');
    dropdown.addEventListener('click', function(event) {
        event.stopPropagation();
        dropdown.classList.toggle('is-active');
    });
    
    // Close dropdown when clicking outside
    document.addEventListener('click', function() {
        dropdown.classList.remove('is-active');
    });
    
    // Handle snippet insertion
    const snippetItems = document.querySelectorAll('.snippet-item');
    snippetItems.forEach(item => {
        item.addEventListener('click', function(e) {
            e.preventDefault();
            
            const snippet = this.getAttribute('data-snippet');
            
            // Insert snippet at cursor position
            const cursor = editor.getCursor();
            editor.replaceRange(snippet, cursor);
            
            // Focus back on editor
            editor.focus();
            
            // Close dropdown
            dropdown.classList.remove('is-active');
            
            // Try to position cursor at the "condition" part if it exists
            const lines = snippet.split('\n');
            const firstLine = lines[0];
            const conditionMatch = firstLine.match(/{%\s*if\s+(.*?)\s*%}/);
            
            if (conditionMatch) {
                const conditionStart = firstLine.indexOf(conditionMatch[1]);
                const conditionEnd = conditionStart + conditionMatch[1].length;
                
                editor.setCursor({
                    line: cursor.line,
                    ch: cursor.ch + conditionStart
                });
                
                editor.setSelection(
                    {line: cursor.line, ch: cursor.ch + conditionStart},
                    {line: cursor.line, ch: cursor.ch + conditionEnd}
                );
            }
        });
    });
    
    // Detect variables button
    const scriptId = document.getElementById('script-id').value;
    document.getElementById('detect-variables').addEventListener('click', function() {
        const templateContent = editor.getValue();
        
        fetch(`/api/scripts/${scriptId}/detect_variables`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ template_content: templateContent })
        })
        .then(response => response.json())
        .then(data => {
            const existingTagsContainer = document.getElementById('existing-variable-tags');
            const newTagsContainer = document.getElementById('new-variable-tags');
            const existingSection = document.getElementById('existing-variables-section');
            const newSection = document.getElementById('new-variables-section');
            
            // Clear containers
            existingTagsContainer.innerHTML = '';
            newTagsContainer.innerHTML = '';
            
            if (data.variables && data.variables.length > 0) {
                // Handle existing variables
                if (data.existing_variables && data.existing_variables.length > 0) {
                    data.existing_variables.forEach(variable => {
                        const tag = document.createElement('span');
                        tag.className = 'tag is-success is-medium';
                        tag.textContent = variable;
                        tag.title = 'Already exists as form field';
                        existingTagsContainer.appendChild(tag);
                    });
                    existingSection.style.display = 'block';
                } else {
                    existingSection.style.display = 'none';
                }
                
                // Handle new variables
                if (data.new_variables && data.new_variables.length > 0) {
                    data.new_variables.forEach(variable => {
                        const tag = document.createElement('span');
                        tag.className = 'tag is-info is-medium variable-tag';
                        tag.textContent = variable;
                        tag.setAttribute('data-variable', variable);
                        tag.title = 'Click to add as form field';
                        tag.addEventListener('click', function() {
                            addVariableAsField(variable);
                        });
                        newTagsContainer.appendChild(tag);
                    });
                    newSection.style.display = 'block';
                } else {
                    // Show a message if no new variables
                    const noNewVarsTag = document.createElement('span');
                    noNewVarsTag.className = 'tag is-light is-medium';
                    noNewVarsTag.textContent = 'All variables already have form fields';
                    newTagsContainer.appendChild(noNewVarsTag);
                    newSection.style.display = 'block';
                }
                
                document.getElementById('detected-variables').classList.remove('is-hidden');
            } else {
                // No variables detected at all
                const noVarsTag = document.createElement('span');
                noVarsTag.className = 'tag is-warning is-medium';
                noVarsTag.textContent = 'No variables detected';
                newTagsContainer.appendChild(noVarsTag);
                
                existingSection.style.display = 'none';
                newSection.style.display = 'block';
                document.getElementById('detected-variables').classList.remove('is-hidden');
            }
        })
        .catch(error => {
            console.error('Error detecting variables:', error);
        });
    });
    
    // Add all fields button (only for new variables)
    document.getElementById('add-all-fields').addEventListener('click', function() {
        const newVariableTags = document.querySelectorAll('#new-variable-tags .variable-tag');
        if (newVariableTags.length === 0) {
            alert('No new variables to add');
            return;
        }
        
        // Save the template first
        const form = document.querySelector('form');
        const formData = new FormData(form);
        
        // Update the template content with the current editor value
        formData.set('content', editor.getValue());
        
        // Save template changes via form submission
        fetch(form.action, {
            method: 'POST',
            body: formData
        })
        .then(response => {
            if (response.ok) {
                // Reset the unsaved changes flag after successful save
                hasUnsavedChanges = false;
                originalContent = editor.getValue();
                
                // After template is saved, add all the new fields
                let addPromises = [];
                newVariableTags.forEach(tag => {
                    const variable = tag.getAttribute('data-variable');
                    addPromises.push(addVariableAsFieldWithoutReload(variable));
                });
                
                // Wait for all fields to be added, then reload
                Promise.all(addPromises).then(() => {
                    location.reload();
                });
            } else {
                alert('Failed to save template changes');
            }
        })
        .catch(error => {
            console.error('Error saving template:', error);
            alert('Error saving template changes');
        });
    });
    
    // Function to add a variable as a form field without reloading
    function addVariableAsFieldWithoutReload(variable) {
        return fetch(`/api/scripts/${scriptId}/add_variable_field`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ variable_name: variable })
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                // Remove the variable from the new variables section
                const newVariableTag = document.querySelector(`#new-variable-tags .variable-tag[data-variable="${variable}"]`);
                if (newVariableTag) {
                    newVariableTag.remove();
                }
                
                // Add to existing variables section
                const existingTagsContainer = document.getElementById('existing-variable-tags');
                const existingSection = document.getElementById('existing-variables-section');
                
                const tag = document.createElement('span');
                tag.className = 'tag is-success is-medium';
                tag.textContent = variable;
                tag.title = 'Already exists as form field';
                existingTagsContainer.appendChild(tag);
                
                // Show existing section if it was hidden
                existingSection.style.display = 'block';
                
                // Check if no more new variables left
                const remainingNewTags = document.querySelectorAll('#new-variable-tags .variable-tag');
                if (remainingNewTags.length === 0) {
                    const newTagsContainer = document.getElementById('new-variable-tags');
                    newTagsContainer.innerHTML = '<span class="tag is-light is-medium">All variables already have form fields</span>';
                }
                
                return true;
            } else {
                console.error('Failed to add field:', data.error);
                return false;
            }
        })
        .catch(error => {
            console.error('Error adding field:', error);
            return false;
        });
    }
    
    // Function to add a variable as a form field (with reload for single additions)
    function addVariableAsField(variable) {
        // Save the template first when adding individual fields
        const form = document.querySelector('form');
        const formData = new FormData(form);
        
        // Update the template content with the current editor value
        formData.set('content', editor.getValue());
        
        // Save template changes via form submission
        fetch(form.action, {
            method: 'POST',
            body: formData
        })
        .then(response => {
            if (response.ok) {
                // Reset the unsaved changes flag after successful save
                hasUnsavedChanges = false;
                originalContent = editor.getValue();
                
                // After template is saved, add the field
                return addVariableAsFieldWithoutReload(variable);
            } else {
                throw new Error('Failed to save template changes');
            }
        })
        .then(success => {
            if (success) {
                // Reload after a short delay to show the update
                setTimeout(() => {
                    location.reload();
                }, 500);
            } else {
                alert('Failed to add field');
            }
        })
        .catch(error => {
            console.error('Error:', error);
            alert('Error: ' + error.message);
        });
    }
    
    // Add beforeunload event to catch browser/tab closing
    window.addEventListener('beforeunload', function(e) {
        if (hasUnsavedChanges) {
            // Standard way of showing a confirmation dialog before leaving the page
            e.preventDefault();
            // Most browsers will ignore this message and show their own standard message
            e.returnValue = 'You have unsaved changes. Are you sure you want to leave?';
            return e.returnValue;
        }
    });
}); 
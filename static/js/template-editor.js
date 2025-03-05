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
            const variableTagsContainer = document.getElementById('variable-tags');
            variableTagsContainer.innerHTML = '';
            
            if (data.variables && data.variables.length > 0) {
                data.variables.forEach(variable => {
                    const tag = document.createElement('span');
                    tag.className = 'tag is-info is-medium variable-tag';
                    tag.textContent = variable;
                    tag.setAttribute('data-variable', variable);
                    tag.addEventListener('click', function() {
                        addVariableAsField(variable);
                    });
                    variableTagsContainer.appendChild(tag);
                });
                
                document.getElementById('detected-variables').classList.remove('is-hidden');
            } else {
                const noVarsTag = document.createElement('span');
                noVarsTag.className = 'tag is-warning is-medium';
                noVarsTag.textContent = 'No variables detected';
                variableTagsContainer.appendChild(noVarsTag);
                
                document.getElementById('detected-variables').classList.remove('is-hidden');
            }
        })
        .catch(error => {
            console.error('Error detecting variables:', error);
        });
    });
    
    // Add all fields button
    document.getElementById('add-all-fields').addEventListener('click', function() {
        const variableTags = document.querySelectorAll('.variable-tag');
        variableTags.forEach(tag => {
            const variable = tag.getAttribute('data-variable');
            addVariableAsField(variable);
        });
    });
    
    // Function to add a variable as a form field
    function addVariableAsField(variable) {
        fetch(`/api/scripts/${scriptId}/add_variable_field`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ variable_name: variable })
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                // Change the tag color to indicate it's been added
                const tags = document.querySelectorAll(`.variable-tag[data-variable="${variable}"]`);
                tags.forEach(tag => {
                    tag.classList.remove('is-info');
                    tag.classList.add('is-success');
                    tag.title = 'Added as form field';
                });
            } else {
                alert(data.error || 'Failed to add field');
            }
        })
        .catch(error => {
            console.error('Error adding field:', error);
            alert('Error adding field: ' + error);
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
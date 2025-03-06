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
}); 
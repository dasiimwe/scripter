// Main JavaScript for Scripter application
document.addEventListener('DOMContentLoaded', () => {
    // Handle navbar burger menu for mobile
    const navbarBurgers = Array.prototype.slice.call(document.querySelectorAll('.navbar-burger'), 0);
    if (navbarBurgers.length > 0) {
        navbarBurgers.forEach(el => {
            el.addEventListener('click', () => {
                const target = document.getElementById(el.dataset.target);
                el.classList.toggle('is-active');
                target.classList.toggle('is-active');
            });
        });
    }
    
    // Handle notification dismissal
    (document.querySelectorAll('.notification .delete') || []).forEach(($delete) => {
        const $notification = $delete.parentNode;
        $delete.addEventListener('click', () => {
            $notification.parentNode.removeChild($notification);
        });
    });
    
    // Handle navbar dropdown functionality
    const dropdowns = document.querySelectorAll('.navbar-item.has-dropdown');
    dropdowns.forEach(dropdown => {
        const link = dropdown.querySelector('.navbar-link');
        
        // Toggle dropdown on click (for mobile and accessibility)
        link.addEventListener('click', (e) => {
            e.preventDefault();
            dropdown.classList.toggle('is-active');
            
            // Close other dropdowns
            dropdowns.forEach(otherDropdown => {
                if (otherDropdown !== dropdown) {
                    otherDropdown.classList.remove('is-active');
                }
            });
        });
    });
    
    // Close dropdowns when clicking outside
    document.addEventListener('click', (e) => {
        if (!e.target.closest('.navbar-item.has-dropdown')) {
            dropdowns.forEach(dropdown => {
                dropdown.classList.remove('is-active');
            });
        }
    });
}); 
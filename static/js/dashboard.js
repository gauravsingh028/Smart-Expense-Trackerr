/**
 * Smart Expense Tracker — Dashboard JavaScript
 *
 * Utility functions for the expense tracker frontend.
 * Chart.js initialization is handled inline in templates
 * for template-variable access.
 */

// Format number as Indian Rupee
function formatCurrency(amount) {
    return '₹' + parseFloat(amount).toLocaleString('en-IN', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
    });
}

// Debounce utility
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        clearTimeout(timeout);
        timeout = setTimeout(() => func.apply(this, args), wait);
    };
}

// Confirm delete with modal
function confirmDeleteAction(url) {
    if (typeof confirmDelete === 'function') {
        confirmDelete(url);
    }
}

// Print report
function printReport() {
    window.print();
}

// Main JavaScript for Crusher Billing System

document.addEventListener('DOMContentLoaded', function() {
    // Auto-dismiss alerts after 5 seconds
    const alerts = document.querySelectorAll('.alert');
    alerts.forEach(function(alert) {
        setTimeout(function() {
            const bsAlert = new bootstrap.Alert(alert);
            bsAlert.close();
        }, 5000);
    });
    
    // Confirm delete actions
    const deleteButtons = document.querySelectorAll('[data-confirm-delete]');
    deleteButtons.forEach(function(button) {
        button.addEventListener('click', function(e) {
            if (!confirm('Are you sure you want to delete this item?')) {
                e.preventDefault();
            }
        });
    });
    
    // Format currency inputs
    const currencyInputs = document.querySelectorAll('.currency-input');
    currencyInputs.forEach(function(input) {
        input.addEventListener('blur', function() {
            const value = parseFloat(this.value);
            if (!isNaN(value)) {
                this.value = value.toFixed(2);
            }
        });
    });
    
    // Auto-calculate totals in invoice creation
    const quantityInputs = document.querySelectorAll('.quantity-input');
    quantityInputs.forEach(function(input) {
        input.addEventListener('input', function() {
            calculateLineTotal(this);
        });
    });
    
    // Print functionality
    const printButtons = document.querySelectorAll('[data-print]');
    printButtons.forEach(function(button) {
        button.addEventListener('click', function() {
            window.print();
        });
    });
});

// Helper function to calculate line total
function calculateLineTotal(input) {
    const row = input.closest('tr');
    const price = parseFloat(row.querySelector('.price-cell').textContent.replace('₹', '')) || 0;
    const quantity = parseFloat(input.value) || 0;
    const gstRate = parseFloat(row.querySelector('.gst-rate').textContent.replace('%', '')) || 0;
    
    const subtotal = price * quantity;
    const gstAmount = subtotal * (gstRate / 100);
    const total = subtotal + gstAmount;
    
    row.querySelector('.amount-cell').textContent = '₹' + subtotal.toFixed(2);
    row.querySelector('.total-cell').textContent = '₹' + total.toFixed(2);
    
    updateInvoiceTotals();
}

// Update invoice totals
function updateInvoiceTotals() {
    let subtotal = 0;
    let cgstTotal = 0;
    let sgstTotal = 0;
    
    document.querySelectorAll('.invoice-line').forEach(function(row) {
        const amount = parseFloat(row.querySelector('.amount-cell').textContent.replace('₹', '')) || 0;
        const gstRate = parseFloat(row.querySelector('.gst-rate').textContent.replace('%', '')) || 0;
        
        subtotal += amount;
        
        if (gstRate > 0) {
            const cgstRate = gstRate / 2;
            const sgstRate = gstRate / 2;
            cgstTotal += amount * (cgstRate / 100);
            sgstTotal += amount * (sgstRate / 100);
        }
    });
    
    const grandTotal = subtotal + cgstTotal + sgstTotal;
    
    document.getElementById('subtotal').textContent = '₹' + subtotal.toFixed(2);
    document.getElementById('cgst').textContent = '₹' + cgstTotal.toFixed(2);
    document.getElementById('sgst').textContent = '₹' + sgstTotal.toFixed(2);
    document.getElementById('grandTotal').textContent = '₹' + grandTotal.toFixed(2);
}

// Format number with Indian currency
function formatCurrency(amount) {
    return '₹' + parseFloat(amount).toFixed(2);
}

// Validate form before submission
function validateInvoiceForm() {
    const items = document.querySelectorAll('.invoice-line');
    if (items.length === 0) {
        alert('Please add at least one item to the invoice.');
        return false;
    }
    
    let hasError = false;
    items.forEach(function(row) {
        const quantity = parseFloat(row.querySelector('.quantity-input').value);
        if (isNaN(quantity) || quantity <= 0) {
            hasError = true;
            row.querySelector('.quantity-input').classList.add('is-invalid');
        } else {
            row.querySelector('.quantity-input').classList.remove('is-invalid');
        }
    });
    
    if (hasError) {
        alert('Please enter valid quantities for all items.');
        return false;
    }
    
    return true;
}

// Export to CSV helper
function exportToCSV(data, filename) {
    const csv = convertToCSV(data);
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    const url = URL.createObjectURL(blob);
    
    link.setAttribute('href', url);
    link.setAttribute('download', filename);
    link.style.visibility = 'hidden';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
}

// Convert data to CSV format
function convertToCSV(data) {
    if (!data || data.length === 0) return '';
    
    const headers = Object.keys(data[0]);
    const csvRows = [];
    
    csvRows.push(headers.join(','));
    
    data.forEach(function(row) {
        const values = headers.map(function(header) {
            const value = row[header];
            return typeof value === 'string' && value.includes(',') ? `"${value}"` : value;
        });
        csvRows.push(values.join(','));
    });
    
    return csvRows.join('\n');
}


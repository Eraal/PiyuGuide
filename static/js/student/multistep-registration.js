// Multi-step Registration Form JavaScript
let currentStep = 1;
const totalSteps = 2;

// DOM elements
const step1 = document.getElementById('step-1');
const step2 = document.getElementById('step-2');
const nextBtn = document.getElementById('next-step-1');
const prevBtn = document.getElementById('prev-step-2');
const progressBar = document.querySelector('.progress-bar');
const stepIndicators = document.querySelectorAll('.step-indicator');

// Step navigation functions
function showStep(stepNumber) {
    // Hide all steps
    step1.classList.add('hidden');
    step2.classList.add('hidden');
    
    // Show current step
    if (stepNumber === 1) {
        step1.classList.remove('hidden');
        step1.classList.add('step-active');
        step2.classList.remove('step-active');
    } else {
        step2.classList.remove('hidden');
        step2.classList.add('step-active');
        step1.classList.remove('step-active');
    }
    
    // Update progress bar
    const progressPercentage = (stepNumber / totalSteps) * 100;
    progressBar.style.width = progressPercentage + '%';
    
    // Update step indicators
    stepIndicators.forEach((indicator, index) => {
        if (index < stepNumber) {
            indicator.classList.remove('bg-gray-300', 'text-gray-500');
            indicator.classList.add('bg-blue-600', 'text-white');
        } else {
            indicator.classList.remove('bg-blue-600', 'text-white');
            indicator.classList.add('bg-gray-300', 'text-gray-500');
        }
    });
    
    currentStep = stepNumber;
}

// Validate step 1 fields
function validateStep1() {
    const requiredFields = [
        'first_name',
        'last_name', 
        'email',
        'password',
        'confirm_password'
    ];
    
    let isValid = true;
    let errorMessage = '';
    
    // Check if all fields are filled
    requiredFields.forEach(fieldName => {
        const field = document.querySelector(`[name="${fieldName}"]`);
        if (!field.value.trim()) {
            isValid = false;
            field.classList.add('border-red-500');
            field.classList.remove('border-gray-200');
        } else {
            field.classList.remove('border-red-500');
            field.classList.add('border-gray-200');
        }
    });
    
    // Check password match
    const password = document.querySelector('[name="password"]').value;
    const confirmPassword = document.querySelector('[name="confirm_password"]').value;
    
    if (password !== confirmPassword) {
        isValid = false;
        errorMessage = 'Passwords do not match!';
        document.querySelector('[name="confirm_password"]').classList.add('border-red-500');
    }
    
    // Check email format
    const email = document.querySelector('[name="email"]').value;
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (email && !emailRegex.test(email)) {
        isValid = false;
        errorMessage = 'Please enter a valid email address!';
        document.querySelector('[name="email"]').classList.add('border-red-500');
    }
    
    if (!isValid && errorMessage) {
        showNotification(errorMessage, 'error');
    }
    
    return isValid;
}

// Show notification function
function showNotification(message, type = 'error') {
    // Remove existing notifications
    const existingNotification = document.querySelector('.notification');
    if (existingNotification) {
        existingNotification.remove();
    }
    
    // Create notification element
    const notification = document.createElement('div');
    notification.className = `notification fixed top-4 right-4 z-50 p-4 rounded-lg shadow-lg transition-all duration-300 transform translate-x-full`;
    
    if (type === 'error') {
        notification.classList.add('bg-red-500', 'text-white');
        notification.innerHTML = `
            <div class="flex items-center">
                <svg class="h-5 w-5 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <span>${message}</span>
            </div>
        `;
    } else {
        notification.classList.add('bg-green-500', 'text-white');
        notification.innerHTML = `
            <div class="flex items-center">
                <svg class="h-5 w-5 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
                </svg>
                <span>${message}</span>
            </div>
        `;
    }
    
    document.body.appendChild(notification);
    
    // Animate in
    setTimeout(() => {
        notification.classList.remove('translate-x-full');
    }, 100);
    
    // Auto remove after 3 seconds
    setTimeout(() => {
        notification.classList.add('translate-x-full');
        setTimeout(() => {
            notification.remove();
        }, 300);
    }, 3000);
}

// Initialize the multi-step form
document.addEventListener('DOMContentLoaded', function() {
    // Initialize the form
    showStep(1);
    
    // Step navigation event listeners
    if (nextBtn) {
        nextBtn.addEventListener('click', function() {
            if (validateStep1()) {
                showStep(2);
                showNotification('Step 1 completed successfully!', 'success');
            }
        });
    }
    
    if (prevBtn) {
        prevBtn.addEventListener('click', function() {
            showStep(1);
        });
    }
    
    // Password toggle functionality (skip managed buttons in template)
    document.querySelectorAll('.toggle-password').forEach(button => {
        if (button.dataset && button.dataset.managed === 'true') return;
        button.addEventListener('click', function() {
            const input = this.parentElement.querySelector('input');
            const type = input.getAttribute('type') === 'password' ? 'text' : 'password';
            input.setAttribute('type', type);
            
            // Toggle icon
            this.classList.toggle('text-blue-600');
        });
    });
    
    // Enhanced form validation
    document.querySelectorAll('input, select').forEach(field => {
        field.addEventListener('blur', function() {
            if (this.hasAttribute('required') && !this.value.trim()) {
                this.classList.add('border-red-500');
                this.classList.remove('border-gray-200');
            } else {
                this.classList.remove('border-red-500');
                this.classList.add('border-gray-200');
            }
        });
        
        field.addEventListener('input', function() {
            if (this.classList.contains('border-red-500') && this.value.trim()) {
                this.classList.remove('border-red-500');
                this.classList.add('border-gray-200');
            }
        });
    });
    
    // Student number formatting
    const studentNumberInput = document.querySelector('[name="student_number"]');
    if (studentNumberInput) {
        studentNumberInput.addEventListener('input', function() {
            let value = this.value.replace(/\D/g, ''); // Remove non-digits
            if (value.length >= 4) {
                value = value.substring(0, 4) + '-' + value.substring(4, 8);
            }
            this.value = value;
        });
    }
    
    // Add smooth transitions with CSS
    const style = document.createElement('style');
    style.textContent = `
        .step-content {
            transition: all 0.3s ease-in-out;
        }
        .step-active {
            animation: slideIn 0.3s ease-in-out;
        }
        @keyframes slideIn {
            from {
                opacity: 0;
                transform: translateX(20px);
            }
            to {
                opacity: 1;
                transform: translateX(0);
            }
        }
        .progress-bar {
            transition: width 0.5s ease-in-out;
        }
        .step-indicator {
            transition: all 0.3s ease-in-out;
        }
        .notification {
            box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05);
        }
    `;
    document.head.appendChild(style);
});

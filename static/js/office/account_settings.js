/**
 * Office Account Settings JavaScript
 * Handles interactive functionality for the account settings page
 */

class OfficeAccountSettings {
    constructor() {
        this.csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
        this.init();
    }

    init() {
        this.setupPasswordToggle();
        this.setupFormValidation();
        this.setupImagePreview();
        this.setupNotifications();
        this.setupModals();
        this.setupAutoSave();
    }

    /**
     * Setup password visibility toggle
     */
    setupPasswordToggle() {
        const toggleButtons = document.querySelectorAll('[onclick*="togglePassword"]');
        
        toggleButtons.forEach(button => {
            button.addEventListener('click', (e) => {
                e.preventDefault();
                const inputId = button.getAttribute('onclick').match(/togglePassword\('([^']+)'\)/)[1];
                this.togglePasswordVisibility(inputId);
            });
        });
    }

    togglePasswordVisibility(inputId) {
        const input = document.getElementById(inputId);
        const icon = document.getElementById(inputId + '_icon');
        
        if (input && icon) {
            if (input.type === 'password') {
                input.type = 'text';
                icon.className = 'fas fa-eye-slash text-gray-400 hover:text-gray-600';
            } else {
                input.type = 'password';
                icon.className = 'fas fa-eye text-gray-400 hover:text-gray-600';
            }
        }
    }

    /**
     * Setup form validation
     */
    setupFormValidation() {
        // Personal Info Form Validation
        const personalForm = document.querySelector('form[action*="update-personal-info"]');
        if (personalForm) {
            personalForm.addEventListener('submit', (e) => {
                if (!this.validatePersonalInfo()) {
                    e.preventDefault();
                }
            });
        }

        // Password Change Form Validation
        const passwordForm = document.querySelector('form[action*="change-password"]');
        if (passwordForm) {
            passwordForm.addEventListener('submit', (e) => {
                if (!this.validatePasswordChange()) {
                    e.preventDefault();
                }
            });

            // Real-time password validation
            const newPasswordInput = document.getElementById('new_password');
            const confirmPasswordInput = document.getElementById('confirm_password');
            
            if (newPasswordInput) {
                newPasswordInput.addEventListener('input', () => {
                    this.validatePasswordStrength(newPasswordInput.value);
                });
            }

            if (confirmPasswordInput) {
                confirmPasswordInput.addEventListener('input', () => {
                    this.validatePasswordMatch();
                });
            }
        }

        // Notification Preferences Form
        const notificationForm = document.querySelector('form[action*="update-notification-preferences"]');
        if (notificationForm) {
            notificationForm.addEventListener('submit', (e) => {
                this.showNotification('Updating notification preferences...', 'info');
            });
        }
    }

    validatePersonalInfo() {
        const firstName = document.getElementById('first_name').value.trim();
        const lastName = document.getElementById('last_name').value.trim();
        const email = document.getElementById('email').value.trim();

        if (!firstName) {
            this.showNotification('First name is required', 'error');
            return false;
        }

        if (!lastName) {
            this.showNotification('Last name is required', 'error');
            return false;
        }

        if (!email || !this.isValidEmail(email)) {
            this.showNotification('Please enter a valid email address', 'error');
            return false;
        }

        return true;
    }

    validatePasswordChange() {
        const currentPassword = document.getElementById('current_password').value;
        const newPassword = document.getElementById('new_password').value;
        const confirmPassword = document.getElementById('confirm_password').value;

        if (!currentPassword) {
            this.showNotification('Current password is required', 'error');
            return false;
        }

        if (!newPassword) {
            this.showNotification('New password is required', 'error');
            return false;
        }

        if (newPassword.length < 8) {
            this.showNotification('Password must be at least 8 characters long', 'error');
            return false;
        }

        if (!this.isStrongPassword(newPassword)) {
            this.showNotification('Password must contain at least one letter, number, and special character', 'error');
            return false;
        }

        if (newPassword !== confirmPassword) {
            this.showNotification('Passwords do not match', 'error');
            return false;
        }

        return true;
    }

    validatePasswordStrength(password) {
        const strengthIndicator = document.getElementById('password-strength') || this.createPasswordStrengthIndicator();
        const strength = this.calculatePasswordStrength(password);
        
        this.updatePasswordStrengthIndicator(strengthIndicator, strength);
    }

    calculatePasswordStrength(password) {
        let score = 0;
        const checks = {
            length: password.length >= 8,
            lowercase: /[a-z]/.test(password),
            uppercase: /[A-Z]/.test(password),
            numbers: /\d/.test(password),
            special: /[!@#$%^&*(),.?":{}|<>]/.test(password)
        };

        Object.values(checks).forEach(check => {
            if (check) score++;
        });

        if (score < 3) return 'weak';
        if (score < 5) return 'medium';
        return 'strong';
    }

    createPasswordStrengthIndicator() {
        const newPasswordField = document.getElementById('new_password');
        const indicator = document.createElement('div');
        indicator.id = 'password-strength';
        indicator.className = 'mt-2 text-sm';
        newPasswordField.parentNode.appendChild(indicator);
        return indicator;
    }

    updatePasswordStrengthIndicator(indicator, strength) {
        const messages = {
            weak: { text: 'Weak password', color: 'text-red-500' },
            medium: { text: 'Medium strength', color: 'text-yellow-500' },
            strong: { text: 'Strong password', color: 'text-green-500' }
        };

        const message = messages[strength];
        indicator.textContent = message.text;
        indicator.className = `mt-2 text-sm ${message.color}`;
    }

    validatePasswordMatch() {
        const newPassword = document.getElementById('new_password').value;
        const confirmPassword = document.getElementById('confirm_password').value;
        const matchIndicator = document.getElementById('password-match') || this.createPasswordMatchIndicator();

        if (confirmPassword) {
            if (newPassword === confirmPassword) {
                matchIndicator.textContent = 'Passwords match';
                matchIndicator.className = 'mt-2 text-sm text-green-500';
            } else {
                matchIndicator.textContent = 'Passwords do not match';
                matchIndicator.className = 'mt-2 text-sm text-red-500';
            }
        } else {
            matchIndicator.textContent = '';
        }
    }

    createPasswordMatchIndicator() {
        const confirmPasswordField = document.getElementById('confirm_password');
        const indicator = document.createElement('div');
        indicator.id = 'password-match';
        indicator.className = 'mt-2 text-sm';
        confirmPasswordField.parentNode.appendChild(indicator);
        return indicator;
    }

    isValidEmail(email) {
        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        return emailRegex.test(email);
    }

    isStrongPassword(password) {
        const hasLetter = /[a-zA-Z]/.test(password);
        const hasNumber = /\d/.test(password);
        const hasSpecial = /[!@#$%^&*(),.?":{}|<>]/.test(password);
        return hasLetter && hasNumber && hasSpecial;
    }

    /**
     * Setup image preview functionality
     */
    setupImagePreview() {
        const profilePicInput = document.getElementById('profile_pic');
        const previewModal = document.getElementById('image-preview-modal');
        const previewImage = document.getElementById('preview-image');
        const confirmUpload = document.getElementById('confirm-upload');
        const cancelUpload = document.getElementById('cancel-upload');
        
        if (profilePicInput) {
            profilePicInput.addEventListener('change', (e) => {
                const file = e.target.files[0];
                if (file) {
                    this.previewProfileImage(file);
                }
            });
        }

        if (confirmUpload) {
            confirmUpload.addEventListener('click', () => {
                this.uploadProfileImage();
            });
        }

        if (cancelUpload) {
            cancelUpload.addEventListener('click', () => {
                this.cancelImageUpload();
            });
        }
    }

    previewProfileImage(file) {
        if (!file.type.startsWith('image/')) {
            this.showNotification('Please select a valid image file', 'error');
            return;
        }

        if (file.size > 5 * 1024 * 1024) { // 5MB limit
            this.showNotification('File size must be less than 5MB', 'error');
            return;
        }

        const reader = new FileReader();
        reader.onload = (e) => {
            const previewImage = document.getElementById('preview-image');
            const previewModal = document.getElementById('image-preview-modal');
            
            if (previewImage && previewModal) {
                previewImage.src = e.target.result;
                previewModal.classList.remove('hidden');
            }
        };
        reader.readAsDataURL(file);
    }

    uploadProfileImage() {
        const form = document.getElementById('profile-pic-form');
        if (form) {
            this.showNotification('Uploading profile picture...', 'info');
            form.submit();
        }
    }

    cancelImageUpload() {
        const previewModal = document.getElementById('image-preview-modal');
        const profilePicInput = document.getElementById('profile_pic');
        
        if (previewModal) {
            previewModal.classList.add('hidden');
        }
        
        if (profilePicInput) {
            profilePicInput.value = '';
        }
    }

    /**
     * Setup notification system
     */
    setupNotifications() {
        // Auto-dismiss flash messages after 5 seconds
        const flashMessages = document.querySelectorAll('.flash-message');
        flashMessages.forEach(message => {
            setTimeout(() => {
                this.dismissFlashMessage(message);
            }, 5000);
        });
    }

    showNotification(message, type = 'info') {
        const notification = document.createElement('div');
        notification.className = `fixed top-4 right-4 z-50 p-4 rounded-xl shadow-lg transition-all duration-300 transform translate-x-full max-w-sm`;
        
        const typeClasses = {
            success: 'bg-green-500 text-white',
            error: 'bg-red-500 text-white',
            warning: 'bg-yellow-500 text-white',
            info: 'bg-blue-500 text-white'
        };

        notification.className += ` ${typeClasses[type] || typeClasses.info}`;

        const icon = {
            success: 'check-circle',
            error: 'exclamation-circle',
            warning: 'exclamation-triangle',
            info: 'info-circle'
        };

        notification.innerHTML = `
            <div class="flex items-center space-x-3">
                <i class="fas fa-${icon[type] || icon.info} text-lg"></i>
                <span class="flex-1">${message}</span>
                <button onclick="this.parentElement.parentElement.remove()" class="text-white hover:text-gray-200 transition-colors">
                    <i class="fas fa-times"></i>
                </button>
            </div>
        `;

        document.body.appendChild(notification);

        // Animate in
        setTimeout(() => {
            notification.classList.remove('translate-x-full');
        }, 100);

        // Auto remove after 5 seconds
        setTimeout(() => {
            this.dismissNotification(notification);
        }, 5000);
    }

    dismissNotification(notification) {
        if (notification && notification.parentElement) {
            notification.classList.add('translate-x-full');
            setTimeout(() => {
                if (notification.parentElement) {
                    notification.parentElement.removeChild(notification);
                }
            }, 300);
        }
    }

    dismissFlashMessage(message) {
        if (message && message.parentElement) {
            message.style.opacity = '0';
            setTimeout(() => {
                if (message.parentElement) {
                    message.parentElement.removeChild(message);
                }
            }, 500);
        }
    }

    /**
     * Setup modal functionality
     */
    setupModals() {
        // Deactivate account modal
        const deactivateBtn = document.getElementById('deactivate-account-btn');
        const deactivateModal = document.getElementById('deactivate-modal');
        const cancelDeactivate = document.getElementById('cancel-deactivate');

        if (deactivateBtn && deactivateModal) {
            deactivateBtn.addEventListener('click', () => {
                deactivateModal.classList.remove('hidden');
            });
        }

        if (cancelDeactivate && deactivateModal) {
            cancelDeactivate.addEventListener('click', () => {
                deactivateModal.classList.add('hidden');
            });
        }

        // Close modals when clicking outside
        const modals = document.querySelectorAll('[id$="-modal"]');
        modals.forEach(modal => {
            modal.addEventListener('click', (e) => {
                if (e.target === modal) {
                    modal.classList.add('hidden');
                }
            });
        });

        // ESC key to close modals
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                modals.forEach(modal => {
                    if (!modal.classList.contains('hidden')) {
                        modal.classList.add('hidden');
                    }
                });
            }
        });
    }

    /**
     * Setup auto-save functionality for preferences
     */
    setupAutoSave() {
        const autoSaveFields = document.querySelectorAll('input[type="checkbox"], select');
        
        autoSaveFields.forEach(field => {
            if (field.closest('form[action*="notification-preferences"]')) {
                field.addEventListener('change', () => {
                    this.debounce(() => {
                        this.autoSavePreferences();
                    }, 1000)();
                });
            }
        });
    }

    autoSavePreferences() {
        const form = document.querySelector('form[action*="notification-preferences"]');
        if (form) {
            const formData = new FormData(form);
            
            fetch(form.action, {
                method: 'POST',
                body: formData,
                headers: {
                    'X-CSRFToken': this.csrfToken
                }
            })
            .then(response => {
                if (response.ok) {
                    this.showNotification('Preferences saved automatically', 'success');
                }
            })
            .catch(error => {
                console.error('Auto-save failed:', error);
            });
        }
    }

    /**
     * Utility function for debouncing
     */
    debounce(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    }
}

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    new OfficeAccountSettings();
});

// Export for use in other modules if needed
window.OfficeAccountSettings = OfficeAccountSettings;

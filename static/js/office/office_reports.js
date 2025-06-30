/**
 * Office Reports JavaScript Functionality
 * Handles report generation, filtering, and export functionality
 */

class ReportsManager {
    constructor() {
        this.loadingModal = document.getElementById("loadingModal");
        this.progressBar = document.getElementById("progressBar");
        this.init();
    }

    init() {
        this.setupEventListeners();
        this.updateFiltersBasedOnReportType('inquiries');
    }

    setupEventListeners() {
        // Report type change handlers
        const reportTypeInputs = document.querySelectorAll('input[name="report_type"]');
        reportTypeInputs.forEach(input => {
            input.addEventListener('change', (e) => {
                this.updateFiltersBasedOnReportType(e.target.value);
            });
        });

        // Generate report button
        const generateReportBtn = document.getElementById("generateReportBtn");
        if (generateReportBtn) {
            generateReportBtn.addEventListener("click", () => {
                this.handleGenerateReport();
            });
        }

        // Quick report buttons
        const quickReportBtns = document.querySelectorAll(".quick-report-btn");
        quickReportBtns.forEach(btn => {
            btn.addEventListener("click", (e) => {
                this.handleQuickReport(e.target.closest('.quick-report-btn'));
            });
        });
    }

    updateFiltersBasedOnReportType(reportType) {
        const statusFilter = document.getElementById("statusFilter");
        const concernFilter = document.getElementById("concernFilter");

        switch (reportType) {
            case 'inquiries':
                this.showElement(statusFilter);
                this.showElement(concernFilter);
                break;
            case 'counseling':
                this.showElement(statusFilter);
                this.hideElement(concernFilter);
                break;
            case 'activity':
            case 'summary':
                this.hideElement(statusFilter);
                this.hideElement(concernFilter);
                break;
        }
    }

    showElement(element) {
        if (element) element.style.display = 'block';
    }

    hideElement(element) {
        if (element) element.style.display = 'none';
    }

    handleGenerateReport() {
        const formData = new FormData(document.getElementById("reportForm"));
        
        // Debug: Log form data
        console.log('Form data collected:');
        for (let [key, value] of formData.entries()) {
            console.log(key, ':', value);
        }
        
        const data = {
            report_type: formData.get('report_type'),
            date_range: formData.get('date_range'),
            format: formData.get('export_format'),
            filters: {
                status: formData.get('status_filter'),
                concern_type: formData.get('concern_filter')
            }
        };

        // Debug: Log final data object
        console.log('Data being sent:', data);
        
        // Validate required fields
        if (!data.report_type) {
            this.showFlashMessage('Please select a report type', 'error');
            return;
        }
        
        if (!data.date_range) {
            this.showFlashMessage('Please select a date range', 'error');
            return;
        }
        
        if (!data.format) {
            this.showFlashMessage('Please select an export format', 'error');
            return;
        }

        this.generateReport(data);
    }

    handleQuickReport(button) {
        const data = {
            report_type: button.dataset.type,
            date_range: button.dataset.range,
            format: button.dataset.format,
            filters: {}
        };

        this.generateReport(data);
    }

    async generateReport(data) {
        try {
            this.showLoadingModal();
            this.simulateProgress();

            const response = await this.makeReportRequest(data);
            
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.error || 'Failed to generate report');
            }

            await this.handleSuccessfulReport(response);
            this.showFlashMessage('Report generated successfully!', 'success');

        } catch (error) {
            console.error('Error generating report:', error);
            this.showFlashMessage(`Failed to generate report: ${error.message}`, 'error');
        } finally {
            this.hideLoadingModal();
        }
    }

    showLoadingModal() {
        if (this.loadingModal) {
            this.loadingModal.classList.remove("hidden");
        }
    }

    hideLoadingModal() {
        if (this.loadingModal) {
            setTimeout(() => {
                this.loadingModal.classList.add("hidden");
                if (this.progressBar) {
                    this.progressBar.style.width = '0%';
                }
            }, 1000);
        }
    }

    simulateProgress() {
        if (!this.progressBar) return;

        let progress = 0;
        this.progressInterval = setInterval(() => {
            progress += Math.random() * 30;
            if (progress > 90) progress = 90;
            this.progressBar.style.width = progress + '%';
        }, 500);
    }

    stopProgress() {
        if (this.progressInterval) {
            clearInterval(this.progressInterval);
        }
        if (this.progressBar) {
            this.progressBar.style.width = '100%';
        }
    }

    async makeReportRequest(data) {
        const csrfToken = document.querySelector('meta[name=csrf-token]')?.getAttribute('content');
        
        return fetch('/office/reports/generate', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken
            },
            body: JSON.stringify(data)
        });
    }

    async handleSuccessfulReport(response) {
        this.stopProgress();

        // Get filename from response headers
        const contentDisposition = response.headers.get('Content-Disposition');
        let filename = 'report';
        
        if (contentDisposition) {
            const filenameMatch = contentDisposition.match(/filename=(.+)/);
            if (filenameMatch) {
                filename = filenameMatch[1].replace(/"/g, '');
            }
        }

        // Create and trigger download
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        
        // Cleanup
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);
    }

    showFlashMessage(message, type) {
        const flashContainer = this.getOrCreateFlashContainer();
        
        const flashDiv = document.createElement('div');
        flashDiv.className = `flash-message relative border-l-4 p-4 mb-3 rounded-lg shadow-lg backdrop-blur-sm ${this.getFlashClass(type)}`;
        
        flashDiv.innerHTML = `
            <div class="flex items-start">
                <div class="flex-shrink-0 mr-3 mt-0.5">
                    <div class="w-6 h-6 rounded-full ${this.getIconBg(type)} flex items-center justify-center">
                        <i class="fas ${this.getIcon(type)} text-white text-xs"></i>
                    </div>
                </div>
                <div class="flex-1">
                    <p class="font-medium">${message}</p>
                </div>
                <button type="button" class="close-flash flex-shrink-0 ml-3 text-gray-400 hover:text-gray-600 transition-colors duration-200" onclick="closeFlashMessage(this)">
                    <i class="fas fa-times"></i>
                </button>
            </div>
        `;
        
        flashContainer.appendChild(flashDiv);
        
        // Auto-remove after 5 seconds
        setTimeout(() => {
            if (flashDiv.parentNode) {
                flashDiv.parentNode.removeChild(flashDiv);
            }
        }, 5000);
    }

    getOrCreateFlashContainer() {
        let container = document.querySelector('.flash-messages');
        if (!container) {
            container = document.createElement('div');
            container.className = 'flash-messages fixed top-20 left-1/2 transform -translate-x-1/2 z-50 w-full max-w-md px-4';
            document.body.appendChild(container);
        }
        return container;
    }

    getFlashClass(type) {
        const classes = {
            'success': 'border-green-500 bg-gradient-to-r from-green-50 to-green-100 text-green-800',
            'error': 'border-red-500 bg-gradient-to-r from-red-50 to-red-100 text-red-800',
            'warning': 'border-yellow-500 bg-gradient-to-r from-yellow-50 to-yellow-100 text-yellow-800',
            'info': 'border-blue-500 bg-gradient-to-r from-blue-50 to-blue-100 text-blue-800'
        };
        return classes[type] || classes['info'];
    }

    getIconBg(type) {
        const classes = {
            'success': 'bg-green-500',
            'error': 'bg-red-500',
            'warning': 'bg-yellow-500',
            'info': 'bg-blue-500'
        };
        return classes[type] || classes['info'];
    }

    getIcon(type) {
        const icons = {
            'success': 'fa-check',
            'error': 'fa-exclamation',
            'warning': 'fa-exclamation-triangle',
            'info': 'fa-info'
        };
        return icons[type] || icons['info'];
    }
}

// Global function for closing flash messages
function closeFlashMessage(button) {
    const flashMessage = button.closest('.flash-message');
    if (flashMessage) {
        flashMessage.remove();
    }
}

// Initialize the reports manager when DOM is loaded
document.addEventListener("DOMContentLoaded", function() {
    new ReportsManager();
});

// Export for potential use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = ReportsManager;
}

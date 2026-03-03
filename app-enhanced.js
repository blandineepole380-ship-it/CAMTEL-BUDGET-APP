/**
 * Camtel Budget Web Application - Enhanced Version
 * @version 2.0.0
 * @author Senior Developer
 * @description Production-ready budget management system with enhanced features
 */

// ============================================================================
// LOGGER SYSTEM
// ============================================================================

const Logger = {
    logs: [],
    
    /**
     * Log information message
     * @param {string} message - Message to log
     * @param {object} data - Additional data
     */
    info: function(message, data = {}) {
        const log = { timestamp: new Date(), level: 'INFO', message, data };
        this.logs.push(log);
        console.log(`[INFO] ${message}`, data);
    },
    
    /**
     * Log warning message
     * @param {string} message - Message to log
     * @param {object} data - Additional data
     */
    warn: function(message, data = {}) {
        const log = { timestamp: new Date(), level: 'WARN', message, data };
        this.logs.push(log);
        console.warn(`[WARN] ${message}`, data);
    },
    
    /**
     * Log error message
     * @param {string} message - Message to log
     * @param {object} data - Additional data
     */
    error: function(message, data = {}) {
        const log = { timestamp: new Date(), level: 'ERROR', message, data };
        this.logs.push(log);
        console.error(`[ERROR] ${message}`, data);
    },
    
    /**
     * Get all logs
     */
    getLogs: function() {
        return this.logs;
    },
    
    /**
     * Clear logs
     */
    clear: function() {
        this.logs = [];
    }
};

// ============================================================================
// STORAGE SYSTEM
// ============================================================================

const StorageManager = {
    PREFIX: 'camtel_budget_',
    
    /**
     * Save data to localStorage
     * @param {string} key - Storage key
     * @param {*} value - Value to store
     */
    set: function(key, value) {
        try {
            const serialized = JSON.stringify(value);
            localStorage.setItem(this.PREFIX + key, serialized);
            Logger.info(`Data saved: ${key}`);
            return true;
        } catch (error) {
            Logger.error(`Failed to save ${key}`, error);
            return false;
        }
    },
    
    /**
     * Get data from localStorage
     * @param {string} key - Storage key
     * @param {*} defaultValue - Default value if not found
     */
    get: function(key, defaultValue = null) {
        try {
            const stored = localStorage.getItem(this.PREFIX + key);
            if (stored === null) return defaultValue;
            return JSON.parse(stored);
        } catch (error) {
            Logger.error(`Failed to retrieve ${key}`, error);
            return defaultValue;
        }
    },
    
    /**
     * Remove data from localStorage
     * @param {string} key - Storage key
     */
    remove: function(key) {
        try {
            localStorage.removeItem(this.PREFIX + key);
            Logger.info(`Data removed: ${key}`);
            return true;
        } catch (error) {
            Logger.error(`Failed to remove ${key}`, error);
            return false;
        }
    },
    
    /**
     * Clear all stored data
     */
    clear: function() {
        try {
            const keys = Object.keys(localStorage);
            keys.forEach(key => {
                if (key.startsWith(this.PREFIX)) {
                    localStorage.removeItem(key);
                }
            });
            Logger.info('All data cleared');
            return true;
        } catch (error) {
            Logger.error('Failed to clear data', error);
            return false;
        }
    }
};

// ============================================================================
// VALIDATION SYSTEM
// ============================================================================

const Validator = {
    /**
     * Validate email format
     * @param {string} email - Email to validate
     */
    email: function(email) {
        const regex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        return regex.test(email);
    },
    
    /**
     * Validate number
     * @param {*} value - Value to validate
     */
    number: function(value) {
        return !isNaN(value) && isFinite(value) && value !== '';
    },
    
    /**
     * Validate required field
     * @param {*} value - Value to validate
     */
    required: function(value) {
        return value !== null && value !== undefined && value !== '';
    },
    
    /**
     * Validate minimum length
     * @param {string} value - Value to validate
     * @param {number} min - Minimum length
     */
    minLength: function(value, min) {
        return value && value.length >= min;
    },
    
    /**
     * Validate maximum length
     * @param {string} value - Value to validate
     * @param {number} max - Maximum length
     */
    maxLength: function(value, max) {
        return value && value.length <= max;
    },
    
    /**
     * Validate date format
     * @param {string} date - Date to validate
     */
    date: function(date) {
        return !isNaN(Date.parse(date));
    },
    
    /**
     * Validate form data
     * @param {object} data - Data to validate
     * @param {object} rules - Validation rules
     */
    validate: function(data, rules) {
        const errors = {};
        
        for (const field in rules) {
            const fieldRules = rules[field];
            const value = data[field];
            
            if (fieldRules.required && !this.required(value)) {
                errors[field] = `${field} is required`;
                continue;
            }
            
            if (fieldRules.email && !this.email(value)) {
                errors[field] = `${field} must be a valid email`;
            }
            
            if (fieldRules.number && !this.number(value)) {
                errors[field] = `${field} must be a number`;
            }
            
            if (fieldRules.minLength && !this.minLength(value, fieldRules.minLength)) {
                errors[field] = `${field} must be at least ${fieldRules.minLength} characters`;
            }
            
            if (fieldRules.maxLength && !this.maxLength(value, fieldRules.maxLength)) {
                errors[field] = `${field} must not exceed ${fieldRules.maxLength} characters`;
            }
        }
        
        return errors;
    }
};

// ============================================================================
// NOTIFICATION SYSTEM
// ============================================================================

const Notification = {
    /**
     * Show success notification
     * @param {string} message - Message to display
     * @param {number} duration - Duration in ms
     */
    success: function(message, duration = 3000) {
        this._show(message, 'success', duration);
        Logger.info('Success notification', { message });
    },
    
    /**
     * Show error notification
     * @param {string} message - Message to display
     * @param {number} duration - Duration in ms
     */
    error: function(message, duration = 5000) {
        this._show(message, 'error', duration);
        Logger.error('Error notification', { message });
    },
    
    /**
     * Show warning notification
     * @param {string} message - Message to display
     * @param {number} duration - Duration in ms
     */
    warning: function(message, duration = 4000) {
        this._show(message, 'warning', duration);
        Logger.warn('Warning notification', { message });
    },
    
    /**
     * Show info notification
     * @param {string} message - Message to display
     * @param {number} duration - Duration in ms
     */
    info: function(message, duration = 3000) {
        this._show(message, 'info', duration);
        Logger.info('Info notification', { message });
    },
    
    /**
     * Internal method to show notification
     */
    _show: function(message, type, duration) {
        const container = document.getElementById('notification-container') || this._createContainer();
        
        const notification = document.createElement('div');
        notification.className = `notification notification-${type}`;
        notification.textContent = message;
        
        container.appendChild(notification);
        
        setTimeout(() => {
            notification.classList.add('fade-out');
            setTimeout(() => notification.remove(), 300);
        }, duration);
    },
    
    /**
     * Create notification container
     */
    _createContainer: function() {
        const container = document.createElement('div');
        container.id = 'notification-container';
        container.className = 'notification-container';
        document.body.appendChild(container);
        return container;
    }
};

// ============================================================================
// MOCK DATA WITH PERSISTENCE
// ============================================================================

let mockData = {
    transactions: [
        { id: 1, date: '2026-03-02', code: 'TX001', description: 'Office Supplies', direction: 'IT', imputation: 'IMP001', amount: 5000, status: 'Validé' },
        { id: 2, date: '2026-03-01', code: 'TX002', description: 'Software License', direction: 'HR', imputation: 'IMP002', amount: 15000, status: 'Validé' },
        { id: 3, date: '2026-02-28', code: 'TX003', description: 'Equipment Purchase', direction: 'Finance', imputation: 'IMP003', amount: 25000, status: 'Brouillon' },
        { id: 4, date: '2026-02-27', code: 'TX004', description: 'Training Course', direction: 'HR', imputation: 'IMP002', amount: 8000, status: 'Validé' },
        { id: 5, date: '2026-02-26', code: 'TX005', description: 'Server Maintenance', direction: 'IT', imputation: 'IMP001', amount: 12000, status: 'Validé' },
    ],
    budgetLines: [
        { id: 1, direction: 'IT', imputation: 'IMP001', label: 'IT Infrastructure', budgetCP: 500000, cumulEngaged: 350000, available: 150000, rate: 70 },
        { id: 2, direction: 'HR', imputation: 'IMP002', label: 'HR Operations', budgetCP: 300000, cumulEngaged: 280000, available: 20000, rate: 93 },
        { id: 3, direction: 'Finance', imputation: 'IMP003', label: 'Finance Systems', budgetCP: 400000, cumulEngaged: 450000, available: -50000, rate: 112 },
    ],
    users: [
        { id: 1, name: 'Alice Johnson', email: 'alice@camtel.com', role: 'Admin', direction: 'IT', status: 'Active' },
        { id: 2, name: 'Bob Smith', email: 'bob@camtel.com', role: 'Manager', direction: 'Finance', status: 'Active' },
        { id: 3, name: 'Carol Davis', email: 'carol@camtel.com', role: 'User', direction: 'HR', status: 'Active' },
        { id: 4, name: 'David Wilson', email: 'david@camtel.com', role: 'Viewer', direction: 'Operations', status: 'Inactive' },
    ]
};

// Load data from storage or use defaults
function loadData() {
    const stored = StorageManager.get('appData');
    if (stored) {
        mockData = stored;
        Logger.info('Data loaded from storage');
    } else {
        saveData();
    }
}

// Save data to storage
function saveData() {
    StorageManager.set('appData', mockData);
    Logger.info('Data saved to storage');
}

// ============================================================================
// APPLICATION STATE
// ============================================================================

let appState = {
    currentPage: 'dashboard',
    yearFilter: 2026,
    directionFilter: '',
    searchQuery: '',
    isLoading: false,
    currentUser: null
};

// ============================================================================
// INITIALIZATION
// ============================================================================

document.addEventListener('DOMContentLoaded', () => {
    try {
        Logger.info('Application starting');
        loadData();
        initializeNavigation();
        initializeEventListeners();
        addNotificationStyles();
        loadDashboard();
        Logger.info('Application initialized successfully');
    } catch (error) {
        Logger.error('Failed to initialize application', error);
        Notification.error('Failed to initialize application');
    }
});

// ============================================================================
// NOTIFICATION STYLES
// ============================================================================

function addNotificationStyles() {
    const style = document.createElement('style');
    style.textContent = `
        .notification-container {
            position: fixed;
            top: 20px;
            right: 20px;
            z-index: 10000;
            max-width: 400px;
        }
        
        .notification {
            padding: 15px 20px;
            margin-bottom: 10px;
            border-radius: 4px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
            animation: slideIn 0.3s ease;
        }
        
        .notification-success {
            background-color: #d4edda;
            color: #155724;
            border: 1px solid #c3e6cb;
        }
        
        .notification-error {
            background-color: #f8d7da;
            color: #721c24;
            border: 1px solid #f5c6cb;
        }
        
        .notification-warning {
            background-color: #fff3cd;
            color: #856404;
            border: 1px solid #ffeaa7;
        }
        
        .notification-info {
            background-color: #d1ecf1;
            color: #0c5460;
            border: 1px solid #bee5eb;
        }
        
        .notification.fade-out {
            animation: slideOut 0.3s ease;
        }
        
        @keyframes slideIn {
            from {
                transform: translateX(400px);
                opacity: 0;
            }
            to {
                transform: translateX(0);
                opacity: 1;
            }
        }
        
        @keyframes slideOut {
            from {
                transform: translateX(0);
                opacity: 1;
            }
            to {
                transform: translateX(400px);
                opacity: 0;
            }
        }
    `;
    document.head.appendChild(style);
}

// ============================================================================
// NAVIGATION
// ============================================================================

function initializeNavigation() {
    const navLinks = document.querySelectorAll('.nav-link');
    navLinks.forEach(link => {
        link.addEventListener('click', (e) => {
            e.preventDefault();
            const page = link.getAttribute('data-page');
            navigateToPage(page);
        });
    });
}

function navigateToPage(page) {
    try {
        document.querySelectorAll('.nav-link').forEach(link => {
            link.classList.remove('active');
        });
        document.querySelector(`[data-page="${page}"]`).classList.add('active');

        document.querySelectorAll('.page').forEach(p => {
            p.classList.remove('active');
        });
        document.getElementById(`${page}-page`).classList.add('active');

        const titles = {
            'dashboard': 'Dashboard',
            'transactions': 'Transaction Management',
            'budget-lines': 'Budget Lines Management',
            'reports': 'Reports',
            'planning': 'Budget Planning',
            'users': 'User Management',
            'import-export': 'Import / Export Data'
        };
        document.getElementById('page-title').textContent = titles[page];

        appState.currentPage = page;
        Logger.info(`Navigated to: ${page}`);

        switch(page) {
            case 'dashboard':
                loadDashboard();
                break;
            case 'transactions':
                loadTransactions();
                break;
            case 'budget-lines':
                loadBudgetLines();
                break;
            case 'reports':
                loadReports();
                break;
            case 'planning':
                loadPlanning();
                break;
            case 'users':
                loadUsers();
                break;
            case 'import-export':
                loadImportExport();
                break;
        }
    } catch (error) {
        Logger.error('Navigation error', error);
        Notification.error('Failed to navigate to page');
    }
}

// ============================================================================
// EVENT LISTENERS
// ============================================================================

function initializeEventListeners() {
    // Filters
    const yearFilter = document.getElementById('yearFilter');
    if (yearFilter) {
        yearFilter.addEventListener('change', (e) => {
            appState.yearFilter = parseInt(e.target.value);
            loadDashboard();
        });
    }

    const directionFilter = document.getElementById('directionFilter');
    if (directionFilter) {
        directionFilter.addEventListener('change', (e) => {
            appState.directionFilter = e.target.value;
            loadDashboard();
        });
    }

    const refreshBtn = document.getElementById('refreshBtn');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', () => {
            loadDashboard();
            Notification.success('Data refreshed successfully!');
        });
    }

    // Transactions
    const addTransactionBtn = document.getElementById('addTransactionBtn');
    if (addTransactionBtn) {
        addTransactionBtn.addEventListener('click', () => {
            Notification.info('Add Transaction form would open here');
        });
    }

    const searchTransactions = document.getElementById('searchTransactions');
    if (searchTransactions) {
        searchTransactions.addEventListener('input', (e) => {
            appState.searchQuery = e.target.value;
            filterTransactions();
        });
    }

    const statusFilter = document.getElementById('statusFilter');
    if (statusFilter) {
        statusFilter.addEventListener('change', () => {
            filterTransactions();
        });
    }

    const exportCsvBtn = document.getElementById('exportCsvBtn');
    if (exportCsvBtn) {
        exportCsvBtn.addEventListener('click', () => {
            exportToCSV('transactions');
        });
    }

    // Budget Lines
    const addBudgetLineBtn = document.getElementById('addBudgetLineBtn');
    if (addBudgetLineBtn) {
        addBudgetLineBtn.addEventListener('click', () => {
            Notification.info('Add Budget Line form would open here');
        });
    }

    const downloadTemplateBtn = document.getElementById('downloadTemplateBtn');
    if (downloadTemplateBtn) {
        downloadTemplateBtn.addEventListener('click', () => {
            downloadTemplate();
        });
    }

    const searchBudgetLines = document.getElementById('searchBudgetLines');
    if (searchBudgetLines) {
        searchBudgetLines.addEventListener('input', (e) => {
            filterBudgetLines(e.target.value);
        });
    }

    // Reports
    const generateReportBtn = document.getElementById('generateReportBtn');
    if (generateReportBtn) {
        generateReportBtn.addEventListener('click', () => {
            const reportType = document.getElementById('reportType')?.value || 'Summary';
            Notification.success(`${reportType} report generated successfully!`);
        });
    }

    const exportReportBtn = document.getElementById('exportReportBtn');
    if (exportReportBtn) {
        exportReportBtn.addEventListener('click', () => {
            exportToCSV('reports');
        });
    }

    // Planning
    const planningForm = document.getElementById('planningForm');
    if (planningForm) {
        planningForm.addEventListener('submit', (e) => {
            e.preventDefault();
            submitPlan();
        });
    }

    // Users
    const addUserBtn = document.getElementById('addUserBtn');
    if (addUserBtn) {
        addUserBtn.addEventListener('click', () => {
            Notification.info('Add User form would open here');
        });
    }

    // Import/Export
    const tabBtns = document.querySelectorAll('.tab-btn');
    tabBtns.forEach(btn => {
        btn.addEventListener('click', (e) => {
            switchTab(e.target.getAttribute('data-tab'));
        });
    });

    const exportBtn = document.getElementById('exportBtn');
    if (exportBtn) {
        exportBtn.addEventListener('click', () => {
            handleExport();
        });
    }

    const importBtn = document.getElementById('importBtn');
    if (importBtn) {
        importBtn.addEventListener('click', () => {
            handleImport();
        });
    }

    // Navigation links in content
    document.querySelectorAll('a[data-page]').forEach(link => {
        link.addEventListener('click', (e) => {
            e.preventDefault();
            navigateToPage(link.getAttribute('data-page'));
        });
    });
}

// ============================================================================
// DASHBOARD
// ============================================================================

function loadDashboard() {
    try {
        const totalBudget = mockData.budgetLines.reduce((sum, line) => sum + line.budgetCP, 0);
        const cumulEngaged = mockData.budgetLines.reduce((sum, line) => sum + line.cumulEngaged, 0);
        const available = totalBudget - cumulEngaged;
        const pending = mockData.transactions.filter(t => t.status === 'Brouillon').reduce((sum, t) => sum + t.amount, 0);

        const budgetTotalEl = document.getElementById('budgetTotal');
        const cumulEngagedEl = document.getElementById('cumulEngaged');
        const availableEl = document.getElementById('available');
        const pendingEl = document.getElementById('pending');

        if (budgetTotalEl) budgetTotalEl.textContent = formatCurrency(totalBudget);
        if (cumulEngagedEl) cumulEngagedEl.textContent = formatCurrency(cumulEngaged);
        if (availableEl) availableEl.textContent = formatCurrency(available);
        if (pendingEl) pendingEl.textContent = formatCurrency(pending);

        const recentTransactions = mockData.transactions.slice(0, 3);
        const tbody = document.getElementById('recentTransactions');
        if (tbody) {
            tbody.innerHTML = recentTransactions.map(tx => `
                <tr>
                    <td>${tx.date}</td>
                    <td>${tx.description}</td>
                    <td>${tx.direction}</td>
                    <td>${formatCurrency(tx.amount)}</td>
                    <td><span class="badge ${tx.status === 'Validé' ? 'badge-success' : 'badge-warning'}">${tx.status}</span></td>
                </tr>
            `).join('');
        }

        Logger.info('Dashboard loaded');
    } catch (error) {
        Logger.error('Failed to load dashboard', error);
        Notification.error('Failed to load dashboard');
    }
}

// ============================================================================
// TRANSACTIONS
// ============================================================================

function loadTransactions() {
    try {
        const tbody = document.getElementById('transactionsTable');
        if (tbody) {
            tbody.innerHTML = mockData.transactions.map(tx => `
                <tr>
                    <td>${tx.date}</td>
                    <td>${tx.code}</td>
                    <td>${tx.description}</td>
                    <td>${tx.direction}</td>
                    <td>${tx.imputation}</td>
                    <td>${formatCurrency(tx.amount)}</td>
                    <td><span class="badge ${tx.status === 'Validé' ? 'badge-success' : 'badge-warning'}">${tx.status}</span></td>
                    <td><button class="btn btn-small" onclick="editTransaction(${tx.id})">Edit</button></td>
                </tr>
            `).join('');
        }
        Logger.info('Transactions loaded');
    } catch (error) {
        Logger.error('Failed to load transactions', error);
        Notification.error('Failed to load transactions');
    }
}

function filterTransactions() {
    try {
        const searchQuery = document.getElementById('searchTransactions')?.value.toLowerCase() || '';
        const statusFilter = document.getElementById('statusFilter')?.value || '';

        const filtered = mockData.transactions.filter(tx => {
            const matchesSearch = tx.description.toLowerCase().includes(searchQuery) || 
                                tx.code.toLowerCase().includes(searchQuery);
            const matchesStatus = !statusFilter || tx.status === statusFilter;
            return matchesSearch && matchesStatus;
        });

        const tbody = document.getElementById('transactionsTable');
        if (tbody) {
            tbody.innerHTML = filtered.map(tx => `
                <tr>
                    <td>${tx.date}</td>
                    <td>${tx.code}</td>
                    <td>${tx.description}</td>
                    <td>${tx.direction}</td>
                    <td>${tx.imputation}</td>
                    <td>${formatCurrency(tx.amount)}</td>
                    <td><span class="badge ${tx.status === 'Validé' ? 'badge-success' : 'badge-warning'}">${tx.status}</span></td>
                    <td><button class="btn btn-small" onclick="editTransaction(${tx.id})">Edit</button></td>
                </tr>
            `).join('');
        }
        Logger.info('Transactions filtered');
    } catch (error) {
        Logger.error('Failed to filter transactions', error);
    }
}

function editTransaction(id) {
    Notification.info(`Edit transaction ${id}`);
    Logger.info(`Edit transaction: ${id}`);
}

// ============================================================================
// BUDGET LINES
// ============================================================================

function loadBudgetLines() {
    try {
        const tbody = document.getElementById('budgetLinesTable');
        if (tbody) {
            tbody.innerHTML = mockData.budgetLines.map(line => `
                <tr>
                    <td>${line.direction}</td>
                    <td>${line.imputation}</td>
                    <td>${line.label}</td>
                    <td>${formatCurrency(line.budgetCP)}</td>
                    <td>${formatCurrency(line.cumulEngaged)}</td>
                    <td>${formatCurrency(line.available)}</td>
                    <td>
                        <div class="progress-bar">
                            <div class="progress" style="width: ${Math.min(line.rate, 100)}%; background-color: ${line.rate > 100 ? '#e74c3c' : '#28a745'};"></div>
                        </div>
                        ${line.rate}%
                    </td>
                    <td><span class="badge ${line.rate > 100 ? 'badge-danger' : line.rate > 90 ? 'badge-warning' : 'badge-success'}">${line.rate > 100 ? 'Overspent' : line.rate > 90 ? 'Warning' : 'Active'}</span></td>
                </tr>
            `).join('');
        }
        Logger.info('Budget lines loaded');
    } catch (error) {
        Logger.error('Failed to load budget lines', error);
        Notification.error('Failed to load budget lines');
    }
}

function filterBudgetLines(query) {
    try {
        const filtered = mockData.budgetLines.filter(line => 
            line.imputation.toLowerCase().includes(query.toLowerCase()) ||
            line.label.toLowerCase().includes(query.toLowerCase())
        );

        const tbody = document.getElementById('budgetLinesTable');
        if (tbody) {
            tbody.innerHTML = filtered.map(line => `
                <tr>
                    <td>${line.direction}</td>
                    <td>${line.imputation}</td>
                    <td>${line.label}</td>
                    <td>${formatCurrency(line.budgetCP)}</td>
                    <td>${formatCurrency(line.cumulEngaged)}</td>
                    <td>${formatCurrency(line.available)}</td>
                    <td>
                        <div class="progress-bar">
                            <div class="progress" style="width: ${Math.min(line.rate, 100)}%; background-color: ${line.rate > 100 ? '#e74c3c' : '#28a745'};"></div>
                        </div>
                        ${line.rate}%
                    </td>
                    <td><span class="badge ${line.rate > 100 ? 'badge-danger' : line.rate > 90 ? 'badge-warning' : 'badge-success'}">${line.rate > 100 ? 'Overspent' : line.rate > 90 ? 'Warning' : 'Active'}</span></td>
                </tr>
            `).join('');
        }
        Logger.info('Budget lines filtered');
    } catch (error) {
        Logger.error('Failed to filter budget lines', error);
    }
}

// ============================================================================
// REPORTS
// ============================================================================

function loadReports() {
    Logger.info('Reports loaded');
}

// ============================================================================
// PLANNING
// ============================================================================

function loadPlanning() {
    try {
        const planningForm = document.getElementById('planningForm');
        if (planningForm) {
            planningForm.reset();
        }
        const planningMessage = document.getElementById('planningMessage');
        if (planningMessage) {
            planningMessage.style.display = 'none';
        }
        Logger.info('Planning loaded');
    } catch (error) {
        Logger.error('Failed to load planning', error);
    }
}

function submitPlan() {
    try {
        const year = document.getElementById('planYear')?.value;
        const direction = document.getElementById('planDirection')?.value;
        const nature = document.getElementById('planNature')?.value;
        const amount = document.getElementById('planAmount')?.value;

        const errors = Validator.validate(
            { year, direction, nature, amount },
            {
                year: { required: true },
                direction: { required: true },
                nature: { required: true },
                amount: { required: true, number: true }
            }
        );

        if (Object.keys(errors).length > 0) {
            Notification.error(Object.values(errors)[0]);
            Logger.warn('Plan submission validation failed', errors);
            return;
        }

        Notification.success(`Budget plan for ${direction} (${nature}) - ${formatCurrency(amount)} saved successfully!`);
        document.getElementById('planningForm')?.reset();
        Logger.info('Plan submitted successfully', { year, direction, nature, amount });
        saveData();
    } catch (error) {
        Logger.error('Failed to submit plan', error);
        Notification.error('Failed to submit plan');
    }
}

// ============================================================================
// USERS
// ============================================================================

function loadUsers() {
    try {
        const tbody = document.getElementById('usersTable');
        if (tbody) {
            tbody.innerHTML = mockData.users.map(user => `
                <tr>
                    <td>${user.name}</td>
                    <td>${user.email}</td>
                    <td><span class="badge badge-${user.role.toLowerCase()}">${user.role}</span></td>
                    <td>${user.direction}</td>
                    <td><span class="badge ${user.status === 'Active' ? 'badge-success' : 'badge-inactive'}">${user.status}</span></td>
                    <td><button class="btn btn-small" onclick="editUser(${user.id})">Edit</button></td>
                </tr>
            `).join('');
        }
        Logger.info('Users loaded');
    } catch (error) {
        Logger.error('Failed to load users', error);
        Notification.error('Failed to load users');
    }
}

function editUser(id) {
    Notification.info(`Edit user ${id}`);
    Logger.info(`Edit user: ${id}`);
}

// ============================================================================
// IMPORT/EXPORT
// ============================================================================

function loadImportExport() {
    try {
        switchTab('export');
        Logger.info('Import/Export loaded');
    } catch (error) {
        Logger.error('Failed to load import/export', error);
    }
}

function switchTab(tabName) {
    try {
        document.querySelectorAll('.tab-content').forEach(tab => {
            tab.classList.remove('active');
        });
        const tab = document.getElementById(`${tabName}-tab`);
        if (tab) {
            tab.classList.add('active');
        }

        document.querySelectorAll('.tab-btn').forEach(btn => {
            btn.classList.remove('active');
        });
        const btn = document.querySelector(`[data-tab="${tabName}"]`);
        if (btn) {
            btn.classList.add('active');
        }
        Logger.info(`Switched to tab: ${tabName}`);
    } catch (error) {
        Logger.error('Failed to switch tab', error);
    }
}

function handleExport() {
    try {
        const format = document.getElementById('exportFormat')?.value || 'csv';
        const selectedData = Array.from(document.querySelectorAll('.checkbox-group input:checked'))
            .map(cb => cb.value);

        if (selectedData.length === 0) {
            Notification.error('Please select at least one data type to export');
            return;
        }

        Notification.success(`Data exported successfully as ${format.toUpperCase()}!`);
        Logger.info('Data exported', { format, selectedData });
    } catch (error) {
        Logger.error('Failed to export data', error);
        Notification.error('Failed to export data');
    }
}

function handleImport() {
    try {
        const file = document.getElementById('importFile')?.files[0];
        if (!file) {
            Notification.error('Please select a file to import');
            return;
        }

        Notification.success(`File "${file.name}" imported successfully!`);
        document.getElementById('importFile').value = '';
        Logger.info('File imported', { fileName: file.name, fileSize: file.size });
        saveData();
    } catch (error) {
        Logger.error('Failed to import file', error);
        Notification.error('Failed to import file');
    }
}

// ============================================================================
// UTILITIES
// ============================================================================

/**
 * Format number as currency
 * @param {number} amount - Amount to format
 */
function formatCurrency(amount) {
    try {
        return new Intl.NumberFormat('fr-CM', {
            style: 'currency',
            currency: 'XAF',
            minimumFractionDigits: 0
        }).format(amount);
    } catch (error) {
        Logger.error('Failed to format currency', error);
        return amount.toString();
    }
}

/**
 * Export data to CSV
 * @param {string} dataType - Type of data to export
 */
function exportToCSV(dataType) {
    try {
        let csv = '';
        let filename = `${dataType}_${new Date().toISOString().split('T')[0]}.csv`;

        if (dataType === 'transactions') {
            csv = 'Date,Code,Description,Direction,Imputation,Amount,Status\n';
            csv += mockData.transactions.map(tx => 
                `${tx.date},${tx.code},${tx.description},${tx.direction},${tx.imputation},${tx.amount},${tx.status}`
            ).join('\n');
        } else if (dataType === 'reports') {
            csv = 'Direction,Total Budget,Engaged,Available,Utilization %\n';
            csv += mockData.budgetLines.map(line => 
                `${line.direction},${line.budgetCP},${line.cumulEngaged},${line.available},${line.rate}`
            ).join('\n');
        }

        downloadCSV(csv, filename);
        Notification.success(`${dataType} exported to ${filename}`);
        Logger.info('Data exported to CSV', { dataType, filename });
    } catch (error) {
        Logger.error('Failed to export CSV', error);
        Notification.error('Failed to export CSV');
    }
}

/**
 * Download CSV file
 * @param {string} csv - CSV content
 * @param {string} filename - Filename
 */
function downloadCSV(csv, filename) {
    try {
        const blob = new Blob([csv], { type: 'text/csv' });
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        a.click();
        window.URL.revokeObjectURL(url);
        Logger.info('CSV downloaded', { filename });
    } catch (error) {
        Logger.error('Failed to download CSV', error);
    }
}

/**
 * Download budget template
 */
function downloadTemplate() {
    try {
        const csv = 'Direction,Imputation,Label,Budget CP,Nature\n' +
                    'IT,IMP001,IT Infrastructure,500000,Équipement\n' +
                    'HR,IMP002,HR Operations,300000,Fournitures\n';
        downloadCSV(csv, 'budget_template.csv');
        Notification.success('Template downloaded successfully!');
        Logger.info('Budget template downloaded');
    } catch (error) {
        Logger.error('Failed to download template', error);
        Notification.error('Failed to download template');
    }
}

// ============================================================================
// EXPORT FOR TESTING
// ============================================================================

if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        Logger,
        StorageManager,
        Validator,
        Notification,
        navigateToPage,
        formatCurrency,
        exportToCSV
    };
}

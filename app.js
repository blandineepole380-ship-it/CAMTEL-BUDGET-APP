// Mock Data
const mockData = {
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

// Application State
let appState = {
    currentPage: 'dashboard',
    yearFilter: 2026,
    directionFilter: '',
    searchQuery: '',
};

// Initialize Application
document.addEventListener('DOMContentLoaded', () => {
    initializeNavigation();
    initializeEventListeners();
    loadDashboard();
});

// Navigation
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
    // Update active nav link
    document.querySelectorAll('.nav-link').forEach(link => {
        link.classList.remove('active');
    });
    document.querySelector(`[data-page="${page}"]`).classList.add('active');

    // Update active page
    document.querySelectorAll('.page').forEach(p => {
        p.classList.remove('active');
    });
    document.getElementById(`${page}-page`).classList.add('active');

    // Update page title
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

    // Load page data
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
}

// Event Listeners
function initializeEventListeners() {
    // Filters
    document.getElementById('yearFilter').addEventListener('change', (e) => {
        appState.yearFilter = parseInt(e.target.value);
        loadDashboard();
    });

    document.getElementById('directionFilter').addEventListener('change', (e) => {
        appState.directionFilter = e.target.value;
        loadDashboard();
    });

    document.getElementById('refreshBtn').addEventListener('click', () => {
        showMessage('Data refreshed successfully!', 'success');
        loadDashboard();
    });

    // Transactions
    document.getElementById('addTransactionBtn').addEventListener('click', () => {
        showMessage('Add Transaction form would open here', 'success');
    });

    document.getElementById('searchTransactions').addEventListener('input', (e) => {
        appState.searchQuery = e.target.value;
        filterTransactions();
    });

    document.getElementById('statusFilter').addEventListener('change', () => {
        filterTransactions();
    });

    document.getElementById('exportCsvBtn').addEventListener('click', () => {
        exportToCSV('transactions');
    });

    // Budget Lines
    document.getElementById('addBudgetLineBtn').addEventListener('click', () => {
        showMessage('Add Budget Line form would open here', 'success');
    });

    document.getElementById('downloadTemplateBtn').addEventListener('click', () => {
        downloadTemplate();
    });

    document.getElementById('searchBudgetLines').addEventListener('input', (e) => {
        filterBudgetLines(e.target.value);
    });

    // Reports
    document.getElementById('generateReportBtn').addEventListener('click', () => {
        const reportType = document.getElementById('reportType').value;
        showMessage(`${reportType} report generated successfully!`, 'success');
    });

    document.getElementById('exportReportBtn').addEventListener('click', () => {
        exportToCSV('reports');
    });

    // Planning
    document.getElementById('planningForm').addEventListener('submit', (e) => {
        e.preventDefault();
        submitPlan();
    });

    // Users
    document.getElementById('addUserBtn').addEventListener('click', () => {
        showMessage('Add User form would open here', 'success');
    });

    // Import/Export
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            switchTab(e.target.getAttribute('data-tab'));
        });
    });

    document.getElementById('exportBtn').addEventListener('click', () => {
        handleExport();
    });

    document.getElementById('importBtn').addEventListener('click', () => {
        handleImport();
    });

    // Navigation links in content
    document.querySelectorAll('a[data-page]').forEach(link => {
        link.addEventListener('click', (e) => {
            e.preventDefault();
            navigateToPage(link.getAttribute('data-page'));
        });
    });
}

// Dashboard
function loadDashboard() {
    // Calculate metrics
    const totalBudget = mockData.budgetLines.reduce((sum, line) => sum + line.budgetCP, 0);
    const cumulEngaged = mockData.budgetLines.reduce((sum, line) => sum + line.cumulEngaged, 0);
    const available = totalBudget - cumulEngaged;
    const pending = mockData.transactions.filter(t => t.status === 'Brouillon').reduce((sum, t) => sum + t.amount, 0);

    document.getElementById('budgetTotal').textContent = formatCurrency(totalBudget);
    document.getElementById('cumulEngaged').textContent = formatCurrency(cumulEngaged);
    document.getElementById('available').textContent = formatCurrency(available);
    document.getElementById('pending').textContent = formatCurrency(pending);

    // Load recent transactions
    const recentTransactions = mockData.transactions.slice(0, 3);
    const tbody = document.getElementById('recentTransactions');
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

// Transactions
function loadTransactions() {
    const tbody = document.getElementById('transactionsTable');
    tbody.innerHTML = mockData.transactions.map(tx => `
        <tr>
            <td>${tx.date}</td>
            <td>${tx.code}</td>
            <td>${tx.description}</td>
            <td>${tx.direction}</td>
            <td>${tx.imputation}</td>
            <td>${formatCurrency(tx.amount)}</td>
            <td><span class="badge ${tx.status === 'Validé' ? 'badge-success' : 'badge-warning'}">${tx.status}</span></td>
            <td><button class="btn btn-small">Edit</button></td>
        </tr>
    `).join('');
}

function filterTransactions() {
    const searchQuery = document.getElementById('searchTransactions').value.toLowerCase();
    const statusFilter = document.getElementById('statusFilter').value;

    const filtered = mockData.transactions.filter(tx => {
        const matchesSearch = tx.description.toLowerCase().includes(searchQuery) || 
                            tx.code.toLowerCase().includes(searchQuery);
        const matchesStatus = !statusFilter || tx.status === statusFilter;
        return matchesSearch && matchesStatus;
    });

    const tbody = document.getElementById('transactionsTable');
    tbody.innerHTML = filtered.map(tx => `
        <tr>
            <td>${tx.date}</td>
            <td>${tx.code}</td>
            <td>${tx.description}</td>
            <td>${tx.direction}</td>
            <td>${tx.imputation}</td>
            <td>${formatCurrency(tx.amount)}</td>
            <td><span class="badge ${tx.status === 'Validé' ? 'badge-success' : 'badge-warning'}">${tx.status}</span></td>
            <td><button class="btn btn-small">Edit</button></td>
        </tr>
    `).join('');
}

// Budget Lines
function loadBudgetLines() {
    const tbody = document.getElementById('budgetLinesTable');
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

function filterBudgetLines(query) {
    const filtered = mockData.budgetLines.filter(line => 
        line.imputation.toLowerCase().includes(query.toLowerCase()) ||
        line.label.toLowerCase().includes(query.toLowerCase())
    );

    const tbody = document.getElementById('budgetLinesTable');
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

// Reports
function loadReports() {
    // Reports page is already populated with sample data
}

// Planning
function loadPlanning() {
    // Reset form
    document.getElementById('planningForm').reset();
    document.getElementById('planningMessage').style.display = 'none';
}

function submitPlan() {
    const year = document.getElementById('planYear').value;
    const direction = document.getElementById('planDirection').value;
    const nature = document.getElementById('planNature').value;
    const amount = document.getElementById('planAmount').value;

    if (!direction || !nature || !amount) {
        showMessage('Please fill in all required fields', 'error');
        return;
    }

    showMessage(`Budget plan for ${direction} (${nature}) - ${formatCurrency(amount)} saved successfully!`, 'success');
    document.getElementById('planningForm').reset();
}

// Users
function loadUsers() {
    const tbody = document.getElementById('usersTable');
    tbody.innerHTML = mockData.users.map(user => `
        <tr>
            <td>${user.name}</td>
            <td>${user.email}</td>
            <td><span class="badge badge-${user.role.toLowerCase()}">${user.role}</span></td>
            <td>${user.direction}</td>
            <td><span class="badge ${user.status === 'Active' ? 'badge-success' : 'badge-inactive'}">${user.status}</span></td>
            <td><button class="btn btn-small">Edit</button></td>
        </tr>
    `).join('');
}

// Import/Export
function loadImportExport() {
    // Reset tabs
    switchTab('export');
}

function switchTab(tabName) {
    document.querySelectorAll('.tab-content').forEach(tab => {
        tab.classList.remove('active');
    });
    document.getElementById(`${tabName}-tab`).classList.add('active');

    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    document.querySelector(`[data-tab="${tabName}"]`).classList.add('active');
}

function handleExport() {
    const format = document.getElementById('exportFormat').value;
    const selectedData = Array.from(document.querySelectorAll('.checkbox-group input:checked'))
        .map(cb => cb.value);

    if (selectedData.length === 0) {
        showMessage('Please select at least one data type to export', 'error');
        return;
    }

    showMessage(`Data exported successfully as ${format.toUpperCase()}!`, 'success');
}

function handleImport() {
    const file = document.getElementById('importFile').files[0];
    if (!file) {
        showMessage('Please select a file to import', 'error');
        return;
    }

    showMessage(`File "${file.name}" imported successfully!`, 'success');
    document.getElementById('importFile').value = '';
}

// Utilities
function formatCurrency(amount) {
    return new Intl.NumberFormat('fr-CM', {
        style: 'currency',
        currency: 'XAF',
        minimumFractionDigits: 0
    }).format(amount);
}

function showMessage(text, type) {
    const messageDiv = document.getElementById('planningMessage') || createMessageDiv();
    messageDiv.textContent = text;
    messageDiv.className = `message ${type}`;
    messageDiv.style.display = 'block';

    setTimeout(() => {
        messageDiv.style.display = 'none';
    }, 3000);
}

function createMessageDiv() {
    const div = document.createElement('div');
    div.id = 'planningMessage';
    document.querySelector('.content').appendChild(div);
    return div;
}

function exportToCSV(dataType) {
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
    showMessage(`${dataType} exported to ${filename}`, 'success');
}

function downloadCSV(csv, filename) {
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    window.URL.revokeObjectURL(url);
}

function downloadTemplate() {
    const csv = 'Direction,Imputation,Label,Budget CP,Nature\n' +
                'IT,IMP001,IT Infrastructure,500000,Équipement\n' +
                'HR,IMP002,HR Operations,300000,Fournitures\n';
    downloadCSV(csv, 'budget_template.csv');
    showMessage('Template downloaded successfully!', 'success');
}

<template>
  <div class="import-form-container">
    <div class="import-card">
      <!-- Header -->
      <div class="import-header">
        <h2>📥 Import Budget Data</h2>
        <p class="subtitle">Upload CSV or Excel file to import transactions</p>
      </div>

      <!-- Alerts -->
      <transition name="fade">
        <div v-if="alertMessage" :class="['alert', `alert-${alertType}`]">
          <div class="alert-content">
            <strong>{{ alertTitle }}</strong>
            <p>{{ alertMessage }}</p>
            <div v-if="alertDetails.length > 0" class="alert-details">
              <p v-for="(detail, idx) in alertDetails.slice(0, 5)" :key="idx" class="detail">
                • {{ detail }}
              </p>
              <p v-if="alertDetails.length > 5" class="detail-more">
                ... and {{ alertDetails.length - 5 }} more
              </p>
            </div>
          </div>
        </div>
      </transition>

      <!-- Form -->
      <form @submit.prevent="handleImport" class="import-form">
        <!-- File Input -->
        <div class="form-group">
          <label for="fileInput" class="form-label">
            <span class="label-text">Select File</span>
            <span class="label-hint">(CSV or XLSX, max 10MB)</span>
          </label>
          <div class="file-input-wrapper">
            <input
              id="fileInput"
              ref="fileInput"
              type="file"
              accept=".csv,.xlsx,.xls"
              class="file-input"
              @change="onFileSelected"
              :disabled="isLoading"
              required
            />
            <div class="file-input-label">
              <span v-if="!selectedFile" class="file-placeholder">
                📁 Click to select file or drag and drop
              </span>
              <span v-else class="file-selected">
                ✓ {{ selectedFile.name }}
              </span>
            </div>
          </div>
          <small class="form-hint">
            Required columns: DATE ENGAGEMENT, DIRECTION, MONTANT, IMPUTATION COMPTABLE
          </small>
        </div>

        <!-- File Info -->
        <transition name="slideDown">
          <div v-if="selectedFile" class="file-info">
            <div class="info-item">
              <span class="info-label">File Name:</span>
              <span class="info-value">{{ selectedFile.name }}</span>
            </div>
            <div class="info-item">
              <span class="info-label">File Size:</span>
              <span class="info-value">{{ formatFileSize(selectedFile.size) }}</span>
            </div>
            <div class="info-item">
              <span class="info-label">File Type:</span>
              <span class="info-value">{{ selectedFile.type || 'Unknown' }}</span>
            </div>
          </div>
        </transition>

        <!-- Year Selection -->
        <div class="form-group">
          <label for="yearSelect" class="form-label">Year</label>
          <select id="yearSelect" v-model="importYear" class="form-control">
            <option v-for="year in availableYears" :key="year" :value="year">
              {{ year }}
            </option>
          </select>
        </div>

        <!-- Progress Bar -->
        <transition name="fade">
          <div v-if="isLoading" class="progress-section">
            <div class="progress-bar">
              <div class="progress-fill" :style="{ width: progressPercent + '%' }"></div>
            </div>
            <p class="progress-text">{{ progressPercent }}% - {{ statusMessage }}</p>
          </div>
        </transition>

        <!-- Buttons -->
        <div class="form-actions">
          <button
            type="submit"
            class="btn btn-primary"
            :disabled="!selectedFile || isLoading"
          >
            <span v-if="!isLoading">📤 Import Data</span>
            <span v-else>⏳ Processing...</span>
          </button>
          <button
            type="button"
            class="btn btn-secondary"
            @click="resetForm"
            :disabled="isLoading"
          >
            Reset
          </button>
          <button
            type="button"
            class="btn btn-outline"
            @click="downloadTemplate"
          >
            📥 Download Template
          </button>
        </div>
      </form>

      <!-- Success Summary -->
      <transition name="slideUp">
        <div v-if="importResult && importResult.success" class="success-summary">
          <h3>✓ Import Successful!</h3>
          <div class="summary-grid">
            <div class="summary-item">
              <span class="summary-label">Imported</span>
              <span class="summary-value">{{ importResult.imported }}</span>
            </div>
            <div class="summary-item">
              <span class="summary-label">Failed</span>
              <span class="summary-value">{{ importResult.failed }}</span>
            </div>
            <div class="summary-item">
              <span class="summary-label">Total</span>
              <span class="summary-value">{{ importResult.total }}</span>
            </div>
          </div>
        </div>
      </transition>

      <!-- Help Section -->
      <div class="help-section">
        <details>
          <summary>📖 Need Help?</summary>
          <div class="help-content">
            <h4>Required Columns</h4>
            <ul>
              <li><strong>DATE ENGAGEMENT</strong> - Format: DD/MM/YYYY</li>
              <li><strong>DIRECTION</strong> - Department name</li>
              <li><strong>INTITULE DE LA COMMANDE</strong> - Order title</li>
              <li><strong>LIBELLE</strong> - Description</li>
              <li><strong>NATURE DE LA DEPENSE</strong> - DEPENSE COURANT or DEPENSE DE CAPITAL</li>
              <li><strong>IMPUTATION COMPTABLE</strong> - Accounting code</li>
              <li><strong>MONTANT</strong> - Amount in numbers (e.g., 5000000)</li>
            </ul>
            <p>
              <strong>Download template:</strong> Click the "Download Template" button to get a sample CSV file.
            </p>
          </div>
        </details>
      </div>
    </div>
  </div>
</template>

<script>
export default {
  name: 'ImportForm',
  data() {
    return {
      selectedFile: null,
      isLoading: false,
      progressPercent: 0,
      statusMessage: '',
      importYear: new Date().getFullYear(),
      alertMessage: '',
      alertType: 'info',
      alertTitle: '',
      alertDetails: [],
      importResult: null,
      abortController: null
    };
  },
  computed: {
    availableYears() {
      const currentYear = new Date().getFullYear();
      return Array.from({ length: 5 }, (_, i) => currentYear - 2 + i);
    }
  },
  methods: {
    onFileSelected(event) {
      const file = event.target.files[0];
      this.alertMessage = '';
      this.importResult = null;

      if (!file) {
        this.selectedFile = null;
        return;
      }

      // Validate file size
      const maxSize = 10 * 1024 * 1024; // 10MB
      if (file.size > maxSize) {
        this.showAlert('error', 'File Too Large', `Maximum file size is 10MB. Your file is ${this.formatFileSize(file.size)}.`);
        this.selectedFile = null;
        return;
      }

      // Validate file type
      const validTypes = ['text/csv', 'application/vnd.ms-excel', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'];
      if (!validTypes.includes(file.type) && !file.name.match(/\.(csv|xlsx|xls)$/i)) {
        this.showAlert('error', 'Invalid File Type', 'Only CSV and XLSX files are supported.');
        this.selectedFile = null;
        return;
      }

      this.selectedFile = file;
    },

    async handleImport() {
      if (!this.selectedFile) {
        this.showAlert('error', 'No File Selected', 'Please select a file to import.');
        return;
      }

      this.isLoading = true;
      this.progressPercent = 0;
      this.statusMessage = 'Preparing file...';
      this.alertMessage = '';

      const formData = new FormData();
      formData.append('file', this.selectedFile);
      formData.append('year', this.importYear);

      this.abortController = new AbortController();
      const timeoutId = setTimeout(() => this.abortController.abort(), 120000);

      try {
        this.statusMessage = 'Uploading file...';
        this.progressPercent = 20;

        const response = await fetch('/api/import', {
          method: 'POST',
          body: formData,
          signal: this.abortController.signal
        });

        this.progressPercent = 60;
        this.statusMessage = 'Processing data...';

        const data = await response.json();

        this.progressPercent = 100;

        if (response.ok && data.success) {
          this.importResult = data;
          this.showAlert('success', 'Import Successful!', `${data.imported} records imported successfully.`, 
            data.failedRecords ? data.failedRecords.map(r => `Row ${r.row}: ${r.error}`) : []);
          this.$emit('import-complete', data);
          setTimeout(() => this.resetForm(), 2000);
        } else {
          const errors = data.validationErrors?.map(e => `Row ${e.row}: ${e.errors.join(', ')}`) || [];
          this.showAlert('error', data.message || 'Import Failed', data.message, errors);
        }

      } catch (error) {
        if (error.name === 'AbortError') {
          this.showAlert('error', 'Import Timeout', 'The import took too long. Please try with a smaller file.');
        } else {
          this.showAlert('error', 'Import Error', error.message || 'An unexpected error occurred.');
        }
      } finally {
        clearTimeout(timeoutId);
        this.isLoading = false;
        this.progressPercent = 0;
        this.statusMessage = '';
      }
    },

    showAlert(type, title, message, details = []) {
      this.alertType = type;
      this.alertTitle = title;
      this.alertMessage = message;
      this.alertDetails = details;
    },

    downloadTemplate() {
      const template = `DATE ENGAGEMENT,DIRECTION,INTITULE DE LA COMMANDE,LIBELLE,NATURE DE LA DEPENSE,IMPUTATION COMPTABLE,MONTANT
01/03/2026,DCF,Achat Serveurs,Matériel Informatique,DEPENSE COURANT,2100-001,5000000
02/03/2026,IT,Licence Logiciel,Software,DEPENSE COURANT,2100-002,2500000
03/03/2026,RH,Formation Personnel,Services,DEPENSE COURANT,2200-001,1200000`;

      const blob = new Blob([template], { type: 'text/csv;charset=utf-8;' });
      const link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.download = 'CAMTEL_Import_Template.csv';
      link.click();
      URL.revokeObjectURL(link.href);
    },

    formatFileSize(bytes) {
      if (bytes === 0) return '0 Bytes';
      const k = 1024;
      const sizes = ['Bytes', 'KB', 'MB'];
      const i = Math.floor(Math.log(bytes) / Math.log(k));
      return Math.round((bytes / Math.pow(k, i)) * 100) / 100 + ' ' + sizes[i];
    },

    resetForm() {
      this.$refs.fileInput.value = '';
      this.selectedFile = null;
      this.progressPercent = 0;
      this.statusMessage = '';
      this.alertMessage = '';
    }
  }
};
</script>

<style scoped>
.import-form-container {
  padding: 20px;
  max-width: 700px;
  margin: 0 auto;
}

.import-card {
  background: white;
  border-radius: 12px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
  padding: 40px;
}

.import-header {
  margin-bottom: 30px;
  text-align: center;
}

.import-header h2 {
  font-size: 28px;
  color: #333;
  margin: 0 0 10px 0;
}

.subtitle {
  color: #666;
  font-size: 14px;
  margin: 0;
}

/* Alerts */
.alert {
  padding: 16px;
  border-radius: 8px;
  margin-bottom: 20px;
  border-left: 4px solid;
}

.alert-success {
  background-color: #d4edda;
  border-color: #28a745;
  color: #155724;
}

.alert-error {
  background-color: #f8d7da;
  border-color: #dc3545;
  color: #721c24;
}

.alert-info {
  background-color: #d1ecf1;
  border-color: #17a2b8;
  color: #0c5460;
}

.alert-content strong {
  display: block;
  margin-bottom: 8px;
}

.alert-details {
  margin-top: 10px;
  max-height: 150px;
  overflow-y: auto;
}

.detail {
  margin: 4px 0;
  font-size: 13px;
}

.detail-more {
  font-style: italic;
  color: inherit;
  opacity: 0.8;
}

/* Form */
.import-form {
  margin: 30px 0;
}

.form-group {
  margin-bottom: 24px;
}

.form-label {
  display: block;
  font-weight: 600;
  color: #333;
  margin-bottom: 8px;
}

.label-text {
  display: block;
}

.label-hint {
  font-size: 12px;
  font-weight: normal;
  color: #999;
}

.file-input-wrapper {
  position: relative;
  margin-bottom: 8px;
}

.file-input {
  position: absolute;
  opacity: 0;
  width: 100%;
  height: 100%;
  cursor: pointer;
}

.file-input-label {
  border: 2px dashed #ddd;
  border-radius: 8px;
  padding: 30px;
  text-align: center;
  background: #f9f9f9;
  cursor: pointer;
  transition: all 0.3s ease;
}

.file-input:hover + .file-input-label,
.file-input:focus + .file-input-label {
  border-color: #4CAF50;
  background: #f0f8f0;
}

.file-placeholder {
  color: #999;
  font-size: 14px;
}

.file-selected {
  color: #28a745;
  font-weight: 600;
}

.form-hint {
  display: block;
  color: #999;
  font-size: 12px;
  margin-top: 6px;
}

.form-control {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid #ddd;
  border-radius: 6px;
  font-size: 14px;
}

/* File Info */
.file-info {
  background: #f5f5f5;
  padding: 16px;
  border-radius: 8px;
  margin-bottom: 20px;
}

.info-item {
  display: flex;
  justify-content: space-between;
  padding: 8px 0;
  border-bottom: 1px solid #e0e0e0;
}

.info-item:last-child {
  border-bottom: none;
}

.info-label {
  font-weight: 600;
  color: #666;
}

.info-value {
  color: #333;
}

/* Progress */
.progress-section {
  margin: 20px 0;
}

.progress-bar {
  width: 100%;
  height: 8px;
  background: #e0e0e0;
  border-radius: 4px;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, #4CAF50, #45a049);
  transition: width 0.3s ease;
}

.progress-text {
  text-align: center;
  color: #666;
  font-size: 12px;
  margin-top: 8px;
}

/* Buttons */
.form-actions {
  display: flex;
  gap: 10px;
  margin-top: 30px;
}

.btn {
  flex: 1;
  padding: 12px 20px;
  border: none;
  border-radius: 6px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.3s ease;
}

.btn-primary {
  background: #4CAF50;
  color: white;
}

.btn-primary:hover:not(:disabled) {
  background: #45a049;
  box-shadow: 0 2px 8px rgba(76, 175, 80, 0.3);
}

.btn-secondary {
  background: #757575;
  color: white;
}

.btn-secondary:hover:not(:disabled) {
  background: #616161;
}

.btn-outline {
  background: white;
  color: #4CAF50;
  border: 2px solid #4CAF50;
}

.btn-outline:hover:not(:disabled) {
  background: #f0f8f0;
}

.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* Success Summary */
.success-summary {
  background: #d4edda;
  border: 1px solid #c3e6cb;
  border-radius: 8px;
  padding: 20px;
  margin-top: 20px;
}

.success-summary h3 {
  color: #155724;
  margin: 0 0 15px 0;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 15px;
}

.summary-item {
  background: white;
  padding: 15px;
  border-radius: 6px;
  text-align: center;
}

.summary-label {
  display: block;
  color: #666;
  font-size: 12px;
  text-transform: uppercase;
  margin-bottom: 5px;
}

.summary-value {
  display: block;
  color: #28a745;
  font-size: 24px;
  font-weight: bold;
}

/* Help Section */
.help-section {
  margin-top: 30px;
  padding-top: 20px;
  border-top: 1px solid #e0e0e0;
}

details {
  cursor: pointer;
}

summary {
  font-weight: 600;
  color: #333;
  padding: 10px;
  background: #f5f5f5;
  border-radius: 6px;
  user-select: none;
}

summary:hover {
  background: #e8e8e8;
}

.help-content {
  padding: 20px 10px;
  color: #666;
  font-size: 13px;
}

.help-content h4 {
  color: #333;
  margin-top: 15px;
  margin-bottom: 10px;
}

.help-content ul {
  margin: 0;
  padding-left: 20px;
}

.help-content li {
  margin-bottom: 8px;
}

/* Animations */
.fade-enter-active, .fade-leave-active {
  transition: opacity 0.3s ease;
}

.fade-enter, .fade-leave-to {
  opacity: 0;
}

.slideDown-enter-active, .slideDown-leave-active {
  transition: all 0.3s ease;
}

.slideDown-enter, .slideDown-leave-to {
  opacity: 0;
  transform: translateY(-10px);
}

.slideUp-enter-active, .slideUp-leave-active {
  transition: all 0.3s ease;
}

.slideUp-enter, .slideUp-leave-to {
  opacity: 0;
  transform: translateY(10px);
}

/* Responsive */
@media (max-width: 600px) {
  .import-card {
    padding: 20px;
  }

  .summary-grid {
    grid-template-columns: 1fr;
  }

  .form-actions {
    flex-direction: column;
  }
}
</style>

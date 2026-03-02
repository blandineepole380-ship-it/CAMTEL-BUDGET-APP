<template>
  <div class="import-container">
    <div class="card">
      <h2>📥 Import Budget Data</h2>
      
      <!-- Error Alert -->
      <div v-if="errorMessage" class="alert alert-danger">
        <strong>Error:</strong> {{ errorMessage }}
        <ul v-if="errorDetails.length > 0">
          <li v-for="(error, idx) in errorDetails.slice(0, 5)" :key="idx">
            {{ error }}
          </li>
          <li v-if="errorDetails.length > 5">
            ... and {{ errorDetails.length - 5 }} more errors
          </li>
        </ul>
      </div>

      <!-- Success Alert -->
      <div v-if="successMessage" class="alert alert-success">
        <strong>✓ Success!</strong> {{ successMessage }}
        <p v-if="importResult">
          Imported: <strong>{{ importResult.imported }}</strong> | 
          Failed: <strong>{{ importResult.failed }}</strong> | 
          Total: <strong>{{ importResult.totalProcessed }}</strong>
        </p>
      </div>

      <!-- File Upload Form -->
      <form @submit.prevent="handleImport">
        <div class="form-group">
          <label for="csvFile">
            <strong>Select CSV File:</strong>
            <span class="text-muted">(Max 10MB, UTF-8 encoded)</span>
          </label>
          <input
            id="csvFile"
            ref="fileInput"
            type="file"
            accept=".csv,.xlsx"
            class="form-control"
            @change="onFileSelected"
            :disabled="isLoading"
            required
          />
          <small class="form-text text-muted">
            Required columns: DATE ENGAGEMENT, DIRECTION, MONTANT, LIBELLE
          </small>
        </div>

        <!-- File Info -->
        <div v-if="selectedFile" class="alert alert-info">
          <strong>Selected File:</strong> {{ selectedFile.name }}<br>
          <strong>Size:</strong> {{ formatFileSize(selectedFile.size) }}
        </div>

        <!-- Progress Bar -->
        <div v-if="isLoading" class="progress mb-3">
          <div 
            class="progress-bar progress-bar-striped progress-bar-animated"
            role="progressbar"
            :style="{ width: progressPercent + '%' }"
            :aria-valuenow="progressPercent"
            aria-valuemin="0"
            aria-valuemax="100"
          >
            {{ progressPercent }}%
          </div>
        </div>

        <!-- Status Message -->
        <div v-if="statusMessage" class="alert alert-info">
          {{ statusMessage }}
        </div>

        <!-- Submit Button -->
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
          class="btn btn-secondary ms-2"
          @click="resetForm"
          :disabled="isLoading"
        >
          Reset
        </button>
      </form>

      <!-- Template Download -->
      <div class="mt-4 pt-4 border-top">
        <h5>📋 Need Help?</h5>
        <p>Download the CSV template to see the required format:</p>
        <button 
          type="button"
          class="btn btn-outline-primary"
          @click="downloadTemplate"
        >
          📥 Download CSV Template
        </button>
      </div>
    </div>
  </div>
</template>

<script>
export default {
  name: 'ImportBudgetData',
  data() {
    return {
      selectedFile: null,
      isLoading: false,
      progressPercent: 0,
      errorMessage: '',
      errorDetails: [],
      successMessage: '',
      statusMessage: '',
      importResult: null,
      abortController: null
    };
  },
  methods: {
    onFileSelected(event) {
      this.selectedFile = event.target.files[0];
      this.errorMessage = '';
      this.successMessage = '';
      this.errorDetails = [];
      this.importResult = null;

      // Validate file
      if (this.selectedFile) {
        if (this.selectedFile.size > 10 * 1024 * 1024) {
          this.errorMessage = 'File too large. Maximum 10MB allowed.';
          this.selectedFile = null;
          return;
        }

        const validTypes = ['text/csv', 'application/vnd.ms-excel', 
          'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'];
        if (!validTypes.includes(this.selectedFile.type)) {
          this.errorMessage = 'Invalid file type. Only CSV and XLSX allowed.';
          this.selectedFile = null;
          return;
        }
      }
    },

    async handleImport() {
      if (!this.selectedFile) {
        this.errorMessage = 'Please select a file first.';
        return;
      }

      this.isLoading = true;
      this.progressPercent = 0;
      this.statusMessage = 'Uploading file...';
      this.errorMessage = '';
      this.successMessage = '';
      this.errorDetails = [];

      const formData = new FormData();
      formData.append('file', this.selectedFile);

      // Create abort controller for timeout
      this.abortController = new AbortController();
      const timeoutId = setTimeout(() => {
        this.abortController.abort();
      }, 120000); // 2 minute timeout

      try {
        this.statusMessage = 'Processing file...';
        this.progressPercent = 30;

        const response = await fetch('/api/import', {
          method: 'POST',
          body: formData,
          signal: this.abortController.signal
        });

        this.progressPercent = 70;

        if (!response.ok) {
          const errorData = await response.json();
          throw new Error(errorData.message || `HTTP Error: ${response.status}`);
        }

        const result = await response.json();
        this.progressPercent = 100;

        if (result.success) {
          this.successMessage = result.message;
          this.importResult = result;
          this.statusMessage = '';
          this.resetForm();
          
          // Emit event to refresh data
          this.$emit('import-success', result);
        } else {
          this.errorMessage = result.message;
          this.errorDetails = result.errors || [];
        }

      } catch (error) {
        this.progressPercent = 0;
        
        if (error.name === 'AbortError') {
          this.errorMessage = 'Import timed out. Please try with a smaller file.';
        } else {
          this.errorMessage = error.message || 'Import failed. Please try again.';
        }
        
        console.error('Import error:', error);

      } finally {
        clearTimeout(timeoutId);
        this.isLoading = false;
        this.statusMessage = '';
      }
    },

    downloadTemplate() {
      const templateData = `DATE ENGAGEMENT,DIRECTION,INTITULE DE LA COMMANDE,LIBELLE,NATURE DE LA DEPENSE,IMPUTATION COMPTABLE,MONTANT
01/03/2026,DCF,Achat Serveurs,Matériel Informatique,DEPENSE COURANT,2100-001,5000000
02/03/2026,IT,Licence Logiciel,Software,DEPENSE COURANT,2100-002,2500000
03/03/2026,RH,Formation Personnel,Services,DEPENSE COURANT,2200-001,1200000`;

      const blob = new Blob([templateData], { type: 'text/csv;charset=utf-8;' });
      const link = document.createElement('a');
      const url = URL.createObjectURL(blob);
      
      link.setAttribute('href', url);
      link.setAttribute('download', 'CAMTEL_Import_Template.csv');
      link.style.visibility = 'hidden';
      
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    },

    formatFileSize(bytes) {
      if (bytes === 0) return '0 Bytes';
      const k = 1024;
      const sizes = ['Bytes', 'KB', 'MB'];
      const i = Math.floor(Math.log(bytes) / Math.log(k));
      return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
    },

    resetForm() {
      this.$refs.fileInput.value = '';
      this.selectedFile = null;
      this.progressPercent = 0;
    }
  }
};
</script>

<style scoped>
.import-container {
  max-width: 600px;
  margin: 20px auto;
}

.card {
  border: 1px solid #ddd;
  border-radius: 8px;
  padding: 30px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.form-group {
  margin-bottom: 20px;
}

.alert {
  padding: 15px;
  margin-bottom: 20px;
  border-radius: 5px;
}

.alert-success {
  background-color: #d4edda;
  color: #155724;
  border: 1px solid #c3e6cb;
}

.alert-danger {
  background-color: #f8d7da;
  color: #721c24;
  border: 1px solid #f5c6cb;
}

.alert-info {
  background-color: #d1ecf1;
  color: #0c5460;
  border: 1px solid #bee5eb;
}

.progress {
  height: 25px;
}

.progress-bar {
  font-size: 14px;
  font-weight: bold;
}

.btn {
  padding: 10px 20px;
  border-radius: 5px;
  cursor: pointer;
  transition: all 0.3s;
}

.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
</style>

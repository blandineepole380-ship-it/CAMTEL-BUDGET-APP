const express = require('express');
const multer = require('multer');
const csv = require('csv-parse');
const fs = require('fs');
const path = require('path');

const router = express.Router();

// Configure multer for file uploads
const storage = multer.memoryStorage();
const upload = multer({
  storage: storage,
  limits: {
    fileSize: 10 * 1024 * 1024 // 10MB limit
  },
  fileFilter: (req, file, cb) => {
    const allowedMimes = ['text/csv', 'application/vnd.ms-excel', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'];
    if (allowedMimes.includes(file.mimetype)) {
      cb(null, true);
    } else {
      cb(new Error('Invalid file type. Only CSV and XLSX allowed.'));
    }
  }
});

// Helper function to parse CSV
async function parseCSV(fileBuffer) {
  return new Promise((resolve, reject) => {
    const records = [];
    
    csv.parse(fileBuffer.toString('utf-8'), {
      columns: true,
      skip_empty_lines: true,
      trim: true,
      relax_column_count: true,
      encoding: 'utf-8'
    })
    .on('data', (data) => {
      records.push(data);
    })
    .on('end', () => {
      resolve(records);
    })
    .on('error', (error) => {
      reject(error);
    });
  });
}

// Helper function to validate row data
function validateRow(row, index) {
  const errors = [];
  
  if (!row['DATE ENGAGEMENT'] || row['DATE ENGAGEMENT'].trim() === '') {
    errors.push(`Row ${index}: Missing DATE ENGAGEMENT`);
  }
  
  if (!row['DIRECTION'] || row['DIRECTION'].trim() === '') {
    errors.push(`Row ${index}: Missing DIRECTION`);
  }
  
  if (!row['MONTANT'] || row['MONTANT'].trim() === '') {
    errors.push(`Row ${index}: Missing MONTANT`);
  }
  
  // Validate amount format
  const montantStr = row['MONTANT'].toString().replace(/\s/g, '').replace(',', '.');
  if (isNaN(parseFloat(montantStr))) {
    errors.push(`Row ${index}: Invalid MONTANT format`);
  }
  
  return errors;
}

// Helper function to format amount
function formatAmount(montantStr) {
  if (!montantStr) return 0;
  return parseFloat(montantStr.toString().replace(/\s/g, '').replace(',', '.'));
}

// Helper function to process data in chunks
async function processInChunks(records, chunkSize = 100, callback) {
  for (let i = 0; i < records.length; i += chunkSize) {
    const chunk = records.slice(i, i + chunkSize);
    await callback(chunk, i);
  }
}

// Main import endpoint
router.post('/import', upload.single('file'), async (req, res) => {
  try {
    // Validate file exists
    if (!req.file) {
      return res.status(400).json({
        success: false,
        message: 'No file uploaded',
        error: 'File is required'
      });
    }

    // Parse CSV
    let records;
    try {
      records = await parseCSV(req.file.buffer);
    } catch (parseError) {
      return res.status(400).json({
        success: false,
        message: 'Failed to parse CSV file',
        error: parseError.message
      });
    }

    if (records.length === 0) {
      return res.status(400).json({
        success: false,
        message: 'CSV file is empty',
        error: 'No data rows found'
      });
    }

    // Validate records
    const validationErrors = [];
    records.forEach((row, index) => {
      const rowErrors = validateRow(row, index + 1);
      validationErrors.push(...rowErrors);
    });

    if (validationErrors.length > 0) {
      return res.status(400).json({
        success: false,
        message: 'Validation failed',
        errors: validationErrors.slice(0, 10), // Return first 10 errors
        totalErrors: validationErrors.length
      });
    }

    // Process records in chunks
    let importedCount = 0;
    let failedCount = 0;
    const failedRecords = [];

    try {
      await processInChunks(records, 100, async (chunk, startIndex) => {
        for (const row of chunk) {
          try {
            // Transform data
            const transactionData = {
              dateEngagement: new Date(row['DATE ENGAGEMENT']),
              direction: row['DIRECTION'].trim(),
              intitule: row['INTITULE DE LA COMMANDE']?.trim() || '',
              libelle: row['LIBELLE']?.trim() || '',
              nature: row['NATURE DE LA DEPENSE']?.trim() || '',
              imputationComptable: row['IMPUTATION COMPTABLE']?.trim() || '',
              montant: formatAmount(row['MONTANT']),
              status: 'VALIDE', // Default status
              createdAt: new Date(),
              updatedAt: new Date()
            };

            // Save to database (adjust to your DB setup)
            // await Transaction.create(transactionData);
            
            // For now, just validate structure
            if (transactionData.montant > 0) {
              importedCount++;
            } else {
              failedRecords.push({
                row: startIndex + chunk.indexOf(row) + 1,
                reason: 'Invalid amount'
              });
              failedCount++;
            }

          } catch (error) {
            failedRecords.push({
              row: startIndex + chunk.indexOf(row) + 1,
              reason: error.message
            });
            failedCount++;
          }
        }
      });

      res.status(200).json({
        success: true,
        message: 'Import completed',
        imported: importedCount,
        failed: failedCount,
        totalProcessed: records.length,
        failedRecords: failedRecords.slice(0, 10)
      });

    } catch (processError) {
      res.status(500).json({
        success: false,
        message: 'Error processing records',
        error: processError.message,
        imported: importedCount
      });
    }

  } catch (error) {
    console.error('Import error:', error);
    res.status(500).json({
      success: false,
      message: 'Import failed',
      error: error.message
    });
  }
});

module.exports = router;

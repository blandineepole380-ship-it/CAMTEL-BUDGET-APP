/**
 * Import Route Handler
 * Handles CSV/XLSX file uploads with comprehensive validation and error handling
 */

const express = require('express');
const multer = require('multer');
const csv = require('csv-parse');
const XLSX = require('xlsx');
const { validateImportData } = require('../validators/importValidator');
const { saveTransaction } = require('../models/Transaction');

const router = express.Router();

// Configure multer
const storage = multer.memoryStorage();
const upload = multer({
  storage,
  limits: {
    fileSize: 10 * 1024 * 1024 // 10MB
  },
  fileFilter: (req, file, cb) => {
    const allowedMimes = [
      'text/csv',
      'application/vnd.ms-excel',
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    ];
    
    if (allowedMimes.includes(file.mimetype) || file.originalname.match(/\.(csv|xlsx|xls)$/i)) {
      cb(null, true);
    } else {
      cb(new Error(`Invalid file type: ${file.mimetype}`));
    }
  }
});

// ============================================
// HELPER FUNCTIONS
// ============================================

/**
 * Parse CSV file buffer
 */
async function parseCSVBuffer(buffer) {
  return new Promise((resolve, reject) => {
    const records = [];
    
    csv.parse(buffer.toString('utf-8'), {
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
      reject(new Error(`CSV parsing error: ${error.message}`));
    });
  });
}

/**
 * Parse Excel file buffer
 */
function parseExcelBuffer(buffer) {
  try {
    const workbook = XLSX.read(buffer, { type: 'buffer' });
    const sheetName = workbook.SheetNames[0];
    const worksheet = workbook.Sheets[sheetName];
    const records = XLSX.utils.sheet_to_json(worksheet);
    return records;
  } catch (error) {
    throw new Error(`Excel parsing error: ${error.message}`);
  }
}

/**
 * Normalize column names
 */
function normalizeRecord(record) {
  const normalized = {};
  Object.keys(record).forEach(key => {
    const normalizedKey = key
      .trim()
      .toUpperCase()
      .replace(/\s+/g, '_');
    normalized[normalizedKey] = record[key];
  });
  return normalized;
}

/**
 * Format monetary amount
 */
function formatAmount(value) {
  if (!value) return 0;
  const str = value.toString().replace(/\s/g, '').replace(',', '.');
  const num = parseFloat(str);
  return isNaN(num) ? 0 : num;
}

/**
 * Process records in chunks
 */
async function processInChunks(records, chunkSize = 100, processor) {
  const results = [];
  for (let i = 0; i < records.length; i += chunkSize) {
    const chunk = records.slice(i, i + chunkSize);
    const chunkResults = await processor(chunk, i);
    results.push(...chunkResults);
  }
  return results;
}

// ============================================
// ROUTE HANDLERS
// ============================================

/**
 * POST /api/import
 * Import transactions from CSV/XLSX file
 */
router.post('/', upload.single('file'), async (req, res, next) => {
  try {
    // Validate file
    if (!req.file) {
      return res.status(400).json({
        success: false,
        message: 'No file uploaded',
        code: 'NO_FILE'
      });
    }

    const { originalname, mimetype, buffer, size } = req.file;
    const year = req.body.year || new Date().getFullYear();

    console.log(`[IMPORT] Processing file: ${originalname} (${size} bytes)`);

    // Parse file based on type
    let records = [];
    try {
      if (mimetype === 'text/csv' || originalname.endsWith('.csv')) {
        records = await parseCSVBuffer(buffer);
      } else if (originalname.match(/\.(xlsx|xls)$/i)) {
        records = parseExcelBuffer(buffer);
      } else {
        throw new Error('Unsupported file format');
      }
    } catch (parseError) {
      return res.status(400).json({
        success: false,
        message: 'Failed to parse file',
        error: parseError.message,
        code: 'PARSE_ERROR'
      });
    }

    if (records.length === 0) {
      return res.status(400).json({
        success: false,
        message: 'File is empty or contains no valid data',
        code: 'EMPTY_FILE'
      });
    }

    console.log(`[IMPORT] Found ${records.length} records to process`);

    // Normalize and validate records
    const validationErrors = [];
    const validRecords = [];

    records.forEach((record, index) => {
      try {
        const normalized = normalizeRecord(record);
        const validation = validateImportData(normalized, index + 1);

        if (!validation.valid) {
          validationErrors.push({
            row: index + 1,
            errors: validation.errors
          });
        } else {
          validRecords.push({
            ...normalized,
            rowIndex: index + 1,
            year
          });
        }
      } catch (error) {
        validationErrors.push({
          row: index + 1,
          errors: [error.message]
        });
      }
    });

    // Report validation errors
    if (validationErrors.length > 0) {
      console.warn(`[IMPORT] Validation errors: ${validationErrors.length}/${records.length}`);
      
      return res.status(400).json({
        success: false,
        message: `Validation failed for ${validationErrors.length} records`,
        validationErrors: validationErrors.slice(0, 20),
        totalErrors: validationErrors.length,
        code: 'VALIDATION_ERROR'
      });
    }

    // Process valid records in chunks
    let importedCount = 0;
    let failedCount = 0;
    const failedRecords = [];

    try {
      await processInChunks(validRecords, 100, async (chunk, startIndex) => {
        const chunkResults = [];

        for (const record of chunk) {
          try {
            const transaction = {
              dateEngagement: new Date(record.DATE_ENGAGEMENT),
              direction: record.DIRECTION?.trim() || '',
              intitule: record.INTITULE_DE_LA_COMMANDE?.trim() || '',
              libelle: record.LIBELLE?.trim() || '',
              nature: record.NATURE_DE_LA_DEPENSE?.trim() || '',
              imputationComptable: record.IMPUTATION_COMPTABLE?.trim() || '',
              montant: formatAmount(record.MONTANT),
              year: record.year,
              status: 'VALIDE',
              createdAt: new Date(),
              updatedAt: new Date()
            };

            // Save to database
            await saveTransaction(transaction);
            importedCount++;
            chunkResults.push({ success: true });

          } catch (error) {
            failedCount++;
            failedRecords.push({
              row: record.rowIndex,
              error: error.message
            });
            chunkResults.push({ success: false, error: error.message });
          }
        }

        return chunkResults;
      });

      console.log(`[IMPORT] Completed: ${importedCount} imported, ${failedCount} failed`);

      res.status(200).json({
        success: true,
        message: 'Import completed successfully',
        imported: importedCount,
        failed: failedCount,
        total: records.length,
        failedRecords: failedRecords.slice(0, 10),
        totalFailedRecords: failedRecords.length,
        code: 'IMPORT_SUCCESS'
      });

    } catch (processError) {
      console.error('[IMPORT] Processing error:', processError);
      res.status(500).json({
        success: false,
        message: 'Error processing records',
        error: processError.message,
        imported: importedCount,
        code: 'PROCESS_ERROR'
      });
    }

  } catch (error) {
    console.error('[IMPORT] Unexpected error:', error);
    next(error);
  }
});

/**
 * GET /api/import/template
 * Download import template
 */
router.get('/template', (req, res) => {
  const template = `DATE ENGAGEMENT,DIRECTION,INTITULE DE LA COMMANDE,LIBELLE,NATURE DE LA DEPENSE,IMPUTATION COMPTABLE,MONTANT
01/03/2026,DCF,Achat Serveurs,Matériel Informatique,DEPENSE COURANT,2100-001,5000000
02/03/2026,IT,Licence Logiciel,Software,DEPENSE COURANT,2100-002,2500000
03/03/2026,RH,Formation Personnel,Services,DEPENSE COURANT,2200-001,1200000`;

  res.setHeader('Content-Type', 'text/csv; charset=utf-8');
  res.setHeader('Content-Disposition', 'attachment; filename="CAMTEL_Import_Template.csv"');
  res.send(template);
});

module.exports = router;

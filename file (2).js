/**
 * Import Data Validator
 * Comprehensive validation rules for budget data
 */

const VALID_NATURES = ['DEPENSE COURANT', 'DEPENSE DE CAPITAL'];
const VALID_STATUSES = ['VALIDE', 'BROUILLON', 'EN ATTENTE'];

/**
 * Validate individual record
 */
function validateImportData(record, rowIndex) {
  const errors = [];

  // Required fields
  if (!record.DATE_ENGAGEMENT || record.DATE_ENGAGEMENT.toString().trim() === '') {
    errors.push('DATE ENGAGEMENT is required');
  } else if (!isValidDate(record.DATE_ENGAGEMENT)) {
    errors.push(`Invalid DATE ENGAGEMENT format: ${record.DATE_ENGAGEMENT}`);
  }

  if (!record.DIRECTION || record.DIRECTION.toString().trim() === '') {
    errors.push('DIRECTION is required');
  }

  if (!record.MONTANT || record.MONTANT.toString().trim() === '') {
    errors.push('MONTANT is required');
  } else {
    const amount = parseFloat(record.MONTANT.toString().replace(/\s/g, '').replace(',', '.'));
    if (isNaN(amount) || amount <= 0) {
      errors.push(`Invalid MONTANT: ${record.MONTANT}`);
    }
  }

  if (!record.IMPUTATION_COMPTABLE || record.IMPUTATION_COMPTABLE.toString().trim() === '') {
    errors.push('IMPUTATION COMPTABLE is required');
  }

  // Optional but validated fields
  if (record.NATURE_DE_LA_DEPENSE && 
      !VALID_NATURES.includes(record.NATURE_DE_LA_DEPENSE.toString().toUpperCase())) {
    errors.push(`Invalid NATURE: must be one of ${VALID_NATURES.join(', ')}`);
  }

  return {
    valid: errors.length === 0,
    errors,
    rowIndex
  };
}

/**
 * Validate date format
 */
function isValidDate(dateString) {
  if (!dateString) return false;
  
  const date = new Date(dateString);
  return date instanceof Date && !isNaN(date);
}

/**
 * Validate amount format
 */
function isValidAmount(amount) {
  const str = amount.toString().replace(/\s/g, '').replace(',', '.');
  const num = parseFloat(str);
  return !isNaN(num) && num > 0;
}

module.exports = {
  validateImportData,
  isValidDate,
  isValidAmount,
  VALID_NATURES,
  VALID_STATUSES
};

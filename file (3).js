/**
 * Import Functionality Tests
 * Comprehensive test suite for data import features
 */

const request = require('supertest');
const app = require('../server');
const fs = require('fs');
const path = require('path');

describe('Import Functionality', () => {
  
  describe('POST /api/import', () => {
    
    test('should import valid CSV file successfully', async () => {
      const csvPath = path.join(__dirname, 'fixtures/valid.csv');
      
      const response = await request(app)
        .post('/api/import')
        .attach('file', csvPath)
        .field('year', '2026');

      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
      expect(response.body.imported).toBeGreaterThan(0);
    });

    test('should reject file without required fields', async () => {
      const csvPath = path.join(__dirname, 'fixtures/invalid.csv');
      
      const response = await request(app)
        .post('/api/import')
        .attach('file', csvPath);

      expect(response.status).toBe(400);
      expect(response.body.success).toBe(false);
      expect(response.body.code).toBe('VALIDATION_ERROR');
    });

    test('should reject oversized file', async () => {
      // Create a file larger than 10MB
      const largeFile = Buffer.alloc(11 * 1024 * 1024);
      
      const response = await request(app)
        .post('/api/import')
        .attach('file', largeFile, 'large.csv');

      expect(response.status).toBe(413);
    });

    test('should handle missing file gracefully', async () => {
      const response = await request(app)
        .post('/api/import');

      expect(response.status).toBe(400);
      expect(response.body.code).toBe('NO_FILE');
    });

    test('should parse amounts with different formats', async () => {
      const csvPath = path.join(__dirname, 'fixtures/amounts.csv');
      
      const response = await request(app)
        .post('/api/import')
        .attach('file', csvPath)
        .field('year', '2026');

      expect(response.status).toBe(200);
      expect(response.body.imported).toBeGreaterThan(0);
    });
  });

  describe('GET /api/import/template', () => {
    
    test('should download CSV template', async () => {
      const response = await request(app)
        .get('/api/import/template');

      expect(response.status).toBe(200);
      expect(response.headers['content-type']).toContain('text/csv');
      expect(response.headers['content-disposition']).toContain('attachment');
    });
  });
});

describe('Data Validation', () => {
  
  test('should validate required fields', () => {
    const { validateImportData } = require('../validators/importValidator');
    
    const invalidRecord = {
      DIRECTION: 'DCF'
      // Missing required fields
    };

    const result = validateImportData(invalidRecord, 1);
    expect(result.valid).toBe(false);
    expect(result.errors.length).toBeGreaterThan(0);
  });

  test('should validate date format', () => {
    const { isValidDate } = require('../validators/importValidator');
    
    expect(isValidDate('01/03/2026')).toBe(true);
    expect(isValidDate('invalid-date')).toBe(false);
    expect(isValidDate('')).toBe(false);
  });

  test('should validate amount format', () => {
    const { isValidAmount } = require('../validators/importValidator');
    
    expect(isValidAmount('5000000')).toBe(true);
    expect(isValidAmount('5,000,000')).toBe(true);
    expect(isValidAmount('5.000.000')).toBe(true);
    expect(isValidAmount('invalid')).toBe(false);
  });
});
```__

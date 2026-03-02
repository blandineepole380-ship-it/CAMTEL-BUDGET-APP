try {
  const response = await fetch('/api/import', {
    method: 'POST',
    body: formData,
    timeout: 60000 // 60 second timeout
  });
  
  if (!response.ok) {
    throw new Error(`Import failed: ${response.statusText}`);
  }
  
  const result = await response.json();
  showSuccessMessage(`${result.imported} rows imported successfully`);
  
} catch (error) {
  console.error('Import error:', error);
  showErrorMessage(`Import failed: ${error.message}`);
}

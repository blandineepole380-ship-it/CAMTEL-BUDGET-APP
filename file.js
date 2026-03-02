// Set reasonable timeout
const importTimeout = setTimeout(() => {
  abortController.abort();
  showErrorMessage('Import timed out. Please try with smaller file.');
}, 120000); // 2 minutes

fetch(url, { signal: abortController.signal })
  .finally(() => clearTimeout(importTimeout));

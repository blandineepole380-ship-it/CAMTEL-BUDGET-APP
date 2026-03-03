# ============================================
# CAMTEL BUDGET SYSTEM - ENVIRONMENT CONFIG
# ============================================

# Server Configuration
PORT=3000
NODE_ENV=production
ALLOWED_ORIGINS=http://localhost:3000,http://localhost:8080,https://camtel-budget-app.onrender.com

# Database Configuration
DATABASE_URL=postgresql://user:password@localhost:5432/camtel_budget
DATABASE_TIMEOUT=30000
DATABASE_POOL_SIZE=10

# Import Settings
MAX_UPLOAD_SIZE=10485760
IMPORT_TIMEOUT=120000
IMPORT_CHUNK_SIZE=100
FILE_ENCODING=utf-8

# API Configuration
API_TIMEOUT=120000
API_RATE_LIMIT=100

# Logging
LOG_LEVEL=info
LOG_FILE=./logs/app.log

# Security
JWT_SECRET=your_jwt_secret_key_here
ENCRYPTION_KEY=your_encryption_key_here

# Email (for notifications)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your_email@gmail.com
SMTP_PASSWORD=your_app_password

# Feature Flags
ENABLE_REPORTS=true
ENABLE_EXPORT=true
ENABLE_IMPORT=true

# Automatic backups every 24 hours
# Manual backup:
pg_dump $DATABASE_URL > backup-$(date +%Y%m%d).sql

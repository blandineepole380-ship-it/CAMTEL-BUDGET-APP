# CAMTEL Budget App (Render-ready)

This package is **made to deploy on Render without errors**.

## Deploy on Render (Docker)
1. Upload these files to your GitHub repo root.
2. In Render: **New Web Service** -> connect repo -> Environment: **Docker**.
3. Add Environment Variables:
   - `SECRET_KEY` = any long random string
   - (optional) `ADMIN_USER`, `ADMIN_PASS`
4. Deploy.

Default login: `admin / admin123`

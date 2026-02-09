# Deployctl Utility for Deploying API + DB Stack

This utility manages deployment of a stack consisting of:

- **API**: FastAPI app with a `/health` endpoint that checks database connectivity.  
- **Database**: PostgreSQL (default version 15).  

---

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## Uility usage
### deploy stack, apply migration.sql
```bash
deploy stack, apply migration.sql
```
### to specify version
```bash
python deployctl.py up -v 15.3
```
### for rollback to previous version
```bash
python deployctl.py rollback
```

# Deployctl Utility for Deploying API + DB Stack

This utility manages deployment of a stack consisting of:

- **API**: FastAPI app with a `/health` endpoint that checks database connectivity.  
- **Database**: PostgreSQL (default version 15).  

---

## Prerequisites
- Ensure docker and docker-compose are installed on you local machine, and works via non-root user
- Python installed also
- Ports 5432 and 8000 are free to use

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
python deployctl.py up
```
### to specify version
```bash
python deployctl.py up -v 15.3
```
### for rollback to previous version
```bash
python deployctl.py rollback
```

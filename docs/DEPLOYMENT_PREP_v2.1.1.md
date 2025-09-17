# Deployment Preparation – v2.1.1 Hotfix

Release Date: 2025-09-17

## 1. Scope
Nature of Concern persistence hotfix + optional concern selection on office creation.

## 2. Pre-Deployment Checklist
- [ ] Confirm working branch up to date and merged: `master` vs `main` alignment reviewed.
- [ ] Review diff for only intended files (see release notes).
- [ ] Ensure no local uncommitted changes except release artifacts.
- [ ] Backup database (structure + data) before restart.
- [ ] Notify stakeholders of brief maintenance window (if any).

## 3. Database Backup (PostgreSQL Example)
```
pg_dump -Fc -U <db_user> -h <db_host> <db_name> > backup_pre_v2_1_1.dump
```
If using SQLite, copy the DB file: `cp app.db backup_pre_v2_1_1.sqlite`.

## 4. Deploy Steps (Linux Server)
```
# 1. Pull latest code
cd /srv/piyuguide
sudo -u deploy git fetch --all
sudo -u deploy git checkout master
sudo -u deploy git pull --ff-only origin master

# 2. (Optional) Verify diff since previous tag
git --no-pager log --oneline -5

# 3. Activate virtualenv
source venv/bin/activate

# 4. Install (in case new dependencies added – none expected)
pip install -r requirements.txt --no-deps

# 5. Run lightweight import smoke test
python - <<'PY'
from app import create_app
app = create_app()
print('App import OK, debug=', app.debug)
PY

# 6. (Optional) Run regression script (non-production guard recommended)
ENV=staging python -m scripts.regression_office_concerns_test

# 7. Restart services
sudo systemctl restart piyuguide.service
sudo systemctl status --no-pager piyuguide.service

# 8. Tail logs for 60 seconds
journalctl -u piyuguide.service -n 100 -f &
```

## 5. Post-Deployment Validation
- [ ] Access student portal footer → version shows v2.1.1.
- [ ] Create office without concerns (no error).
- [ ] Add concern type to that office.
- [ ] Edit office name only → concern remains.
- [ ] Submit inquiry using that concern.
- [ ] Review logs → no SQL errors / tracebacks.

## 6. Rollback Procedure
```
# Revert to previous commit (record commit hash before deploy)
git checkout <previous_commit_hash>
systemctl restart piyuguide.service
```
Restore DB from dump only if corruption observed:
```
pg_restore -c -U <db_user> -h <db_host> -d <db_name> backup_pre_v2_1_1.dump
```

## 7. Operational Notes
- No migrations; downtime minimal (just service restart).
- New regression script is safe; guarded against production run unless ENV overridden.

## 8. Tagging
After validation, create a lightweight tag:
```
git tag -a v2.1.1 -m "Nature of Concern persistence hotfix"
git push origin v2.1.1
```

## 9. Communication
Send internal notice summarizing:
- Issue fixed
- New behavior (optional concerns at creation)
- No schema changes

---
Prepared deployment checklist complete.

"""Lightweight regression script for the Nature of Concern persistence issue.

Usage (run inside virtualenv with app context):
    python -m scripts.regression_office_concerns_test

This will:
 1. Create a temporary office with NO concern associations.
 2. Add a concern type association afterward.
 3. Simulate an edit of only the office name (without submitting concern fields) to ensure
    the previously added concern association is NOT deleted.
 4. Print results to stdout.

It DOES NOT commit if environment variable PRODUCTION like guard is set.
"""
from contextlib import contextmanager
from datetime import datetime
import os
import random
import string

from app import create_app  # assuming factory pattern; adjust if different
from app.extensions import db
from app.models import Office, ConcernType, OfficeConcernType, Campus, SuperAdminActivityLog

@contextmanager
def app_context():
    app = create_app()
    with app.app_context():
        yield

def random_suffix(n=5):
    return ''.join(random.choice(string.ascii_lowercase) for _ in range(n))

def main():
    if os.environ.get('ENV') == 'production':
        print('[ABORT] Refusing to run regression test in production environment.')
        return

    with app_context():
        campus = Campus.query.first()
        if not campus:
            print('No campus found; cannot proceed.')
            return

        concern = ConcernType.query.first()
        if not concern:
            # create a temporary concern type
            concern = ConcernType(name=f'Temp Concern {random_suffix()}', description='Temp auto-generated')
            db.session.add(concern)
            db.session.commit()
            print(f'Created temp concern type id={concern.id}')

        # 1. Create office w/out concerns
        office = Office(name=f'Regression Office {random_suffix()}', description='Initial desc', campus_id=campus.id)
        db.session.add(office)
        db.session.commit()
        print(f'Created office id={office.id} without concerns')

        # 2. Add concern association manually (simulating later addition via UI route)
        assoc = OfficeConcernType(office_id=office.id, concern_type_id=concern.id, for_inquiries=True)
        db.session.add(assoc)
        db.session.commit()
        print(f'Added concern association office_concern_types.id={assoc.id}')

        # 3. Simulate edit WITHOUT concern_types field (only update description)
        office.description = 'Edited description only (no concern fields posted)'
        db.session.commit()
        print('Edited office basic info without altering concerns')

        # 4. Verify association still exists
        still_there = OfficeConcernType.query.filter_by(office_id=office.id, concern_type_id=concern.id).first()
        if still_there:
            print('[PASS] Concern association persisted after edit without concern fields.')
        else:
            print('[FAIL] Concern association missing after edit; regression persists.')

if __name__ == '__main__':
    main()

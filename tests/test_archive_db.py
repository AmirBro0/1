import hashlib
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from app import db


def upload(tmp_path, name='upload.mov', payload=b'fixture-video'):
    path = tmp_path / name
    path.write_bytes(payload)
    return path, hashlib.sha256(payload).hexdigest()


def new_run(tmp_path, *, key=None, payload=b'fixture-video', name='clip.mov', origin='ui', config=None):
    path, digest = upload(tmp_path, 'temp-' + str(len(list(tmp_path.glob('temp-*')))) + '.mov', payload)
    return db.create_run(tmp_path, path, name, 'video/quicktime', digest, key, digest + ':settings', origin, config)


def reports(job_id):
    api = {'job_id': job_id, 'status': 'done', 'verdict': 'violation', 'violations': [
        {'type': 'V13', 'timecode_sec': 2, 'description': 'Observed', 'evidence_frames': []}]}
    ui = {'verdict': 'violation', 'violations': [{'rule': {'id': 'V13'}, 'timecode': 2}],
          'review': [{'rule': {'id': 'X00'}, 'timecode': 3}], 'video': {'duration_sec': 10}, 'notes': ['real note']}
    return api, ui


@pytest.fixture(autouse=True)
def initialized(tmp_path):
    db.init(tmp_path)


def test_upload_idempotency_blob_dedup_and_intentional_new_run(tmp_path):
    first = new_run(tmp_path, key='request-A', config={'threshold': .5, 'API_KEY': 'never-save'})
    run = db.get_run(tmp_path, first['job_id'])
    assert run['config_snapshot'] == {'threshold': .5}
    assert run['asset']['availability'] == 'available'
    assert run['accepted_at'] > 0
    again = new_run(tmp_path, key='request-A', config={'threshold': .5, 'API_KEY': 'never-save'})
    assert again == {'job_id': first['job_id'], 'created': False}
    second = new_run(tmp_path, key='request-B')
    assert second['job_id'] != first['job_id']
    assert db.get_run(tmp_path, second['job_id'])['asset']['id'] == run['asset']['id']
    assert len(list((tmp_path / 'assets').iterdir())) == 1
    assert not list(tmp_path.glob('temp-*'))
    with pytest.raises(ValueError, match='Ключ'):
        new_run(tmp_path, key='request-A', payload=b'different-video', config={'threshold': .5})
    assert db.list_runs(tmp_path)['total'] == 2


def test_concurrent_same_key_creates_one_run(tmp_path):
    paths = [upload(tmp_path, f'race-{i}.mov') for i in range(5)]
    def accept(item):
        path, digest = item
        return db.create_run(tmp_path, path, 'clip.mov', 'video/quicktime', digest, 'same-key', digest)
    with ThreadPoolExecutor(max_workers=5) as pool:
        results = list(pool.map(accept, paths))
    assert len({r['job_id'] for r in results}) == 1
    assert sum(r['created'] for r in results) == 1
    assert db.list_runs(tmp_path)['total'] == 1
    assert not any(path.exists() for path, _ in paths)


def test_atomic_claim_and_progress_execution_fence(tmp_path):
    ids = {new_run(tmp_path, payload=str(i).encode())['job_id'] for i in range(4)}
    with ThreadPoolExecutor(max_workers=8) as pool:
        claims = list(pool.map(lambda _: db.claim_next(tmp_path), range(8)))
    claims = [c for c in claims if c]
    assert {c['id'] for c in claims} == ids
    assert len(claims) == 4
    job = claims[0]
    assert job['status'] == 'processing' and job['revision'] == 1 and job['execution_token']
    assert not db.set_progress(tmp_path, job['id'], 'detect', .5, token='obsolete')
    assert db.set_progress(tmp_path, job['id'], 'detect', .5, token=job['execution_token'])
    api, ui = reports(job['id'])
    assert not db.complete_run(tmp_path, job['id'], api, ui, execution_token='obsolete')
    assert db.complete_run(tmp_path, job['id'], api, ui, execution_token=job['execution_token'])
    assert not db.fail(tmp_path, job['id'], 'late error', execution_token=job['execution_token'])
    assert db.get_run(tmp_path, job['id'])['status'] == 'done'


def test_full_report_stable_ids_review_and_summary_pagination(tmp_path):
    run_id = new_run(tmp_path, name='Bank A.mov')['job_id']
    api, ui = reports(run_id)
    assert db.complete_run(tmp_path, run_id, api, ui)
    run = db.get_run(tmp_path, run_id)
    event = run['result']['violations'][0]['event_id']
    assert run['api_result'] == api
    assert 'event_id' not in ui['violations'][0]  # caller payload is untouched
    assert run['asset']['duration_sec'] == 10
    reviewed = db.patch_review(tmp_path, run_id, {'review_status': 'reviewed', 'last_playback_sec': 99,
                                                  'reviewed_event_ids': [event, event]})
    assert reviewed['last_playback_sec'] == 10
    assert reviewed['reviewed_event_ids'] == [event]
    with pytest.raises(ValueError, match='принадлежит'):
        db.patch_review(tmp_path, run_id, {'reviewed_event_ids': ['another-run-event']})
    assert db.complete_run(tmp_path, run_id, {'corrupt': 'late callback'}, {})
    assert db.get_run(tmp_path, run_id)['api_result'] == api
    assert db.get_run(tmp_path, run_id)['result']['violations'][0]['event_id'] == event
    listed = db.list_runs(tmp_path, search='Bank A', status='completed', review_status='reviewed', limit=1)
    assert listed['total'] == 1 and listed['items'][0]['violation_count'] == 1
    assert 'result' not in listed['items'][0]
    assert db.list_runs(tmp_path, offset=1)['items'] == []


def test_shared_asset_deleted_only_after_last_run_and_reader(tmp_path):
    first, second = new_run(tmp_path)['job_id'], new_run(tmp_path)['job_id']
    with db.asset_reader(tmp_path, second) as path:
        assert path.is_file()
        assert db.delete_run(tmp_path, first)
        assert path.is_file()
        assert db.delete_run(tmp_path, second)
        assert path.is_file()  # open response still owns a lease
        assert db.get_run(tmp_path, first) is None
        assert db.get_run(tmp_path, second) is None
        with pytest.raises(FileNotFoundError):
            with db.asset_reader(tmp_path, second):
                pass
    assert not path.exists()
    assert db.delete_run(tmp_path, second)  # idempotent tombstone


def test_running_delete_waits_for_worker_and_cannot_resurrect(tmp_path):
    run_id = new_run(tmp_path, key='will-delete')['job_id']
    job = db.claim_next(tmp_path)
    path = db.get_job(tmp_path, run_id)['file_path']
    from pathlib import Path
    path = Path(path)
    db.delete_run(tmp_path, run_id)
    assert path.exists()
    assert db.get_run(tmp_path, run_id) is None
    assert not db.complete_run(tmp_path, run_id, *reports(run_id), execution_token=job['execution_token'])
    assert not path.exists()
    assert db.list_runs(tmp_path)['total'] == 0
    with pytest.raises(ValueError, match='удалённой'):
        new_run(tmp_path, key='will-delete')


def test_disk_failure_preserves_staged_result_and_retry_does_not_analyze(tmp_path, monkeypatch):
    run_id = new_run(tmp_path)['job_id']
    job = db.claim_next(tmp_path)
    actual_connect = db.connect
    calls = 0
    def fail_second_connect(data_dir):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise sqlite3.OperationalError('disk is full')
        return actual_connect(data_dir)
    monkeypatch.setattr(db, 'connect', fail_second_connect)
    with pytest.raises(sqlite3.OperationalError):
        db.complete_run(tmp_path, run_id, *reports(run_id), execution_token=job['execution_token'])
    monkeypatch.setattr(db, 'connect', actual_connect)
    fallback = db.get_run(tmp_path, run_id)
    assert fallback['status'] == 'done'
    assert fallback['archive_status'] == 'save_failed'
    assert fallback['result']['notes'] == ['real note']
    saved = db.retry_save(tmp_path, run_id)
    assert saved['archive_status'] == 'saved'
    assert saved['api_result'] == reports(run_id)[0]
    assert not (tmp_path / 'staged' / f'{run_id}.json').exists()


def test_recovery_fails_running_preserves_pending_and_staged_checkpoint(tmp_path):
    first = new_run(tmp_path)['job_id']
    job = db.claim_next(tmp_path)
    queued = new_run(tmp_path, payload=b'another')['job_id']
    api, ui = reports(first)
    staged = tmp_path / 'staged'
    staged.mkdir()
    (staged / f'{first}.json').write_text(json.dumps({'api': api, 'result': ui,
                                                    'execution_token': job['execution_token']}), encoding='utf-8')
    db.recover_interrupted(tmp_path)
    assert db.get_job(tmp_path, first)['status'] == 'failed'
    assert db.get_job(tmp_path, first)['stage'] == 'interrupted'
    assert db.get_job(tmp_path, queued)['status'] == 'queued'
    assert not db.set_progress(tmp_path, first, 'detect', .9, token=job['execution_token'])
    assert db.retry_save(tmp_path, first)['status'] == 'done'
    assert db.claim_next(tmp_path)['id'] == queued


def test_legacy_sqlite_and_oko_import_are_lossless_partial_and_idempotent(tmp_path):
    legacy = tmp_path / 'legacy'
    legacy.mkdir()
    original, _ = upload(legacy, 'old.mov')
    raw = {'job_id': 'old', 'status': 'done', 'verdict': 'no_violation', 'violations': [], 'extra': 'keep'}
    with sqlite3.connect(legacy / 'jobs.sqlite3') as conn:
        conn.execute('''CREATE TABLE jobs(id TEXT PRIMARY KEY,file_path TEXT NOT NULL,status TEXT NOT NULL,
            result_json TEXT,error TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP,updated_at TEXT DEFAULT CURRENT_TIMESTAMP)''')
        conn.execute('INSERT INTO jobs(id,file_path,status,result_json) VALUES(?,?,?,?)',
                     ('old', str(original), 'done', json.dumps(raw)))
    folder = legacy / 'jobs' / 'a1b2c3d4'
    folder.mkdir(parents=True)
    api, ui = reports('a1b2c3d4')
    (folder / 'api.json').write_text(json.dumps(api), encoding='utf-8')
    (folder / 'ui.json').write_text(json.dumps({'job_id': 'a1b2c3d4', 'result': ui}), encoding='utf-8')
    db.init(legacy)
    backups = list((legacy / 'backups').glob('legacy-before-integration-*.sqlite3'))
    assert len(backups) == 1
    backup_bytes = backups[0].read_bytes()
    with sqlite3.connect(backups[0]) as backup:
        assert 'video_asset_id' not in {r[1] for r in backup.execute('PRAGMA table_info(jobs)')}
        assert json.loads(backup.execute('SELECT result_json FROM jobs WHERE id=?', ('old',)).fetchone()[0]) == raw
    db.init(legacy)
    assert list((legacy / 'backups').glob('legacy-before-integration-*.sqlite3')) == backups
    assert backups[0].read_bytes() == backup_bytes
    assert db.list_runs(legacy)['total'] == 2
    assert original.exists()
    assert db.get_run(legacy, 'old')['api_result'] == raw
    imported = db.get_run(legacy, 'a1b2c3d4')
    assert imported['archive_status'] == 'partial'
    assert imported['asset']['availability'] == 'missing'
    assert imported['result']['notes'] == ['real note']
    assert imported['result']['violations'][0]['event_id']
    assert json.loads((folder / 'api.json').read_text(encoding='utf-8')) == api


def test_ttl_never_expires_ui_archive_but_api_is_temporary(tmp_path):
    ui = new_run(tmp_path)['job_id']
    api = new_run(tmp_path, payload=b'api-only', origin='api')['job_id']
    db.complete_run(tmp_path, ui, *reports(ui))
    db.complete_run(tmp_path, api, *reports(api))
    assert db.get_run(tmp_path, ui)['asset']['availability'] == 'available'
    assert db.get_run(tmp_path, api)['asset']['availability'] == 'missing'
    with db.connect(tmp_path) as conn:
        conn.execute("UPDATE jobs SET updated_at=datetime('now','-100 hours')")
    assert db.purge_expired(tmp_path, 24) == 1
    assert db.get_run(tmp_path, ui)
    assert db.get_run(tmp_path, api) is None
    assert db.list_runs(tmp_path)['total'] == 1


def test_queue_limit_is_atomic_but_retry_still_returns_original(tmp_path):
    run_id = new_run(tmp_path, key='one', config={'max_queue': 1})['job_id']
    assert new_run(tmp_path, key='one', config={'max_queue': 1}) == {'job_id': run_id, 'created': False}
    with pytest.raises(db.QueueFullError):
        new_run(tmp_path, key='two', config={'max_queue': 1})
    assert db.list_runs(tmp_path)['total'] == 1


def test_late_completion_cannot_convert_model_failure_to_success(tmp_path):
    run_id = new_run(tmp_path)['job_id']
    job = db.claim_next(tmp_path)
    assert db.fail(tmp_path, run_id, 'модель недоступна', execution_token=job['execution_token'])
    assert not db.complete_run(tmp_path, run_id, *reports(run_id), execution_token=job['execution_token'])
    run = db.get_run(tmp_path, run_id)
    assert run['status'] == 'failed' and run['result'] is None
    assert not (tmp_path / 'staged' / f'{run_id}.json').exists()


def test_unicode_history_search_and_failed_save_filter(tmp_path):
    run_id = new_run(tmp_path, name='Банк Касса.mov')['job_id']
    assert db.list_runs(tmp_path, search='бАНК')['total'] == 1
    job = db.claim_next(tmp_path)
    staged = tmp_path / 'staged'
    staged.mkdir()
    api, result = reports(run_id)
    (staged / f'{run_id}.json').write_text(json.dumps({'api': api, 'result': result,
                                                     'execution_token': job['execution_token']}), encoding='utf-8')
    assert db.mark_save_failed(tmp_path, run_id)
    listed = db.list_runs(tmp_path, status='save_failed')
    assert listed['total'] == 1 and listed['items'][0]['status'] == 'done'
    assert db.retry_save(tmp_path, run_id)['archive_status'] == 'saved'


def test_legacy_backup_includes_committed_uncheckpointed_wal(tmp_path):
    legacy = tmp_path / 'wal-legacy'
    legacy.mkdir()
    source = sqlite3.connect(legacy / 'jobs.sqlite3')
    try:
        source.execute('PRAGMA journal_mode=WAL')
        source.execute('PRAGMA wal_autocheckpoint=0')
        source.execute('''CREATE TABLE jobs(id TEXT PRIMARY KEY,file_path TEXT NOT NULL,status TEXT NOT NULL,
            result_json TEXT,error TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP,updated_at TEXT DEFAULT CURRENT_TIMESTAMP)''')
        raw = {'job_id': 'wal-job', 'status': 'done', 'verdict': 'no_violation', 'violations': []}
        source.execute('INSERT INTO jobs(id,file_path,status,result_json) VALUES(?,?,?,?)',
                       ('wal-job', str(legacy / 'removed.mov'), 'done', json.dumps(raw)))
        source.commit()
        assert (legacy / 'jobs.sqlite3-wal').stat().st_size > 0
        db.init(legacy)
        backup_path, = (legacy / 'backups').glob('legacy-before-integration-*.sqlite3')
        with sqlite3.connect(backup_path) as backup:
            restored = backup.execute('SELECT result_json FROM jobs WHERE id=?', ('wal-job',)).fetchone()
            assert restored and json.loads(restored[0]) == raw
            assert 'video_asset_id' not in {r[1] for r in backup.execute('PRAGMA table_info(jobs)')}
    finally:
        source.close()

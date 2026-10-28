#!/usr/bin/env python3
"""Check ESTEC vacancy links in report-only mode.

Run from the repository root. Only independently confirmed HTTP 404/410
responses are reported for manual review. This script never writes files.
Network errors, 403, 429, and redirects are inconclusive.
"""

import concurrent.futures
import datetime as dt
import json
import os
from pathlib import Path
import re
import time
import urllib.error
import urllib.request

SHARDS = (
    'esa', 'telespazio', 'atg', 'starion', 'ssc', 'he-space',
    'terma-serco', 'ets-axient', 'secondary', 'other',
)
DATA_DIR = Path('data/vacancies')
REQUEST_DIR = Path('data/requests')
USER_AGENT = 'Mozilla/5.0 (compatible; ESTECVacancyWatch-LinkCheck/1.0)'
TIMEOUT = 18
WORKERS = 5


def fetch_status(url):
    request = urllib.request.Request(url, headers={
        'User-Agent': USER_AGENT,
        'Accept': 'text/html,application/xhtml+xml,application/pdf,*/*;q=0.8',
    })
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            # urlopen follows redirects; a successful generic careers page is
            # not proof that the specific vacancy is still open.
            return response.status, response.geturl(), None
    except urllib.error.HTTPError as exc:
        return exc.code, url, None
    except Exception as exc:
        return None, url, type(exc).__name__


def check(entry):
    shard, vacancy = entry
    url = vacancy.get('url', '')
    if not isinstance(url, str) or not url.startswith(('https://', 'http://')):
        return shard, vacancy, 'uncertain', 'Missing or invalid URL'

    first, final_url, error = fetch_status(url)
    if first in (404, 410):
        time.sleep(2)
        second, _, second_error = fetch_status(url)
        if second in (404, 410):
            return shard, vacancy, 'gone', f'HTTP {first}, then {second}'
        return shard, vacancy, 'uncertain', f'HTTP {first}, then {second or second_error}'
    if error:
        return shard, vacancy, 'uncertain', error
    if first != 200:
        return shard, vacancy, 'uncertain', f'HTTP {first}'
    if final_url.rstrip('/') != url.rstrip('/'):
        return shard, vacancy, 'uncertain', f'Redirected to {final_url}'
    return shard, vacancy, 'ok', 'HTTP 200'


def main():
    entries = []
    for shard in SHARDS:
        path = DATA_DIR / f'{shard}.json'
        db = json.loads(path.read_text(encoding='utf-8'))
        for vacancy in db['vacancies']:
            if vacancy.get('status', 'active') not in ('closed', 'withdrawn', 'expired'):
                entries.append((shard, vacancy))

    counts = {'ok': 0, 'uncertain': 0, 'gone': 0}
    gone_by_shard = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for shard, vacancy, result, reason in pool.map(check, entries):
            counts[result] += 1
            if result != 'ok':
                print(f'{result.upper():9} [{shard}] {vacancy.get("title")} — {reason} — {vacancy.get("url")}')
            if result == 'gone':
                gone_by_shard.setdefault(shard, []).append((vacancy, reason))

    print('SUMMARY:', json.dumps(counts))
    print('REPORT ONLY: no request files created and no vacancy records changed.')
    print('Confirmed HTTP 404/410 candidates require manual review before closure.')



if __name__ == '__main__':
    main()

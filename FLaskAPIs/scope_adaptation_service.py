#!/usr/bin/env python3
"""Diagnostic-only frozen-SCOPE control; ordinary SCOPE scoring is unchanged.

Both modes keep scoring and logging the same requests. In frozen mode, replies
retain the last applied configuration from the first request at/after the
cutoff. This isolates actuation, not controller runtime or best-static tuning.
"""
import json
import math
import os

from flask import request
import numpy as np
import scope_diagnostic_service as diagnostic

service = diagnostic.service
MODE = os.environ.get('SCOPE_ADAPTATION_MODE', 'adaptive')
FREEZE_AT = float(os.environ['SCOPE_ADAPTATION_FREEZE_SECONDS'])
if MODE not in ('adaptive', 'frozen') or not math.isfinite(FREEZE_AT) or FREEZE_AT <= 0:
    raise ValueError('Invalid adaptation control settings')
ORIGINAL_SCORE = service._score_candidates
ORIGINAL_HEALTH = service.health


def apply_control(scores, candidates, base, settings, timestamp, mode, cutoff):
    if settings['variant'] != 'SCOPE' or not math.isfinite(timestamp):
        raise ValueError('Adaptation check requires SCOPE and a finite timestamp')
    frozen = mode == 'frozen' and timestamp >= cutoff
    settings.update(control_mode=mode, freeze_after_seconds=cutoff,
                    control_frozen=frozen,
                    optimizer_recommended_index=int(scores['best_index']))
    if frozen:
        current = service._current_candidate(base)
        vector = np.array([current[c] for c in service.CANDIDATE_COLUMNS])
        matches = np.flatnonzero(np.all(np.isclose(
            candidates[service.CANDIDATE_COLUMNS].to_numpy(), vector,
            rtol=0, atol=1e-9), axis=1))
        if len(matches) != 1:
            raise ValueError('Frozen control requires exactly one current candidate')
        scores['best_index'] = int(matches[0])
        # Selection was forced by the experimental control, not the hard budget.
        scores['constraint_active'] = False
    return scores


def controlled_score(base, app_weights, candidates, settings):
    scores = ORIGINAL_SCORE(base, app_weights, candidates, settings)
    timestamp = float(request.get_json(force=True)['timestamp'])
    return apply_control(scores, candidates, base, settings, timestamp, MODE, FREEZE_AT)


def controlled_health():
    response = ORIGINAL_HEALTH()
    body = response.get_json()
    body.update(control_mode=MODE, freeze_after_seconds=FREEZE_AT)
    return service.jsonify(body)


service._score_candidates = controlled_score
service.app.view_functions['health'] = controlled_health
metadata = diagnostic.SESSION_DIR/'metadata.json'
record = json.loads(metadata.read_text())
record.update(purpose='paired adaptation diagnostic; frozen mode overrides actuation',
              control_mode=MODE, freeze_after_seconds=FREEZE_AT)
metadata.write_text(json.dumps(record, indent=2))

if __name__ == '__main__':
    service.app.run(host='127.0.0.1', port=service.PORT)

#!/usr/bin/env python3
"""Isolated diagnostic wrapper: ordinary SCOPE, optionally frozen at a cutoff.

Uses the model and optimizer copied from the source pilot. No Java or routing
change is required. The frozen control follows ordinary SCOPE before the cutoff
and holds the configuration already in force at its first later request.
"""
from __future__ import annotations
import math
import os
import json


class FreezeControl:
    def __init__(self, cutoff=None):
        if cutoff is not None and (not math.isfinite(cutoff) or cutoff<=0):
            raise ValueError('Freeze cutoff must be positive and finite')
        self.cutoff=cutoff
        self.identity=None
        self.last_time=-math.inf
        self.seen_before=False
        self.frozen=None

    def observe(self, data, current):
        identity=tuple(data[k] for k in ('iteration','simulation_seed','num_devices','policy','run_id'))
        timestamp=float(data['timestamp'])
        if not math.isfinite(timestamp) or timestamp<=self.last_time:
            raise ValueError('Non-increasing request time')
        if self.identity is not None and identity!=self.identity:
            raise ValueError('A service process must serve exactly one simulation')
        if data['policy']!='SCOPE':raise ValueError('Lambda check requires policy SCOPE with its hard bound')
        self.identity=identity;self.last_time=timestamp
        if self.cutoff is None or timestamp<self.cutoff:
            self.seen_before=True
            return False
        if not self.seen_before:raise ValueError('Frozen control has no pre-cutoff history')
        current=tuple(float(x) for x in current)
        if self.frozen is None:self.frozen=current
        if len(current)!=len(self.frozen) or any(abs(x-y)>1e-9 for x,y in zip(current,self.frozen)):
            raise ValueError('Configuration changed after the freeze cutoff')
        return True


def serve():
    # Delayed imports keep the control independently testable without model I/O.
    import numpy as np
    import scope_diagnostic_service as diagnostic
    service=diagnostic.service
    raw=os.environ.get('SCOPE_FREEZE_AFTER_SECONDS','')
    cutoff=float(raw) if raw else None
    control=FreezeControl(cutoff)
    metadata_path=diagnostic.SESSION_DIR/'metadata.json'
    metadata=json.loads(metadata_path.read_text())
    metadata.update(purpose='Lambda calibration with explicit adaptive or pre-shift-frozen control',
                    lambda_check_wrapper=1,freeze_after_seconds=cutoff,
                    control_note='Frozen control follows ordinary SCOPE before cutoff and then holds the configuration already in force. Counterfactual predictions after cutoff are logged but never applied.')
    metadata_path.write_text(json.dumps(metadata,indent=2)+'\n')
    original_score=service._score_candidates
    original_health=service.app.view_functions['health']

    def score(base, app_weights, candidates, settings):
        data=service.request.get_json(force=True)
        current=service._current_candidate(base)
        vector=[current[c] for c in service.CANDIDATE_COLUMNS]
        frozen=control.observe(data,vector)
        scores=original_score(base,app_weights,candidates,settings)
        settings.update(freeze_after_seconds=cutoff,selection_mode='frozen' if frozen else 'adaptive',
                        counterfactual_best_index=int(scores['best_index']))
        if frozen:
            match=np.flatnonzero(np.all(np.isclose(
                candidates[service.CANDIDATE_COLUMNS].to_numpy(),vector,rtol=0,atol=1e-9),axis=1))
            if len(match)!=1:raise ValueError('Frozen configuration must occur exactly once in the candidate batch')
            scores['best_index']=int(match[0])
        return scores

    def health():
        value=original_health().get_json()
        value.update(lambda_check_wrapper=1,freeze_after_seconds=cutoff)
        return service.jsonify(value)

    service._score_candidates=score
    service.app.view_functions['health']=health
    service.app.run(host='127.0.0.1',port=service.PORT,threaded=False)


if __name__=='__main__':serve()

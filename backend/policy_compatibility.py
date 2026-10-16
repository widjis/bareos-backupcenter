"""Fail-closed live-policy capability checks, independent of local feature flags."""
ADVANCED_FIELDS=frozenset({'triggerMode','afterJob','windowEndWita','retryCount','retryIntervalMinutes'})
BLOCKER='The Bareos policy helper is older than the local scheduling contract. Synchronize and verify the helper before live Apply.'

def helper_compatible(result):
    rows=result.get('jobs')
    return isinstance(rows,list) and bool(rows) and all(isinstance(row,dict) and ADVANCED_FIELDS<=row.keys() for row in rows)

def current_capabilities(result,configured):
    compatible=helper_compatible(result)
    ready=compatible and result.get('executionReady') is True
    reason=None if ready else (BLOCKER if not compatible else 'Scheduling execution has not passed native acceptance. Live Apply remains disabled.')
    return {**result,'applyEnabled':bool(configured and ready),'helperCompatible':compatible,'liveApplyBlocker':reason}

def local_preview(result,reason=BLOCKER):
    return {**result,'applyEnabled':False,'targetVerified':False,'verification':'Local preview only','liveApplyBlocker':reason}

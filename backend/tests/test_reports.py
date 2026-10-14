from datetime import date
from backend.reports import period,csv_report,csv_safe
import pytest


def test_wita_day_boundaries_are_inclusive():
    a,b=period(date(2026,10,14),date(2026,10,14))
    assert a.isoformat()=='2026-10-14T00:00:00+08:00'
    assert b.isoformat()=='2026-10-15T00:00:00+08:00'
    assert (b-a).total_seconds()==86400


@pytest.mark.parametrize('value',['=SUM(1,2)',' +formula','@formula','\tformula'])
def test_spreadsheet_formula_cells_are_neutralized(value):
    assert csv_safe(value).startswith("'")


def test_report_limits_date_range_and_labels_coverage():
    with pytest.raises(ValueError):period(date(2026,10,14),date(2026,10,13))
    with pytest.raises(ValueError):period(date(2025,1,1),date(2026,10,14))
    output=csv_report({'dateFrom':'2026-10-14','dateTo':'2026-10-14','coverage':'Observed only','total':1,'sessions':[{'id':1,'name':'=malicious','started':'2026-10-14T00:00:00+00:00','ended':None}]})
    assert "'=malicious" in output and '2026-10-14T08:00:00+08:00' in output
    assert 'Observed only' in output

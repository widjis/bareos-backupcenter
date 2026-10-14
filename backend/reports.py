"""Scoped observed-session reports with explicit coverage and safe CSV output."""
import csv
import io
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

ZONE=ZoneInfo("Asia/Makassar")


def period(start,end):
    if end<start or (end-start).days>365:raise ValueError("Choose a date period from 1 through 366 days.")
    return datetime.combine(start,time.min,ZONE),datetime.combine(end+timedelta(days=1),time.min,ZONE)


def csv_safe(value):
    text=str(value if value is not None else "")
    if text.lstrip().startswith(("=","+","-","@")) or text.startswith(("\t","\r","\n")):text="'"+text
    return text


def csv_report(report):
    out=io.StringIO(newline="")
    writer=csv.writer(out)
    writer.writerow(["Backup session report","Timezone: Asia/Makassar",report["dateFrom"],report["dateTo"]])
    writer.writerow(["Environment",csv_safe(report.get("scope",{}).get("name","Configured environment"))])
    def local(value):
        return datetime.fromisoformat(value).astimezone(ZONE).isoformat() if value else "Unknown"
    writer.writerow(["First observation WITA",local(report.get("firstObservation")),"Last observation WITA",local(report.get("lastObservation")),"Generated WITA",local(report.get("generatedAt"))])
    writer.writerow(["Coverage",report["coverage"],"Observed rows",report["total"],"Exported rows",len(report["sessions"])])
    writer.writerow(["JobId","Backup job","Level","Last observed result","Started WITA","Ended WITA","Recorded bytes","Files","Errors"])
    for row in report["sessions"]:
        dates=[]
        for key in ("started","ended"):
            value=row.get(key)
            dates.append(datetime.fromisoformat(value).astimezone(ZONE).isoformat() if value else "")
        writer.writerow([csv_safe(x) for x in [row.get("id"),row.get("name"),row.get("level"),row.get("status"),*dates,row.get("bytes"),row.get("files"),row.get("errors")]])
    return out.getvalue()

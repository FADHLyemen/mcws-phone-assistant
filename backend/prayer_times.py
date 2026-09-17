"""Live prayer & iqama times, parsed from the AthanPlus monthly widget.

Defaults to MCWS (masjid_id RKxwV5dO). To use a different masjid that publishes
on AthanPlus, set the ATHANPLUS_MASJID_ID environment variable to its id.
"""
import os, re, requests
from datetime import date, datetime, timedelta
from bs4 import BeautifulSoup

MASJID_ID = os.environ.get("ATHANPLUS_MASJID_ID", "RKxwV5dO")
WIDGET = "https://timing.athanplus.com/masjid/widgets/monthly"
PRAYERS = ["fajr", "dhuhr", "asr", "maghrib", "isha"]

def _fetch_month(d: date):
    params = {"theme": "1", "masjid_id": MASJID_ID, "date": d.strftime("%Y-%m-01")}
    r = requests.get(WIDGET, params=params, timeout=20,
                     headers={"User-Agent": "MCWS-Assistant"})
    r.raise_for_status()
    return BeautifulSoup(r.text, "lxml")

def _parse(soup):
    """Return {day_int: {'adhan': {...}, 'iqama': {...}, 'sunrise': str}} plus jumuah."""
    out = {}
    tt = soup.find("table", id="time-table")
    for tr in tt.find_all("tr"):
        cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
        if len(cells) == 9 and cells[0].isdigit():
            day = int(cells[0])
            # day, hijri, dow, FAJR, SUNRISE, DHUHR, ASR, MAGHRIB, ISHA
            out.setdefault(day, {})["adhan"] = {
                "fajr": cells[3], "dhuhr": cells[5], "asr": cells[6],
                "maghrib": cells[7], "isha": cells[8],
            }
            out[day]["sunrise"] = cells[4]
    iq = soup.find("table", id="iqamah-table")
    for tr in iq.find_all("tr"):
        cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
        if len(cells) == 6 and re.match(r"[A-Z]{3},\s*\d", cells[0]):
            day = int(cells[0].split(",")[1])
            out.setdefault(day, {})["iqama"] = {
                "fajr": cells[1], "dhuhr": cells[2], "asr": cells[3],
                "maghrib": cells[4], "isha": cells[5],
            }
    jt = soup.find("table", id="jumuah-table")
    jumuah = []
    if jt:
        for tr in jt.find_all("tr"):
            cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
            for c in cells:
                if re.match(r"\d{1,2}:\d{2}\s*(AM|PM)", c):
                    jumuah.append(c)
    return out, jumuah

def get_prayer_times(d: date = None):
    """Adhan + iqama for a specific date (default today, US/Eastern)."""
    if d is None:
        try:
            from zoneinfo import ZoneInfo
            d = datetime.now(ZoneInfo("America/Detroit")).date()
        except Exception:
            d = date.today()
    soup = _fetch_month(d)
    month, jumuah = _parse(soup)
    day = month.get(d.day)
    if not day:
        return {"error": "no data for %s" % d.isoformat()}
    return {
        "date": d.isoformat(),
        "weekday": d.strftime("%A"),
        "adhan": day.get("adhan", {}),
        "iqama": day.get("iqama", {}),
        "sunrise": day.get("sunrise"),
        "jumuah": jumuah,
        "source": "AthanPlus (MCWS)",
    }

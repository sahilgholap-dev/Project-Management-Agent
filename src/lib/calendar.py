"""Working-calendar date math (client_config.working_calendar).

All capacity and scheduling arithmetic is done in working days: ISO weekdays
listed in ``workdays`` minus dates listed in ``holidays``. Weeks are ISO weeks,
Monday start (confirmed NEW-OQ 5).
"""

from __future__ import annotations

from datetime import date, timedelta


class WorkingCalendar:
    def __init__(self, config: dict):
        self.workdays: frozenset[int] = frozenset(config["workdays"])  # ISO 1=Mon..7=Sun
        self.holidays: frozenset[date] = frozenset(
            date.fromisoformat(d) for d in config.get("holidays", [])
        )
        self.hours_per_day: float = float(config["hours_per_day"])

    def is_working_day(self, day: date) -> bool:
        return day.isoweekday() in self.workdays and day not in self.holidays

    def next_working_day(self, day: date) -> date:
        while not self.is_working_day(day):
            day += timedelta(days=1)
        return day

    def working_days_between(self, start: date, end: date) -> list[date]:
        """All working days in [start, end] inclusive."""
        if end < start:
            return []
        days = []
        day = start
        while day <= end:
            if self.is_working_day(day):
                days.append(day)
            day += timedelta(days=1)
        return days

    def count_working_days(self, start: date, end: date) -> int:
        return len(self.working_days_between(start, end))

    def add_working_days(self, start: date, n: int) -> date:
        """The date n working days after start, where start itself counts as
        day 0 if it is a working day. add_working_days(d, 0) is the first
        working day >= d."""
        day = self.next_working_day(start)
        while n > 0:
            day = self.next_working_day(day + timedelta(days=1))
            n -= 1
        return day

    def nominal_days_per_week(self) -> int:
        return len(self.workdays)


def week_monday(day: date) -> date:
    """Monday of day's ISO week."""
    return day - timedelta(days=day.isoweekday() - 1)


def weeks_touching(start: date, end: date) -> list[date]:
    """Mondays of every ISO week the inclusive range [start, end] touches."""
    if end < start:
        return []
    weeks = []
    monday = week_monday(start)
    while monday <= end:
        weeks.append(monday)
        monday += timedelta(days=7)
    return weeks

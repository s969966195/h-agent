#!/usr/bin/env python3
"""
h_agent/scheduler/cron.py - Cron expression parser and scheduler.

Supports standard 5-field cron expressions:
  ┌───────────── minute (0-59)
  │ ┌───────────── hour (0-23)
  │ │ ┌───────────── day of month (1-31)
  │ │ │ ┌───────────── month (1-12)
  │ │ │ │ ┌───────────── day of week (0-6, Sunday=0)
  │ │ │ │ │
  * * * * *

Special expressions:
  @yearly, @monthly, @weekly, @daily, @hourly
  @reboot (not supported)
"""

import re
import time
from typing import List, Optional, Tuple
from datetime import datetime, timedelta


# ============================================================
# Cron Expression Parsing
# ============================================================

class CronExpression:
    """Parse and evaluate cron expressions."""
    
    # Special aliases
    ALIASES = {
        "@yearly": "0 0 1 1 *",
        "@annually": "0 0 1 1 *",
        "@monthly": "0 0 1 * *",
        "@weekly": "0 0 * * 0",
        "@daily": "0 0 * * *",
        "@midnight": "0 0 * * *",
        "@hourly": "0 * * * *",
    }
    
    def __init__(self, expression: str):
        """Initialize with a cron expression string."""
        # Resolve aliases
        expr = expression.strip()
        if expr in self.ALIASES:
            expr = self.ALIASES[expr]
        
        self.raw = expression
        self.parts = expr.split()
        
        if len(self.parts) != 5:
            raise ValueError(
                f"Invalid cron expression '{expression}': "
                f"expected 5 fields (minute hour day month weekday), got {len(self.parts)}"
            )
        
        self.minute, self.hour, self.day, self.month, self.weekday = self.parts
    
    def _parse_field(self, field: str, min_val: int, max_val: int) -> List[int]:
        """Parse a single cron field into a list of valid values."""
        values = set()
        
        # Handle wildcards
        if field == "*":
            return list(range(min_val, max_val + 1))
        
        # Handle step values (*/n)
        if field.startswith("*/"):
            step = int(field[2:])
            if step <= 0:
                raise ValueError(f"Invalid step value: {step}")
            return list(range(min_val, max_val + 1, step))
        
        # Handle ranges (e.g., 1-5)
        if "-" in field and "/" not in field:
            parts = field.split("-")
            if len(parts) != 2:
                raise ValueError(f"Invalid range: {field}")
            start, end = int(parts[0]), int(parts[1])
            if start > end:
                raise ValueError(f"Invalid range: {field} (start > end)")
            return list(range(start, end + 1))
        
        # Handle steps with ranges (e.g., 1-10/2)
        if "/" in field:
            range_part, step_part = field.split("/")
            step = int(step_part)
            if step <= 0:
                raise ValueError(f"Invalid step value: {step}")
            
            if range_part == "*":
                return list(range(min_val, max_val + 1, step))
            else:
                parts = range_part.split("-")
                if len(parts) != 2:
                    raise ValueError(f"Invalid range: {range_part}")
                start, end = int(parts[0]), int(parts[1])
                return list(range(start, end + 1, step))
        
        # Handle lists (e.g., 1,3,5)
        if "," in field:
            result = set()
            for part in field.split(","):
                result.update(self._parse_field(part.strip(), min_val, max_val))
            return sorted(result)
        
        # Single value
        try:
            val = int(field)
            if val < min_val or val > max_val:
                raise ValueError(
                    f"Value {val} out of range [{min_val}, {max_val}]"
                )
            return [val]
        except ValueError as e:
            raise ValueError(f"Invalid cron field value '{field}': {e}")
    
    def _matches(self, field: str, value: int, min_val: int, max_val: int) -> bool:
        """Check if a field matches a given value."""
        parsed = set(self._parse_field(field, min_val, max_val))
        return value in parsed
    
    def matches(self, dt: Optional[datetime] = None) -> bool:
        """Check if the expression matches the given datetime (or now)."""
        if dt is None:
            dt = datetime.now()
        
        return (
            self._matches(self.minute, dt.minute, 0, 59) and
            self._matches(self.hour, dt.hour, 0, 23) and
            self._matches(self.day, dt.day, 1, 31) and
            self._matches(self.month, dt.month, 1, 12) and
            self._matches(self.weekday, dt.weekday(), 0, 6)
        )
    
    def next_run(self, after: Optional[datetime] = None, max_iterations: int = 1000) -> Optional[datetime]:
        """Calculate the next run time after the given datetime."""
        if after is None:
            after = datetime.now()
        
        # Start from the next minute
        current = after.replace(second=0, microsecond=0) + timedelta(minutes=1)
        
        for _ in range(max_iterations):
            if self.matches(current):
                return current
            # Move to next minute, but optimize by jumping to next hour/day/month boundaries
            current = self._next_candidate(current)
        
        return None
    
    def _next_candidate(self, dt: datetime) -> datetime:
        """Get the next candidate datetime to check."""
        # Simple increment, could be optimized
        return dt + timedelta(minutes=1)
    
    def describe(self) -> str:
        """Return a human-readable description of the cron expression."""
        desc = []
        
        # Minute
        if self.minute == "*":
            desc.append("every minute")
        elif self.minute.startswith("*/"):
            desc.append(f"every {self.minute[2:]} minutes")
        elif "," in self.minute:
            desc.append(f"at minutes {self.minute}")
        elif "-" in self.minute:
            desc.append(f"at minute {self.minute}")
        else:
            desc.append(f"at minute {self.minute}")
        
        # Hour
        if self.hour != "*":
            if self.hour.startswith("*/"):
                desc.append(f"every {self.hour[2:]} hours")
            elif "," in self.hour:
                desc.append(f"at hours {self.hour}")
            elif "-" in self.hour:
                desc.append(f"during hours {self.hour}")
            else:
                desc.append(f"at hour {self.hour}")
        
        # Day
        if self.day != "*":
            if "," in self.day:
                desc.append(f"on days {self.day}")
            elif "-" in self.day:
                desc.append(f"on days {self.day}")
            else:
                desc.append(f"on day {self.day}")
        
        # Month
        month_names = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
                      "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        if self.month != "*":
            if self.month.startswith("*/"):
                desc.append(f"every {self.month[2:]} months")
            elif "," in self.month:
                months = [month_names[int(m)] for m in self.month.split(",")]
                desc.append(f"in {', '.join(months)}")
            elif "-" in self.month:
                parts = self.month.split("-")
                desc.append(f"from {month_names[int(parts[0])]} to {month_names[int(parts[1])]}")
            else:
                desc.append(f"in {month_names[int(self.month)]}")
        
        # Weekday
        day_names = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
        if self.weekday != "*":
            if "," in self.weekday:
                days = [day_names[int(d)] for d in self.weekday.split(",")]
                desc.append(f"on {', '.join(days)}")
            elif "-" in self.weekday:
                parts = self.weekday.split("-")
                desc.append(f"from {day_names[int(parts[0])]} to {day_names[int(parts[1])]}")
            else:
                desc.append(f"on {day_names[int(self.weekday)]}")
        
        return ", ".join(desc) if desc else "every minute"


# ============================================================
# Cron Job Runner
# ============================================================

def parse_cron(expression: str) -> CronExpression:
    """Parse a cron expression, raising ValueError if invalid."""
    return CronExpression(expression)


def validate_cron(expression: str) -> Tuple[bool, Optional[str]]:
    """Validate a cron expression. Returns (is_valid, error_message)."""
    try:
        CronExpression(expression)
        return True, None
    except ValueError as e:
        return False, str(e)


def get_next_run_time(expression: str, after: Optional[datetime] = None) -> Optional[datetime]:
    """Get the next run time for a cron expression."""
    try:
        cron = CronExpression(expression)
        return cron.next_run(after)
    except ValueError:
        return None


def format_next_run(dt: Optional[datetime]) -> str:
    """Format a datetime as a human-readable string."""
    if dt is None:
        return "N/A"
    now = datetime.now()
    diff = dt - now
    
    if diff.total_seconds() < 0:
        return "overdue"
    elif diff.total_seconds() < 60:
        return "in < 1 minute"
    elif diff.total_seconds() < 3600:
        mins = int(diff.total_seconds() / 60)
        return f"in {mins} minute{'s' if mins > 1 else ''}"
    elif diff.total_seconds() < 86400:
        hours = int(diff.total_seconds() / 3600)
        return f"in {hours} hour{'s' if hours > 1 else ''}"
    else:
        days = int(diff.total_seconds() / 86400)
        return f"in {days} day{'s' if days > 1 else ''}"

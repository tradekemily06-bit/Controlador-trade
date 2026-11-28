from __future__ import annotations

from datetime import datetime, timedelta, timezone

from data.timeframes import get_timeframe_interval, normalize_timeframe


def expected_last_closed_candle(timeframe: str, *, provider_now: datetime, close_grace_seconds: float = 3.0) -> datetime:
    """Calculate the last closed candle from the provider/server clock.

    provider_now must be an aware timestamp supplied by the data provider
    (for MT5, the broker/server clock), never the user's device clock. The
    returned candle-open timestamp is normalized to UTC. Daily and weekly
    boundaries are calculated in provider-local time before UTC conversion.
    """
    if not isinstance(provider_now, datetime) or provider_now.tzinfo is None:
        raise ValueError("provider_now must be a timezone-aware provider timestamp")
    if isinstance(close_grace_seconds, bool) or not isinstance(close_grace_seconds, (int, float)):
        raise ValueError("close_grace_seconds must be a non-negative number")
    if close_grace_seconds < 0:
        raise ValueError("close_grace_seconds must be a non-negative number")

    normalized = normalize_timeframe(timeframe)
    interval = get_timeframe_interval(normalized)
    eligible = provider_now - timedelta(seconds=float(close_grace_seconds))

    if normalized.endswith("d"):
        local_midnight = eligible.replace(hour=0, minute=0, second=0, microsecond=0)
        count = int(normalized[:-1])
        if count == 1:
            bucket_start = local_midnight
        else:
            ordinal = local_midnight.date().toordinal()
            bucket_start = local_midnight - timedelta(days=ordinal % count)
    elif normalized.endswith("w"):
        local_midnight = eligible.replace(hour=0, minute=0, second=0, microsecond=0)
        monday = local_midnight - timedelta(days=local_midnight.weekday())
        count = int(normalized[:-1])
        if count == 1:
            bucket_start = monday
        else:
            anchor = datetime(1970, 1, 5, tzinfo=eligible.tzinfo)
            weeks = (monday.date() - anchor.date()).days // 7
            bucket_start = monday - timedelta(weeks=weeks % count)
    else:
        interval_seconds = int(interval.total_seconds())
        local_epoch = int(eligible.timestamp())
        bucket_epoch = (local_epoch // interval_seconds) * interval_seconds
        bucket_start = datetime.fromtimestamp(bucket_epoch, tz=eligible.tzinfo)

    return (bucket_start - interval).astimezone(timezone.utc)

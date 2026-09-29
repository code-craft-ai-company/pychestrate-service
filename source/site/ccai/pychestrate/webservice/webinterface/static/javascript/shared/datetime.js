/*
 * The one date-time formatter of every bundle (XC-14, RES-20).
 *
 * The glossary's form is ``YYYY-MM-DD HH:MM``, 24-hour, with the zone
 * spelled out ("2026-09-22 16:34 PDT"). Bundles used to print the
 * browser's default locale format, which gave "9/22/2026, 4:34:12 PM"
 * (12-hour, no zone, a different shape for every locale), and to parse
 * with ``new Date(text)``, which reads a REST timestamp that carries no
 * zone designator as the viewer's local time and so shifts it by the
 * viewer's UTC offset.
 *
 * This file is bundled into each bundle by esbuild (the bundles do not
 * load it on their own), so every bundle formats a time the same way.
 */

// An ISO date-time whose text carries no zone designator ("Z" or
// "+hh:mm") at the end.
const ISO_DATE_TIME_PATTERN = /^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}/;
const ZONE_DESIGNATOR_PATTERN = /(?:Z|[+-]\d{2}:?\d{2})$/i;

export function pad_two(number) {
  const rtnval = (number < 10 ? "0" : "") + String(number);
  return rtnval;
}

/*
 * Parse a REST timestamp. The server stores UTC; a timestamp that
 * arrives without a zone designator is therefore UTC, never the
 * viewer's local time. Returns null when the value is not a date-time.
 */
export function parse_timestamp(value) {
  if (typeof value !== "string" || value.length === 0) {
    const rtnval2 = null;
    return rtnval2;
  }
  let text = value.trim();
  if (ISO_DATE_TIME_PATTERN.test(text) === true && ZONE_DESIGNATOR_PATTERN.test(text) === false) {
    text = text.replace(" ", "T") + "Z";
  }
  const parsed = new Date(text);
  if (Number.isNaN(parsed.getTime()) === true) {
    const rtnval2 = null;
    return rtnval2;
  }
  const rtnval = parsed;
  return rtnval;
}

/*
 * The short name of the viewer's zone at ``instant`` ("PDT", "GMT+2"),
 * or a numeric "UTC-07:00" when the browser cannot name it.
 */
export function zone_label(instant) {
  try {
    const parts = new Intl.DateTimeFormat(void 0, { timeZoneName: "short" }).formatToParts(instant);
    for (const part of parts) {
      if (part.type === "timeZoneName" && part.value.length > 0) {
        const rtnval2 = part.value;
        return rtnval2;
      }
    }
  } catch (error) {
  }
  const offset_minutes = -instant.getTimezoneOffset();
  const sign = offset_minutes >= 0 ? "+" : "-";
  const magnitude = Math.abs(offset_minutes);
  const rtnval = "UTC" + sign + pad_two(Math.floor(magnitude / 60)) + ":" + pad_two(magnitude % 60);
  return rtnval;
}

/* "2026-09-22 16:34 PDT": a Date in the glossary's form. */
export function format_instant(instant) {
  const date_part = instant.getFullYear() + "-" + pad_two(instant.getMonth() + 1) + "-" + pad_two(instant.getDate());
  const time_part = pad_two(instant.getHours()) + ":" + pad_two(instant.getMinutes());
  const rtnval = date_part + " " + time_part + " " + zone_label(instant);
  return rtnval;
}

/* "16:34:12 PDT": the time of day of a Date, for "as of" stamps. */
export function format_clock_instant(instant) {
  const rtnval = pad_two(instant.getHours()) + ":" + pad_two(instant.getMinutes()) + ":" + pad_two(instant.getSeconds()) + " " + zone_label(instant);
  return rtnval;
}

/*
 * A REST timestamp in the glossary's form; an em dash when there is none,
 * and the text itself when it is not a date-time.
 */
export function format_timestamp(value) {
  if (value === null || value === void 0 || value.length === 0) {
    const rtnval2 = "—";
    return rtnval2;
  }
  const parsed = parse_timestamp(value);
  if (parsed === null) {
    const rtnval2 = value;
    return rtnval2;
  }
  const rtnval = format_instant(parsed);
  return rtnval;
}

/*
 * How long something ran, for a list row (ORC-11): "< 1s", "45s", "3m 12s",
 * "2h 5m", "1d 4h". A run with no start has no duration ("—"). One that is
 * still running (``still_running``) is measured up to ``now`` and says so
 * ("3m 12s so far"); under a second is "< 1s"; one that has ended without a recorded finish has none.
 */
export function format_duration(started, finished, still_running, now) {
  const start = parse_timestamp(started);
  if (start === null) {
    return "—";
  }
  let end = parse_timestamp(finished);
  let open = false;
  if (end === null) {
    if (still_running !== true) {
      return "—";
    }
    end = now instanceof Date ? now : new Date();
    open = true;
  }
  const total = Math.max(0, Math.round((end.getTime() - start.getTime()) / 1000));
  let text;
  if (total < 1) {
    text = "< 1s";
  } else if (total < 60) {
    text = String(total) + "s";
  } else if (total < 3600) {
    text = String(Math.floor(total / 60)) + "m " + String(total % 60) + "s";
  } else if (total < 86400) {
    text = String(Math.floor(total / 3600)) + "h " + String(Math.floor((total % 3600) / 60)) + "m";
  } else {
    text = String(Math.floor(total / 86400)) + "d " + String(Math.floor((total % 86400) / 3600)) + "h";
  }
  return open ? text + " so far" : text;
}

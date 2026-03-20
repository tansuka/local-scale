const USER_TIME_ZONE = new Intl.DateTimeFormat().resolvedOptions().timeZone;

const DATE_FORMATTER = new Intl.DateTimeFormat(undefined, {
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
  timeZone: USER_TIME_ZONE,
});

const DATE_TIME_FORMATTER = new Intl.DateTimeFormat(undefined, {
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
  timeZone: USER_TIME_ZONE,
});

export function formatDate(value: string | Date): string {
  return DATE_FORMATTER.format(typeof value === "string" ? new Date(value) : value);
}

export function formatDateTime(value: string | Date): string {
  return DATE_TIME_FORMATTER.format(typeof value === "string" ? new Date(value) : value);
}

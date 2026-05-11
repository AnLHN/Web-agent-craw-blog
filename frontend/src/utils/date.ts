export function prettyDate(iso?: string | null): string {
  if (!iso) {
    return "-";
  }

  const value = new Date(iso);
  if (Number.isNaN(value.getTime())) {
    return "-";
  }

  return value.toLocaleString();
}

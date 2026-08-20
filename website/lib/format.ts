export function money(v: number | string | null | undefined): string {
  return Number(v ?? 0).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

export function today(): string {
  return new Date().toISOString().slice(0, 10);
}

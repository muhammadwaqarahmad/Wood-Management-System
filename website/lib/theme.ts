export type Theme = "light" | "dark" | "system";

export function applyTheme(theme: Theme): void {
  const root = document.documentElement;
  if (theme === "system") root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", theme);
  localStorage.setItem("asw_theme", theme);
}

export function currentTheme(): Theme {
  if (typeof window === "undefined") return "system";
  return (localStorage.getItem("asw_theme") as Theme) || "system";
}

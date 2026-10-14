import { readFileSync } from "node:fs";
export function localLogin() {
  const text = readFileSync(".env", "utf8");
  const value = (key: string) => {
    const row = text.split("\n").find((x) => x.startsWith(key + "="));
    if (!row) throw new Error("Application test login is not configured.");
    const raw = row.slice(key.length + 1).trim();
    return raw.startsWith('"') ? JSON.parse(raw) : raw;
  };
  return {
    username: value("BACKUPCENTER_ADMIN_USERNAME"),
    password: value("BACKUPCENTER_ADMIN_PASSWORD"),
  };
}

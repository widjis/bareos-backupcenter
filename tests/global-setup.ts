import { request } from "@playwright/test";
import { chmodSync } from "node:fs";
import { localLogin } from "./auth-helpers";
export default async function setup() {
  const api = await request.newContext({ baseURL: "http://127.0.0.1:3000" });
  const response = await api.post("/api/auth/login", {
    headers: {
      Origin: "http://127.0.0.1:3000",
      "X-Backup-Center-Action": "confirmed",
    },
    data: localLogin(),
  });
  if (!response.ok())
    throw new Error(
      "Application test sign-in failed; check the local initial Admin account.",
    );
  await api.storageState({ path: ".local/playwright-auth.json" });
  chmodSync(".local/playwright-auth.json", 0o600);
  await api.dispose();
}

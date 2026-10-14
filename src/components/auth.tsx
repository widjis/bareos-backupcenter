"use client";
import { createContext, useContext, useEffect, useRef, useState } from "react";
import { Eye, EyeOff, ShieldCheck } from "lucide-react";
import { useUnsavedDraft } from "./draft-guard";
import type { Ref } from "react";
import { NativeSelectField } from "./form-controls";
import { apiFetch } from "@/lib/api";

export type Identity = {
  username: string;
  role: "Admin" | "Backup Operator" | "Viewer";
  enabled?: boolean;
};
const UserContext = createContext<Identity | null>(null);
export const useIdentity = () => useContext(UserContext);
export const actionHeaders = {
  "Content-Type": "application/json",
  "X-Backup-Center-Action": "confirmed",
};

export function PasswordField({
  label,
  value,
  onChange,
  autoComplete = "current-password",
  invalid = false,
  describedBy,
  inputRef,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  autoComplete?: string;
  invalid?: boolean;
  describedBy?: string;
  inputRef?: Ref<HTMLInputElement>;
}) {
  const [shown, setShown] = useState(false);
  return (
    <label className="auth-field">
      <span>{label}</span>
      <div className="password-input">
        <input
          ref={inputRef}
          aria-invalid={invalid}
          aria-describedby={describedBy}
          aria-label={label}
          type={shown ? "text" : "password"}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          autoComplete={autoComplete}
          maxLength={256}
        />
        <button
          type="button"
          aria-label={(shown ? "Hide " : "Show ") + label.toLowerCase()}
          aria-pressed={shown}
          onClick={() => setShown(!shown)}
        >
          {shown ? <EyeOff size={17} /> : <Eye size={17} />}
        </button>
      </div>
    </label>
  );
}
export function AuthGate({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<Identity | null>(null),
    [loading, setLoading] = useState(true),
    [error, setError] = useState("");
  const [username, setUsername] = useState(""),
    [password, setPassword] = useState(""),
    [busy, setBusy] = useState(false);
  const nameInput = useRef<HTMLInputElement>(null),
    loginPassword = useRef<HTMLInputElement>(null);
  const [attempted, setAttempted] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    fetch("/api/auth/me", { signal: controller.signal })
      .then(async (r) => {
        if (r.ok) setUser(await r.json());
        else if (r.status !== 401)
          setError("Identity service unavailable. Retry sign-in.");
      })
      .catch(() => {
        if (!controller.signal.aborted)
          setError("Identity service unavailable. Retry sign-in.");
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    const interval = setInterval(() => {
      fetch("/api/auth/me", { signal: controller.signal })
        .then(async (r) => {
          if (r.ok) setUser(await r.json());
          else if (r.status === 401)
            window.dispatchEvent(new Event("backupcenter-auth-expired"));
        })
        .catch(() => {});
    }, 30000);
    const expired = () => {
      setUser(null);
      setPassword("");
      setError("Your session ended. Sign in again to continue.");
    };
    window.addEventListener("backupcenter-auth-expired", expired);
    return () => {
      controller.abort();
      clearInterval(interval);
      window.removeEventListener("backupcenter-auth-expired", expired);
    };
  }, []);
  if (loading)
    return (
      <main className="auth-page">
        <p role="status">Checking application session…</p>
      </main>
    );
  if (user)
    return <UserContext.Provider value={user}>{children}</UserContext.Provider>;
  return (
    <main className="auth-page">
      <section className="auth-card panel">
        <ShieldCheck size={32} aria-hidden="true" />
        <h1>Sign in to Backup Center</h1>
        <p>Use your local application account.</p>
        <form
          noValidate
          onSubmit={async (e) => {
            e.preventDefault();
            if (busy) return;
            setAttempted(true);
            if (!/^[a-z][a-z0-9_.-]{2,63}$/.test(username) || !password) {
              setError("Enter a valid username and password.");
              if (!/^[a-z][a-z0-9_.-]{2,63}$/.test(username))
                nameInput.current?.focus();
              else loginPassword.current?.focus();
              return;
            }
            setBusy(true);
            setError("");
            try {
              const r = await fetch("/api/auth/login", {
                method: "POST",
                headers: actionHeaders,
                body: JSON.stringify({ username, password }),
              });
              const result = await r.json();
              if (!r.ok)
                throw new Error(
                  typeof result.detail === "string"
                    ? result.detail
                    : "Unable to sign in.",
                );
              setPassword("");
              setUser(result);
            } catch (e) {
              setError(e instanceof Error ? e.message : "Unable to sign in.");
            } finally {
              setBusy(false);
            }
          }}
        >
          <label className="auth-field">
            <span>Username</span>
            <input
              ref={nameInput}
              autoComplete="username"
              value={username}
              maxLength={64}
              onChange={(e) => setUsername(e.target.value)}
              aria-invalid={
                attempted && !/^[a-z][a-z0-9_.-]{2,63}$/.test(username)
              }
              aria-describedby="login-error"
            />
          </label>
          <PasswordField
            label="Password"
            inputRef={loginPassword}
            invalid={attempted && !password}
            describedBy="login-error"
            value={password}
            onChange={setPassword}
          />
          <p className="auth-error" id="login-error" role="alert">
            {error}
          </p>
          <button className="button" type="submit" disabled={busy}>
            {busy ? "Signing in…" : "Sign in"}
          </button>
        </form>
        <small>Single environment · Sessions expire after 8 hours</small>
      </section>
    </main>
  );
}
export function AccountMenu() {
  const user = useIdentity();
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  return (
    <div className="account-menu">
      <span>
        {user?.username} · {user?.role}
      </span>
      <button
        className="text-button"
        disabled={busy}
        onClick={async () => {
          setBusy(true);
          try {
            const r = await apiFetch("/api/auth/logout", {
              method: "POST",
              headers: actionHeaders,
            });
            if (!r.ok) throw new Error();
            window.dispatchEvent(new Event("backupcenter-auth-expired"));
          } catch {
            setError("Sign-out failed. Retry.");
          } finally {
            setBusy(false);
          }
        }}
      >
        Sign out
      </button>
      {error && <span role="alert">{error}</span>}
    </div>
  );
}
export function UserSettings() {
  const identity = useIdentity();
  const [users, setUsers] = useState<Identity[]>([]),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const [username, setUsername] = useState(""),
    [password, setPassword] = useState(""),
    [role, setRole] = useState<Identity["role"]>("Viewer");
  const createName = useRef<HTMLInputElement>(null),
    createPassword = useRef<HTMLInputElement>(null),
    currentPassword = useRef<HTMLInputElement>(null),
    newPassword = useRef<HTMLInputElement>(null);
  const [createAttempted, setCreateAttempted] = useState(false),
    [passwordAttempted, setPasswordAttempted] = useState(false);
  const [editing, setEditing] = useState<Identity | null>(null);
  const [enabled, setEnabled] = useState(true);
  const [current, setCurrent] = useState(""),
    [next, setNext] = useState("");
  useUnsavedDraft(
    Boolean(
      username ||
      password ||
      current ||
      next ||
      (editing &&
        (role !== editing.role || enabled !== (editing.enabled !== false))),
    ),
  );
  const dialog = useRef<HTMLDialogElement>(null),
    back = useRef<HTMLButtonElement>(null),
    opener = useRef<HTMLElement | null>(null);
  const load = async () => {
    try {
      const r = await apiFetch("/api/users");
      if (!r.ok) throw new Error();
      setUsers((await r.json()).users);
    } catch {
      setError("Account list unavailable. Retry in Settings.");
    }
  };
  useEffect(() => {
    if (identity?.role === "Admin") void load();
  }, [identity]);
  return (
    <section className="panel identity-settings">
      <h2>Application accounts</h2>
      <p>
        Admin manages local accounts. Backup Operator runs and cancels backups.
        Viewer reads this environment.
      </p>
      {identity?.role === "Admin" && (
        <>
          <ul>
            {users.map((u) => (
              <li key={u.username}>
                {u.username} · {u.role} ·{" "}
                {u.enabled === false ? "Disabled" : "Enabled"}{" "}
                <button
                  className="text-button"
                  onClick={() => {
                    setEditing(u);
                    setRole(u.role);
                    setEnabled(u.enabled !== false);
                    opener.current = document.activeElement as HTMLElement;
                    dialog.current?.showModal();
                    back.current?.focus();
                  }}
                >
                  Change access
                </button>
              </li>
            ))}
          </ul>
          <form
            noValidate
            className="identity-form"
            onSubmit={(e) => {
              e.preventDefault();
              setCreateAttempted(true);
              if (
                !/^[a-z][a-z0-9_.-]{2,63}$/.test(username) ||
                password.length < 14
              ) {
                setError(
                  "Use a lowercase username (3–64 characters) and a password of at least 14 characters.",
                );
                if (!/^[a-z][a-z0-9_.-]{2,63}$/.test(username))
                  createName.current?.focus();
                else createPassword.current?.focus();
                return;
              }
              setError("");
              setEditing(null);
              opener.current = document.activeElement as HTMLElement;
              dialog.current?.showModal();
              back.current?.focus();
            }}
          >
            <label className="auth-field">
              <span>New username</span>
              <input
                ref={createName}
                aria-invalid={
                  createAttempted && !/^[a-z][a-z0-9_.-]{2,63}$/.test(username)
                }
                aria-describedby="identity-error"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="off"
              />
            </label>
            <PasswordField
              label="New account password"
              inputRef={createPassword}
              invalid={createAttempted && password.length < 14}
              describedBy="identity-error"
              autoComplete="new-password"
              value={password}
              onChange={setPassword}
            />
            <NativeSelectField
              label="Role"
              value={role}
              onChange={(v) => setRole(v as Identity["role"])}
              options={["Viewer", "Backup Operator", "Admin"].map((v) => ({
                value: v,
                label: v,
              }))}
            />
            <button className="button" type="submit" disabled={busy}>
              Review account
            </button>
          </form>
        </>
      )}
      <h3>Change your password</h3>
      <form
        noValidate
        className="identity-form"
        onSubmit={async (e) => {
          e.preventDefault();
          if (busy) return;
          setPasswordAttempted(true);
          if (!current || next.length < 14) {
            setError(
              "Enter your current password and a new password of at least 14 characters.",
            );
            if (!current) currentPassword.current?.focus();
            else newPassword.current?.focus();
            return;
          }
          setBusy(true);
          setError("");
          try {
            const r = await apiFetch("/api/auth/password", {
              method: "POST",
              headers: actionHeaders,
              body: JSON.stringify({ current, password: next }),
            });
            const result = await r.json();
            if (!r.ok)
              throw new Error(
                typeof result.detail === "string"
                  ? result.detail
                  : "Password change failed.",
              );
            setCurrent("");
            setNext("");
            window.dispatchEvent(new Event("backupcenter-auth-expired"));
          } catch (e) {
            setError(
              e instanceof Error ? e.message : "Password change failed.",
            );
          } finally {
            setBusy(false);
          }
        }}
      >
        <PasswordField
          label="Current password"
          inputRef={currentPassword}
          invalid={passwordAttempted && !current}
          describedBy="identity-error"
          value={current}
          onChange={setCurrent}
        />
        <PasswordField
          label="New password"
          inputRef={newPassword}
          invalid={passwordAttempted && next.length < 14}
          describedBy="identity-error"
          value={next}
          onChange={setNext}
          autoComplete="new-password"
        />
        <button className="button" type="submit" disabled={busy}>
          Change password
        </button>
      </form>
      <p className="auth-error" id="identity-error" role="alert">
        {error}
      </p>
      <dialog
        ref={dialog}
        aria-labelledby="account-confirm-title"
        onCancel={(e) => {
          if (busy) e.preventDefault();
        }}
        onClose={() => {
          opener.current?.focus();
          if (editing) {
            setEditing(null);
            setRole("Viewer");
          }
        }}
      >
        <div className="account-confirm">
          <h2 id="account-confirm-title">
            {editing ? "Change account access?" : "Create application account?"}
          </h2>
          <p>
            {editing?.username || username} will have {role} access to this
            entire backup environment.
          </p>
          {editing && (
            <>
              <NativeSelectField
                label="Account role"
                value={role}
                onChange={(v) => setRole(v as Identity["role"])}
                options={["Viewer", "Backup Operator", "Admin"].map((v) => ({
                  value: v,
                  label: v,
                }))}
              />
              <label>
                <input
                  type="checkbox"
                  checked={enabled}
                  onChange={(e) => setEnabled(e.target.checked)}
                />{" "}
                Account enabled
              </label>
              <p>
                Changes take effect on subsequent requests. Disabling ends this
                user's sessions; queued operations recheck permissions.
              </p>
            </>
          )}
          <div className="dialog-actions">
            <button
              className="button"
              ref={back}
              disabled={busy}
              onClick={() => dialog.current?.close()}
            >
              Go back
            </button>
            <button
              className="button"
              disabled={busy}
              onClick={async () => {
                if (busy) return;
                setBusy(true);
                setError("");
                try {
                  const r = await apiFetch(
                    editing ? "/api/users/" + editing.username : "/api/users",
                    {
                      method: "POST",
                      headers: actionHeaders,
                      body: JSON.stringify(
                        editing
                          ? { role, enabled, confirmed: true }
                          : { username, password, role, confirmed: true },
                      ),
                    },
                  );
                  const result = await r.json();
                  if (!r.ok)
                    throw new Error(
                      typeof result.detail === "string"
                        ? result.detail
                        : "Account creation failed.",
                    );
                  setUsername("");
                  setPassword("");
                  dialog.current?.close();
                  await load();
                } catch (e) {
                  setError(
                    e instanceof Error ? e.message : "Account creation failed.",
                  );
                } finally {
                  setBusy(false);
                }
              }}
            >
              {busy ? "Saving…" : editing ? "Change access" : "Create account"}
            </button>
          </div>
          {error && <p role="alert">{error}</p>}
        </div>
      </dialog>
    </section>
  );
}

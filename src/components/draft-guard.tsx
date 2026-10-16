"use client";
import { useEffect, useRef } from "react";
export type NavigationDraft = {
  view: string;
  query: string;
  page: number;
  section?: string;
};
const draftOwners = new Map<symbol, boolean>();
export function useUnsavedDraft(dirty: boolean) {
  const owner = useRef(Symbol("form-draft"));
  useEffect(() => {
    draftOwners.set(owner.current, dirty);
    const emit = () =>
      window.dispatchEvent(
        new CustomEvent("backupcenter-draft", {
          detail: [...draftOwners.values()].some(Boolean),
        }),
      );
    emit();
    const before = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };
    if (dirty) window.addEventListener("beforeunload", before);
    return () => {
      draftOwners.delete(owner.current);
      emit();
      window.removeEventListener("beforeunload", before);
    };
  }, [dirty]);
}
export function DiscardDraftDialog({
  pending,
  onBack,
  onDiscard,
  description = "Your unsaved account, policy or password entries will be cleared when you leave this settings page.",
}: {
  description?: string;
  pending: NavigationDraft | null;
  onBack: () => void;
  onDiscard: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null),
    back = useRef<HTMLButtonElement>(null),
    opener = useRef<HTMLElement | null>(null);
  useEffect(() => {
    if (!pending) return;
    opener.current = document.activeElement as HTMLElement;
    dialog.current?.showModal();
    back.current?.focus();
    return () => {
      dialog.current?.close();
      opener.current?.focus();
    };
  }, [pending]);
  return (
    <dialog
      ref={dialog}
      className="restore-confirm"
      aria-labelledby="discard-title"
      onCancel={(e) => {
        e.preventDefault();
        onBack();
      }}
    >
      <div className="account-confirm">
        <h2 id="discard-title">Discard unsaved changes?</h2>
        <p>{description}</p>
        <div className="dialog-actions">
          <button className="button" ref={back} onClick={onBack}>
            Go back
          </button>
          <button className="button" onClick={onDiscard}>
            Discard changes
          </button>
        </div>
      </div>
    </dialog>
  );
}

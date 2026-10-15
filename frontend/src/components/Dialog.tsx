import { useEffect, useRef, type ReactNode } from "react";

export function Dialog({ label, drawer = false, onClose, children }: { label: string; drawer?: boolean; onClose: () => void; children: ReactNode }) {
  const element = useRef<HTMLDivElement>(null);
  const close = useRef(onClose);
  close.current = onClose;
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const focusable = () => Array.from(element.current?.querySelectorAll<HTMLElement>('button:not([disabled]), input:not([disabled]), a[href], textarea:not([disabled]), [tabindex="0"]') ?? []);
    (element.current?.querySelector<HTMLElement>("input") ?? focusable()[0] ?? element.current)?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") { event.preventDefault(); close.current(); }
      if (event.key !== "Tab") return;
      const items = focusable(); const first = items[0]; const last = items.at(-1);
      if (!first) { event.preventDefault(); return; }
      if (event.shiftKey && (document.activeElement === first || document.activeElement === element.current)) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    };
    element.current?.addEventListener("keydown", onKey);
    const node = element.current;
    return () => { node?.removeEventListener("keydown", onKey); document.body.style.overflow = overflow; previous?.focus(); };
  }, []);
  return <div className={drawer ? "drawer-backdrop" : "modal-backdrop"} onMouseDown={event => { if (event.target === event.currentTarget) onClose(); }}>
    <div ref={element} tabIndex={-1} className={drawer ? "drawer" : "modal"} role="dialog" aria-modal="true" aria-label={label}>{children}</div>
  </div>;
}

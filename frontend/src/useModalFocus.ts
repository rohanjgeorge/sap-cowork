import { useEffect, useRef } from "react";
export function useModalFocus(onClose: () => void) {
  const ref = useRef<HTMLElement>(null),
    close = useRef(onClose);
  close.current = onClose;
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const element = ref.current;
    if (!element) return;
    const controls = () =>
      Array.from(
        element.querySelectorAll<HTMLElement>(
          "button:not(:disabled),input:not(:disabled),select,textarea,a[href]",
        ),
      ).filter((e) => e.tabIndex !== -1);
    (element.querySelector<HTMLElement>("input") || controls()[0])?.focus();
    function key(e: KeyboardEvent) {
      if (e.key === "Escape") {
        e.preventDefault();
        close.current();
      }
      if (e.key === "Tab") {
        const list = controls(),
          first = list[0],
          last = list.at(-1);
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last?.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first?.focus();
        }
      }
    }
    document.addEventListener("keydown", key);
    return () => {
      document.removeEventListener("keydown", key);
      previous?.focus();
    };
  }, []);
  return ref;
}

import { useEffect } from "react";

export function useVisibleViewport() {
  useEffect(() => {
    const viewport = window.visualViewport;
    const root = document.getElementById("root");
    if (!viewport || !root) return;

    const ajustarAltura = () => {
      // Safari shrinks the visual viewport when the keyboard opens.
      if (viewport.scale !== 1) {
        root.style.removeProperty("--visible-viewport-height");
        return;
      }

      root.style.setProperty("--visible-viewport-height", viewport.height + "px");

      const campo = document.activeElement;
      if (!(campo instanceof HTMLInputElement || campo instanceof HTMLTextAreaElement)) return;

      const control = campo.closest("[data-purpose='chat-input-panel']") ?? campo;
      control.scrollIntoView({ block: "nearest", inline: "nearest" });
    };

    ajustarAltura();
    viewport.addEventListener("resize", ajustarAltura);
    return () => {
      viewport.removeEventListener("resize", ajustarAltura);
      root.style.removeProperty("--visible-viewport-height");
    };
  }, []);
}

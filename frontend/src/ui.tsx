import { useEffect, useRef, useState, type ReactNode } from "react";
import { mediaURL } from "./api";
export function Icon({ name }: { name: string }) {
  return (
    <svg className="icon" aria-hidden="true">
      <use href={"#i-" + name} />
    </svg>
  );
}
export function ImageAsset({
  path,
  alt = "",
  className,
}: {
  path: string;
  alt?: string;
  className?: string;
}) {
  const [url, setURL] = useState("");
  const host = useRef<HTMLSpanElement>(null);
  const [visible, setVisible] = useState(!globalThis.IntersectionObserver);
  useEffect(() => {
    if (!globalThis.IntersectionObserver) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          setVisible(true);
          observer.disconnect();
        }
      },
      { rootMargin: "160px" },
    );
    if (host.current) observer.observe(host.current);
    return () => observer.disconnect();
  }, []);
  useEffect(() => {
    if (!visible) return;
    let live = true;
    setURL("");
    void mediaURL(path).then(
      (u) => {
        if (live) setURL(u);
      },
      () => {},
    );
    return () => {
      live = false;
    };
  }, [path, visible]);
  return (
    <span ref={host} className="asset-image">
      {url ? (
        <img className={className} src={url} alt={alt} />
      ) : (
        <span aria-label={alt}>
          <Icon name="sticker" />
        </span>
      )}
    </span>
  );
}
export function Modal({
  children,
  onClose,
  label,
  className = "",
  onNavigate,
}: {
  children: ReactNode;
  onClose: () => void;
  label: string;
  className?: string;
  onNavigate?: (delta: number) => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current!;
    dialog.showModal();
    dialog.focus();
    return () => dialog.close();
  }, []);
  return (
    <dialog
      ref={ref}
      tabIndex={-1}
      className={className}
      aria-label={label}
      onKeyDown={(e) => {
        if (onNavigate && ["ArrowLeft", "ArrowRight"].includes(e.key)) {
          e.preventDefault();
          onNavigate(e.key === "ArrowLeft" ? -1 : 1);
        }
        if (e.key === "Escape") {
          e.preventDefault();
          onClose();
        }
      }}
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
    >
      {children}
    </dialog>
  );
}

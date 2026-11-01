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
  useEffect(() => {
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
  }, [path]);
  return url ? (
    <img className={className} src={url} alt={alt} />
  ) : (
    <span aria-label={alt}>
      <Icon name="sticker" />
    </span>
  );
}
export function Modal({
  children,
  onClose,
  label,
  className = "",
}: {
  children: ReactNode;
  onClose: () => void;
  label: string;
  className?: string;
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

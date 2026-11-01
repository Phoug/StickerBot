export interface Sticker {
  id: string;
  emoji: string;
  preview_id: string;
  is_video?: boolean;
  is_animated?: boolean;
}
export interface Pack {
  id: string;
  name: string;
  title: string;
  status: "draft" | "ready" | "import_pending";
  count: number;
  source_name?: string;
  stickers: Sticker[];
}
export interface Media {
  id: string;
  duration: number;
  kind?: "photo" | "video";
  width?: number;
  height?: number;
}
export interface Album {
  kind: "album";
  photos: Media[];
}
export interface Edit {
  source_id: string;
  start: number;
  end: number;
  shape: "original" | "square" | "rounded" | "circle";
  zoom: number;
  x: number;
  y: number;
}
interface Insets {
  top: number;
  bottom: number;
  left: number;
  right: number;
}
export interface Telegram {
  initData: string;
  viewportStableHeight?: number;
  safeAreaInset?: Insets;
  contentSafeAreaInset?: Insets;
  isFullscreen?: boolean;
  isVersionAtLeast?: (v: string) => boolean;
  ready: () => void;
  expand: () => void;
  requestFullscreen?: () => void;
  disableVerticalSwipes?: () => void;
  enableVerticalSwipes?: () => void;
  onEvent?: (name: string, fn: () => void) => void;
  offEvent?: (name: string, fn: () => void) => void;
  setHeaderColor?: (color: string) => void;
  setBackgroundColor?: (color: string) => void;
  BackButton?: {
    show: () => void;
    hide: () => void;
    onClick: (fn: () => void) => void;
    offClick?: (fn: () => void) => void;
  };
  HapticFeedback?: {
    notificationOccurred: (type: string) => void;
    selectionChanged?: () => void;
  };
}
declare global {
  interface Window {
    Telegram?: { WebApp: Telegram };
  }
}

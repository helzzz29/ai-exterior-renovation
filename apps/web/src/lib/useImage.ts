import { useEffect, useState } from "react";

/** Load an image for drawing on a canvas. Returns null until it has loaded. */
export function useImage(url: string | null | undefined): HTMLImageElement | null {
  const [loaded, setLoaded] = useState<{ url: string; img: HTMLImageElement } | null>(null);
  useEffect(() => {
    if (!url) return;
    let cancelled = false;
    const img = new window.Image();
    img.onload = () => {
      if (!cancelled) setLoaded({ url, img });
    };
    img.src = url;
    return () => {
      cancelled = true;
    };
  }, [url]);
  return loaded && loaded.url === url ? loaded.img : null;
}

/** Load several images keyed by url (material swatches). */
export function useImages(urls: string[]): Record<string, HTMLImageElement> {
  const [map, setMap] = useState<Record<string, HTMLImageElement>>({});
  const key = urls.join("|");
  useEffect(() => {
    let cancelled = false;
    for (const url of key ? key.split("|") : []) {
      const img = new window.Image();
      img.onload = () => {
        if (!cancelled) setMap((m) => (m[url] ? m : { ...m, [url]: img }));
      };
      img.src = url;
    }
    return () => {
      cancelled = true;
    };
  }, [key]);
  return map;
}

/** Width of an element, kept up to date (for fitting the canvas to the screen). */
export function useElementWidth<T extends HTMLElement>(): [(el: T | null) => void, number] {
  const [el, setEl] = useState<T | null>(null);
  const [width, setWidth] = useState(0);
  useEffect(() => {
    if (!el) return;
    setWidth(el.clientWidth);
    if (typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver((entries) => setWidth(entries[0].contentRect.width));
    ro.observe(el);
    return () => ro.disconnect();
  }, [el]);
  return [setEl, width];
}

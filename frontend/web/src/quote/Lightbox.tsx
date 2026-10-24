import { useEffect, useState } from "react";
import type { Photo } from "@shared/types";

export function PhotoGrid({ photos, onOpen }: { photos: Photo[]; onOpen: (i: number) => void }) {
  if (photos.length === 0) return <p className="muted">The customer has not sent any photos.</p>;
  return (
    <div className="photo-grid">
      {photos.map((p, i) => (
        <button key={p.id} className="photo" onClick={() => onOpen(i)} aria-label={`Open photo: ${p.caption}`}>
          <img src={p.url} alt={p.caption} loading="lazy" />
          <span>{p.caption}</span>
        </button>
      ))}
    </div>
  );
}

export function Lightbox({ photos, index, onClose }: { photos: Photo[]; index: number; onClose: () => void }) {
  const [i, setI] = useState(index);
  const [zoom, setZoom] = useState(1);
  const p = photos[i];
  const go = (d: number) => {
    setI((v) => (v + d + photos.length) % photos.length);
    setZoom(1);
  };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (e.key === "ArrowLeft") go(-1);
      if (e.key === "ArrowRight") go(1);
      if (e.key === "+" || e.key === "=") setZoom((z) => Math.min(4, z + 0.5));
      if (e.key === "-") setZoom((z) => Math.max(1, z - 0.5));
    };
    window.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="lightbox" role="dialog" aria-modal="true" aria-label="Photo viewer" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="lb-bar">
        <span>{p.caption} <small className="num">({i + 1} of {photos.length})</small></span>
        <div className="lb-tools">
          <button className="btn small" onClick={() => setZoom((z) => Math.max(1, z - 0.5))} disabled={zoom <= 1} aria-label="Zoom out">−</button>
          <button className="btn small" onClick={() => setZoom(1)} aria-label="Reset zoom">{Math.round(zoom * 100)}%</button>
          <button className="btn small" onClick={() => setZoom((z) => Math.min(4, z + 0.5))} disabled={zoom >= 4} aria-label="Zoom in">+</button>
          <button className="btn small" onClick={onClose}>Close</button>
        </div>
      </div>
      <div className="lb-stage">
        {photos.length > 1 && <button className="lb-nav prev" onClick={() => go(-1)} aria-label="Previous photo">‹</button>}
        <div className="lb-scroll">
          <img src={p.url} alt={p.caption} style={{ width: `${zoom * 100}%` }} onDoubleClick={() => setZoom((z) => (z > 1 ? 1 : 2))} />
        </div>
        {photos.length > 1 && <button className="lb-nav next" onClick={() => go(1)} aria-label="Next photo">›</button>}
      </div>
    </div>
  );
}

"use client";
import { useRef, useState } from "react";
import { shortId } from "@/lib/format";
import { videoWatchUrl } from "@/lib/bridge";
import { useDialogAutoOpen } from "./ui";

// Minimal shape every video-bearing API response already provides; kept structural (not tied to
// BridgeVideo/VideoCard) so any of them can be passed here without extra mapping.
export interface PreviewableVideo {
  video_id: number;
  external_video_id: string | null;
  caption: string | null;
  video_reference: string | null;
}

function VideoPreviewDialog({ v, close, ru }: { v: PreviewableVideo; close: () => void; ru: boolean }) {
  const ref = useRef<HTMLDialogElement>(null);
  useDialogAutoOpen(ref);
  // The trigger only renders a clickable control when this id is present; falling back to ""
  // rather than interpolating null keeps a freak call inert instead of requesting .../null.
  const id = v.external_video_id ?? "";
  return (
    <dialog className="video-dialog" ref={ref} onClose={close} aria-labelledby="video-dialog-title">
      <div className="order-dialog-head">
        <h2 id="video-dialog-title">{v.caption || shortId(id)}</h2>
        <button className="btn" onClick={() => ref.current?.close()}>{ru ? "Закрыть" : "Close"}</button>
      </div>
      <iframe src={`https://www.tiktok.com/embed/v2/${id}`} allow="encrypted-media;" allowFullScreen />
      <div style={{ padding: "12px 24px" }}>
        <a href={videoWatchUrl(v)} target="_blank" rel="noopener noreferrer">{ru ? "Открыть в TikTok ↗" : "Open on TikTok ↗"}</a>
      </div>
    </dialog>
  );
}

// No thumbnail exists anywhere in the ingested data or documented TikTok API surface (checked
// live and against docs/tiktok-api-capability-matrix.md) — this is the actual fallback: a click
// opens the real TikTok post via its public embed player, not a static image.
export function VideoTrigger({ v, ru, className, title, children }:
    { v: PreviewableVideo; ru: boolean; className?: string; title?: string; children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  if (!v.external_video_id) return <>{children}</>;
  return (
    <>
      <button type="button" className={className ?? "order-link"} onClick={() => setOpen(true)}
              title={title ?? (ru ? "Открыть креатив" : "Open the creative")}>
        {children}
      </button>
      {open && <VideoPreviewDialog v={v} close={() => setOpen(false)} ru={ru} />}
    </>
  );
}

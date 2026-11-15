"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { API_BASE } from "./lib";

export type Notification = {
  id: number;
  title: string;
  source: string;
  category: string;
  url: string;
  published_at: string;
};

const STORAGE_KEY = "mi:lastReadId";
const MAX_ITEMS = 50;

function readLastRead(): number {
  try {
    return Number(localStorage.getItem(STORAGE_KEY)) || 0;
  } catch {
    return 0;
  }
}

function writeLastRead(id: number): void {
  try {
    localStorage.setItem(STORAGE_KEY, String(id));
  } catch {
    // Private mode / blocked storage — unread simply resets on reload.
  }
}

/**
 * Subscribes to the backend SSE stream and keeps a rolling list of notifications
 * with an unread count. Seeds the list with the latest items on mount, then
 * appends live ones as articles are ingested. Falls back silently if the stream
 * cannot connect.
 */
export function useNotifications() {
  const [items, setItems] = useState<Notification[]>([]);
  const [unread, setUnread] = useState(0);
  const [connected, setConnected] = useState(false);
  const lastReadRef = useRef(0);

  useEffect(() => {
    lastReadRef.current = readLastRead();
    let source: EventSource | null = null;
    let cancelled = false;

    async function init() {
      let latestId = 0;
      try {
        const res = await fetch(`${API_BASE}/api/notifications?limit=10`, { cache: "no-store" });
        if (res.ok) {
          const data: { items: Notification[]; latest_id: number } = await res.json();
          if (cancelled) return;
          setItems(data.items);
          latestId = data.latest_id;
          setUnread(data.items.filter((n) => n.id > lastReadRef.current).length);
        }
      } catch {
        // Backend not reachable yet; the stream attempt below will keep retrying.
      }
      if (cancelled) return;

      source = new EventSource(`${API_BASE}/api/stream?since_id=${latestId}`);
      source.onopen = () => setConnected(true);
      source.onerror = () => setConnected(false);
      source.addEventListener("article", (event) => {
        const note: Notification = JSON.parse((event as MessageEvent).data);
        setItems((prev) =>
          prev.some((p) => p.id === note.id) ? prev : [note, ...prev].slice(0, MAX_ITEMS),
        );
        setUnread((count) => (note.id > lastReadRef.current ? count + 1 : count));
      });
    }

    init();
    return () => {
      cancelled = true;
      source?.close();
    };
  }, []);

  const markAllRead = useCallback(() => {
    setItems((prev) => {
      const top = prev[0]?.id ?? lastReadRef.current;
      lastReadRef.current = top;
      writeLastRead(top);
      return prev;
    });
    setUnread(0);
  }, []);

  return { items, unread, connected, markAllRead };
}

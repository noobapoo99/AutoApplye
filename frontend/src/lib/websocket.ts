"use client";

import { useEffect, useRef, useState } from "react";

import type { LogEvent } from "@/types";

const RECONNECT_DELAY_MS = 3000;
const HEARTBEAT_MS = 25000;
const MAX_LOGS = 200;

function getSocketUrl(): string | null {
  // Try dedicated WS env var first
  const wsEnv = process.env.NEXT_PUBLIC_WS_URL?.replace(/\/$/, "");
  if (wsEnv) return `${wsEnv}/ws/logs`;

  // Derive from API URL
  const apiUrl = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "");
  if (apiUrl) {
    const wsUrl = apiUrl
      .replace(/^https:\/\//, "wss://")
      .replace(/^http:\/\//, "ws://");
    return `${wsUrl}/ws/logs`;
  }

  // Fallback: use current page host
  if (typeof window !== "undefined") {
    const proto = window.location.protocol === "https:" ? "wss" : "ws";
    return `${proto}://${window.location.host}/ws/logs`;
  }

  return null;
}

export function useAgentLogs() {
  const [logs, setLogs] = useState<LogEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const socketRef = useRef<WebSocket | null>(null);
  const reconnectRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const heartbeatRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    const socketUrl = getSocketUrl();
    let cancelled = false;

    const clearHeartbeat = () => {
      if (heartbeatRef.current) {
        clearInterval(heartbeatRef.current);
        heartbeatRef.current = null;
      }
    };

    const clearReconnect = () => {
      if (reconnectRef.current) {
        clearTimeout(reconnectRef.current);
        reconnectRef.current = null;
      }
    };

    const scheduleReconnect = () => {
      if (cancelled || reconnectRef.current || !socketUrl) {
        return;
      }

      reconnectRef.current = setTimeout(() => {
        reconnectRef.current = null;
        connect();
      }, RECONNECT_DELAY_MS);
    };

    const startHeartbeat = () => {
      clearHeartbeat();
      heartbeatRef.current = setInterval(() => {
        if (socketRef.current?.readyState === WebSocket.OPEN) {
          try {
            socketRef.current.send("ping");
          } catch {
            clearHeartbeat();
          }
        }
      }, HEARTBEAT_MS);
    };

    const connect = () => {
      if (!socketUrl || cancelled) {
        return;
      }

      const socket = new WebSocket(socketUrl);
      socketRef.current = socket;

      socket.onopen = () => {
        if (cancelled) {
          socket.close();
          return;
        }
        setConnected(true);
        startHeartbeat();
      };

      socket.onmessage = (event) => {
        try {
          const parsed = JSON.parse(event.data) as LogEvent;
          setLogs((current) => [...current, parsed].slice(-MAX_LOGS));
        } catch {
          setLogs((current) =>
            [
              ...current,
              {
                event: "message",
                timestamp: new Date().toISOString(),
                payload: event.data,
              },
            ].slice(-MAX_LOGS),
          );
        }
      };

      socket.onerror = () => {
        setConnected(false);
      };

      socket.onclose = () => {
        clearHeartbeat();
        setConnected(false);
        if (socketRef.current === socket) {
          socketRef.current = null;
        }
        scheduleReconnect();
      };
    };

    if (!socketUrl) {
      setConnected(false);
      return;
    }

    connect();

    return () => {
      cancelled = true;
      clearHeartbeat();
      clearReconnect();
      if (socketRef.current) {
        socketRef.current.close();
        socketRef.current = null;
      }
    };
  }, []);

  return { logs, connected };
}

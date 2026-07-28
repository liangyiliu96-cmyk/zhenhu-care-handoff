import { useEffect, useRef } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { getAuthHeaders } from '@/core/auth-bridge';

interface WardEvent {
  total_patients: number;
  alert_count: number;
  pending_review: number;
  high_risk: number;
  timestamp: number;
}

/** 接入 /ward/events SSE，实时更新 ward/nurse 相关查询缓存 */
export function useWardRealtime() {
  const qc = useQueryClient();
  const ref = useRef<EventSource | null>(null);

  useEffect(() => {
    const headers = getAuthHeaders();
    const url = new URL('/ward/events', window.location.origin);
    if (headers['x-user-id']) url.searchParams.set('x-user-id', headers['x-user-id']);
    if (headers['x-role']) url.searchParams.set('x-role', headers['x-role']);
    // SSE 不支持自定义 header，改用查询参数
    const es = new EventSource(url.toString());

    let lastUpdate = 0;
    es.onmessage = (event) => {
      try {
        const data: WardEvent = JSON.parse(event.data);
        // 防抖 10 秒内不重复刷新
        if (data.timestamp - lastUpdate < 10) return;
        lastUpdate = data.timestamp;
        qc.invalidateQueries({ queryKey: ['ward'] });
        qc.invalidateQueries({ queryKey: ['nurse'] });
        qc.invalidateQueries({ queryKey: ['patients'] });
      } catch { /* ignore parse errors */ }
    };

    ref.current = es;
    return () => { es.close(); };
  }, [qc]);
}

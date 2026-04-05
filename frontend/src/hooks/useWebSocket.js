import { useEffect, useRef } from 'react';
import { CricketWebSocket } from '../services/api';
import { useStore } from '../store/useStore';

export function useWebSocket(matchId) {
  const wsRef = useRef(null);
  const { setMatchState, setOdds, setSignal, setWsConnected } = useStore();

  useEffect(() => {
    const ws = new CricketWebSocket(matchId, {
      onConnect: () => setWsConnected(true),
      onDisconnect: () => setWsConnected(false),
      onMatchState: (data) => setMatchState(data),
      onOdds: (data) => setOdds(data),
      onSignal: (data) => setSignal(data),
    });

    ws.connect();
    wsRef.current = ws;

    return () => ws.disconnect();
  }, [matchId]);

  return wsRef;
}

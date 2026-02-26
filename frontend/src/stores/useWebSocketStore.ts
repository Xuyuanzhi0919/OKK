/**
 * WebSocket状态管理
 */
import { create } from 'zustand'
import type { TickerData, OrderBookData, TradesData } from '@/services/websocket'

interface WebSocketState {
  // 连接状态
  connected: boolean
  setConnected: (connected: boolean) => void

  // Ticker数据
  tickers: Map<string, TickerData>
  setTicker: (symbol: string, data: TickerData) => void
  getTicker: (symbol: string) => TickerData | undefined

  // 订单簿数据
  orderbooks: Map<string, OrderBookData>
  setOrderBook: (symbol: string, data: OrderBookData) => void
  getOrderBook: (symbol: string) => OrderBookData | undefined

  // 成交记录数据
  trades: Map<string, TradesData>
  setTrades: (symbol: string, data: TradesData) => void
  getTrades: (symbol: string) => TradesData | undefined

  // 清理数据
  clear: () => void
}

export const useWebSocketStore = create<WebSocketState>()((set, get) => ({
  connected: false,
  tickers: new Map(),
  orderbooks: new Map(),
  trades: new Map(),

  setConnected: (connected) => set({ connected }),

  setTicker: (symbol, data) =>
    set((state) => {
      const newTickers = new Map(state.tickers)
      newTickers.set(symbol, data)
      return { tickers: newTickers }
    }),

  getTicker: (symbol) => get().tickers.get(symbol),

  setOrderBook: (symbol, data) =>
    set((state) => {
      const newOrderbooks = new Map(state.orderbooks)
      newOrderbooks.set(symbol, data)
      return { orderbooks: newOrderbooks }
    }),

  getOrderBook: (symbol) => get().orderbooks.get(symbol),

  setTrades: (symbol, data) =>
    set((state) => {
      const newTrades = new Map(state.trades)
      newTrades.set(symbol, data)
      return { trades: newTrades }
    }),

  getTrades: (symbol) => get().trades.get(symbol),

  clear: () =>
    set({
      tickers: new Map(),
      orderbooks: new Map(),
      trades: new Map(),
    }),
}))

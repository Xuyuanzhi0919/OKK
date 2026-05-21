export interface AdaptiveGridTrendPreset {
  fast: number
  slow: number
  entry: number
  stop: number
  takeProfit: number
  cooldownMinutes: number
  riskPercent?: number
  maxPositionUsd?: number
}

export const ADAPTIVE_GRID_TREND_PRESETS: Record<string, AdaptiveGridTrendPreset> = {
  BTC: { fast: 20, slow: 80, entry: 0.6, stop: 2.8, takeProfit: 6.0, cooldownMinutes: 60 },
  ETH: { fast: 12, slow: 80, entry: 0.6, stop: 1.8, takeProfit: 6.0, cooldownMinutes: 120 },
  SOL: { fast: 20, slow: 80, entry: 0.6, stop: 2.8, takeProfit: 3.2, cooldownMinutes: 60 },
  BNB: { fast: 30, slow: 80, entry: 0.25, stop: 1.8, takeProfit: 6.0, cooldownMinutes: 120 },
  XRP: { fast: 20, slow: 80, entry: 0.6, stop: 2.8, takeProfit: 3.2, cooldownMinutes: 60 },
  AVAX: { fast: 12, slow: 160, entry: 0.25, stop: 1.8, takeProfit: 4.5, cooldownMinutes: 120 },
  LINK: { fast: 20, slow: 80, entry: 0.6, stop: 2.8, takeProfit: 6.0, cooldownMinutes: 120 },
  DOT: { fast: 30, slow: 80, entry: 0.6, stop: 2.8, takeProfit: 6.0, cooldownMinutes: 120 },
  ATOM: { fast: 30, slow: 160, entry: 0.25, stop: 2.8, takeProfit: 6.0, cooldownMinutes: 120 },
  OP: { fast: 30, slow: 80, entry: 0.6, stop: 1.8, takeProfit: 6.0, cooldownMinutes: 120 },
  ARB: { fast: 20, slow: 160, entry: 0.9, stop: 2.8, takeProfit: 3.2, cooldownMinutes: 240, riskPercent: 2, maxPositionUsd: 800 },
  EDEN: { fast: 20, slow: 80, entry: 0.6, stop: 1.8, takeProfit: 3.2, cooldownMinutes: 60 },
}

export function extractCoin(symbol?: string): string {
  return symbol?.split('-')[0] ?? ''
}

export function getAdaptiveGridTrendPreset(symbol?: string): AdaptiveGridTrendPreset {
  const coin = extractCoin(symbol || 'BTC-USDT-SWAP')
  return ADAPTIVE_GRID_TREND_PRESETS[coin] ?? ADAPTIVE_GRID_TREND_PRESETS.BTC
}

export function getAdaptiveGridTrendPresetForBacktest(symbol?: string) {
  const preset = getAdaptiveGridTrendPreset(symbol)
  return {
    fast: preset.fast,
    slow: preset.slow,
    entry: preset.entry,
    stop: preset.stop,
    takeProfit: preset.takeProfit,
    cooldownSeconds: preset.cooldownMinutes * 60,
    riskPerTrade: (preset.riskPercent ?? 1) / 100,
    maxPositionUsd: preset.maxPositionUsd ?? 500,
  }
}

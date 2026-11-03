// Budget-driven restock recommendations built from demand forecasts.

const TREND_RANK = { increasing: 0, stable: 1, decreasing: 2 }

const growthRate = (forecast) =>
  forecast.current_demand > 0
    ? (forecast.forecasted_demand - forecast.current_demand) / forecast.current_demand
    : 0

// Increasing demand first, then stable, then decreasing; fastest growth first within a trend.
export function rankForecasts(forecasts) {
  return [...forecasts].sort((a, b) => {
    const trendDiff = (TREND_RANK[a.trend] ?? 3) - (TREND_RANK[b.trend] ?? 3)
    if (trendDiff !== 0) return trendDiff
    return growthRate(b) - growthRate(a)
  })
}

// Cost of restocking every item at its full forecasted demand.
export function fullRestockCost(forecasts) {
  return forecasts.reduce((sum, f) => sum + f.forecasted_demand * f.unit_cost, 0)
}

// Greedy fill: walk the ranked items and give each as much of its forecasted demand
// as the remaining budget allows. Items that only partly fit get a partial quantity,
// and cheaper items further down can still use leftover budget.
// Excluded items are returned with quantity 0 so they can be re-included.
// The loop works in integer cents so float drift can't cost a unit.
const toCents = (amount) => Math.round(amount * 100)

export function buildRecommendations(forecasts, budget, excludedSkus = new Set()) {
  const budgetCents = toCents(Math.max(0, budget))
  let remainingCents = budgetCents
  const lines = rankForecasts(forecasts).map((forecast) => {
    const excluded = excludedSkus.has(forecast.item_sku)
    const unitCents = toCents(forecast.unit_cost)
    let quantity = 0
    if (!excluded && unitCents > 0) {
      quantity = Math.min(forecast.forecasted_demand, Math.floor(remainingCents / unitCents))
      remainingCents -= quantity * unitCents
    }
    const lineTotal = (quantity * unitCents) / 100
    return {
      sku: forecast.item_sku,
      name: forecast.item_name,
      trend: forecast.trend,
      forecastedDemand: forecast.forecasted_demand,
      unitCost: forecast.unit_cost,
      leadTimeDays: forecast.lead_time_days,
      quantity,
      lineTotal,
      excluded,
      fulfillment: excluded ? 'excluded'
        : quantity === 0 ? 'none'
        : quantity < forecast.forecasted_demand ? 'partial'
        : 'full'
    }
  })

  const totalCost = (budgetCents - remainingCents) / 100
  return { lines, totalCost, remaining: remainingCents / 100 }
}

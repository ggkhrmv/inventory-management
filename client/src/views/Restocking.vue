<template>
  <div class="restocking">
    <div class="page-header">
      <h2>{{ t('restocking.title') }}</h2>
      <p>{{ t('restocking.description') }}</p>
    </div>

    <div v-if="loading" class="loading">{{ t('common.loading') }}</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <div v-else>
      <div v-if="successOrder" class="banner banner-success" role="status">
        <div>
          <strong>{{ t('restocking.successTitle', { orderNumber: successOrder.order_number }) }}</strong>
          <span class="banner-body">
            {{ t('restocking.successBody', { date: formatDate(successOrder.expected_delivery), days: successOrder.lead_time_days }) }}
          </span>
        </div>
        <router-link to="/orders" class="banner-link">{{ t('restocking.viewOrders') }}</router-link>
      </div>
      <div v-if="submitError" class="banner banner-error" role="alert">
        <strong>{{ t('restocking.submitError') }}</strong>
      </div>

      <div class="card budget-card">
        <div class="card-header">
          <h3 class="card-title">{{ t('restocking.budget') }}</h3>
        </div>
        <div class="budget-value">{{ formatCurrency(budget, currentCurrency) }}</div>
        <input
          id="budget-slider"
          class="budget-slider"
          type="range"
          min="0"
          :max="maxBudget"
          step="500"
          v-model.number="budget"
          :aria-label="t('restocking.budget')"
          :style="{ '--fill': sliderFill }"
        />
        <div class="slider-scale">
          <span>{{ formatCurrency(0, currentCurrency) }}</span>
          <span>{{ formatCurrency(maxBudget, currentCurrency) }}</span>
        </div>
      </div>

      <div class="stats-grid">
        <div class="stat-card info">
          <div class="stat-label">{{ t('restocking.allocated') }}</div>
          <div class="stat-value">{{ formatCurrency(recommendations.totalCost, currentCurrency) }}</div>
        </div>
        <div class="stat-card success">
          <div class="stat-label">{{ t('restocking.remaining') }}</div>
          <div class="stat-value">{{ formatCurrency(recommendations.remaining, currentCurrency) }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">{{ t('restocking.itemsSelected') }}</div>
          <div class="stat-value">{{ itemsInOrder }}</div>
        </div>
      </div>

      <div class="card">
        <div class="card-header">
          <div>
            <h3 class="card-title">{{ t('restocking.recommendations') }}</h3>
            <p class="card-hint">{{ t('restocking.recommendationsHint') }}</p>
          </div>
        </div>
        <div class="table-container">
          <table class="restock-table">
            <thead>
              <tr>
                <th class="col-include">{{ t('restocking.table.include') }}</th>
                <th class="col-sku">{{ t('restocking.table.sku') }}</th>
                <th>{{ t('restocking.table.item') }}</th>
                <th class="col-trend">{{ t('restocking.table.trend') }}</th>
                <th class="col-num">{{ t('restocking.table.forecast') }}</th>
                <th class="col-num">{{ t('restocking.table.recommendedQty') }}</th>
                <th class="col-num">{{ t('restocking.table.unitCost') }}</th>
                <th class="col-num">{{ t('restocking.table.lineTotal') }}</th>
                <th class="col-lead">{{ t('restocking.table.leadTime') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="line in recommendations.lines"
                :key="line.sku"
                :class="{ muted: line.fulfillment === 'none' || line.fulfillment === 'excluded' }"
              >
                <td class="col-include">
                  <input
                    type="checkbox"
                    :checked="!line.excluded"
                    :aria-label="`${t('restocking.table.include')}: ${line.sku}`"
                    @change="toggleExcluded(line.sku)"
                  />
                </td>
                <td class="col-sku"><strong>{{ line.sku }}</strong></td>
                <td>{{ translateProductName(line.name) }}</td>
                <td class="col-trend">
                  <span :class="['badge', getTrendClass(line.trend)]">{{ t(`trends.${line.trend}`) }}</span>
                </td>
                <td class="col-num">{{ line.forecastedDemand.toLocaleString() }}</td>
                <td class="col-num">
                  <strong>{{ line.quantity.toLocaleString() }}</strong>
                  <span v-if="line.fulfillment === 'partial'" class="tag tag-partial">{{ t('restocking.partial') }}</span>
                  <span v-else-if="line.fulfillment === 'none'" class="tag">{{ t('restocking.notFunded') }}</span>
                  <span v-else-if="line.fulfillment === 'excluded'" class="tag">{{ t('restocking.excluded') }}</span>
                </td>
                <td class="col-num">{{ formatCurrencyWithDecimals(line.unitCost, currentCurrency, 2) }}</td>
                <td class="col-num"><strong>{{ formatCurrencyWithDecimals(line.lineTotal, currentCurrency, 2) }}</strong></td>
                <td class="col-lead">{{ t('orders.submittedOrders.leadTimeDays', { days: line.leadTimeDays }) }}</td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="order-actions">
          <span v-if="recommendations.totalCost === 0" class="no-allocation">{{ t('restocking.noAllocation') }}</span>
          <button
            type="button"
            class="btn-primary"
            :disabled="recommendations.totalCost === 0 || submitting"
            @click="placeOrder"
          >
            {{ submitting ? t('restocking.placingOrder') : t('restocking.placeOrder') }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, computed, onMounted } from 'vue'
import { api } from '../api'
import { useI18n } from '../composables/useI18n'
import { formatCurrency, formatCurrencyWithDecimals } from '../utils/currency'
import { buildRecommendations, fullRestockCost } from '../utils/restock'

const STEP = 500

export default {
  name: 'Restocking',
  setup() {
    const { t, currentLocale, currentCurrency, translateProductName } = useI18n()

    const loading = ref(true)
    const error = ref(null)
    const forecasts = ref([])
    const budget = ref(0)
    const excluded = ref(new Set())
    const submitting = ref(false)
    const successOrder = ref(null)
    const submitError = ref(false)

    const maxBudget = computed(() => Math.ceil(fullRestockCost(forecasts.value) / 1000) * 1000)

    const sliderFill = computed(() => {
      if (maxBudget.value <= 0) return '0%'
      return `${Math.min(100, Math.max(0, (budget.value / maxBudget.value) * 100))}%`
    })

    const recommendations = computed(() =>
      buildRecommendations(forecasts.value, budget.value, excluded.value)
    )

    const itemsInOrder = computed(
      () => recommendations.value.lines.filter(line => line.quantity > 0).length
    )

    const loadForecasts = async () => {
      try {
        loading.value = true
        error.value = null
        forecasts.value = await api.getDemandForecasts()
        budget.value = Math.round(maxBudget.value / 2 / STEP) * STEP
      } catch (err) {
        error.value = t('restocking.loadError')
        console.error('Load error:', err)
      } finally {
        loading.value = false
      }
    }

    const toggleExcluded = (sku) => {
      const next = new Set(excluded.value)
      if (next.has(sku)) next.delete(sku)
      else next.add(sku)
      excluded.value = next
    }

    const getTrendClass = (trend) => {
      const map = { increasing: 'success', stable: 'info', decreasing: 'warning' }
      return map[trend] || 'info'
    }

    const formatDate = (dateString) => {
      const date = new Date(dateString)
      if (isNaN(date.getTime())) return ''
      const locale = currentLocale.value === 'ja' ? 'ja-JP' : 'en-US'
      return date.toLocaleDateString(locale, { year: 'numeric', month: 'short', day: 'numeric' })
    }

    const placeOrder = async () => {
      if (submitting.value || recommendations.value.totalCost === 0) return
      submitting.value = true
      submitError.value = false
      successOrder.value = null
      try {
        const items = recommendations.value.lines
          .filter(line => line.quantity > 0)
          .map(line => ({ sku: line.sku, quantity: line.quantity }))
        successOrder.value = await api.createRestockOrder({ items, budget: budget.value })
        excluded.value = new Set()
      } catch (err) {
        // Server detail is English/USD only, so show the localized message and log the detail
        submitError.value = true
        console.error('Restock order failed:', err.response?.data?.detail || err)
      } finally {
        submitting.value = false
      }
    }

    onMounted(loadForecasts)

    return {
      t,
      currentCurrency,
      translateProductName,
      formatCurrency,
      formatCurrencyWithDecimals,
      loading,
      error,
      budget,
      maxBudget,
      sliderFill,
      recommendations,
      itemsInOrder,
      toggleExcluded,
      getTrendClass,
      formatDate,
      placeOrder,
      submitting,
      successOrder,
      submitError
    }
  }
}
</script>

<style scoped>
.budget-value {
  font-size: 2.25rem;
  font-weight: 700;
  color: #0f172a;
  margin-bottom: 1rem;
}

.budget-slider {
  -webkit-appearance: none;
  appearance: none;
  width: 100%;
  height: 8px;
  border-radius: 4px;
  outline: none;
  cursor: pointer;
  background: linear-gradient(to right, #0f172a 0%, #0f172a var(--fill), #e2e8f0 var(--fill), #e2e8f0 100%);
}

.budget-slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: white;
  border: 3px solid #0f172a;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.2);
}

.budget-slider::-moz-range-thumb {
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: white;
  border: 3px solid #0f172a;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.2);
}

.budget-slider::-moz-range-track {
  height: 8px;
  border-radius: 4px;
  background: transparent;
}

.budget-slider:focus-visible {
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.4);
}

.slider-scale {
  display: flex;
  justify-content: space-between;
  margin-top: 0.5rem;
  font-size: 0.813rem;
  color: #64748b;
}

.card-hint {
  margin: 0.25rem 0 0;
  font-size: 0.875rem;
  color: #64748b;
}

.restock-table {
  width: 100%;
}

.col-include {
  width: 70px;
  text-align: center;
}

.col-sku {
  width: 110px;
}

.col-trend {
  width: 120px;
}

.col-lead {
  width: 100px;
}

.col-num {
  text-align: right;
  white-space: nowrap;
}

.muted td {
  color: #94a3b8;
}

.muted td strong {
  color: #94a3b8;
}

.tag {
  display: inline-block;
  margin-left: 0.5rem;
  font-size: 0.75rem;
  font-weight: 500;
  color: #64748b;
}

.tag-partial {
  color: #b45309;
}

.order-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 1rem;
  padding-top: 1rem;
  border-top: 1px solid #e2e8f0;
  margin-top: 1rem;
}

.no-allocation {
  font-size: 0.875rem;
  color: #64748b;
}

.btn-primary {
  background: #0f172a;
  color: white;
  border: none;
  border-radius: 8px;
  padding: 0.625rem 1.25rem;
  font-size: 0.938rem;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.2s;
}

.btn-primary:hover:not(:disabled) {
  background: #1e293b;
}

.btn-primary:disabled {
  background: #cbd5e1;
  cursor: not-allowed;
}

.banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  padding: 1rem;
  border-radius: 8px;
  margin-bottom: 1.25rem;
  font-size: 0.938rem;
}

.banner-body {
  margin-left: 0.5rem;
}

.banner-success {
  background: #f0fdf4;
  border: 1px solid #bbf7d0;
  color: #166534;
}

.banner-error {
  background: #fef2f2;
  border: 1px solid #fecaca;
  color: #991b1b;
  justify-content: flex-start;
}

.banner-link {
  color: #166534;
  font-weight: 600;
  text-decoration: underline;
  white-space: nowrap;
}
</style>

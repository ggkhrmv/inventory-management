<template>
  <Teleport to="body">
    <Transition name="modal">
      <div v-if="isOpen && backlogItem" class="modal-overlay" @click="close">
        <div class="modal-container" @click.stop>
          <div class="modal-header">
            <h3 class="modal-title">
              {{ isView ? t('purchaseOrder.viewTitle') : t('purchaseOrder.createTitle') }}
            </h3>
            <button class="close-button" :aria-label="t('purchaseOrder.close')" @click="close">
              <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                <path d="M15 5L5 15M5 5L15 15" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
              </svg>
            </button>
          </div>

          <div class="modal-body">
            <div class="item-line">
              <div>
                <div class="item-name">{{ translateProductName(backlogItem.item_name) }}</div>
                <div class="item-sku">SKU: {{ backlogItem.item_sku }}</div>
              </div>
              <div class="item-sku">{{ t('purchaseOrder.shortage') }}: {{ shortage }}</div>
            </div>

            <!-- View mode -->
            <template v-if="isView">
              <div v-if="loading" class="state-message">{{ t('purchaseOrder.loading') }}</div>
              <div v-else-if="loadError" class="state-message error-message">{{ loadError }}</div>
              <div v-else-if="purchaseOrder" class="info-grid">
                <div class="info-item">
                  <div class="info-label">{{ t('purchaseOrder.poNumber') }}</div>
                  <div class="info-value">{{ purchaseOrder.id }}</div>
                </div>
                <div class="info-item">
                  <div class="info-label">{{ t('purchaseOrder.status') }}</div>
                  <div class="info-value">{{ purchaseOrder.status }}</div>
                </div>
                <div class="info-item">
                  <div class="info-label">{{ t('purchaseOrder.supplierName') }}</div>
                  <div class="info-value">{{ purchaseOrder.supplier_name }}</div>
                </div>
                <div class="info-item">
                  <div class="info-label">{{ t('purchaseOrder.quantity') }}</div>
                  <div class="info-value">{{ purchaseOrder.quantity }}</div>
                </div>
                <div class="info-item">
                  <div class="info-label">{{ t('purchaseOrder.unitCost') }}</div>
                  <div class="info-value">{{ formatMoney(purchaseOrder.unit_cost) }}</div>
                </div>
                <div class="info-item">
                  <div class="info-label">{{ t('purchaseOrder.total') }}</div>
                  <div class="info-value">{{ formatMoney(purchaseOrder.quantity * purchaseOrder.unit_cost) }}</div>
                </div>
                <div class="info-item">
                  <div class="info-label">{{ t('purchaseOrder.expectedDelivery') }}</div>
                  <div class="info-value">{{ formatDate(purchaseOrder.expected_delivery_date) }}</div>
                </div>
                <div class="info-item">
                  <div class="info-label">{{ t('purchaseOrder.createdDate') }}</div>
                  <div class="info-value">{{ formatDate(purchaseOrder.created_date) }}</div>
                </div>
                <div v-if="purchaseOrder.notes" class="info-item full">
                  <div class="info-label">{{ t('purchaseOrder.notes') }}</div>
                  <div class="info-value">{{ purchaseOrder.notes }}</div>
                </div>
              </div>
            </template>

            <!-- Create mode -->
            <form v-else id="po-form" @submit.prevent="submit">
              <div class="form-grid">
                <div class="form-field full">
                  <label for="po-supplier">{{ t('purchaseOrder.supplierName') }}</label>
                  <input id="po-supplier" v-model="form.supplier_name" type="text" autocomplete="off" />
                </div>
                <div class="form-field">
                  <label for="po-quantity">{{ t('purchaseOrder.quantity') }}</label>
                  <input id="po-quantity" v-model.number="form.quantity" type="number" min="1" step="1" />
                </div>
                <div class="form-field">
                  <label for="po-cost">{{ t('purchaseOrder.unitCost') }}</label>
                  <input id="po-cost" v-model.number="form.unit_cost" type="number" min="0" step="0.01" />
                </div>
                <div class="form-field full">
                  <label for="po-date">{{ t('purchaseOrder.expectedDelivery') }}</label>
                  <input id="po-date" v-model="form.expected_delivery_date" type="date" />
                </div>
                <div class="form-field full">
                  <label for="po-notes">{{ t('purchaseOrder.notes') }}</label>
                  <textarea id="po-notes" v-model="form.notes" rows="3"></textarea>
                </div>
              </div>

              <div class="total-row">
                <span class="total-label">{{ t('purchaseOrder.total') }}</span>
                <span class="total-value">{{ formatMoney(total) }}</span>
              </div>

              <div v-if="submitError" class="error-message" role="alert">{{ submitError }}</div>
            </form>
          </div>

          <div class="modal-footer">
            <button type="button" class="btn-secondary" @click="close">{{ t('purchaseOrder.close') }}</button>
            <button
              v-if="!isView"
              type="submit"
              form="po-form"
              class="btn-primary"
              :disabled="!isValid || submitting"
            >
              {{ submitting ? t('purchaseOrder.submitting') : t('purchaseOrder.submit') }}
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script>
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { api } from '../api'
import { useI18n } from '../composables/useI18n'

const toDateInput = (date) => {
  const y = date.getFullYear()
  const m = String(date.getMonth() + 1).padStart(2, '0')
  const d = String(date.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

const defaultDeliveryDate = () => {
  const date = new Date()
  date.setDate(date.getDate() + 7)
  return toDateInput(date)
}

export default {
  name: 'PurchaseOrderModal',
  props: {
    isOpen: { type: Boolean, default: false },
    backlogItem: { type: Object, default: null },
    mode: {
      type: String,
      default: 'create',
      validator: (v) => ['create', 'view'].includes(v)
    }
  },
  emits: ['close', 'po-created'],
  setup(props, { emit }) {
    const { t, translateProductName, currentLocale } = useI18n()

    const form = ref({
      supplier_name: '',
      quantity: null,
      unit_cost: null,
      expected_delivery_date: '',
      notes: ''
    })
    const submitting = ref(false)
    const submitError = ref(null)
    const purchaseOrder = ref(null)
    const loading = ref(false)
    const loadError = ref(null)

    const isView = computed(() => props.mode === 'view')

    const shortage = computed(() => {
      if (!props.backlogItem) return 0
      return Math.max(0, props.backlogItem.quantity_needed - props.backlogItem.quantity_available)
    })

    const total = computed(() => {
      const q = Number(form.value.quantity)
      const c = Number(form.value.unit_cost)
      if (!Number.isFinite(q) || !Number.isFinite(c)) return 0
      return q * c
    })

    const isValid = computed(() => {
      const f = form.value
      const q = Number(f.quantity)
      const c = f.unit_cost
      const date = new Date(f.expected_delivery_date)
      return (
        f.supplier_name.trim().length > 0 &&
        Number.isFinite(q) && q > 0 &&
        c !== null && c !== '' && Number.isFinite(Number(c)) && Number(c) >= 0 &&
        !isNaN(date.getTime())
      )
    })

    const formatMoney = (value) => {
      const n = Number(value)
      if (!Number.isFinite(n)) return '-'
      return n.toLocaleString(currentLocale.value === 'ja' ? 'ja-JP' : 'en-US', {
        style: 'currency',
        currency: 'USD'
      })
    }

    const formatDate = (value) => {
      if (!value) return '-'
      const date = new Date(value)
      if (isNaN(date.getTime())) return '-'
      return date.toLocaleDateString(currentLocale.value === 'ja' ? 'ja-JP' : 'en-US', {
        year: 'numeric',
        month: 'long',
        day: 'numeric'
      })
    }

    const errorMessage = (err, fallback) => {
      const status = err?.response?.status
      if (status === 409) return t('purchaseOrder.alreadyExists')
      const detail = err?.response?.data?.detail
      if (typeof detail === 'string') return detail
      if (Array.isArray(detail) && detail[0]?.msg) return detail[0].msg
      return fallback
    }

    const prefillUnitCost = async (sku) => {
      try {
        const items = await api.getInventory()
        const match = Array.isArray(items) ? items.find(i => i.sku === sku) : null
        // Don't clobber a value the user already typed
        if (match && form.value.unit_cost === null && props.backlogItem?.item_sku === sku) {
          form.value.unit_cost = match.unit_cost
        }
      } catch (err) {
        console.error('Failed to prefill unit cost:', err)
      }
    }

    const initCreate = () => {
      submitError.value = null
      submitting.value = false
      form.value = {
        supplier_name: '',
        quantity: shortage.value > 0 ? shortage.value : null,
        unit_cost: null,
        expected_delivery_date: defaultDeliveryDate(),
        notes: ''
      }
      prefillUnitCost(props.backlogItem.item_sku)
    }

    const loadPO = async () => {
      purchaseOrder.value = null
      loadError.value = null
      if (props.backlogItem.purchase_order) {
        purchaseOrder.value = props.backlogItem.purchase_order
        return
      }
      const itemId = props.backlogItem.id
      loading.value = true
      try {
        const po = await api.getPurchaseOrderByBacklogItem(itemId)
        if (props.backlogItem?.id === itemId) purchaseOrder.value = po
      } catch (err) {
        console.error('Failed to load purchase order:', err)
        loadError.value = errorMessage(err, t('purchaseOrder.loadFailed'))
      } finally {
        loading.value = false
      }
    }

    watch(
      () => [props.isOpen, props.backlogItem, props.mode],
      ([open, item, mode]) => {
        if (!open || !item) return
        if (mode === 'view') loadPO()
        else initCreate()
      },
      { immediate: true }
    )

    const submit = async () => {
      if (!isValid.value || submitting.value) return
      submitting.value = true
      submitError.value = null
      try {
        const created = await api.createPurchaseOrder({
          backlog_item_id: props.backlogItem.id,
          supplier_name: form.value.supplier_name.trim(),
          quantity: Number(form.value.quantity),
          unit_cost: Number(form.value.unit_cost),
          expected_delivery_date: form.value.expected_delivery_date,
          notes: form.value.notes.trim()
        })
        emit('po-created', created)
      } catch (err) {
        console.error('Failed to create purchase order:', err)
        submitError.value = errorMessage(err, t('purchaseOrder.createFailed'))
      } finally {
        submitting.value = false
      }
    }

    const close = () => emit('close')

    const onKeydown = (e) => {
      if (e.key === 'Escape' && props.isOpen) close()
    }
    onMounted(() => document.addEventListener('keydown', onKeydown))
    onBeforeUnmount(() => document.removeEventListener('keydown', onKeydown))

    return {
      t,
      translateProductName,
      form,
      submitting,
      submitError,
      purchaseOrder,
      loading,
      loadError,
      isView,
      shortage,
      total,
      isValid,
      formatMoney,
      formatDate,
      submit,
      close
    }
  }
}
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 2000;
  padding: 1rem;
}

.modal-container {
  background: white;
  border-radius: 12px;
  box-shadow: 0 20px 50px rgba(0, 0, 0, 0.15);
  max-width: 700px;
  width: 100%;
  max-height: 90vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1.5rem;
  border-bottom: 1px solid #e2e8f0;
}

.modal-title {
  font-size: 1.25rem;
  font-weight: 700;
  color: #0f172a;
  letter-spacing: -0.025em;
}

.close-button {
  background: none;
  border: none;
  color: #64748b;
  cursor: pointer;
  padding: 0.5rem;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  transition: all 0.15s ease;
}

.close-button:hover {
  background: #f1f5f9;
  color: #0f172a;
}

.modal-body {
  flex: 1;
  overflow-y: auto;
  padding: 2rem;
}

.item-line {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 1rem;
  padding-bottom: 1rem;
  margin-bottom: 1.25rem;
  border-bottom: 1px solid #e2e8f0;
}

.item-name {
  font-size: 1.125rem;
  font-weight: 700;
  color: #0f172a;
}

.item-sku {
  font-size: 0.813rem;
  color: #64748b;
  font-family: 'Monaco', 'Courier New', monospace;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 1rem;
}

.form-field {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
}

.form-field.full {
  grid-column: 1 / -1;
}

.form-field label,
.info-label {
  font-size: 0.813rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: #64748b;
}

.form-field input,
.form-field textarea {
  padding: 0.625rem 0.75rem;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  font-size: 0.938rem;
  font-family: inherit;
  color: #0f172a;
  background: white;
}

.form-field input:focus,
.form-field textarea:focus {
  outline: none;
  border-color: #2563eb;
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.15);
}

.total-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 1.25rem;
  padding: 1rem 1.25rem;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
}

.total-label {
  font-size: 0.813rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: #64748b;
}

.total-value {
  font-size: 1.5rem;
  font-weight: 700;
  color: #0f172a;
}

.info-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 1.25rem;
}

.info-item {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
}

.info-item.full {
  grid-column: 1 / -1;
}

.info-value {
  font-size: 0.938rem;
  color: #0f172a;
  font-weight: 500;
  white-space: pre-wrap;
}

.state-message {
  text-align: center;
  color: #64748b;
  padding: 2rem 0;
}

.error-message {
  margin-top: 1rem;
  padding: 0.75rem 1rem;
  background: #fef2f2;
  border: 1px solid #fecaca;
  border-radius: 8px;
  color: #991b1b;
  font-size: 0.875rem;
}

.state-message.error-message {
  margin-top: 0;
}

.btn-primary {
  padding: 0.625rem 1.25rem;
  background: #0f172a;
  border: 1px solid #0f172a;
  border-radius: 8px;
  font-weight: 500;
  font-size: 0.875rem;
  color: white;
  cursor: pointer;
  transition: all 0.15s ease;
  font-family: inherit;
}

.btn-primary:hover:not(:disabled) {
  background: #1e293b;
}

.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.modal-footer {
  padding: 1.5rem;
  border-top: 1px solid #e2e8f0;
  display: flex;
  justify-content: flex-end;
  gap: 0.75rem;
}

.btn-secondary {
  padding: 0.625rem 1.25rem;
  background: #f1f5f9;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  font-weight: 500;
  font-size: 0.875rem;
  color: #334155;
  cursor: pointer;
  transition: all 0.15s ease;
  font-family: inherit;
}

.btn-secondary:hover {
  background: #e2e8f0;
  border-color: #cbd5e1;
}

/* Modal transition animations */
.modal-enter-active,
.modal-leave-active {
  transition: opacity 0.2s ease;
}

.modal-enter-from,
.modal-leave-to {
  opacity: 0;
}

.modal-enter-active .modal-container,
.modal-leave-active .modal-container {
  transition: transform 0.2s ease;
}

.modal-enter-from .modal-container,
.modal-leave-to .modal-container {
  transform: scale(0.95);
}
</style>

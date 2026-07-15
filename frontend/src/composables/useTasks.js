import { ref } from 'vue'
import {
  listTasks,
  createTask as apiCreate,
  updateTask as apiUpdate,
  deleteTask as apiDelete,
} from '../api/tasks'

export function useTasks() {
  const tasks = ref([])
  const loading = ref(false)
  const error = ref(null)

  async function load(silent = false) {
    if (!silent) loading.value = true
    error.value = null
    try {
      tasks.value = await listTasks()
    } catch (e) {
      error.value = e.message
    } finally {
      if (!silent) loading.value = false
    }
  }

  async function add(task) {
    const created = await apiCreate(task)
    tasks.value.unshift(created)
    return created
  }

  async function update(id, patch) {
    const updated = await apiUpdate(id, patch)
    const idx = tasks.value.findIndex((t) => t.id === id)
    if (idx !== -1) tasks.value[idx] = updated
    return updated
  }

  async function remove(id) {
    await apiDelete(id)
    tasks.value = tasks.value.filter((t) => t.id !== id)
  }

  return { tasks, loading, error, load, add, update, remove }
}

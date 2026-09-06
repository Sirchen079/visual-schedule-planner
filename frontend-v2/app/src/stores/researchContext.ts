import { defineStore } from 'pinia'
export const useResearchContext = defineStore('researchContext', {
  state: () => ({ project: null as { id: number; title: string } | null }),
})

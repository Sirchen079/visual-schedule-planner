import { defineStore } from 'pinia'
import { finishOnboarding, readOnboarding, type OnboardingOutcome } from '../api/onboarding'
import { createTask } from '../api/tasks'
import { HttpError } from '../api/http'
import type { GuidePage } from '../content/guides'

export const useHelpStore = defineStore('help', {
  state: () => ({
    guideOpen: false, page: 'usage' as GuidePage, section: 0,
    tourOpen: false, tourStep: 0, returnToTour: false,
    initialized: false, initializing: false, interacted: false,
    savingOutcome: false, unsavedOutcome: null as OnboardingOutcome | null, saveError: '',
    practiceTitle: '', practiceTaskId: null as number | null,
    practiceSaving: false, practiceError: '', practiceUncertain: false,
  }),
  actions: {
    async initialize() {
      if (this.initialized || this.initializing) return
      this.initializing = true
      try {
        const state = await readOnboarding()
        // A delayed startup response cannot reopen a guide the user has closed.
        if (state.show_automatically && !this.interacted) this.tourOpen = true
        this.initialized = true
      } catch { /* The local guide remains available if the status request fails. */ }
      finally { this.initializing = false }
    },
    openGuide(page: GuidePage = 'usage', section = 0) {
      this.interacted = true
      this.returnToTour = this.tourOpen
      this.tourOpen = false
      this.page = page; this.section = section; this.guideOpen = true
    },
    closeGuide() {
      this.guideOpen = false
      if (this.returnToTour) this.tourOpen = true
      this.returnToTour = false
    },
    startTour() {
      this.interacted = true
      this.guideOpen = false; this.returnToTour = false
      this.tourStep = 0; this.tourOpen = true
      // Retain an already saved practice task for this session, so replay does
      // not silently invite another copy of the same first task.
    },
    async finishTour(outcome: OnboardingOutcome) {
      this.interacted = true
      this.guideOpen = false; this.tourOpen = false; this.returnToTour = false
      this.unsavedOutcome = outcome
      await this.retrySaveOutcome()
    },
    async retrySaveOutcome() {
      if (!this.unsavedOutcome || this.savingOutcome) return
      const outcome = this.unsavedOutcome
      this.savingOutcome = true; this.saveError = ''
      try {
        await finishOnboarding(outcome)
        if (this.unsavedOutcome === outcome) this.unsavedOutcome = null
      } catch {
        this.saveError = '这次关闭引导的记录还没保存，下次启动可能再次出现。其他功能可以继续使用。'
      } finally { this.savingOutcome = false }
    },
    async savePractice() {
      const title = this.practiceTitle.trim()
      if (!title || this.practiceSaving || this.practiceTaskId || this.practiceUncertain) return
      this.practiceSaving = true; this.practiceError = ''
      try {
        const task = await createTask({ title })
        this.practiceTaskId = task.id
        if (typeof window !== 'undefined') window.dispatchEvent(new Event('zhishi:tasks-changed'))
      } catch (error) {
        if (error instanceof HttpError && error.status === 422) {
          this.practiceError = '标题没有保存，请缩短到 200 个字以内后再试。'
        } else {
          this.practiceUncertain = true
          this.practiceError = '没能确认保存结果。请先到看板查看，避免重复创建；你可以继续往下学。'
        }
      } finally { this.practiceSaving = false }
    },
  },
})

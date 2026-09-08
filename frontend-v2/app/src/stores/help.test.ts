import { beforeEach, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import * as onboarding from '../api/onboarding'
import { useHelpStore } from './help'

vi.mock('../api/onboarding', () => ({ readOnboarding: vi.fn(), finishOnboarding: vi.fn() }))
beforeEach(() => { setActivePinia(createPinia()); vi.resetAllMocks() })

it('a delayed first-run response cannot override a manual close', async () => {
  let resolve!: (value: onboarding.OnboardingState) => void
  vi.mocked(onboarding.readOnboarding).mockReturnValue(new Promise(done => { resolve = done }))
  const help = useHelpStore(), pending = help.initialize()
  help.openGuide(); help.closeGuide()
  resolve({ status: 'pending', has_history: false, show_automatically: true })
  await pending
  expect(help.tourOpen).toBe(false)
})

it('an interrupted status save closes the guide and can be retried without resetting it', async () => {
  vi.mocked(onboarding.finishOnboarding).mockRejectedValueOnce(new Error('offline'))
    .mockResolvedValue({ status: 'skipped', has_history: false, show_automatically: false })
  const help = useHelpStore(); help.startTour()
  await help.finishTour('skipped')
  expect(help.tourOpen).toBe(false); expect(help.saveError).not.toBe('')
  await help.retrySaveOutcome()
  expect(help.unsavedOutcome).toBe(null); expect(help.saveError).toBe('')
})

it('reading an API chapter returns to the same guide step', () => {
  const help = useHelpStore(); help.startTour(); help.tourStep = 4
  help.openGuide('api', 2)
  expect(help.guideOpen && !help.tourOpen).toBe(true)
  help.closeGuide()
  expect(help.tourOpen).toBe(true); expect(help.tourStep).toBe(4)
})

it('only a confirmed task created during the exercise advances the tour', () => {
  const help = useHelpStore()
  help.taskCreated(1)
  expect(help.createdTaskId).toBe(null)
  help.startTour(); help.tourStep = 3; help.taskCreated(7)
  expect(help.tourStep).toBe(4); expect(help.createdTaskId).toBe(7)
  help.startTour()
  expect(help.createdTaskId).toBe(null)
})

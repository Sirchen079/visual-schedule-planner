import { beforeEach, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import * as onboarding from '../api/onboarding'
import * as tasks from '../api/tasks'
import { useHelpStore } from './help'

vi.mock('../api/onboarding', () => ({ readOnboarding: vi.fn(), finishOnboarding: vi.fn() }))
vi.mock('../api/tasks', () => ({ createTask: vi.fn() }))
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

it('practice only writes on explicit save and cannot double-submit', async () => {
  let resolve!: (value: tasks.Task) => void
  vi.mocked(tasks.createTask).mockReturnValue(new Promise(done => { resolve = done }))
  const help = useHelpStore(); help.startTour(); help.practiceTitle = ' My real task '
  expect(tasks.createTask).not.toHaveBeenCalled()
  const pending = help.savePractice()
  await help.savePractice()
  expect(tasks.createTask).toHaveBeenCalledTimes(1)
  expect(tasks.createTask).toHaveBeenCalledWith({ title: 'My real task' })
  resolve({ id: 7 } as tasks.Task); await pending
  help.startTour(); await help.savePractice()
  expect(tasks.createTask).toHaveBeenCalledTimes(1)
})

it('a lost save response does not invite an automatic duplicate write', async () => {
  vi.mocked(tasks.createTask).mockRejectedValue(new Error('lost response'))
  const help = useHelpStore(); help.practiceTitle = 'Important task'
  await help.savePractice(); await help.savePractice()
  expect(help.practiceUncertain).toBe(true)
  expect(tasks.createTask).toHaveBeenCalledTimes(1)
  expect(help.practiceError).toContain('到看板查看')
})

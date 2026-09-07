import type { components } from './contracts/rest'
import { http } from './http'

export type OnboardingState = components['schemas']['OnboardingState']
export type OnboardingOutcome = components['schemas']['OnboardingFinish']['outcome']
export const readOnboarding = () => http.get<OnboardingState>('/api/settings/onboarding')
export const finishOnboarding = (outcome: OnboardingOutcome) =>
  http.post<OnboardingState>('/api/settings/onboarding', { outcome })

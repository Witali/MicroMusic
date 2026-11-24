// Transport policy only; the shared C++ core independently enforces budgets.
export function encodingPolicy(profile, accuracy = false) {
  if (![3, 4, 6, 8].includes(profile)) throw Error('Некорректный профиль кодирования.');
  return Object.freeze({
    accuracyLevel: accuracy ? profile : 0,
    targetBitrate: !accuracy && (profile === 3 || profile === 8) ? profile * 1000 : 0,
    wireProfile: profile <= 4 ? 4 : 6,
    budgetKind: accuracy ? 'accuracy-allocation' : profile === 3 || profile === 8 ? 'complete-v9' : 'v5-control'
  });
}

export function bitrateBudget(samples, policy, sampleRate) {
  return Math.floor(samples * policy.targetBitrate / (8 * sampleRate));
}

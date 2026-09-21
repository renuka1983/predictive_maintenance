/** Level names and copy shared by navigation and upgrade prompts. */

export const LEVEL_NAMES = {
  0: 'Onboarding',
  1: 'Reactive (CMMS)',
  2: 'Predictive (CMMS + Production)',
  3: 'Real-time (Full + IoT)',
  4: 'Enterprise (Multi-site)',
};

export const LEVEL_PRICING = {
  0: 'Free',
  1: '$199/mo',
  2: '$499/mo',
  3: '$1,499/mo',
  4: '$2,999/mo',
};

/** How often the Level 3 monitoring page re-polls the backend. */
export const POLL_INTERVAL_MS = 10000;

export const SENSOR_UNITS = {
  vibration: 'mm/s',
  temperature: '°C',
  pressure: 'bar',
  current: 'A',
  rpm: 'rpm',
  acoustic: 'dB',
  oil_quality: 'idx',
};

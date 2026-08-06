export interface BandPowers {
  theta: number;  // 4–8 Hz
  alpha: number;  // 8–13 Hz
  beta:  number;  // 13–30 Hz
}

/**
 * Goertzel algorithm — computes signal power at one frequency bin.
 * O(N) per target frequency; cheaper than a full FFT for a small fixed band set.
 */
export function goertzel(samples: number[], targetHz: number, sampleRate: number): number {
  const N = samples.length;
  const k = Math.round(N * targetHz / sampleRate);
  const omega = (2 * Math.PI * k) / N;
  const coeff = 2 * Math.cos(omega);
  let s0 = 0, s1 = 0, s2 = 0;
  for (const x of samples) {
    s0 = x + coeff * s1 - s2;
    s2 = s1;
    s1 = s0;
  }
  return s1 * s1 + s2 * s2 - coeff * s1 * s2;
}

/** Sum Goertzel power across all integer-Hz bins in [lo, hi). */
function sumBand(samples: number[], loHz: number, hiHz: number, sampleRate: number): number {
  let power = 0;
  for (let f = loHz; f < hiHz; f++) {
    power += goertzel(samples, f, sampleRate);
  }
  return power;
}

/**
 * Compute EEG band powers from a window of samples.
 * @param samples  Array of EEG amplitude values (length should be a power of 2, typically 256).
 * @param sampleRate  Hz; default 256 (Muse 2 native rate).
 */
export function bandPowers(samples: number[], sampleRate = 256): BandPowers {
  return {
    theta: sumBand(samples, 4, 8, sampleRate),   // 4,5,6,7 Hz
    alpha: sumBand(samples, 8, 13, sampleRate),  // 8..12 Hz
    beta:  sumBand(samples, 13, 30, sampleRate), // 13..29 Hz
  };
}
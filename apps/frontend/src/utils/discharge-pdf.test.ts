import { describe, expect, it } from 'vitest';

import { calculatePdfSlices, dischargePdfFilename } from './discharge-pdf';

describe('discharge PDF helpers', () => {
  it('paginates a tall canvas without dropping pixels', () => {
    const slices = calculatePdfSlices(1000, 3600);

    expect(slices.length).toBeGreaterThan(1);
    expect(slices[0].sourceY).toBe(0);
    expect(slices.reduce((sum, slice) => sum + slice.sourceHeight, 0)).toBe(3600);
    expect(slices.at(-1)!.sourceY + slices.at(-1)!.sourceHeight).toBe(3600);
  });

  it('removes filesystem-unsafe characters from the download name', () => {
    expect(dischargePdfFilename('张/患者:01', 'patient-1')).toBe('张_患者_01_出院小结.pdf');
    expect(dischargePdfFilename('张/患者:01', 'patient-1', true)).toBe('张_患者_01_出院小结草稿.pdf');
  });
});

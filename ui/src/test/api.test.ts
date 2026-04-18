import { describe, it, expect } from 'vitest'
import { filtersToQS, splitFreq } from '../api'

describe('filtersToQS', () => {
  it('returns empty string for empty filters and no extras', () => {
    expect(filtersToQS({})).toBe('')
  })

  it('builds query string from freq filters', () => {
    const qs = filtersToQS({ freq_min: 88, freq_max: 108 })
    expect(qs).toBe('?freq_min=88&freq_max=108')
  })

  it('omits undefined values', () => {
    expect(filtersToQS({ freq_min: 88, freq_max: undefined })).toBe('?freq_min=88')
  })

  it('omits empty-string values', () => {
    expect(filtersToQS({}, { threshold: '' })).toBe('')
  })

  it('merges extra params alongside filters', () => {
    const qs = filtersToQS({ freq_min: 88 }, { threshold: -5 })
    expect(qs).toContain('freq_min=88')
    expect(qs).toContain('threshold=-5')
  })

  it('includes time filters', () => {
    const qs = filtersToQS({ time_min: '2024-01-01 00:00:00', time_max: '2024-01-02 00:00:00' })
    expect(qs).toContain('time_min=')
    expect(qs).toContain('time_max=')
  })
})

describe('splitFreq', () => {
  it('splits MHz suffix', () => {
    expect(splitFreq('144M')).toEqual(['144', 'M'])
  })

  it('splits kHz suffix', () => {
    expect(splitFreq('500k')).toEqual(['500', 'k'])
  })

  it('splits GHz suffix', () => {
    expect(splitFreq('1.2G')).toEqual(['1.2', 'G'])
  })

  it('defaults to MHz when no unit suffix', () => {
    expect(splitFreq('144')).toEqual(['144', 'M'])
  })

  it('handles decimal MHz', () => {
    expect(splitFreq('88.5M')).toEqual(['88.5', 'M'])
  })
})

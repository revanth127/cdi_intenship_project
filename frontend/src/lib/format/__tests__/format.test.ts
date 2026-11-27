import { describe, it, expect } from 'vitest';
import {
  formatIndianCurrency,
  formatIndianNumber,
  formatQuantityWithUnit,
  formatPercentage,
  groupIndianDigits,
} from '../index';

describe('Indian Digit Grouping', () => {
  it('handles numbers under 1,000 without commas', () => {
    expect(groupIndianDigits('0')).toBe('0');
    expect(groupIndianDigits('42')).toBe('42');
    expect(groupIndianDigits('500')).toBe('500');
  });

  it('correctly groups thousands (4 digits)', () => {
    expect(groupIndianDigits('1234')).toBe('1,234');
    expect(groupIndianDigits('5000')).toBe('5,000');
  });

  it('correctly groups ten thousands (5 digits)', () => {
    expect(groupIndianDigits('12345')).toBe('12,345');
    expect(groupIndianDigits('40000')).toBe('40,000');
  });

  it('correctly groups lakhs (6 digits: 1,23,456)', () => {
    expect(groupIndianDigits('123456')).toBe('1,23,456');
    expect(groupIndianDigits('100000')).toBe('1,00,000');
  });

  it('correctly groups ten lakhs (7 digits: 12,34,567)', () => {
    expect(groupIndianDigits('1234567')).toBe('12,34,567');
  });

  it('correctly groups crores (8+ digits: 1,23,45,678)', () => {
    expect(groupIndianDigits('12345678')).toBe('1,23,45,678');
    expect(groupIndianDigits('10000000')).toBe('1,00,00,000');
  });
});

describe('formatIndianCurrency', () => {
  it('formats positive currency with rupee symbol and paise', () => {
    expect(formatIndianCurrency(123456)).toBe('₹1,23,456.00');
    expect(formatIndianCurrency(50)).toBe('₹50.00');
    expect(formatIndianCurrency(18500)).toBe('₹18,500.00');
  });

  it('supports hiding paise', () => {
    expect(formatIndianCurrency(123456, { showPaise: false })).toBe('₹1,23,456');
  });

  it('formats negative currency with minus sign by default', () => {
    expect(formatIndianCurrency(-1234.5)).toBe('-₹1,234.50');
  });

  it('formats negative currency with parentheses when requested', () => {
    expect(formatIndianCurrency(-1234.5, { negativeFormat: 'parentheses' })).toBe('(₹1,234.50)');
    expect(formatIndianCurrency(-50000, { negativeFormat: 'parentheses' })).toBe('(₹50,000.00)');
  });

  it('handles null, undefined and zero gracefully', () => {
    expect(formatIndianCurrency(0)).toBe('₹0.00');
    expect(formatIndianCurrency(null)).toBe('₹0.00');
    expect(formatIndianCurrency(undefined)).toBe('₹0.00');
  });
});

describe('formatQuantityWithUnit', () => {
  it('formats quantities with units attached', () => {
    expect(formatQuantityWithUnit(40, 'kg')).toBe('40 kg');
    expect(formatQuantityWithUnit(10, 'L')).toBe('10 L');
    expect(formatQuantityWithUnit(200, 'packets')).toBe('200 packets');
    expect(formatQuantityWithUnit(1, 'carton')).toBe('1 carton');
  });

  it('formats quantities with decimals and Indian grouping', () => {
    expect(formatQuantityWithUnit(120000, 'g')).toBe('1,20,000 g');
    expect(formatQuantityWithUnit(19.5, 'L', 1)).toBe('19.5 L');
  });
});

describe('formatPercentage', () => {
  it('formats positive and negative percentages with optional sign', () => {
    expect(formatPercentage(5.0, true)).toBe('+5.0%');
    expect(formatPercentage(5.0, false)).toBe('5.0%');
    expect(formatPercentage(-6.0, true)).toBe('-6.0%');
    expect(formatPercentage(0)).toBe('0.0%');
  });
});

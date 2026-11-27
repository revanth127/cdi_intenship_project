import { describe, it, expect } from 'vitest';
import {
  formatIndianCurrency,
  formatIndianNumber,
  formatQuantityWithUnit,
  formatPercentage,
  groupIndianDigits,
  formatIndianDecimal,
  convertBaseQuantity,
  convertToBaseQuantity,
  formatBaseQuantity,
  formatUnitCost,
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

  it('supports a custom number of decimals without dropping integer zeroes', () => {
    expect(formatPercentage(-3.0, true, 2)).toBe('-3.00%');
    expect(formatPercentage(37.7, false, 2)).toBe('37.70%');
  });
});

describe('formatIndianDecimal', () => {
  it('groups Indian digits and trims trailing decimal zeroes', () => {
    expect(formatIndianDecimal(120000, 3)).toBe('1,20,000');
    expect(formatIndianDecimal(19.5, 3)).toBe('19.5');
    expect(formatIndianDecimal(3.8, 3)).toBe('3.8');
  });

  it('never strips meaningful integer zeroes when no decimals are shown', () => {
    expect(formatIndianDecimal(120, 0)).toBe('120');
    expect(formatIndianDecimal(1000, 0)).toBe('1,000');
  });
});

describe('base/display quantity conversion', () => {
  it('converts mass and volume base quantities into display units', () => {
    expect(convertBaseQuantity(40000, 'g', 'kg')).toBe(40);
    expect(convertBaseQuantity(19500, 'ml', 'L')).toBe(19.5);
    expect(convertBaseQuantity(194, 'piece', 'piece')).toBe(194);
  });

  it('round-trips display quantities back to integer base units', () => {
    expect(convertToBaseQuantity(40, 'g', 'kg')).toBe(40000);
    expect(convertToBaseQuantity(19.5, 'ml', 'L')).toBe(19500);
    expect(convertToBaseQuantity(9, 'piece', 'piece')).toBe(9);
  });

  it('formats base quantities in their display unit', () => {
    expect(formatBaseQuantity(40000, 'g', 'kg')).toBe('40');
    expect(formatBaseQuantity(19500, 'ml', 'L')).toBe('19.5');
  });

  it('converts paise per base unit into rupees per display unit', () => {
    expect(formatUnitCost(4.3125, 'g', 'kg')).toBe('₹43.13');
    expect(formatUnitCost(14, 'ml', 'L')).toBe('₹140.00');
    expect(formatUnitCost(250, 'piece', 'piece')).toBe('₹2.50');
  });
});

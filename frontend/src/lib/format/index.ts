/**
 * Centralized Indian Number & Currency Formatting Module
 * Standardizes:
 *  - Indian digit grouping (e.g. 1,23,456.00)
 *  - Rupee symbol (₹)
 *  - Negative values in parentheses or with minus sign
 *  - Standard unit labeling (kg, L, packets, piece)
 */

export interface CurrencyFormatOptions {
  showPaise?: boolean;
  negativeFormat?: 'minus' | 'parentheses';
}

/**
 * Splits the integer portion of a number string into Indian digit groups:
 * Last 3 digits together, then groups of 2 preceding it.
 * E.g., "1234567" -> "12,34,567"
 */
export function groupIndianDigits(numStr: string): string {
  if (!numStr || numStr === '0') return '0';
  const cleanStr = numStr.replace(/^0+/, '') || '0';
  if (cleanStr.length <= 3) return cleanStr;

  const lastThree = cleanStr.slice(-3);
  const otherNumbers = cleanStr.slice(0, -3);

  // Group preceding digits into chunks of 2 from right to left
  const groups: string[] = [];
  let i = otherNumbers.length;
  while (i > 0) {
    const start = Math.max(0, i - 2);
    groups.unshift(otherNumbers.slice(start, i));
    i -= 2;
  }

  return groups.join(',') + ',' + lastThree;
}

/**
 * Formats a numeric value using Indian grouping and decimal places.
 * E.g., 1234567.89 -> "12,34,567.89"
 */
export function formatIndianNumber(
  value: number | string | null | undefined,
  decimals: number = 0
): string {
  if (value === null || value === undefined || isNaN(Number(value))) {
    return '0' + (decimals > 0 ? '.' + '0'.repeat(decimals) : '');
  }

  const num = Number(value);
  const isNegative = num < 0;
  const absNum = Math.abs(num);

  const fixedStr = absNum.toFixed(decimals);
  const [intPart, decPart] = fixedStr.split('.');
  const groupedInt = groupIndianDigits(intPart);

  const result = decPart ? `${groupedInt}.${decPart}` : groupedInt;
  return isNegative ? `-${result}` : result;
}

/**
 * Formats a currency value with the Indian Rupee symbol (₹) and Indian digit grouping.
 * Negative numbers can be formatted with minus ("-₹1,234.00") or parentheses ("(₹1,234.00)").
 */
export function formatIndianCurrency(
  amount: number | string | null | undefined,
  options: CurrencyFormatOptions = {}
): string {
  const { showPaise = true, negativeFormat = 'minus' } = options;
  if (amount === null || amount === undefined || isNaN(Number(amount))) {
    return showPaise ? '₹0.00' : '₹0';
  }

  const num = Number(amount);
  const isNegative = num < 0;
  const absNum = Math.abs(num);

  const formattedAbs = formatIndianNumber(absNum, showPaise ? 2 : 0);

  if (isNegative) {
    if (negativeFormat === 'parentheses') {
      return `(₹${formattedAbs})`;
    }
    return `-₹${formattedAbs}`;
  }

  return `₹${formattedAbs}`;
}

/**
 * Formats a quantity with its mandatory unit.
 * E.g., formatQuantityWithUnit(40, 'kg') -> "40 kg"
 */
export function formatQuantityWithUnit(
  quantity: number | string | null | undefined,
  unit: string,
  decimals: number = 0
): string {
  if (quantity === null || quantity === undefined || isNaN(Number(quantity))) {
    return `0 ${unit}`;
  }
  const formatted = formatIndianNumber(quantity, decimals);
  return `${formatted} ${unit}`;
}

/**
 * Formats variance or margin percentages.
 * E.g., formatPercentage(5.0, true) -> "+5.0%"
 */
export function formatPercentage(
  pct: number | string | null | undefined,
  showSign: boolean = false
): string {
  if (pct === null || pct === undefined || isNaN(Number(pct))) {
    return '0.0%';
  }
  const num = Number(pct);
  const formatted = Math.abs(num).toFixed(1);
  if (num > 0 && showSign) {
    return `+${formatted}%`;
  }
  if (num < 0) {
    return `-${formatted}%`;
  }
  return `${formatted}%`;
}

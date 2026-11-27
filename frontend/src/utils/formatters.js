/**
 * Formatting utilities for Indian monetary figures, quantities, and dates.
 */

export function formatPaise(paise, includeSymbol = true) {
  if (paise === null || paise === undefined) return includeSymbol ? '₹0.00' : '0.00';
  const isNegative = paise < 0;
  const absPaise = Math.abs(paise);
  const rupees = absPaise / 100;
  
  // Format in Indian numbering system
  const formatted = rupees.toLocaleString('en-IN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  
  const prefix = isNegative ? '-' : '';
  const sym = includeSymbol ? '₹' : '';
  return `${prefix}${sym}${formatted}`;
}

export function formatRupees(rupees, includeSymbol = true) {
  if (rupees === null || rupees === undefined) return includeSymbol ? '₹0.00' : '0.00';
  const val = Number(rupees);
  const formatted = Math.abs(val).toLocaleString('en-IN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  const prefix = val < 0 ? '-' : '';
  const sym = includeSymbol ? '₹' : '';
  return `${prefix}${sym}${formatted}`;
}

export function formatQuantity(qty, unit) {
  if (qty === null || qty === undefined) return `0 ${unit || ''}`;
  const num = Number(qty);
  
  if (unit === 'g' && num >= 1000) {
    return `${(num / 1000).toLocaleString('en-IN', { maximumFractionDigits: 2 })} kg`;
  }
  if (unit === 'ml' && num >= 1000) {
    return `${(num / 1000).toLocaleString('en-IN', { maximumFractionDigits: 2 })} L`;
  }
  return `${num.toLocaleString('en-IN')} ${unit || ''}`;
}

export function formatDate(isoStr) {
  if (!isoStr) return '-';
  try {
    const d = new Date(isoStr);
    return d.toLocaleDateString('en-IN', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
    });
  } catch (e) {
    return isoStr;
  }
}

export function formatDateTime(isoStr) {
  if (!isoStr) return '-';
  try {
    const d = new Date(isoStr);
    return d.toLocaleString('en-IN', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch (e) {
    return isoStr;
  }
}

export function formatPercent(val) {
  if (val === null || val === undefined) return '0.0%';
  const num = Number(val);
  const prefix = num > 0 ? '+' : '';
  return `${prefix}${num.toFixed(1)}%`;
}

import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { SummaryStrip } from '../SummaryStrip';

describe('SummaryStrip Component', () => {
  const mockData = {
    ordersTodayCount: 4,
    ordersTodayValuePaise: 4800000, // Rs 48,000
    awaitingApprovalCount: 2,
    awaitingApprovalValuePaise: 2400000, // Rs 24,000
    stockShortagesCount: 1,
    varianceAlertsCount: 2,
    outstandingDuesPaise: 12450000, // Rs 1,24,500
    costPerPacketRupees: 31.14,
    standardCostRupees: 30.50,
  };

  it('renders all 6 required summary metric labels and formatted tabular figures', () => {
    render(<SummaryStrip data={mockData} />);

    // Verify all 6 metric blocks are present
    expect(screen.getByText('Orders today')).toBeInTheDocument();
    expect(screen.getByText('Awaiting approval')).toBeInTheDocument();
    expect(screen.getByText('Stock shortages')).toBeInTheDocument();
    expect(screen.getByText('Variance alerts')).toBeInTheDocument();
    expect(screen.getByText('Outstanding dues')).toBeInTheDocument();
    expect(screen.getByText('Cost per packet')).toBeInTheDocument();

    // Verify context lines with Indian Rupee formatting
    expect(screen.getByText(/4 orders, ₹48,000 value/)).toBeInTheDocument();
    expect(screen.getByText(/2 orders, ₹24,000/)).toBeInTheDocument();
    expect(screen.getByText(/1 items below reorder/)).toBeInTheDocument();
    expect(screen.getByText(/2 runs over tolerance/)).toBeInTheDocument();
    expect(screen.getByText('₹1,24,500')).toBeInTheDocument();
    expect(screen.getByText('₹31.14')).toBeInTheDocument();
    expect(screen.getByText(/Std: ₹30.50/)).toBeInTheDocument();
  });

  it('renders skeleton loading state matching final layout when isLoading is true', () => {
    render(<SummaryStrip isLoading={true} />);
    expect(screen.getByTestId('summary-strip-skeleton')).toBeInTheDocument();
  });

  it('renders inline error with a working retry action when isError is true', () => {
    const retryFn = vi.fn();
    render(<SummaryStrip isError={true} onRetry={retryFn} />);

    expect(screen.getByText('Could not load summary metrics.')).toBeInTheDocument();
    const retryBtn = screen.getByRole('button', { name: /retry/i });
    expect(retryBtn).toBeInTheDocument();

    retryBtn.click();
    expect(retryFn).toHaveBeenCalledTimes(1);
  });
});

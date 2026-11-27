import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import React from 'react';
import { StatusChip } from '../status-chip';

describe('StatusChip Component', () => {
  it('renders with label text and never with color alone', () => {
    render(<StatusChip status="ok" label="In stock" />);
    const chip = screen.getByTestId('status-chip');
    expect(chip).toBeInTheDocument();
    expect(chip).toHaveTextContent('In stock');
    expect(chip).toHaveAttribute('data-status', 'ok');
  });

  it('renders breach status for order shortages with explicit text label', () => {
    render(<StatusChip status="breach" label="Short by 24" />);
    const chip = screen.getByTestId('status-chip');
    expect(chip).toHaveTextContent('Short by 24');
    expect(chip).toHaveAttribute('data-status', 'breach');
    expect(chip.className).toContain('bg-status-breach-bg');
    expect(chip.className).toContain('text-status-breach-text');
  });

  it('renders warning status with warning color tokens', () => {
    render(<StatusChip status="warning" label="Low stock" />);
    const chip = screen.getByTestId('status-chip');
    expect(chip).toHaveTextContent('Low stock');
    expect(chip).toHaveAttribute('data-status', 'warning');
    expect(chip.className).toContain('bg-status-warning-bg');
    expect(chip.className).toContain('text-status-warning-text');
  });
});
